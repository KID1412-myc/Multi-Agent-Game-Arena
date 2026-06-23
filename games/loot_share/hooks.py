"""
分赃 — hook 调引擎
===================
6人6轮。公开身份+秘密目标。每轮随机赃款，各自出价。
求和≤赃款则按出价分配，>则谈判破裂全员0分。
6轮后达成秘密目标者胜。
"""

import logging, random, re
from typing import Optional

from engine.hooks import GameHooks
from engine.schema import GameContext, CoTOutput, CriticalEvent

logging.basicConfig(level=logging.INFO, format="[LOOT] %(message)s", force=True)
logger = logging.getLogger("maga.loot")

IDENTITIES = ["老大", "会计", "打手", "骗子", "小偷", "线人"]

GOALS = [
    ("称霸", "总分最高（必须独赢，不能并列第一）"),
    ("垫底", "总分最低 + 总分≥6"),
    ("中游", "总分排名居中的一或两名（动态，随淘汰调整）"),
    ("毁灭者", "≥3回合谈判破裂 + 总分排名上半区"),
    ("和平奖", "≥3回合谈判成功 + 不能是倒数第二名"),
    ("盯上", "总分 > {target} 的总分"),
]


class LootShareHooks(GameHooks):

    def __init__(self):
        super().__init__()
        self.identities: dict[str, str] = {}     # pid → 公开身份
        self.goals: dict[str, tuple] = {}         # pid → (目标名, 条件描述)
        self.bids: dict[str, int] = {}            # pid → 本轮出价
        self.bankrupt_count: int = 0              # 谈判破裂次数
        self.last_bankrupt_top: str | None = None # 上轮破裂时出价最高者
        self._pending_elimination: str | None = None  # 定向淘汰
        self._pending_random: bool = False            # 随机淘汰
        self.loot: int = 0                        # 本轮赃款
        self.stalk_targets: dict[str, str] = {}   # "盯上"目标: pid → target_pid
        self.round_bids: dict[int, dict[str, int]] = {}  # round_num → {pid: bid}

    # ============================================================
    # 新路径
    # ============================================================

    async def run_round(self, ctx, round_num: int) -> bool:
        a = self.arena
        alive = [p for p in ctx.round.players.values() if p.is_alive]
        if len(alive) <= 1:
            return False

        # ── 随机赃款 + 私密信息 ──
        self.loot = random.randint(5, 15)
        logger.info(f"第{round_num}轮赃款: {self.loot}")
        self._send_private_info(ctx)
        ctx.round.public_log.append(f"💰 第{round_num}轮赃款: {self.loot} 分")
        await a.emit_state(ctx)  # 立即推送，开局就显示赃款和身份

        # ── 阶段 1：发言 ──
        await a.collect_speeches(ctx, alive)
        speech_cots = a.save_speech_cots(ctx)

        # ── 阶段 2：出价 ──
        self.bids.clear()
        for agent in a.players.values():
            agent.quick_action_prompt = f"本轮赃款{self.loot}。只回复一个整数，例如：5"
        try:
            await a.collect_actions(ctx, alive, parallel=True)
        finally:
            for agent in a.players.values():
                agent.quick_action_prompt = None

        for p in alive:
            raw = p.last_cot.secret_action if p.last_cot else ""
            bid = self._parse_bid(raw)
            self.bids[p.id] = bid

        # CoT 合并
        for pid, p in ctx.round.players.items():
            if p.is_alive and pid in speech_cots and p.last_cot:
                old = speech_cots[pid]
                p.last_cot = p.last_cot.model_copy(update={
                    "situation_assessment": old.get("situation_assessment", ""),
                    "internal_strategy": old.get("internal_strategy", ""),
                    "public_speech": old.get("public_speech", ""),
                })

        # ── 结算 ──
        self._pending_elimination = None
        self._pending_random = False
        result_text = self._resolve_bids(ctx, alive, round_num)
        if self._pending_elimination:
            victim = ctx.round.players[self._pending_elimination]
            a.eliminate(ctx, self._pending_elimination)
            logger.info(f"💀 {victim.name} 连续两次破裂出价最高，被定向淘汰！")
            ctx.round.public_log.append(f"💀 {victim.name} 连续两次破裂出价最高，被淘汰！")
        elif self._pending_random:
            alive_now = [p for p in ctx.round.players.values() if p.is_alive]
            if len(alive_now) > 2:
                victim = random.choice(alive_now)
                a.eliminate(ctx, victim.id)
                logger.info(f"💀 已破裂 {self.bankrupt_count} 轮——{victim.name} 被随机淘汰！")
                ctx.round.public_log.append(f"💀 已破裂 {self.bankrupt_count} 轮，{victim.name} 被随机淘汰！")

        for pid, p in ctx.round.players.items():
            if p.is_alive and p.last_cot:
                bid = self.bids.get(pid, 0)
                p.last_cot = p.last_cot.model_copy(update={
                    "secret_action": f"开价 {bid}",
                })

        # ── DM + 推送 ──
        self.memory.add_critical_event(CriticalEvent(
            round_number=round_num,
            event=f"## 第{round_num}轮 赃款{self.loot}\n{result_text}",
            related_players=[],
        ))
        actions = [(p, p.last_cot) for p in ctx.round.players.values() if p.last_cot]
        await a.dm_judge(ctx, actions)
        # 盲投模式：DM 裁决不进温记忆，避免分数泄露。6 轮游戏热记忆足够。
        self.memory.update_warm_summary("")
        await a.emit_state(ctx)

        if round_num >= ctx.game_config.total_rounds:
            return False
        return True

    # ============================================================
    # 旧钩子
    # ============================================================

    async def on_game_start(self, ctx):
        pids = [p.id for p in ctx.round.players.values()]
        random.shuffle(pids)

        # 分配公开身份
        ids_copy = list(IDENTITIES)
        random.shuffle(ids_copy)
        for i, pid in enumerate(pids):
            self.identities[pid] = ids_copy[i]

        # 分配秘密目标（先存，盯上再后处理——需要找到称霸者）
        goals_copy = list(GOALS)
        random.shuffle(goals_copy)
        for i, pid in enumerate(pids):
            self.goals[pid] = goals_copy[i]

        # 盯上目标 = 称霸玩家（不告知称霸者的目标）
        dominator_pid = next((pid for pid in pids if self.goals[pid][0] == "称霸"), None)
        for pid in pids:
            goal_name, goal_desc = self.goals[pid]
            if goal_name == "盯上":
                target = dominator_pid if dominator_pid else [o for o in pids if o != pid][0]
                self.stalk_targets[pid] = target
                tname = ctx.round.players[target].name
                goal_desc = goal_desc.format(target=f"{tname}（{target}）")
                self.goals[pid] = (goal_name, goal_desc)

        # 发送公开身份 + 秘密目标
        for pid in pids:
            identity = self.identities[pid]
            goal_name, goal_desc = self.goals[pid]
            # 公开身份（所有人可见——发送给每个玩家）
            id_list = "\n".join(
                f"  - {oid} ({ctx.round.players[oid].name}): 【{self.identities[oid]}】"
                for oid in pids)
            self.memory.add_private(pid,
                f"## 🔐 你的秘密目标（获胜条件）\n"
                f"**{goal_name}**：{goal_desc}\n\n"
                f"⚠️ 只有达成自己的秘密目标才能获胜，积分高低不是关键！\n\n"
                f"## 全玩家公开身份（所有人可见，仅供参考）\n{id_list}\n\n"
                f"## 你的公开身份: 【{identity}】\n"
                f"（公开身份只是面具——任何身份都可能是任何秘密目标）\n\n"
                f"每人都只有一个不同的秘密目标。你只知道自己的，别人的目标要从开价和发言中推理。")
            # 前端显示（LLM 不可见，仅观战者可见）
            stalk_info = ""
            if goal_name == "盯上":
                target = self.stalk_targets.get(pid, "")
                tname = ctx.round.players[target].name if target in ctx.round.players else target
                stalk_info = f" → {tname}"
            ctx.round.players[pid].fraud_tag = identity
            ctx.round.players[pid].see_tag = f"目标: {goal_name}{stalk_info}"

        self.bankrupt_count = 0
        self.last_bankrupt_top = None
        return ctx

    async def check_win_condition(self, ctx):
        if ctx.round.round_number < ctx.game_config.total_rounds:
            return None

        alive = [p for p in ctx.round.players.values() if p.is_alive]
        if not alive:
            return None

        # 排序（降序）
        ranked = sorted(alive, key=lambda p: p.resources.get("points", 0), reverse=True)
        scores = {p.id: p.resources.get("points", 0) for p in alive}
        ranks = {}
        for i, p in enumerate(ranked):
            ranks[p.id] = i + 1  # 1-indexed

        winners = []
        n = len(alive)
        mid_positions = [n // 2, n // 2 + 1] if n % 2 == 0 else [n // 2 + 1]
        for p in alive:
            goal_name, _ = self.goals[p.id]
            met = False
            if goal_name == "称霸":
                top_score = max(scores.values())
                sole = sum(1 for s in scores.values() if s == top_score) == 1
                met = ranks[p.id] == 1 and sole
            elif goal_name == "垫底":
                met = ranks[p.id] == n and scores[p.id] >= 6
            elif goal_name == "中游":
                met = ranks[p.id] in mid_positions
            elif goal_name == "毁灭者":
                met = self.bankrupt_count >= 3 and ranks[p.id] <= (n + 1) // 2
            elif goal_name == "和平奖":
                met = (6 - self.bankrupt_count) >= 3 and ranks[p.id] != n - 1
            elif goal_name == "盯上":
                target = self.stalk_targets.get(p.id)
                if target and target in scores:
                    met = scores[p.id] > scores[target]
            if met:
                winners.append(p.id)
                logger.info(f"  {p.name}【{self.identities[p.id]}】达成目标「{goal_name}」✓")

        return ",".join(winners) if winners else None

    # ============================================================
    # 内部
    # ============================================================

    def _send_private_info(self, ctx):
        rn = ctx.round.round_number
        for pid, p in ctx.round.players.items():
            if not p.is_alive:
                continue
            goal_name, goal_desc = self.goals.get(pid, ("?", "?"))
            # 前三轮全盲：连自己分都不显示；第4轮起公开
            if rn <= 3:
                id_list = "\n".join(
                    f"  - {oid} ({ctx.round.players[oid].name})【{self.identities.get(oid, '?')}】: ? 分"
                    for oid in ctx.round.players if ctx.round.players[oid].is_alive)
                info = f"## 玩家身份（你的 ID: {pid}）\n{id_list}"
            else:
                id_list = "\n".join(
                    f"  - {oid} ({ctx.round.players[oid].name})【{self.identities.get(oid, '?')}】: {ctx.round.players[oid].resources.get('points', 0)} 分"
                    for oid in ctx.round.players if ctx.round.players[oid].is_alive)
                info = f"## 玩家身份与积分（你的 ID: {pid}，{p.resources.get('points', 0)} 分）\n{id_list}"

            info += f"\n\n## 🔐 你的秘密目标: {goal_name}——{goal_desc}"
            info += f"\n\n## 本轮赃款: {self.loot}"
            info += "\n每人写想要的份额。求和 ≤ 赃款 → 按出价分配。求和 > 赃款 → 全拿0。"
            info += "\n⚠️ 每两次破裂淘汰1人：同一人连续出价最高→定向淘汰，否则→随机淘汰。"

            # 前三轮提示
            if rn <= 3:
                info += "\n\n⚠️ 前三轮全盲——你连自己的积分都不知道。第4轮公开全员积分榜和破裂次数。"

            # 前三轮隐藏破裂次数；第4轮起公开
            if rn >= 4:
                info += f"\n已达成的破裂回合: {self.bankrupt_count}"

            # 第5轮起：公开上轮每个人的出价
            if rn >= 5:
                prev = rn - 1
                if prev in self.round_bids:
                    bid_list = "\n".join(
                        f"  - {oid} ({ctx.round.players[oid].name}): 开了 {self.round_bids[prev].get(oid, '?')}"
                        for oid in ctx.round.players if ctx.round.players[oid].is_alive)
                    info += f"\n\n## 🔎 第{prev}轮出价公开\n{bid_list}"

            info += "\n\n## 出价阶段\n在 secret_action 中只写一个整数（你想要多少）。不要写小数。"
            self.memory.add_private(pid, info)

    def _parse_bid(self, text: str) -> int:
        t = text.strip().replace(" ", "")
        if not t:
            return 0
        nums = re.findall(r'\d+', t)
        if nums:
            return max(0, int(nums[0]))
        cn = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        for k, v in cn.items():
            if k in t:
                return v
        return 0

    def _resolve_bids(self, ctx, alive, round_num) -> str:
        if not self.bids:
            return "无人出价"

        # 存储本轮出价（供后续轮次公开）
        self.round_bids[round_num] = dict(self.bids)

        logger.info(f"=== Round {round_num} 出价汇总（赃款{self.loot}）===")
        total = 0
        for p in alive:
            bid = self.bids.get(p.id, 0)
            total += bid
            raw = p.last_cot.secret_action if p.last_cot else ""
            logger.info(f"  {p.name}【{self.identities[p.id]}】: 开{bid}  raw=[{raw[:60]}]")

        if total <= self.loot:
            for p in alive:
                bid = self.bids.get(p.id, 0)
                p.resources["points"] = p.resources.get("points", 0) + bid
            truth = f"求和 {total} ≤ 赃款 {self.loot}，谈判成功！全员按出价分配。"
            self.last_bankrupt_top = None  # 成功则重置追踪
        else:
            self.bankrupt_count += 1
            truth = f"求和 {total} > 赃款 {self.loot}，谈判破裂！全员拿0。破裂回合: {self.bankrupt_count}"
            # 找出本轮出价最高者（平票则无人被标记）
            top_bid = max(self.bids.values())
            top_pids = [pid for pid, b in self.bids.items() if b == top_bid]
            if len(top_pids) == 1:
                cur_top = top_pids[0]
                if self.bankrupt_count % 2 == 0:
                    # 每两次破裂触发淘汰：同一人→定向，不同人→随机
                    if self.last_bankrupt_top == cur_top:
                        self._pending_elimination = cur_top
                    else:
                        self._pending_random = True
                self.last_bankrupt_top = cur_top
            else:
                if self.bankrupt_count % 2 == 0:
                    self._pending_random = True
                self.last_bankrupt_top = None  # 平票则无人被标记
        logger.info(f"  → {truth}")

        # 前三轮只告诉"谈判结束"，不透露成败
        if round_num <= 3:
            ctx.round.public_log.append(f"💰 第{round_num}轮赃款{self.loot}，谈判结束。")
        else:
            ctx.round.public_log.append(truth)
        return truth
