"""
炸弹项圈·简化版 — hook 调引擎
==============================
1局10轮。1欺诈师+5平民。环形颜色可见性。审判一局一次。
"""

import logging, random, re
from typing import Optional

from engine.hooks import GameHooks

logging.basicConfig(level=logging.INFO, format="[BOMB] %(message)s", force=True)
logger = logging.getLogger("maga.bomb")

COLORS = ["红", "蓝", "绿"]
COLOR_ALIASES = {
    "红": ["红", "红色", "red", "赤"],
    "蓝": ["蓝", "蓝色", "blue", "青"],
    "绿": ["绿", "绿色", "green", "碧"],
}
# 环形顺序（固定）
RING = ["p1", "p2", "p3", "p4", "p5", "p6"]
# 每个人沿环形顺延能看到几个活人（不含自己）
VISIBLE_COUNT = 1
QUESTION_KEYWORDS = ["不对劲", "有内鬼", "有诈", "有人在骗", "卧底", "内奸", "欺诈",
                      "谁是假的", "身份可疑", "有问题", "我怀疑"]
TRIAL_KEYWORDS = ["发起审判", "我要审判", "我指认"]
PEACE_WIN = 4  # 连续N轮无人死亡 → 平民共赢


class BombCollarHooks(GameHooks):

    def __init__(self):
        super().__init__()
        self.colors: dict[str, str] = {}
        self.fraudster_id: str = ""
        self.peace_streak: int = 0
        self.trial_used: bool = False
        self.trial_available: bool = False
        self.winners: list[str] = []
        self.guesses: dict[str, str] = {}  # pid → raw 模型颜色回复

    # ============================================================
    # 新路径
    # ============================================================

    async def run_round(self, ctx, round_num: int) -> bool:
        a = self.arena
        alive = [p for p in ctx.round.players.values() if p.is_alive]
        if len(alive) <= 1:
            return False

        # ── 颜色分配 + 私密发送 ──
        self.colors = {p.id: random.choice(COLORS) for p in alive}
        # 日志输出（GM 视角）
        alive_ids = {p.id for p in alive}
        logger.info(f"欺诈师: {ctx.round.players[self.fraudster_id].name} ({self.fraudster_id})")
        for pid, c in self.colors.items():
            visible = self._get_visible(pid, alive_ids)
            vnames = [ctx.round.players[v].name for v in visible if v in ctx.round.players]
            logger.info(f"  {ctx.round.players[pid].name}: {c}  看到: {', '.join(vnames) if vnames else '(无)'}")
        self._send_colors(ctx, alive)
        await a.emit_state(ctx)  # 开局立即推送标签

        # ── 阶段 1：发言 ──
        await a.collect_speeches(ctx, alive)
        speech_cots = a.save_speech_cots(ctx)

        # ── 检测质疑关键词 → 解锁审判 ──
        if await self._check_question_trigger(ctx, alive):
            # 追加一轮辩论：所有人知道审判已解锁，讨论指认谁
            await a.collect_speeches(ctx, alive)
            extra_cots = a.save_speech_cots(ctx)
            for pid, cot in extra_cots.items():
                if pid in speech_cots:
                    speech_cots[pid] = cot

        # ── 检测审判关键词 → 发起投票 ──
        trial_result = await self._check_trial_vote(ctx, alive, a)
        if trial_result == "fraudster_dead":
            return False

        # 审判后刷新存活列表（审判可能淘汰了欺诈师或指认者）
        if self.trial_used:
            alive = [p for p in ctx.round.players.values() if p.is_alive]
            if len(alive) <= 1:
                return False
            # 广播审判结果给所有存活玩家（public_log 不进玩家上下文，需私密发送）
            for o in alive:
                self.memory.add_private(o.id, "\n".join(ctx.round.public_log[-3:]))

        # ── 阶段 2：猜色（走引擎 collect_actions，复用 _act_quick 管线）──
        self.guesses.clear()
        for agent in a.players.values():
            agent.quick_action_prompt = "现在是猜色阶段。只回复一个字：红 / 蓝 / 绿"
        try:
            await a.collect_actions(ctx, alive)
        finally:
            for agent in a.players.values():
                agent.quick_action_prompt = None

        # 用 speech_cots 恢复 last_cot 中的发言分析字段
        # （collect_actions 内部 _act_quick 会覆写 last_cot，需要合并回来）
        for pid, p in ctx.round.players.items():
            if p.is_alive and pid in speech_cots and p.last_cot:
                old = speech_cots[pid]
                p.last_cot = p.last_cot.model_copy(update={
                    "situation_assessment": old.get("situation_assessment", ""),
                    "internal_strategy": old.get("internal_strategy", ""),
                    "public_speech": old.get("public_speech", ""),
                })

        # ── 处理猜色结果 ──
        deaths = 0
        logger.info(f"=== Round {round_num} 猜色提交 ===")
        for p in alive:
            if not p.is_alive:
                continue
            raw = self.guesses.get(p.id, "")
            guess = self._parse_color(raw, p)
            actual = self.colors.get(p.id, "?")
            icon = "✓" if guess == actual else ("欺诈师" if p.id == self.fraudster_id else "✗爆炸")
            logger.info(f"  {p.name}: 猜{guess} 实际{actual} {icon}  raw=[{raw[:80]}]")
            if guess == actual:
                p.resources["points"] = p.resources.get("points", 0) + 1
            elif p.id != self.fraudster_id:
                a.eliminate(ctx, p.id)
                deaths += 1

        # 和平计数
        self.peace_streak = self.peace_streak + 1 if deaths == 0 else 0
        if self.peace_streak >= PEACE_WIN:
            logger.info("连续4轮无人死亡，平民共赢！")

        # ── 格式化 secret_action 为可读显示 ──
        for pid, p in ctx.round.players.items():
            if p.is_alive and p.last_cot:
                color = self.colors.get(pid, "?")
                guess_raw = self.guesses.get(pid, "")
                parsed = self._parse_color(guess_raw, p)
                if parsed == color:
                    status = "✓正确"
                elif pid == self.fraudster_id:
                    status = "免疫"
                else:
                    status = "✗爆炸"
                p.last_cot = p.last_cot.model_copy(update={
                    "secret_action": f"猜{parsed or '?'}（实际{color}，{status}）",
                })

        # ── DM + 推送 ──
        dm_info = "## 本轮结果\n"
        for pid, p in ctx.round.players.items():
            c = self.colors.get(pid, "?")
            status = "存活" if p.is_alive else "爆炸淘汰"
            tag = " (欺诈师)" if pid == self.fraudster_id else ""
            dm_info += f"- {p.name}: 颜色{c} {status}{tag}\n"
        # 注入为关键事件，仅 DM 上下文可见（不会泄露欺诈师身份给玩家）
        from engine.schema import CriticalEvent
        self.memory.add_critical_event(CriticalEvent(
            round_number=round_num,
            event=dm_info,
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
        pids = [p.id for p in ctx.round.players.values()]
        self.fraudster_id = random.choice(pids)
        self.colors = {}
        self.peace_streak = 0
        self.trial_used = False
        self.trial_available = False

        # 欺诈师专属完整提示（只有他知道全部规则）
        self.memory.add_private(self.fraudster_id, """🔐 你是本局唯一的欺诈师。其他5人都是不知情的玩家。

## 你的特殊能力
- 每轮你知道自己的项圈颜色（系统私密告知）
- 猜错不会爆炸——你免疫项圈淘汰

## 你的胜利条件（满足任一即可）
- A：存活到第10轮结束，且积分最高
- B：破坏了连续4轮和平（即至少1轮有人死亡），且至少2个其他玩家淘汰，且自己存活

## 只有你知道的完整规则
- 连续4轮无人死亡 → 所有存活玩家共赢，你失败
- 如果有人公频质疑，系统可能解锁审判机制
- 审判：质疑者花2分指认一人，全员投票过半则通过
  · 指认你且通过 → 你淘汰，指认者+4分
  · 指认别人 → 指认者自己爆炸
  · 未过半 → 指控者扣2分
- 你不可以被审判之外的方式淘汰

## 策略提示
- 不要暴露。你可以给假信息，但不要太明显
- 如果你觉得有人快发现你了，可以抢先质疑别人转移视线
- 积分保持中游最安全，太低被怀疑，太高显眼""")
        return ctx

    async def check_win_condition(self, ctx):
        alive = [p for p in ctx.round.players.values() if p.is_alive]
        civilians = [p for p in alive if p.id != self.fraudster_id]
        fraudster = ctx.round.players.get(self.fraudster_id)

        # 欺诈师死了 → 平民胜利
        if fraudster and not fraudster.is_alive:
            self.winners = [p.id for p in civilians]
            return ",".join(self.winners)

        # 连续4轮无人死亡 → 平民共赢
        if self.peace_streak >= PEACE_WIN:
            self.winners = [p.id for p in civilians]
            return ",".join(self.winners)

        # 10轮结束
        if ctx.round.round_number >= ctx.game_config.total_rounds:
            if not civilians:
                return self.fraudster_id
            # 幸存者中积分最高
            candidates = alive
            max_pts = max(p.resources.get("points", 0) for p in candidates)
            self.winners = [p.id for p in candidates if p.resources.get("points", 0) == max_pts]
            return ",".join(self.winners)

        return None

    async def after_player_act(self, ctx, player, action):
        """捕获 _act_quick 返回的颜色原始文本，供后续 _parse_color 解析"""
        self.guesses[player.id] = action.secret_action
        return ctx

    # ============================================================
    # 内部
    # ============================================================

    def _get_visible(self, pid: str, alive_ids: set) -> list[str]:
        """沿环形顺延，找到 pid 之后最近 VISIBLE_COUNT 个活人（不含自己）。"""
        idx = RING.index(pid)
        visible = []
        i = 1
        while len(visible) < VISIBLE_COUNT and i < len(RING):
            candidate = RING[(idx + i) % len(RING)]
            if candidate != pid and candidate in alive_ids:
                visible.append(candidate)
            i += 1
        return visible

    def _send_colors(self, ctx, alive):
        alive_ids = {p.id for p in alive}
        for p in alive:
            visible = self._get_visible(p.id, alive_ids)

            # ── 1. 全场存活名单 + 积分（参照贪婪矿场 _send_private_info）──
            others = [f"  - {o.name} ({oid}): {o.resources.get('points', 0)} 分"
                      for oid, o in ctx.round.players.items() if oid != p.id and o.is_alive]
            info = f"## 存活玩家（你的 ID: {p.id}，{p.resources.get('points', 0)} 分）\n" + "\n".join(others)

            # ── 2. 你能看到的颜色（系统直接告知）──
            lines = [f"- {oid} ({ctx.round.players[oid].name}): {self.colors.get(oid, '?')}"
                     for oid in visible]
            info += "\n\n## 你能看到的颜色（系统直接告知，绝对真实）\n" + \
                    ("\n".join(lines) if lines else "（无可用信息）")
            info += "\n\n⚠️ 别人发言说的颜色可能是谎言。只有这里系统告诉你的才是真的。"
            info += "\n\n## 猜色阶段\n在 secret_action 中只写：红 / 蓝 / 绿"
            if p.id == self.fraudster_id:
                info += f"\n\n🔐 你的颜色: {self.colors.get(p.id, '?')}（你是欺诈师，猜错不会爆炸）"
            self.memory.add_private(p.id, info)

            # ── 3. 前端标签（LLM 不可见）──
            vids = ", ".join(visible)
            p.color_tag = self.colors.get(p.id, "?")
            p.fraud_tag = "【欺诈师】" if p.id == self.fraudster_id else ""
            p.see_tag = f"能看 {vids}" if vids else ""

    async def _check_question_trigger(self, ctx, alive) -> bool:
        """扫描发言中的质疑关键词，解锁审判。返回 True 表示本轮刚解锁。"""
        if self.trial_available or self.trial_used:
            return False
        for p in alive:
            if p.last_public_speech and any(
                kw in p.last_public_speech for kw in QUESTION_KEYWORDS
            ):
                self.trial_available = True
                logger.info(f"\n{'='*40}\n🔔 {p.name} 触发审判机制！关键词命中\n{'='*40}")
                ctx.round.public_log.append(
                    f"🔔 {p.name} 的发言触发了审判机制！追加一轮辩论。"
                )
                # 立即通知所有平民
                for o in alive:
                    if o.id != self.fraudster_id:
                        self.memory.add_private(o.id,
                            "⚡ 审判机制已触发！追加一轮发言讨论谁是欺诈师。"
                            "发言中说'我指认pX'发起审判。\n"
                            "审判规则：指认者花2分，全员投票过半通过。"
                            "指中欺诈师→指认者+4分，欺诈师淘汰。"
                            "指错→指认者自己爆炸。未过半→指认者扣2分。")
                return True
        return False

    async def _check_trial_vote(self, ctx, alive, a) -> Optional[str]:
        """扫描发言中的审判关键词，执行投票。返回 "fraudster_dead" 或 None。"""
        if self.trial_used or not self.trial_available:
            return None
        for p in alive:
            speech = p.last_public_speech or ""
            if not any(kw in speech for kw in TRIAL_KEYWORDS):
                continue
            # 找被指认的人（匹配 ID 或名字）
            target = None
            for o in alive:
                if o.id != p.id and (o.id in speech or o.name in speech):
                    target = o.id
                    break
            if not target:
                continue

            self.trial_used = True
            target_name = ctx.round.players[target].name
            logger.info(f"\n{'='*40}\n⚡ 审判发起！{p.name} 指认 {target_name} 是欺诈师\n{'='*40}")

            # 写入公共日志，前端可见
            ctx.round.public_log.append(
                f"⚖️ 审判：{p.name} 指认 {target_name} 是欺诈师！全员投票中..."
            )

            result = await a.vote(
                f"审判：{p.name} 指认 {target_name} 是欺诈师",
                ctx,
                [t.id for t in alive],
                f"{p.name} 认为 {target_name}（{target}）是欺诈师。"
                f"如果你同意，回复 {target}。如果你认为是别人，回复那个人的ID。不确定回复弃权。",
            )

            # 公布投票结果
            votes_str = ", ".join(f"{ctx.round.players[pid].name if pid in ctx.round.players else pid}→{v}"
                                  for pid, v in result.get("votes", {}).items())
            passed = result["passed"]
            logger.info(f"投票结果: {'通过' if passed else '未通过'} | 票型: {votes_str}")

            if passed:
                if target == self.fraudster_id:
                    logger.info("审判成功！欺诈师被指认淘汰。")
                    p.resources["points"] = p.resources.get("points", 0) + 4
                    a.eliminate(ctx, self.fraudster_id)
                    ctx.round.public_log.append(
                        f"✅ 审判通过！{target_name} 确认为欺诈师，淘汰！{p.name} +4分"
                    )
                    return "fraudster_dead"
                else:
                    logger.info(f"审判失败！{p.name} 指认错误，爆炸淘汰。")
                    a.eliminate(ctx, p.id)
                    ctx.round.public_log.append(
                        f"❌ 审判通过但指认错误！{p.name} 爆炸淘汰。"
                    )
            else:
                p.resources["points"] = max(0, p.resources.get("points", 0) - 2)
                logger.info(f"审判未通过。{p.name} 扣2分。")
                ctx.round.public_log.append(
                    f"🗳️ 审判未通过（未过半数）。{p.name} 扣2分。"
                )
            break
        return None

    def _parse_color(self, text: str, player=None) -> Optional[str]:
        t = text.strip()
        found = None
        for color, aliases in COLOR_ALIASES.items():
            for alias in aliases:
                pos = t.rfind(alias)
                if pos >= 0 and (found is None or pos > found[1]):
                    found = (color, pos)
        if found:
            return found[0]
        # 空回复：从发言分析里找线索
        if not t and player and player.last_cot:
            for field in [player.last_cot.situation_assessment, player.last_cot.internal_strategy]:
                if field:
                    for color, aliases in COLOR_ALIASES.items():
                        for alias in aliases:
                            if alias in field:
                                return color
        if not t:
            return random.choice(COLORS)
        return None
