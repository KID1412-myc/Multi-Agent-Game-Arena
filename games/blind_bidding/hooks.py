"""
盲投暗标 — hook 调引擎
========================
6轮。每轮秘密出价0-10，最高且唯一者赢得奖池（10-出价分）。
多人同价最高 → 全部作废。
"""

import logging, re
from typing import Optional

from engine.hooks import GameHooks
from engine.schema import GameContext, CoTOutput, CriticalEvent

logging.basicConfig(level=logging.INFO, format="[BID] %(message)s", force=True)
logger = logging.getLogger("maga.bid")


class BlindBiddingHooks(GameHooks):

    def __init__(self):
        super().__init__()
        self.bids: dict[str, int] = {}

    # ============================================================
    # 新路径
    # ============================================================

    async def run_round(self, ctx, round_num: int) -> bool:
        a = self.arena
        alive = [p for p in ctx.round.players.values() if p.is_alive]
        if len(alive) <= 1:
            return False

        # ── 私密信息 ──
        self._send_private_info(ctx)

        # ── 阶段 1：发言 ──
        await a.collect_speeches(ctx, alive)
        speech_cots = a.save_speech_cots(ctx)

        # ── 阶段 2：出价 ──
        self.bids.clear()
        for agent in a.players.values():
            agent.quick_action_prompt = "现在是出价阶段。只回复一个整数，例如：5"
        try:
            await a.collect_actions(ctx, alive, parallel=True)
        finally:
            for agent in a.players.values():
                agent.quick_action_prompt = None

        # 解析出价（从 _act_quick 返回的 secret_action 中提取数字）
        for p in alive:
            raw = p.last_cot.secret_action if p.last_cot else ""
            bid = self._parse_bid(raw)
            self.bids[p.id] = bid

        # CoT 合并：恢复发言分析字段
        for pid, p in ctx.round.players.items():
            if p.is_alive and pid in speech_cots and p.last_cot:
                old = speech_cots[pid]
                p.last_cot = p.last_cot.model_copy(update={
                    "situation_assessment": old.get("situation_assessment", ""),
                    "internal_strategy": old.get("internal_strategy", ""),
                    "public_speech": old.get("public_speech", ""),
                })

        # ── 结算 ──
        result_text = self._resolve_bids(ctx, alive, round_num)

        # 格式化 secret_action 为可读显示
        for pid, p in ctx.round.players.items():
            if p.is_alive and p.last_cot:
                bid = self.bids.get(pid, 0)
                p.last_cot = p.last_cot.model_copy(update={
                    "secret_action": f"出价 {bid}",
                })

        # ── DM + 推送 ──
        self.memory.add_critical_event(CriticalEvent(
            round_number=round_num,
            event=f"## 第{round_num}轮结果\n{result_text}",
            related_players=[],
        ))
        actions = [(p, p.last_cot) for p in ctx.round.players.values() if p.last_cot]
        await a.dm_judge(ctx, actions)
        await a.emit_state(ctx)

        if round_num >= ctx.game_config.total_rounds:
            return False
        return True

    # ============================================================
    # 旧钩子兼容
    # ============================================================

    async def on_game_start(self, ctx):
        self.bids = {}
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

    # ============================================================
    # 内部
    # ============================================================

    def _send_private_info(self, ctx):
        for pid, p in ctx.round.players.items():
            if not p.is_alive:
                continue
            others = [f"  - {o.name} ({oid}): {o.resources.get('points', 0)} 分"
                      for oid, o in ctx.round.players.items() if oid != pid and o.is_alive]
            info = f"## 存活玩家（你的 ID: {pid}，{p.resources.get('points', 0)} 分）\n" + "\n".join(others)
            info += "\n\n## 本轮规则"
            info += "\n唯一最高：扣出价+10。平票最高：损失平摊。不最高：只亏出价的一半。"
            info += "\n（例：出7唯一赢→净赚3，2人平票出7→各亏3，出6不中→只亏3）"
            info += "\n\n## 出价阶段\n在 secret_action 中只写一个整数，例如：5"
            self.memory.add_private(pid, info)

    def _parse_bid(self, text: str) -> int:
        """从任意文本中提取出价数字。空→0，超10→10，中文数字→int。"""
        t = text.strip().replace(" ", "").replace(" ", "")
        if not t:
            return 0
        # 找阿拉伯数字
        nums = re.findall(r'\d+', t)
        if nums:
            n = int(nums[0])
            return max(0, min(10, n))
        # 中文数字
        cn = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        for k, v in cn.items():
            if k in t:
                return v
        return 0

    def _resolve_bids(self, ctx, alive, round_num) -> str:
        """结算出价：所有人扣出价，唯一最高者再+10。返回结果描述。"""
        if not self.bids:
            return "无人出价"

        logger.info(f"=== Round {round_num} 出价汇总 ===")
        for p in alive:
            bid = self.bids.get(p.id, 0)
            logger.info(f"  {p.name}: 出{bid}  raw=[{p.last_cot.secret_action if p.last_cot else ''}]"[:80])

        # 找最高出价 + 统计人数
        max_bid = max(self.bids.values())
        top_bidders = [pid for pid, bid in self.bids.items() if bid == max_bid]

        if len(top_bidders) > 1:
            # 平票：损失平摊（例：2人出7 → 各亏7//2=3）
            loss_each = max_bid // len(top_bidders)
            for pid in top_bidders:
                p = ctx.round.players[pid]
                p.resources["points"] = p.resources.get("points", 0) - loss_each
            # 其他人：亏一半
            for p in alive:
                if p.id not in top_bidders:
                    half = self.bids.get(p.id, 0) // 2
                    p.resources["points"] = p.resources.get("points", 0) - half
            names = [ctx.round.players[pid].name for pid in top_bidders]
            result = f"最高出价 {max_bid} 有 {len(top_bidders)} 人平票（{', '.join(names)}），各亏 {loss_each}。其他人亏半价。"
            logger.info(f"  → {result}")
            ctx.round.public_log.append(result)
            return result

        # 唯一最高：赢家扣出价+10，其他人亏一半
        winner_id = top_bidders[0]
        winner = ctx.round.players[winner_id]
        winner.resources["points"] = winner.resources.get("points", 0) - max_bid + 10
        for p in alive:
            if p.id != winner_id:
                half = self.bids.get(p.id, 0) // 2
                p.resources["points"] = p.resources.get("points", 0) - half
        net = 10 - max_bid
        result = f"{winner.name} 出 {max_bid} 独占最高，净得 {net} 分（-{max_bid}+10）。其他人亏半价。"
        logger.info(f"  → {result}")
        ctx.round.public_log.append(result)
        return result
