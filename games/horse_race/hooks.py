"""
赛马博弈 — hook 调引擎
========================
6人选1-6号马，得票最少的马获胜。投它的人各+5分。平票均分。
"""

import logging, random, re
from typing import Optional

from engine.hooks import GameHooks
from engine.schema import GameContext, CoTOutput, CriticalEvent

logging.basicConfig(level=logging.INFO, format="[RACE] %(message)s", force=True)
logger = logging.getLogger("maga.race")


class HorseRaceHooks(GameHooks):

    def __init__(self):
        super().__init__()
        self.picks: dict[str, int] = {}  # pid → horse 1-6

    async def run_round(self, ctx, round_num: int) -> bool:
        a = self.arena
        alive = [p for p in ctx.round.players.values() if p.is_alive]
        if len(alive) <= 1:
            return False

        self._send_private_info(ctx)

        await a.collect_speeches(ctx, alive)
        speech_cots = a.save_speech_cots(ctx)

        self.picks.clear()
        for agent in a.players.values():
            agent.quick_action_prompt = "现在是投票阶段。只回复一个数字（1-6），例如：3"
        try:
            await a.collect_actions(ctx, alive, parallel=True)
        finally:
            for agent in a.players.values():
                agent.quick_action_prompt = None

        for p in alive:
            raw = p.last_cot.secret_action if p.last_cot else ""
            pick = self._parse_pick(raw)
            self.picks[p.id] = pick

        for pid, p in ctx.round.players.items():
            if p.is_alive and pid in speech_cots and p.last_cot:
                old = speech_cots[pid]
                p.last_cot = p.last_cot.model_copy(update={
                    "situation_assessment": old.get("situation_assessment", ""),
                    "internal_strategy": old.get("internal_strategy", ""),
                    "public_speech": old.get("public_speech", ""),
                })

        result_text = self._resolve(ctx, alive, round_num)

        for pid, p in ctx.round.players.items():
            if p.is_alive and p.last_cot:
                pick = self.picks.get(pid, 0)
                p.last_cot = p.last_cot.model_copy(update={
                    "secret_action": f"投 {pick} 号马",
                })

        self.memory.add_critical_event(CriticalEvent(
            round_number=round_num,
            event=f"## 第{round_num}轮赛马\n{result_text}",
            related_players=[],
        ))
        actions = [(p, p.last_cot) for p in ctx.round.players.values() if p.last_cot]
        await a.dm_judge(ctx, actions)
        await a.emit_state(ctx)

        if round_num >= ctx.game_config.total_rounds:
            return False
        return True

    async def on_game_start(self, ctx):
        self.picks = {}
        return ctx

    async def check_win_condition(self, ctx):
        if ctx.round.round_number >= ctx.game_config.total_rounds:
            alive = [p for p in ctx.round.players.values() if p.is_alive]
            if not alive:
                return None
            max_pts = max(p.resources.get("points", 0) for p in alive)
            winners = [p.id for p in alive if p.resources.get("points", 0) == max_pts]
            return ",".join(winners) if winners else None
        return None

    def _send_private_info(self, ctx):
        for pid, p in ctx.round.players.items():
            if not p.is_alive:
                continue
            others = [f"  - {o.name} ({oid}): {o.resources.get('points', 0)} 分"
                      for oid, o in ctx.round.players.items() if oid != pid and o.is_alive]
            info = f"## 存活玩家（你的 ID: {pid}，{p.resources.get('points', 0)} 分）\n" + "\n".join(others)
            info += "\n\n## 赛马投票"
            info += "\n选一匹马（1-6）。得票最少的马获胜——投它的人各+5分。平票则均分。"
            info += "\n\n## 投票阶段\n在 secret_action 中只写一个整数（1-6），例如：3"
            self.memory.add_private(pid, info)

    def _parse_pick(self, text: str) -> int:
        t = text.strip()
        if not t:
            return random.randint(1, 6)
        nums = re.findall(r'\d+', t)
        if nums:
            n = int(nums[0])
            return max(1, min(6, n))
        return random.randint(1, 6)

    def _resolve(self, ctx, alive, round_num) -> str:
        if not self.picks:
            return "无人投票"

        votes = {i: 0 for i in range(1, 7)}
        for p in alive:
            pick = self.picks.get(p.id, 0)
            if 1 <= pick <= 6:
                votes[pick] += 1
            logger.info(f"  {p.name}: 投 {pick} 号马")

        min_votes = min(votes.values())
        winners = [h for h, v in votes.items() if v == min_votes]
        share = 5 // len(winners) if winners else 0

        if len(winners) == 1:
            result = f"{winners[0]} 号马得票最少（{min_votes}票），投它的人各+5分"
        else:
            result = f"{', '.join(str(w) for w in winners)} 号马并列最少（{min_votes}票），均分5→各+{share}分"

        for p in alive:
            pick = self.picks.get(p.id, 0)
            if pick in winners:
                p.resources["points"] = p.resources.get("points", 0) + share

        logger.info(f"  → {result}")
        ctx.round.public_log.append(result)
        return result
