"""
贪婪矿场 v2 — hook 调引擎
==========================
使用引擎 API 编排回合，所有游戏逻辑在 hooks 内闭环。
"""

import logging
import re
from typing import Optional

from engine.hooks import GameHooks
from engine.schema import GameContext, PlayerState, CoTOutput, DMVerdict

logging.basicConfig(level=logging.INFO, format="[GREEDY] %(message)s", force=True)
logger = logging.getLogger("maga.greedy_mine")

# 行动编码
DEV, DEF, LOOT = "DEV", "DEF", "LOOT"
ACTION_RE = re.compile(r'\b(DEV|DEF|LOOT(?:-(p[1-6]))?)\b')

# 矩阵
DEV_NO_RAID, DEV_PER_RAIDER = +2, -4
DEF_NO_RAID, DEF_BLOCK = -1, 0
LOOT_VS_DEV, LOOT_VS_DEF, LOOT_VS_LOOT = +5, -1, -3


class GreedyMineHooks(GameHooks):

    def __init__(self):
        super().__init__()
        self.actions: dict[str, tuple[str, Optional[str]]] = {}

    # ============================================================
    # 新路径：hook 编排回合
    # ============================================================

    async def run_round(self, ctx: GameContext, round_num: int) -> bool:
        """每轮由 hook 完全控制：发言 → 行动 → DM → 结算"""
        a = self.arena
        alive = [p for p in ctx.round.players.values() if p.is_alive]
        if len(alive) <= 1:
            return False

        # ── 阶段 1：全员发言 ──
        self._send_private_info(ctx)
        await a.collect_speeches(ctx, alive)
        speech_cots = a.save_speech_cots(ctx)

        # ── 阶段 2：全员行动 ──
        self.actions.clear()
        await a.collect_actions(ctx, alive)

        # 用 speech_cots 恢复 last_cot
        for pid, p in ctx.round.players.items():
            if p.is_alive and p.last_cot and pid in speech_cots:
                old = speech_cots[pid]
                p.last_cot = p.last_cot.model_copy(update={
                    "situation_assessment": old.get("situation_assessment", ""),
                    "internal_strategy": old.get("internal_strategy", ""),
                    "public_speech": old.get("public_speech", ""),
                })

        # ── 阶段 3：DM ──
        logger.info(f"=== Round {round_num} 行动汇总 ===")
        for pid, (act, target) in self.actions.items():
            p = ctx.round.players.get(pid)
            if p and p.is_alive:
                tname = ctx.round.players[target].name if target else ""
                logger.info(f"  {p.name}: {act}" + (f" → {tname}" if target else ""))
        dm_actions = [(p, p.last_cot) for p in ctx.round.players.values() if p.last_cot]
        await a.dm_judge(ctx, dm_actions)

        # ── 阶段 4：结算 ──
        deltas = self._apply_matrix(ctx)
        a.apply_delta(ctx, deltas)
        logger.info(f"  结算: {', '.join(f'{k}={v:+d}' for k,v in deltas.items())}")
        for pid, p in ctx.round.players.items():
            if p.is_alive and p.resources.get("gold", 0) <= 0:
                a.eliminate(ctx, pid)
                logger.info(f"  淘汰: {p.name}")

        # 末位淘汰（第 4 轮起）
        if round_num >= 4:
            alive = [(pid, p) for pid, p in ctx.round.players.items() if p.is_alive]
            if len(alive) > 1:
                min_gold = min(p.resources.get("gold", 0) for _, p in alive)
                for pid, p in alive:
                    if p.resources.get("gold", 0) == min_gold:
                        a.eliminate(ctx, pid)
                        logger.info(f"  末位淘汰 ({round_num}轮): {p.name}")

        # ── 阶段 5：推送状态 ──
        for pid, p in ctx.round.players.items():
            if p.is_alive and pid in self.actions and p.last_cot:
                p.last_cot = p.last_cot.model_copy(update={
                    "secret_action": self._fmt_action(pid, ctx),
                })
        await a.emit_state(ctx)
        if round_num >= ctx.game_config.total_rounds:
            return False
        return True

    # ============================================================
    # 旧钩子（兼容）
    # ============================================================

    async def after_player_act(self, ctx, player, action):
        self.actions[player.id] = self._parse_action(action.secret_action, player, ctx)
        return ctx

    async def check_win_condition(self, ctx):
        alive = [p for p in ctx.round.players.values() if p.is_alive]
        if len(alive) == 1:
            return alive[0].id
        if ctx.round.round_number >= ctx.game_config.total_rounds:
            golds = [p.resources.get("gold", 0) for p in alive]
            winners = [p.id for p in alive if p.resources.get("gold", 0) == max(golds)]
            return ",".join(winners) if winners else None
        return None

    # ============================================================
    # 内部
    # ============================================================

    def _send_private_info(self, ctx):
        for pid, p in ctx.round.players.items():
            if not p.is_alive:
                continue
            others = [f"  - {o.name} ({oid}): {o.resources.get('gold', 0)} 金币"
                      for oid, o in ctx.round.players.items() if oid != pid and o.is_alive]
            info = f"## 存活玩家（你的 ID: {pid}）\n" + "\n".join(others)
            info += "\n\n## 行动编码：DEV / DEF / LOOT-p1~p6"
            self.memory.add_private(pid, info)

    def _fmt_action(self, pid, ctx):
        act, target = self.actions.get(pid, (None, None))
        if act == DEV:
            return "发育（挖矿 +2）"
        elif act == DEF:
            return "防御（架盾 -1）"
        elif act == LOOT and target:
            tname = ctx.round.players[target].name if target in ctx.round.players else target
            return f"掠夺 → {tname}"
        return ""

    def _parse_action(self, text, player, ctx):
        t = text.strip()
        matches = ACTION_RE.findall(t)
        if matches:
            last = matches[-1]
            code, target_id = last[0], last[1] if len(last) > 1 else None
            if code.startswith("LOOT") and target_id and target_id != player.id:
                return (LOOT, target_id)
            return (DEF if code == "DEF" else DEV, None)
        # 中文回退
        t_clean = t.replace(" ", "")
        for pid, p in ctx.round.players.items():
            if pid != player.id and p.is_alive:
                if f"掠夺{pid}" in t_clean:
                    return (LOOT, pid)
        if "防御" in t_clean:
            return (DEF, None)
        return (DEV, None)

    def _apply_matrix(self, ctx):
        deltas = {pid: 0 for pid in ctx.round.players}
        raiders, counts = [], {}
        for pid, (act, target) in self.actions.items():
            if act == LOOT and target:
                raiders.append((pid, target))
                counts[target] = counts.get(target, 0) + 1
        alive_count = sum(1 for p in ctx.round.players.values() if p.is_alive)
        mass_raided = {t for t, c in counts.items() if c >= alive_count // 2}

        for pid, (act, target) in self.actions.items():
            p = ctx.round.players.get(pid)
            if not p or not p.is_alive:
                continue
            raiders_on_me = [r for r, t in raiders if t == pid]

            if act == DEV:
                deltas[pid] += DEV_PER_RAIDER * len(raiders_on_me) if raiders_on_me else DEV_NO_RAID
            elif act == DEF:
                if pid in mass_raided:
                    deltas[pid] += -3
                    for rid in raiders_on_me:
                        deltas[rid] += 3
                elif raiders_on_me:
                    deltas[pid] += DEF_BLOCK
                else:
                    deltas[pid] += DEF_NO_RAID
            elif act == LOOT and target:
                target_act = self.actions.get(target, (DEV, None))[0]
                if target_act == DEV:
                    deltas[pid] += LOOT_VS_DEV
                elif target_act == DEF and target not in mass_raided:
                    deltas[pid] += LOOT_VS_DEF
                elif target_act == LOOT:
                    deltas[pid] += LOOT_VS_LOOT
                for rid in raiders_on_me:
                    if rid != target:
                        deltas[pid] += LOOT_VS_LOOT

        return deltas
