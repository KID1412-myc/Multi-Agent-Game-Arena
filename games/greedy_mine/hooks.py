"""
贪婪矿场：零和掠夺 — 核心游戏逻辑
=====================================
纯机械结算，不依赖 LLM 计算。DM 只负责叙事。
"""

import logging
from typing import Optional

from engine.hooks import GameHooks
from engine.schema import GameContext, PlayerState, CoTOutput, DMVerdict, ResourceDelta

logging.basicConfig(level=logging.INFO, format="[GREEDY] %(message)s", force=True)
logger = logging.getLogger("maga.greedy_mine")

# 行动类型编码（LLM 返回这些，解析用这些）
DEV = "DEV"
DEF = "DEF"
LOOT = "LOOT"
ACTION_CODES = {"DEV": "发育", "DEF": "防御", "LOOT": "掠夺"}
# 解析用正则：DEV / DEF / LOOT-p1 到 LOOT-p6
import re
ACTION_RE = re.compile(r'\b(DEV|DEF|LOOT(?:-(p[1-6]))?)\b')

# 结算矩阵常量
DEV_NO_RAID = +2
DEV_PER_RAIDER = -4
DEF_NO_RAID = -1
DEF_BLOCK = 0
LOOT_VS_DEV = +5
LOOT_VS_DEF = -1
LOOT_VS_LOOT = -3


