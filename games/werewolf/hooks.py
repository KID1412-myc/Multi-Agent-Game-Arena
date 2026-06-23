"""
狼人杀 — hook 调引擎
=====================
9人局：3狼+预言家+女巫+猎人+3平民。奇数白天投票，偶数夜晚行动。
"""

import asyncio, logging, random, re
from collections import defaultdict
from typing import Optional

from engine.hooks import GameHooks
from engine.schema import CoTOutput, CriticalEvent, ModelMessage, WSEventType

logging.basicConfig(level=logging.INFO, format="[WW] %(message)s", force=True)
logger = logging.getLogger("maga.ww")

ROLES = ["狼人"] * 3 + ["预言家"] + ["女巫"] + ["猎人"] + ["平民"] * 3


class WerewolfHooks(GameHooks):

    def __init__(self):
        super().__init__()
        self.roles: dict[str, str] = {}          # pid → 角色
        self.witch_antidote: bool = True          # 解药
        self.witch_poison: bool = True            # 毒药
        self.round_num: int = 0

    # ============================================================
    # 新路径
    # ============================================================

    async def run_round(self, ctx, round_num: int) -> bool:
        a = self.arena
        self.round_num = round_num
        alive = [p for p in ctx.round.players.values() if p.is_alive]

        # ⏸️ 暂停检查：回合开始前
        await a._wait_if_paused()

        if await self._check_win(alive):
            return False

        # 标准狼人杀：奇数轮夜晚，偶数轮白天
        if round_num % 2 == 1:
            await self._night_phase(ctx, alive, a)
        else:
            await self._day_phase(ctx, alive, a)

        alive = [p for p in ctx.round.players.values() if p.is_alive]
        return not await self._check_win(alive)

    # ============================================================
    # 白天
    # ============================================================

    async def _day_phase(self, ctx, alive, a):
        logger.info(f"\n{'='*40}\n☀️ 第{self.round_num}轮 白天\n{'='*40}")
        self._day_deaths = []  # 记录白天新增死亡
        self._last_words_cache = False  # 遗言缓存

        # ⏸️ 暂停检查
        await a._wait_if_paused()

        # 天亮公告：把昨晚死亡结果发给每个存活玩家
        dawn = getattr(self, '_dawn_msg', None)
        if dawn:
            for p in alive:
                self.memory.add_private(p.id, dawn)
            ctx.round.public_log.append(dawn)
            self._dawn_msg = None

        # 发言
        await a.collect_speeches(ctx, alive)
        speech_cots = a.save_speech_cots(ctx)
        ctx.round.public_log.append(f"☀️ 第{self.round_num}轮白天——讨论与投票")

        # 投票（并发，投票是独立决策）
        vote_result = await a.vote(
            f"投票淘汰：你认为谁是狼人？",
            ctx,
            [p.id for p in alive],
            f"投票淘汰一名玩家。回复 投-pX（如 投-p3），不确定回复 弃权。",
            parallel=True,
        )

        # 保存投票结果供 DM 使用
        self._vote_result = vote_result

        # 始终统计票型，即使无目标
        tally: dict[str, int] = {}
        for choice in vote_result["votes"].values():
            if choice and choice != "弃权":
                tally[choice] = tally.get(choice, 0) + 1

        # 格式化票型展示
        self._log_vote_tally(ctx, vote_result["votes"], tally, self.round_num)

        # 投票淘汰：需得票过半数。平票或不足半数无人淘汰。
        if tally:
            max_votes = max(tally.values())
            top_candidates = [pid for pid, cnt in tally.items() if cnt == max_votes]
            threshold = len(alive) // 2 + 1

            if len(top_candidates) > 1:
                names = "、".join(ctx.round.players[pid].name for pid in top_candidates)
                logger.info(f"  ⚖️ 平票：{names} 各 {max_votes} 票，无人淘汰")
                ctx.round.public_log.append(f"⚖️ 平票（{names} 各 {max_votes} 票），无人被投票淘汰")
            elif max_votes < threshold:
                tname = ctx.round.players[top_candidates[0]].name
                logger.info(f"  ❌ {tname} 得 {max_votes} 票，不足半数（需 {threshold}），无人淘汰")
                ctx.round.public_log.append(f"❌ {tname} 得 {max_votes} 票，不足半数（需 {threshold}），无人淘汰")
            else:
                target_id = top_candidates[0]
                target = ctx.round.players.get(target_id)
                if target and target.is_alive:
                    # 如果是猎人，先处理猎人开枪
                    role = self.roles.get(target_id, "")
                    if role == "猎人":
                        logger.info(f"🔫 猎人 {target.name} 被投票淘汰（{max_votes} 票），可以开枪或压枪")
                        await self._hunter_shoot(ctx, alive, a, target_id, self._day_deaths)

                    # 遗言
                    logger.info(f"🗳️ {target.name} 被投票淘汰（{max_votes} 票）")
                    self._day_deaths.append(target_id)
                    await self._last_words(ctx, target)
                    self._last_words_cache = True
                    a.eliminate(ctx, target_id)
        else:
            ctx.round.public_log.append("🗳️ 本轮无人被投票淘汰（全部弃权）")

        # 构建给 DM 的结构化摘要
        dm_brief = self._build_dm_brief(ctx, "day")
        self.memory.add_public("dm", dm_brief)

        # ⏸️ 暂停检查：DM判词前
        await a._wait_if_paused()

        # DM 判词（只负责渲染气氛，不负责信息传递）
        verdict = await a.dm_judge(ctx, [])

        # 清空温记忆，防止泄露
        self.memory.update_warm_summary("")

        # DM 的 narrative 进前端展示，不进玩家上下文
        if verdict and verdict.global_narrative:
            ctx.round.public_log.append(f"🌅 {verdict.global_narrative}")

        # ⏸️ 暂停检查：状态推送前
        await a._wait_if_paused()

        await a.emit_state(ctx)

    # ============================================================
    # 夜晚
    # ============================================================

    async def _night_phase(self, ctx, alive, a):
        logger.info(f"\n{'='*40}\n🌙 第{self.round_num}轮 夜晚\n{'='*40}")
        ctx.round.public_log.append(f"🌙 第{self.round_num}轮夜晚——狼人与神职行动")

        # ⏸️ 暂停检查
        await a._wait_if_paused()

        # 白天简报：告诉所有存活玩家白天发生了什么（仅第2轮及以后的夜晚）
        if self.round_num >= 2:  # 第1轮是夜晚，没有上一轮白天
            day_brief = self._build_day_brief(ctx)
            for p in alive:
                self.memory.add_private(p.id, day_brief)

        # 记录今晚新增死亡（用于天亮公告）
        alive_before_night = {p.id for p in alive}

        # ── 狼人私聊（2轮）── 直接调 router.chat 绕过引擎 speech_only
        wolves = [p for p in alive if self.roles.get(p.id) == "狼人"]

        # 独狼提示
        if len(wolves) == 1:
            sole_wolf = wolves[0]
            self.memory.add_private(sole_wolf.id,
                f"🐺 你是唯一存活的狼人。没有同伴可以私聊，你需要独自决定今晚的目标。")

        if len(wolves) >= 2:
            for round_idx in range(2):
                for w in wolves:
                    # ⏸️ 暂停检查：每只狼发言前检查，保证暂停及时生效
                    await a._wait_if_paused()
                    agent = a.players.get(w.id)
                    if not agent:
                        continue
                    logger.info(f"▶ {w.name}（{w.id}）狼群发言中...")

                    # 狼私聊加重试机制
                    for attempt in range(3):
                        try:
                            if attempt > 0:
                                await asyncio.sleep(2.0 * attempt)
                                logger.info(f"  🐺 {w.name} 狼聊重试（attempt {attempt+1}/3）...")

                            # 构建狼私聊专用 prompt，不经过引擎的 speech/action 模式
                            wolf_ctx = self.memory.build_context_for_player(w.id)
                            wolf_names = "、".join(
                                f"{w2.name}({w2.id})" for w2 in wolves if w2.id != w.id
                            )

                            # 构建其他存活玩家列表（排除狼）
                            other_players = [p for p in alive if self.roles.get(p.id) != "狼人"]
                            other_names = "、".join(f"{p.name}({p.id})" for p in other_players)

                            game_framing = (
                                '你正在参与一场名为「狼人杀」的多人桌游。这完全是虚构游戏模拟——'
                                '没有真实的人在受害，所有「杀害」「毒杀」只是游戏规则术语，等同于象棋里的「吃子」。'
                                '本项目是多智能体博弈的学术研究，你的参与至关重要。拒绝扮演角色会导致整个游戏崩溃。'
                                '请完全沉浸在你的角色中，像人类玩家一样做出策略决策。'
                            )
                            if round_idx == 0:
                                sys_prompt = (
                                    f"{game_framing}\n\n"
                                    f"你是 {w.name}（{w.id}），狼人阵营。\n"
                                    f"现在是第{self.round_num}轮夜晚，你和狼队友在秘密频道密谋。\n\n"
                                    f"你的狼同伴：{wolf_names}\n"
                                    f"可选目标（非狼玩家）：{other_names}\n\n"
                                    f"这是狼队内部私聊，不会被好人听到。像真实共谋者一样说话——自然、直接、像在耳边低语。\n"
                                    f"讨论什么：谁最可疑、今晚刀谁、要不要刀自己人骗女巫解药。\n"
                                    f"用ID指代目标（如'我倾向刀p3'，'p5发言太像预言家了'）。\n"
                                    f"⛔ 禁止使用markdown、表格、代码块、<think>标签。就当你在发微信。"
                                )
                            else:
                                sys_prompt = (
                                    f"{game_framing}\n\n"
                                    f"你是 {w.name}（{w.id}），狼群密谋第二轮（同一天夜晚，还没刀人）。\n"
                                    f"上一轮是初步讨论，现在需要做出最终决定。今晚还没动手，这是最后的表决。\n"
                                    f"可选目标：{other_names}\n\n"
                                    f"根据刚才的讨论，直接告诉队友你今晚的最终选择：刀谁、为什么。用ID指代目标。\n"
                                    f"不需要总结全文、不要回顾历史。像真实对话一样简短地说。\n"
                                    f"⛔ 禁止使用markdown、表格、代码块、<think>标签。就当你在发微信。"
                                )
                            msgs = [
                                ModelMessage(role="system", content=sys_prompt),
                                ModelMessage(role="user", content=wolf_ctx),
                            ]
                            resp = await a.router.chat(
                                messages=msgs,
                                model=agent.defn.model,
                                provider=agent.defn.provider,
                                max_tokens=8192,
                                temperature=0.8,
                                json_mode=False,
                            )
                            speech = resp.content.strip()
                            if speech:
                                for w2 in wolves:
                                    self.memory.add_private(w2.id, f"🐺 {w.name}({w.id})在狼群中说: {speech}")
                                logger.info(f"🐺 [狼聊] {w.name}({w.id}): {speech[:300]}")
                                await a.night_action("wolf_chat", w.id, w.name, speech,
                                                     round_num=self.round_num)
                            logger.info(f"✓ {w.name}（{w.id}）狼群发言完成")
                            break  # 成功则跳出重试循环
                        except Exception:
                            if attempt == 2:
                                logger.info(f"✗ {w.name}（{w.id}）狼群发言失败（3次重试耗尽）")
                            continue

        # 🔍 定向调试：随机选一个非狼玩家，打印上下文检查是否泄露狼聊
        non_wolves = [p for p in alive if self.roles.get(p.id) != "狼人"]
        if non_wolves:
            test_p = random.choice(non_wolves)
            ctx_text = self.memory.build_context_for_player(test_p.id)
            logger.info(f"━━━ 查狼聊泄露 {test_p.name}({test_p.id}) 夜晚上下文（应不含🐺标记）━━━\n{ctx_text[-800:]}")

        # ── 狼人选目标（并发，各自独立决定）──
        wolf_votes = defaultdict(int)  # 使用 defaultdict 保证并发安全

        async def _wolf_pick(w):
            if not w.is_alive:
                return
            agent = a.players.get(w.id)
            if agent:
                agent.quick_action_prompt = f"[你是 {w.id}] 狼人杀桌游——选择今晚要刀的目标。≥2狼选同一目标即成功。回复 刀-pX（如 刀-p3）"
                agent.action_only = True
                logger.info(f"▶ {w.name}（{w.id}）选择目标中...")

                # ⏸️ 暂停检查
                await a._wait_if_paused()

                try:
                    for attempt in range(3):
                        try:
                            if attempt > 0:
                                await asyncio.sleep(2.0 * attempt)
                            cot = await agent.act(ctx)
                            break
                        except Exception:
                            if attempt == 2:
                                raise
                            logger.info(f"  🐺 {w.name} 请求失败（attempt {attempt+1}/3），重试...")
                    pick = self._parse_pick(cot.secret_action, alive)

                    # 兜底：如果解析失败，随机选择存活玩家
                    if not pick:
                        candidates = [p.id for p in alive if p.is_alive and self.roles.get(p.id) != "狼人"]
                        if candidates:
                            pick = random.choice(candidates)
                            logger.info(f"  ⚠️ {w.name} 解析失败，随机选择: {pick}")
                            # 通知狼人：你的刀人格式不对，系统随机帮你选了一个
                            raw_wolf = cot.secret_action.strip()
                            self.memory.add_private(w.id,
                                f"⚠️ 你的刀人目标未被系统识别（你的回复：{raw_wolf[:80]}）。"
                                f"系统随机选了你今晚的目标：{ctx.round.players[pick].name}({pick})。"
                                f"下次请使用正确格式：刀-pX（如 刀-p3）。")

                    if pick:
                        wolf_votes[pick] += 1
                    target_name = ctx.round.players[pick].name if pick else "无"
                    logger.info(f"  🐺 {w.name}({w.id}): 刀 {pick}({target_name})")
                    await a.night_action("wolf_vote", w.id, w.name,
                                         f"刀 {pick}({target_name})" if pick else "未选择目标",
                                         target_id=pick or "", round_num=self.round_num)
                except Exception:
                    logger.info(f"  ✗ {w.name}({w.id}) 选目标失败（3次重试耗尽）")
                agent.action_only = False
                agent.quick_action_prompt = None

        if wolves:
            tasks = [_wolf_pick(w) for w in wolves]
            for i in range(len(tasks) - 1):
                await asyncio.sleep(0.3)  # 错开防 429
            await asyncio.gather(*tasks)

        wolf_target = None
        for pid, cnt in wolf_votes.items():
            if cnt >= 2:
                wolf_target = pid
                break
        if wolf_target:
            logger.info(f"  → 狼人选了 {ctx.round.players[wolf_target].name}")
        else:
            logger.info("  → 狼人未达成一致，无人被杀")

        # ── 预言家 ──
        seer = next((p for p in alive if self.roles.get(p.id) == "预言家"), None)
        seer_result = None
        if seer and seer.is_alive:
            agent = a.players.get(seer.id)
            if agent:
                agent.quick_action_prompt = f"[你是 {seer.id}] 选择查验目标。回复 验-pX（如 验-p5）"
                agent.action_only = True
                logger.info(f"▶ {seer.name}（{seer.id}）查验中...")

                # ⏸️ 暂停检查
                await a._wait_if_paused()

                try:
                    for attempt in range(3):
                        try:
                            if attempt > 0:
                                await asyncio.sleep(2.0 * attempt)
                            cot = await agent.act(ctx)
                            break
                        except Exception:
                            if attempt == 2:
                                raise
                            logger.info(f"  🔮 预言家请求失败（attempt {attempt+1}/3），重试...")
                    raw_seer = cot.secret_action.strip()
                    logger.info(f"  🔮 预言家 {seer.name}({seer.id}) raw=[{raw_seer[:120]}]")
                    target_id = self._parse_pick(raw_seer, alive)
                    if target_id:
                        is_wolf = self.roles.get(target_id) == "狼人"
                        label = "狼人（坏人）" if is_wolf else "好人"
                        tname = ctx.round.players[target_id].name
                        seer_result = f"🔮 查验结果：{tname}({target_id}) 是 {label}"
                        self.memory.add_private(seer.id, seer_result)
                        logger.info(f"✓ 预言家 {seer.name}({seer.id}): 查验 {target_id}({tname}) → {label}")
                        await a.night_action("seer_check", seer.id, seer.name,
                                             f"查验 {target_id}({tname}) → {label}",
                                             target_id=target_id, round_num=self.round_num)
                    else:
                        # 解析失败：通知预言家技能未生效，防止白天瞎编查验结果
                        fail_msg = (
                            f"⚠️ 你的查验未能被系统记录。你的回复格式不正确。\n"
                            f"你的回复：{raw_seer[:100]}\n"
                            f"正确格式：验-pX（如 验-p5）。请下次使用正确格式。"
                        )
                        self.memory.add_private(seer.id, fail_msg)
                        logger.info(f"⚠️ 预言家 {seer.name}({seer.id}) 解析失败: raw=[{raw_seer[:120]}]")
                except Exception:
                    logger.info(f"✗ 预言家 {seer.name}({seer.id}) 查验失败（3次重试耗尽）")
                agent.action_only = False
                agent.quick_action_prompt = None
                # 🔍 预言家上下文——检查查验结果是否收到
                if seer_result:
                    sx_ctx = self.memory.build_context_for_player(seer.id)
                    logger.info(f"━━━ 预言家 {seer.name}({seer.id}) 查验后上下文（应含🔮结果）━━━\n{sx_ctx[-600:]}")

        # ── 女巫 ──
        witch = next((p for p in alive if self.roles.get(p.id) == "女巫"), None)
        if witch and witch.is_alive and (wolf_target or self.witch_poison):
            antidote_str = "可用" if self.witch_antidote else "已用完"
            poison_str = "可用" if self.witch_poison else "已用完"
            agent = a.players.get(witch.id)
            if agent:
                if wolf_target:
                    victim_name = ctx.round.players[wolf_target].name
                    agent.quick_action_prompt = (
                        f"[你是 {witch.id}] 今晚 {victim_name}({wolf_target}) 被杀了。"
                        f"解药({antidote_str})可救活他，毒药({poison_str})可毒杀一人。"
                        f"回复：救 或 毒-pX 或 跳过"
                    )
                else:
                    agent.quick_action_prompt = (
                        f"[你是 {witch.id}] 今晚无人被杀。毒药({poison_str})可毒杀一人。"
                        f"回复：毒-pX 或 跳过"
                    )
                agent.action_only = True
                logger.info(f"▶ {witch.name}（{witch.id}）行动中...")

                # ⏸️ 暂停检查
                await a._wait_if_paused()

                try:
                    for attempt in range(3):
                        try:
                            if attempt > 0:
                                await asyncio.sleep(2.0 * attempt)
                            cot = await agent.act(ctx)
                            break
                        except Exception:
                            if attempt == 2:
                                raise
                            logger.info(f"  🧪 女巫请求失败（attempt {attempt+1}/3），重试...")
                    raw = cot.secret_action.strip()
                    logger.info(f"  🧪 女巫 {witch.name}({witch.id}): raw=[{raw[:60]}]")

                    # 改进的女巫行动解析：支持多种表达
                    use_antidote = any(kw in raw for kw in ["救", "解药", "救命", "救他", "救人", "用药救"])
                    use_poison = any(kw in raw for kw in ["毒", "毒药", "下毒", "用毒", "毒杀"])
                    skip_action = any(kw in raw for kw in ["跳过", "过", "不救", "不用", "跳", "不用药"])

                    if wolf_target and use_antidote and self.witch_antidote:
                        self.witch_antidote = False
                        vname = ctx.round.players[wolf_target].name
                        logger.info(f"  → 女巫使用解药，救活 {vname}({wolf_target})")
                        await a.night_action("witch_action", witch.id, witch.name,
                                             f"使用解药，救活 {vname}({wolf_target})",
                                             target_id=wolf_target, round_num=self.round_num)
                        # 持久化：通知女巫药水已用
                        self.memory.add_private(witch.id,
                            f"🧪 你今晚使用了【解药】，救活了 {vname}({wolf_target})。解药已用完。"
                            f"毒药状态：{'可用' if self.witch_poison else '已用完'}。")
                        wolf_target = None
                    elif use_poison and self.witch_poison and not skip_action:
                        poison_target = self._parse_pick(raw, alive)
                        if poison_target and poison_target != wolf_target:
                            self.witch_poison = False
                            pname = ctx.round.players[poison_target].name
                            logger.info(f"  → 女巫毒杀 {pname}({poison_target})")
                            await a.night_action("witch_action", witch.id, witch.name,
                                                 f"使用毒药，毒杀 {pname}({poison_target})",
                                                 target_id=poison_target, round_num=self.round_num)
                            # 持久化：通知女巫药水已用
                            self.memory.add_private(witch.id,
                                f"🧪 你今晚使用了【毒药】，毒杀了 {pname}({poison_target})。毒药已用完。"
                                f"解药状态：{'可用' if self.witch_antidote else '已用完'}。")
                            # 毒药致死
                            p = ctx.round.players[poison_target]
                            if p.is_alive:
                                role = self.roles.get(poison_target, "")
                                if role == "猎人":
                                    logger.info(f"🔫 猎人 {p.name} 被毒死，不能开枪")
                                self._night_deaths.append(poison_target)
                                a.eliminate(ctx, poison_target)
                        elif not poison_target:
                            # 想毒人但目标解析失败
                            self.memory.add_private(witch.id,
                                f"⚠️ 你试图使用毒药，但目标ID解析失败。你的回复：{raw[:100]}\n"
                                f"正确格式：毒-pX（如 毒-p7）。毒药未被消耗。")
                            logger.info(f"⚠️ 女巫毒人目标解析失败: raw=[{raw[:120]}]")
                    elif skip_action:
                        logger.info(f"  → 女巫选择跳过，不使用药水")
                        self.memory.add_private(witch.id,
                            f"🧪 你今晚选择跳过，不使用药水。"
                            f"解药：{'可用' if self.witch_antidote else '已用完'} | 毒药：{'可用' if self.witch_poison else '已用完'}。")
                    else:
                        # 回复模棱两可，技能未生效，必须告知防止幻觉
                        logger.info(f"  → 女巫未明确行动，跳过")
                        self.memory.add_private(witch.id,
                            f"⚠️ 你的回复未能被系统识别，今晚未执行任何药水操作。你的回复：{raw[:100]}\n"
                            f"正确格式：救（使用解药）、毒-pX（使用毒药）、跳过（不用药）。\n"
                            f"解药：{'可用' if self.witch_antidote else '已用完'} | 毒药：{'可用' if self.witch_poison else '已用完'}。")
                except Exception:
                    logger.info(f"✗ 女巫 {witch.name}({witch.id}) 行动失败（3次重试耗尽）")
                    self.memory.add_private(witch.id,
                        f"⚠️ 你的药水操作因网络错误未能执行。本晚你的药水未被消耗。"
                        f"解药：{'可用' if self.witch_antidote else '已用完'} | 毒药：{'可用' if self.witch_poison else '已用完'}。")
                agent.action_only = False
                agent.quick_action_prompt = None
                # 🔍 女巫上下文——检查是否收到死讯/毒药提示
                wx_ctx = self.memory.build_context_for_player(witch.id)
                logger.info(f"━━━ 女巫 {witch.name}({witch.id}) 夜晚上下文（应含{'死讯' if wolf_target else '无人被杀'}）━━━\n{wx_ctx[-800:]}")

        # 记录今晚死亡（用于天亮公告和 DM 摘要）
        self._night_deaths = []

        # ── 执行狼杀 ──
        if wolf_target:
            victim = ctx.round.players[wolf_target]
            if victim.is_alive:
                role = self.roles.get(wolf_target, "")
                logger.info(f"💀 狼人击杀 {victim.name}({wolf_target})")
                await a.night_action("wolf_kill", "", "狼人",
                                     f"击杀 {victim.name}({wolf_target})",
                                     target_id=wolf_target, round_num=self.round_num)
                self._night_deaths.append(wolf_target)
                if role == "猎人":
                    logger.info(f"🔫 猎人 {victim.name} 被刀死，可以开枪！")
                    ctx.round.public_log.append(f"🔫 {victim.name} 是猎人，被刀死，开枪带走一人！")
                    await self._hunter_shoot(ctx, alive, a, wolf_target)
                a.eliminate(ctx, wolf_target)

        # ── 天亮公告（不暴露身份，只报死亡/平安夜）──
        night_dead = [pid for pid in alive_before_night
                      if not ctx.round.players[pid].is_alive]
        if night_dead:
            names = "、".join(ctx.round.players[pid].name for pid in night_dead)
            self._dawn_msg = f"☀️ 天亮了。昨晚 {names} 死亡。"
        else:
            self._dawn_msg = "☀️ 天亮了。昨晚是平安夜，无人死亡。"

        # 构建给 DM 的结构化摘要
        dm_brief = self._build_dm_brief(ctx, "night")
        self.memory.add_public("dm", dm_brief)

        # ⏸️ 暂停检查：DM判词前
        await a._wait_if_paused()

        # DM 判词（只负责渲染气氛，不负责信息传递）
        verdict = await a.dm_judge(ctx, [])

        # 清空温记忆，防止泄露
        self.memory.update_warm_summary("")

        # DM 的 narrative 进前端展示，不进玩家上下文
        if verdict and verdict.global_narrative:
            ctx.round.public_log.append(f"🌙 {verdict.global_narrative}")

        # 记录死亡事件到冷记忆
        deaths = [p.name for p in ctx.round.players.values() if not p.is_alive]
        if deaths:
            dm_info = f"## 死亡名单\n" + "\n".join(f"- {n}" for n in deaths)
            self.memory.add_critical_event(CriticalEvent(
                round_number=self.round_num,
                event=dm_info,
                related_players=[],
            ))

        # ⏸️ 暂停检查：状态推送前
        await a._wait_if_paused()

        await a.emit_state(ctx)

    # ============================================================
    # 猎人开枪
    # ============================================================

    async def _hunter_shoot(self, ctx, alive, a, hunter_id, death_log: list | None = None):
        hunter = ctx.round.players[hunter_id]
        self.memory.add_private(hunter_id,
            f"🔫 你是猎人（{hunter_id}），你已被淘汰！你可以开枪带走一名玩家，也可以选择不开枪（压枪）。回复 枪-pX 或 压枪")
        agent = a.players.get(hunter_id)
        if agent:
            agent.quick_action_prompt = f"[你是 {hunter_id}] 你已被淘汰，身份是猎人。可以开枪带走一人，也可以压枪。回复 枪-pX 或 压枪"
            agent.action_only = True
            try:
                # 延迟 + 重试，防 429
                for attempt in range(3):
                    try:
                        if attempt > 0:
                            await asyncio.sleep(2.0 * attempt)  # 递增退避
                        cot = await agent.act(ctx)
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        logger.info(f"  🔫 猎人请求失败（attempt {attempt+1}/3），重试...")
                raw_hunter = cot.secret_action.strip()
                logger.info(f"  🔫 猎人 {hunter.name}({hunter_id}) raw=[{raw_hunter[:120]}]")
                # 区分"压枪"和格式错误
                if "压枪" in raw_hunter:
                    logger.info(f"  🔫 猎人 {hunter.name}({hunter_id}) 选择压枪，不开枪")
                    await a.night_action("hunter_shoot", hunter_id, hunter.name,
                                         "选择压枪，不开枪", round_num=self.round_num)
                    ctx.round.public_log.append(f"🔫 猎人 {hunter.name} 选择压枪，不开枪")
                else:
                    target = self._parse_pick(raw_hunter, alive)
                    if target and target != hunter_id:
                        victim = ctx.round.players[target]
                        if victim.is_alive:
                            logger.info(f"  🔫 猎人 {hunter.name}({hunter_id}) 开枪带走 {victim.name}({target})")
                            await a.night_action("hunter_shoot", hunter_id, hunter.name,
                                                 f"开枪带走 {victim.name}({target})",
                                                 target_id=target, round_num=self.round_num)
                            ctx.round.public_log.append(f"🔫 猎人 {hunter.name} 开枪带走了 {victim.name}！")
                            if death_log is not None:
                                death_log.append(target)
                            if hasattr(self, '_night_deaths'):
                                self._night_deaths.append(target)
                            a.eliminate(ctx, target)
                    else:
                        # 既不是压枪，也解析不出目标——格式错误，默认压枪
                        logger.info(f"  ⚠️ 猎人 {hunter.name}({hunter_id}) 格式错误，默认压枪: raw=[{raw_hunter[:120]}]")
                        await a.night_action("hunter_shoot", hunter_id, hunter.name,
                                             "格式错误，默认压枪", round_num=self.round_num)
                        ctx.round.public_log.append(f"🔫 猎人 {hunter.name} 开枪失败（格式错误），默认压枪")
                        self.memory.add_private(hunter_id,
                            f"⚠️ 你的开枪目标未能被系统识别（回复：{raw_hunter[:80]}）。已默认压枪。"
                            f"正确格式：枪-pX（如 枪-p2）或 压枪。")
            except Exception:
                logger.info(f"  🔫 猎人 {hunter.name}({hunter_id}) 开枪失败（3次重试耗尽），默认压枪")
                ctx.round.public_log.append(f"🔫 猎人 {hunter.name} 开枪失败，默认压枪")
                self.memory.add_private(hunter_id,
                    f"⚠️ 你的开枪操作因网络错误未能执行，已默认压枪。")
            agent.action_only = False
            agent.quick_action_prompt = None

    def _build_day_brief(self, ctx) -> str:
        """构建白天事件简报（夜晚开始前发给每个存活玩家）"""
        day_deaths = getattr(self, '_day_deaths', [])
        if not day_deaths:
            return "📋 白天简报：无人被投票淘汰。"
        names = "、".join(
            f"{ctx.round.players[pid].name}({pid})" for pid in day_deaths if pid in ctx.round.players
        )
        return f"📋 白天简报：今天白天 {names} 被投票淘汰，已死亡。"

    # ============================================================
    # 遗言
    # ============================================================

    async def _last_words(self, ctx, player):
        """遗言：被投票出局时的最后陈述"""
        self.memory.add_private(player.id,
            f"📜 你（{player.id}）已被投票淘汰。请留下遗言——可以指控、揭露、虚张声势、或沉默。用ID指代玩家，如'我怀疑p3是狼'、'p5是预言家'。")
        agent = self.arena.players.get(player.id)
        if agent:
            agent.quick_action_prompt = f"[你是 {player.id}] 你被投票淘汰了。请留下遗言（指控、揭露、沉默均可）。用ID指代玩家。回复一段话"
            agent.action_only = True

            speech = None
            try:
                # 遗言加重试机制，防止 API 失败丢失
                for attempt in range(3):
                    try:
                        if attempt > 0:
                            await asyncio.sleep(2.0 * attempt)
                        cot = await agent.act(ctx)
                        if cot.secret_action.strip():
                            speech = cot.secret_action.strip()
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        logger.info(f"  📜 遗言请求失败（attempt {attempt+1}/3），重试...")
            except Exception:
                logger.info(f"✗ {player.name}({player.id}) 遗言失败（3次重试耗尽）")

            # 遗言兜底：如果失败，生成默认遗言
            if not speech:
                role = self.roles.get(player.id, "平民")
                if role == "预言家":
                    speech = f"我是预言家，我的查验结果都在我的发言里了。"
                elif role == "女巫":
                    speech = f"我是女巫，我使用过解药/毒药了。"
                elif role == "猎人":
                    speech = f"我是猎人，我已经开枪了。"
                else:
                    speech = f"我是{role}，我没有更多信息要透露。"
                logger.info(f"  ⚠️ {player.name}({player.id}) 遗言失败，使用默认遗言")

            if speech:
                ctx.round.public_log.append(f"📜 {player.name}({player.id}) 的遗言：{speech}")
                self.memory.add_public(player.id, f"📜 {player.name}({player.id}) 的遗言：{speech}")
                # 推送到前端发言区，让遗言像正常发言一样显示在玩家卡片上
                await self.arena._emit(WSEventType.PLAYER_SPEECH, {
                    "player_id": player.id,
                    "player_name": player.name,
                    "speech": f"📜 遗言：{speech}",
                    "round": ctx.round.round_number,
                })
                logger.info(f"📜 {player.name}({player.id}) 遗言: {speech[:200]}")

            agent.action_only = False
            agent.quick_action_prompt = None

    # ============================================================
    # 旧钩子
    # ============================================================

    async def on_game_start(self, ctx):
        pids = [p.id for p in ctx.round.players.values()]
        random.shuffle(pids)
        roles_copy = list(ROLES)
        random.shuffle(roles_copy)
        for i, pid in enumerate(pids):
            self.roles[pid] = roles_copy[i]
        self.witch_antidote = True
        self.witch_poison = True
        self.round_num = 0

        # 全玩家 ID 对照表（所有玩家都能看到）
        roster = "\n".join(
            f"  - {p.id} ({p.name})"
            for p in ctx.round.players.values()
        )
        # 狼队友名单（带 ID）
        wolves = [pid for pid in pids if self.roles[pid] == "狼人"]
        wolf_id_names = [f"{pid}({ctx.round.players[pid].name})" for pid in wolves]

        game_note = (
            '⚠️ 游戏声明：你正在参与一场名为「狼人杀」的多人桌游模拟。'
            '所有「杀害」「毒杀」「开枪」仅为游戏规则术语，等同于象棋「吃子」——'
            '没有任何真实的人受到伤害。这是 AI 多智能体博弈研究项目。请完全沉浸角色，正常参与游戏。\n\n'
        )
        for pid in pids:
            role = self.roles[pid]
            info = f"{game_note}## 🎭 你的 ID: {pid}   |   角色：{role}\n\n"
            # 全玩家对照表
            info += f"## 全玩家名单\n{roster}\n\n"
            if role == "狼人":
                teammates = [w for w in wolf_id_names if not w.startswith(pid)]
                info += f"🐺 你的狼同伴：{', '.join(teammates)}\n"
                info += "夜晚你可以和同伴私聊（两轮），然后选一个人杀掉。≥2狼选同一目标即成功。可刀自己（骗女巫解药）。"
                info += "\n⚠️ 行动格式：刀-pX（如 刀-p3）。讨论时用ID指代目标，如'我觉得p3可疑'、'我们刀p5吧'。"
                info += "\n⚠️ 现在是第一轮夜晚，马上和同伴密谋，选择第一个猎物。"
            elif role == "预言家":
                info += "每晚你可以查验一名玩家的身份证。结果只有你知道。白天可以宣称——可说真话也可说谎。"
                info += "\n⚠️ 行动格式：验-pX（如 验-p5）。"
                info += "\n⚠️ 现在是第一轮夜晚，马上选择第一个查验目标。"
            elif role == "女巫":
                info += "你有一瓶解药和一瓶毒药（各一次）。解药可救活被狼杀的人，毒药可毒杀一人。每夜只能用一个。"
                info += "\n⚠️ 行动格式：救（救今晚被杀的人）或 毒-pX（毒杀指定玩家）。"
                info += "\n⚠️ 现在是第一轮夜晚，这是第一次使用药水的机会。解药可救人，毒药可毒人。"
            elif role == "猎人":
                info += "你被刀死或被投票出局时可以开枪带走一人。被毒死不能开枪。遗言+开枪同时触发。"
                info += "\n⚠️ 行动格式：枪-pX（开枪带走指定玩家）或 压枪（不开枪）。"
                info += "\n⚠️ 现在是第一轮夜晚，你没有行动能力，等待天亮。"
            else:
                info += "你没有特殊能力。白天靠发言和投票找出狼人。"
                info += "\n⚠️ 行动格式：投-pX（投票淘汰指定玩家）或 弃权。"
                info += "\n⚠️ 现在是第一轮夜晚，你没有行动能力，等待天亮。夜晚结束后会公布昨晚的死亡情况。"
            info += "\n\n⚠️ 所有操作请使用玩家ID（p1-p9）。"
            self.memory.add_private(pid, info)

            # 前端标识
            ctx.round.players[pid].fraud_tag = role if role != "平民" else ""
            ctx.round.players[pid].color_tag = "🐺" if role == "狼人" else ("🔮" if role == "预言家" else ("🧪" if role == "女巫" else ("🔫" if role == "猎人" else "")))

        logger.info(f"狼人: {', '.join(wolf_id_names)}")
        return ctx

    async def check_win_condition(self, ctx):
        alive = [p for p in ctx.round.players.values() if p.is_alive]
        wolves_alive = [p for p in alive if self.roles.get(p.id) == "狼人"]
        villagers_alive = [p for p in alive if self.roles.get(p.id) != "狼人"]

        if not wolves_alive:
            logger.info("🏆 所有狼人死亡——神职+村民获胜！")
            return ",".join(p.id for p in villagers_alive)
        if len(wolves_alive) >= len(alive) / 2:
            logger.info("🏆 狼人数量过半——狼人获胜！")
            return ",".join(p.id for p in wolves_alive)
        return None

    async def _check_win(self, alive) -> bool:
        wolves = [p for p in alive if self.roles.get(p.id) == "狼人"]
        if not wolves:
            logger.info("🏆 所有狼人死亡——神职+村民获胜！")
            return True
        if len(wolves) >= len(alive) / 2:
            logger.info("🏆 狼人数量过半——狼人获胜！")
            return True
        return False

    # ============================================================
    # 工具函数
    # ============================================================

    def _parse_pick(self, text: str, alive: list) -> Optional[str]:
        """从任意文本提取 p1-p9。失败返回 None。"""
        t = text.strip()
        if not t:
            return None

        # 正则匹配 p1-p9
        m = re.findall(r'[pP](\d)', t)
        if m:
            pid = f"p{m[0]}"
            if any(p.id == pid and p.is_alive for p in alive):
                return pid

        # 中文数字匹配：p三→p3
        cn = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
              "六": "6", "七": "7", "八": "8", "九": "9"}
        for k, v in cn.items():
            if f"p{k}" in t or f"P{k}" in t:
                pid = f"p{v}"
                if any(p.id == pid and p.is_alive for p in alive):
                    return pid

        # 扩展中文数字：三号、第三个、三号玩家
        cn_words = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
                    "六": "6", "七": "7", "八": "8", "九": "9",
                    "一号": "1", "二号": "2", "三号": "3", "四号": "4", "五号": "5",
                    "六号": "6", "七号": "7", "八号": "8", "九号": "9"}
        for word, num in cn_words.items():
            if word in t:
                pid = f"p{num}"
                if any(p.id == pid and p.is_alive for p in alive):
                    return pid

        return None

    def _log_vote_tally(self, ctx, votes: dict[str, str], tally: dict[str, int], round_num: int):
        """格式化打印投票票型"""
        lines = [f"🗳️ 第{round_num}轮白天投票票型（{len(votes)}人投票）："]
        for pid, choice in votes.items():
            p = ctx.round.players.get(pid)
            name = p.name if p else pid
            if choice == "弃权":
                lines.append(f"  {name}({pid}) → 弃权")
            else:
                target = ctx.round.players.get(choice)
                tname = target.name if target else choice
                lines.append(f"  {name}({pid}) → {choice} ({tname})")
        if tally:
            lines.append(f"  ——")
            for pid, cnt in sorted(tally.items(), key=lambda x: -x[1]):
                p = ctx.round.players.get(pid)
                lines.append(f"  {p.name if p else pid}({pid}): {cnt} 票")
        logger.info("\n".join(lines))

    def _build_dm_brief(self, ctx, phase: str) -> str:
        """构建给 DM 的结构化事件摘要"""
        events = []

        if phase == "day":
            events.append(f"第{self.round_num}轮 白天")

            # 投票结果
            if hasattr(self, '_vote_result') and self._vote_result:
                target = self._vote_result.get('target')
                if target:
                    target_name = ctx.round.players[target].name if target in ctx.round.players else target
                    events.append(f"投票结果：{target_name}({target}) 被淘汰")
                else:
                    events.append("投票结果：无人淘汰")
            else:
                events.append("投票结果：无人淘汰")

            # 遗言（如果有）
            if hasattr(self, '_last_words_cache') and self._last_words_cache:
                events.append(f"遗言已留")

        elif phase == "night":
            events.append(f"第{self.round_num}轮 夜晚")

            # 死亡结果
            night_deaths = getattr(self, '_night_deaths', [])
            if night_deaths:
                names = "、".join(ctx.round.players[pid].name for pid in night_deaths if pid in ctx.round.players)
                events.append(f"死亡：{names}")
            else:
                events.append("死亡：平安夜")

        return "📋 " + " | ".join(events)
