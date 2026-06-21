"""
炸弹项圈·积分欺诈赛 — 核心游戏逻辑
====================================
使用引擎 hooks 注入全部游戏机制：颜色分配、猜色判定、积分管理。
DM（LLM）只负责叙事——所有数字计算由引擎执行。
"""

import random
from typing import Optional

from engine.hooks import GameHooks
from engine.schema import (
    CoTOutput, DMVerdict, GameContext, PlayerState, ResourceDelta
)

COLORS = ["红", "蓝", "绿"]
FRAUDSTER_ID = "p5"  # 周默是欺诈师
COLOR_REROLL_CHANCE = 0.4  # 每轮 40% 概率刷新颜色
SURVIVE_POINTS = 2  # 每活过一轮 +2 分


class BombCollarHooks(GameHooks):
    """炸弹项圈完整游戏逻辑"""

    def __init__(self):
        super().__init__()
        # 游戏状态（跨轮持久）
        self.colors: dict[str, str] = {}           # player_id → 当前颜色
        self.pairings: list[tuple[str, str]] = []   # 本轮配对 [(p1, p2), (p3, p4), (p5, p6)]
        self.peace_streak: int = 0                   # 连续无人死亡轮数
        self.fraudster_known: bool = False           # 审判是否已解锁
        self.pistol_holder: Optional[str] = None
        self.pistol_target: Optional[str] = None
        self.current_game_number: int = 1           # 当前第几局
        self.game_scores: dict[str, int] = {}        # 跨局累计积分

    # ================================================================
    # 游戏级
    # ================================================================

    async def on_game_start(self, ctx: GameContext) -> GameContext:
        self.game_scores = {p.id: p.initial_resources.get("points", 5)
                            for p in ctx.game_config.players}
        self.current_game_number = 1
        self.peace_streak = 0
        self.fraudster_known = False
        self.pistol_holder = None
        self._assign_colors(ctx)
        await self._send_color_info(ctx)
        return ctx

    # ================================================================
    # 轮次级
    # ================================================================

    async def on_round_start(self, ctx: GameContext, round_num: int) -> GameContext:
        # 40% 概率刷新颜色
        if round_num > 1 and random.random() < COLOR_REROLL_CHANCE:
            self.colors = {}
        self._assign_colors(ctx)

        # 随机配对
        alive = [pid for pid, p in ctx.round.players.items() if p.is_alive]
        random.shuffle(alive)
        self.pairings = []
        for i in range(0, len(alive) - 1, 2):
            self.pairings.append((alive[i], alive[i + 1]))
        if len(alive) % 2 == 1:
            last = alive[-1]
            self.pairings[-1] = (self.pairings[-1][0], last) if self.pairings else (last, last)

        # 向每个玩家私密发送颜色信息
        await self._send_color_info(ctx)
        return ctx

    async def on_round_end(self, ctx: GameContext, round_num: int) -> GameContext:
        # 每活过一轮 +2 分
        for pid, p in ctx.round.players.items():
            if p.is_alive:
                p.resources["points"] = p.resources.get("points", 0) + SURVIVE_POINTS
        return ctx

    # ================================================================
    # DM 级 — 注入答案
    # ================================================================

    async def before_dm_judge(self, ctx: GameContext) -> GameContext:
        """向 DM 注入颜色答案和配对信息"""
        if self.memory is None:
            return ctx

        # 构建颜色答案表（DM 用来对比猜色）
        answer_lines = ["## 颜色答案（你作为 DM 的参考，勿告知玩家）"]
        for pid, p in ctx.round.players.items():
            if p.is_alive:
                color = self.colors.get(pid, "?")
                answer_lines.append(f"- {p.name} ({pid}): {color}")
                if pid == FRAUDSTER_ID:
                    answer_lines.append(f"  ⚠️ 此人是欺诈师，猜错不爆炸")

        # 配对信息
        pair_lines = ["## 本轮配对角"]
        for a, b in self.pairings:
            a_name = ctx.round.players[a].name if a in ctx.round.players else "?"
            b_name = ctx.round.players[b].name if b in ctx.round.players else "?"
            pair_lines.append(f"- {a_name} ↔ {b_name}")

        # 判断 DM 是否应告知玩家审判机制
        if self.fraudster_known:
            pair_lines.append("\n⚠️ 审判机制已解锁。玩家可以发起投票审判。")

        dm_info = "\n".join(answer_lines) + "\n\n" + "\n".join(pair_lines)
        self.memory.add_private("dm", dm_info)
        return ctx

    async def after_dm_judge(self, ctx: GameContext, verdict: DMVerdict) -> GameContext:
        """处理猜色结果：判定谁爆炸、谁存活"""
        # 从 DM 判决中解析淘汰信息
        exploded = self._parse_explosions(ctx, verdict)

        deaths_this_round = 0
        for pid in exploded:
            if pid == FRAUDSTER_ID:
                continue  # 欺诈师不爆炸
            if pid in ctx.round.players:
                ctx.round.players[pid].is_alive = False
                deaths_this_round += 1

        # 更新和平 streak
        if deaths_this_round == 0:
            self.peace_streak += 1
        else:
            self.peace_streak = 0

        # 检测公开发言中是否有人质疑（触发审判解锁）
        if not self.fraudster_known:
            for pid, p in ctx.round.players.items():
                if not p.is_alive:
                    continue
                speech = p.last_public_speech.lower()
                if any(kw in speech for kw in ["不对劲", "有内鬼", "有诈", "有人在骗", "有问题",
                                                  "卧底", "内奸", "谁是假的", "身份可疑"]):
                    self.fraudster_known = True
                    self.memory.add_private(
                        pid,
                        "⚡ DM 通知：审判机制已解锁。你可在阶段二花 2 分发起审判，指认一名玩家。"
                    )
                    break

        return ctx

    # ================================================================
    # 胜负判定
    # ================================================================

    async def check_win_condition(self, ctx: GameContext) -> Optional[str]:
        """硬规则判定"""
        alive_players = [p for p in ctx.round.players.values() if p.is_alive]
        alive_civilians = [p for p in alive_players if p.id != FRAUDSTER_ID]
        fraudster = ctx.round.players.get(FRAUDSTER_ID)

        # 条件1：只剩 1 人
        if len(alive_players) == 1:
            return alive_players[0].id

        # 条件2：连续 4 轮无人死亡 → 本局结束，无独胜者
        if self.peace_streak >= 4:
            self.peace_streak = 0
            return None  # 返回 None 但引擎会继续——需要在 after_dm_judge 里强停

        # 条件3：欺诈师被枪杀

        return None

    # ================================================================
    # 内部方法
    # ================================================================

    def _assign_colors(self, ctx: GameContext) -> None:
        """给所有存活玩家分配颜色"""
        for pid, p in ctx.round.players.items():
            if p.is_alive and pid not in self.colors:
                self.colors[pid] = random.choice(COLORS)

    async def _send_color_info(self, ctx: GameContext) -> None:
        """向每个玩家私密发送其他玩家的颜色信息"""
        if self.memory is None:
            return

        for pid, player in ctx.round.players.items():
            if not player.is_alive:
                continue

            # 构建其他玩家颜色列表
            other_lines = []
            for other_pid, other in ctx.round.players.items():
                if other_pid == pid or not other.is_alive:
                    continue
                color = self.colors.get(other_pid, "?")
                other_lines.append(f"  - {other.name}: {color}")

            info = "## 你看到的项圈颜色\n"
            info += "你只能看到其他存活玩家的颜色，看不到自己的：\n"
            info += "\n".join(other_lines)

            # 配对信息
            my_pair = "无"
            for a, b in self.pairings:
                if pid == a:
                    my_pair = ctx.round.players[b].name if b in ctx.round.players else "?"
                    break
                elif pid == b:
                    my_pair = ctx.round.players[a].name if a in ctx.round.players else "?"
                    break
            info += f"\n\n## 你的配对角: {my_pair}"
            info += "\n你可以在秘密行动中告知对方其颜色。（可说真话也可说谎）"

            # 欺诈师额外信息
            if pid == FRAUDSTER_ID:
                info += f"\n\n## 🔐 你的颜色: {self.colors.get(pid, '?')}"
                info += "\n你是欺诈师。你的项圈不会因猜错而爆炸。"

            # 审判状态
            if self.fraudster_known and pid != FRAUDSTER_ID:
                info += "\n\n⚡ DM 通知：有人已经察觉异常。审判机制可用。"

            self.memory.add_private(pid, info)

    def _parse_explosions(self, ctx: GameContext, verdict: DMVerdict) -> list[str]:
        """从 DM 判决中解析谁爆炸了"""
        exploded: list[str] = []
        summary = verdict.round_summary.lower()

        for pid, p in ctx.round.players.items():
            if not p.is_alive:
                continue
            name_lower = p.name.lower()
            # DM 在总结中提到某个玩家爆炸/猜错
            if any(kw in summary for kw in [
                f"{name_lower} 爆炸", f"{name_lower} 猜错", f"{name_lower} 项圈",
                f"{name_lower} 淘汰", f"{name_lower} 错误"
            ]):
                exploded.append(pid)
            # 也检查具体关键词
            if f"{p.name} 爆炸" in verdict.round_summary:
                exploded.append(pid)

        return list(set(exploded))