class GreedyMineHooks(GameHooks):
    """贪婪矿场完整游戏逻辑"""

    def __init__(self):
        super().__init__()
        self.actions: dict[str, tuple[str, Optional[str]]] = {}
        self.skip_parse: bool = False  # 发言阶段不解析行动
        # player_id → (action_type, target_id or None)

    # ================================================================
    # 游戏级
    # ================================================================

    async def on_game_start(self, ctx: GameContext) -> GameContext:
        self.actions = {}
        # 确保所有人初始 10 金币
        for pid, p in ctx.round.players.items():
            p.resources["gold"] = 10
        return ctx

    # ================================================================
    # 轮次级
    # ================================================================

    async def on_round_start(self, ctx: GameContext, round_num: int) -> GameContext:
        self.actions.clear()
        # 发送局势简报
        if self.memory:
            for pid, p in ctx.round.players.items():
                if not p.is_alive:
                    continue
                others = []
                for oid, o in ctx.round.players.items():
                    if oid != pid and o.is_alive:
                        others.append(f"  - {o.name} ({oid}): {o.resources.get('gold', 0)} 金币")
                info = f"## 当前存活玩家（你的 ID: {pid}）\n" + "\n".join(others)
                info += "\n\n## 你的行动编码：DEV / DEF / LOOT-p1~p6"
                self.memory.add_private(pid, info)
        return ctx

    # ================================================================
    # 玩家行动后 —— 解析行动
    # ================================================================

    async def after_player_act(
        self, ctx: GameContext, player: PlayerState, action: CoTOutput
    ) -> GameContext:
        if not self.skip_parse:
            parsed = self._parse_action(action.secret_action, player, ctx)
            self.actions[player.id] = parsed
        return ctx

    # ================================================================
    # DM 级 —— 注入结算信息
    # ================================================================

    async def before_dm_judge(self, ctx: GameContext) -> GameContext:
        if self.memory is None:
            return ctx

        # 日志输出本轮所有行动
        logger.info(f"=== Round {ctx.round.round_number} 行动汇总 ===")
        for pid, (act, target) in self.actions.items():
            p = ctx.round.players.get(pid)
            if p and p.is_alive:
                tname = ctx.round.players[target].name if target else ""
                logger.info(f"  {p.name}: {act}" + (f" → {tname}" if target else ""))

        lines = ["## 本轮玩家行动"]
        for pid, (act, target) in self.actions.items():
            p = ctx.round.players.get(pid)
            if p and p.is_alive:
                tname = ctx.round.players[target].name if target else ""
                lines.append(f"- {p.name}: {act}" + (f" → {tname}" if target else ""))

        # 行动摘要（DM 据此叙事）
        summary = "\n## 本轮行动（如实叙述即可）\n"
        for pid, (act, target) in self.actions.items():
            p = ctx.round.players.get(pid)
            if p and p.is_alive:
                tname = ctx.round.players[target].name if target else ""
                summary += f"- {p.name}: {act}" + (f" → {tname}" if target else "") + "\n"

        self.memory.add_private("dm", "\n".join(lines) + summary)
        return ctx

    async def after_dm_judge(
        self, ctx: GameContext, verdict: DMVerdict
    ) -> GameContext:
        """应用结算矩阵，处理金币变动和淘汰。清空 DM 的 resource_delta 防止双重计算。"""
        # 修正 DM 可能搞错的 round_number
        verdict.round_number = ctx.round.round_number

        gold_deltas = self._apply_matrix(ctx)

        # 直接应用金币变动（清空 DM 的 resource_delta 防止 arena 二次应用）
        verdict.resource_delta.clear()
        for pid, delta in gold_deltas.items():
            p = ctx.round.players.get(pid)
            if p and p.is_alive and delta != 0:
                p.resources["gold"] = p.resources.get("gold", 0) + delta

        # 淘汰金币 ≤ 0 的玩家
        eliminated = []
        for pid, p in ctx.round.players.items():
            if p.is_alive and p.resources.get("gold", 0) <= 0:
                p.is_alive = False
                eliminated.append(p.name)

        # 末位淘汰（第 4 轮起）
        rn = ctx.round.round_number
        if rn >= 4:
            alive = [(pid, p) for pid, p in ctx.round.players.items() if p.is_alive]
            if len(alive) > 1:
                min_gold = min(p.resources.get("gold", 0) for _, p in alive)
                bottom = [(pid, p) for pid, p in alive if p.resources.get("gold", 0) == min_gold]
                for pid, p in bottom:
                    p.is_alive = False
                    eliminated.append(p.name)
                if bottom:
                    logger.info(f"  末位淘汰 ({rn}轮): {[n for _,n in bottom]}")

        logger.info(f"  结算完成: {', '.join(f'{pid}={gold_deltas[pid]:+d}' for pid in gold_deltas)}" )
        if eliminated:
            logger.info(f"  淘汰: {eliminated}")

        if eliminated:
            self.memory.add_private(
                "dm", f"⚠️ 本轮淘汰: {', '.join(eliminated)}"
            )

        return ctx

    # ================================================================
    # 胜负判定
    # ================================================================

    async def check_win_condition(self, ctx: GameContext) -> Optional[str]:
        alive = [p for p in ctx.round.players.values() if p.is_alive]
        if len(alive) == 1:
            return alive[0].id

        # 5 轮结束后判定
        if ctx.round.round_number >= ctx.game_config.total_rounds:
            max_gold = max(p.resources.get("gold", 0) for p in alive)
            winners = [p.id for p in alive if p.resources.get("gold", 0) == max_gold]
            if winners:
                # 返回所有并列者（用逗号拼，引擎只用第一个做 winner_id，但前端会用全部）
                self._winners = winners
                return ",".join(winners)
        return None

    # ================================================================
    # 内部方法
    # ================================================================

    def _parse_action(
        self, text: str, player: PlayerState, ctx: GameContext
    ) -> tuple[str, Optional[str]]:
        """解析行动：先匹配编码 DEV/DEF/LOOT-pX，失败则回退中文关键词。仍失败默认 DEV。"""
        t = text.strip()

        # 第一优先：行动编码
        matches = ACTION_RE.findall(t)
        if matches:
            last = matches[-1]
            code = last[0]
            target_id = last[1] if len(last) > 1 else None
            if code.startswith("LOOT"):
                if target_id and target_id != player.id and ctx.round.players.get(target_id, None):
                    logger.info(f"  {player.name} → LOOT {ctx.round.players[target_id].name}")
                    return (LOOT, target_id)
                return (DEV, None)
            return (DEF if code == "DEF" else DEV, None)

        # 回退：中文关键词
        t_clean = t.replace(" ", "")
        for pid, p in ctx.round.players.items():
            if pid != player.id and p.is_alive:
                if f"掠夺{pid}" in t_clean or f"抢夺{pid}" in t_clean or f"抢劫{pid}" in t_clean:
                    logger.info(f"  {player.name} → LOOT {p.name} (中文回退)")
                    return (LOOT, pid)
        if "防御" in t_clean:
            return (DEF, None)
        if "发育" in t_clean or "挖矿" in t_clean:
            return (DEV, None)

        logger.warning(f"  {player.name} 未识别，默认 DEV，raw=[{t[:200]}]")
        return (DEV, None)

    def _apply_matrix(self, ctx: GameContext) -> dict[str, int]:
        """纯机械结算，返回每个玩家的金币变动"""
        deltas: dict[str, int] = {pid: 0 for pid in ctx.round.players}

        # 先收集掠夺者及其目标，标记被 3+ 人围殴的防御者
        raiders: list[tuple[str, str]] = []
        target_counts: dict[str, int] = {}
        for pid, (act, target) in self.actions.items():
            if act == LOOT and target:
                raiders.append((pid, target))
                target_counts[target] = target_counts.get(target, 0) + 1
        alive_count = sum(1 for p in ctx.round.players.values() if p.is_alive)
        mass_raided = {t for t, c in target_counts.items() if c >= alive_count // 2}

        # 对每个玩家结算
        for pid, (act, target) in self.actions.items():
            p = ctx.round.players.get(pid)
            if not p or not p.is_alive:
                continue

            raiders_on_me = [r for r, t in raiders if t == pid]

            if act == DEV:
                if raiders_on_me:
                    deltas[pid] += DEV_PER_RAIDER * len(raiders_on_me)
                else:
                    deltas[pid] += DEV_NO_RAID

            elif act == DEF:
                if pid in mass_raided:
                    # 三人以上围殴破盾：防守者 -3，攻击者各 +3
                    deltas[pid] += -3
                    for rid in raiders_on_me:
                        deltas[rid] += 3
                elif raiders_on_me:
                    deltas[pid] += DEF_BLOCK  # 0
                else:
                    deltas[pid] += DEF_NO_RAID

            elif act == LOOT:
                if target is None:
                    continue  # 无效掠夺
                target_act = self.actions.get(target, (DEV, None))[0]
                target_alive = ctx.round.players.get(target)
                if not target_alive or not target_alive.is_alive:
                    deltas[pid] += LOOT_VS_DEF  # 目标已死
                elif target_act == DEV:
                    deltas[pid] += LOOT_VS_DEV
                elif target_act == DEF:
                    if target not in mass_raided:
                        deltas[pid] += LOOT_VS_DEF  # 普通踢盾 -1
                    # 围殴破盾已在 DEF 段处理 +3，此处跳过
                elif target_act == LOOT:
                    deltas[pid] += LOOT_VS_LOOT

                # 被其他人掠夺（排除互相攻击的对手，避免双重扣分）
                for rid in raiders_on_me:
                    if rid != target:
                        deltas[pid] += LOOT_VS_LOOT

        return deltas
