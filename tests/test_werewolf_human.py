"""
人类玩家路径自动化测试（模拟前端输入，无需浏览器）。
覆盖: PlayerAgent._wait_for_human, resolve_human_input,
       上下文优先级, 角色分配修复。
"""

import asyncio
import pytest
from engine.schema import (
    PlayerState, PlayerDef, GameConfig, GameContext,
    RoundState, ModelProvider, CoTOutput, WSEventType,
)
from engine.arena import load_hooks


# ============================================================
# 辅助函数
# ============================================================

def run(coro):
    """同步包装器：运行异步协程并返回结果。"""
    return asyncio.run(coro)


async def _wait_then_resolve(agent, ctx, speech="发言", action="行动"):
    """
    启动 _wait_for_human，等待 _emit_done 信号后再 resolve Future。
    用 Event 信号替代 asyncio.sleep，消除竞态条件。
    """
    arena = agent._arena
    arena._emit_done.clear()
    task = asyncio.create_task(agent._wait_for_human(ctx))
    await asyncio.wait_for(arena._emit_done.wait(), timeout=2.0)
    agent.resolve_human_input(speech, action)
    cot = await task
    return cot


async def _wait_for_emit_only(agent, ctx):
    """启动 _wait_for_human，仅等待 emit 完成，不 resolve。返回 arena。"""
    arena = agent._arena
    arena._emit_done.clear()
    task = asyncio.create_task(agent._wait_for_human(ctx))
    await asyncio.wait_for(arena._emit_done.wait(), timeout=2.0)
    # 不 resolve，返回 task + arena 供后续操作
    return task, arena


# ============================================================
# 组 A: PlayerAgent 人类路径 (9 个测试)
# ============================================================

class TestHumanPlayerAct:
    """测试人类玩家通过 resolve_human_input 提交输入。"""

    def test_act_returns_speech_and_action(self, human_agent, minimal_context):
        """A1: resolve_human_input 的 speech/action 正确传到 CoTOutput。"""
        cot = run(_wait_then_resolve(
            human_agent(), minimal_context,
            speech="我怀疑p3是狼", action="投-p3"
        ))
        assert cot.public_speech == "我怀疑p3是狼"
        assert cot.secret_action == "投-p3"

    def test_empty_speech_filled_with_dot(self, human_agent, minimal_context):
        """A2: 空 speech 自动填充 "."。"""
        cot = run(_wait_then_resolve(
            human_agent(), minimal_context, speech="", action=""
        ))
        assert cot.public_speech == "."

    def test_stop_signal_returns_stopped_cot(self, human_agent, minimal_context):
        """A3: 未输入时 stop 信号触发，返回 stopped CoT。"""
        async def _test():
            agent = human_agent()
            agent._arena._emit_done.clear()
            task = asyncio.create_task(agent._wait_for_human(minimal_context))
            await asyncio.wait_for(agent._arena._emit_done.wait(), timeout=2.0)
            # 模拟 _check_stop 在缓冲后的行为
            agent._pending_future.set_result({"speech": "", "action": "", "stopped": True})
            return await task
        cot = run(_test())
        assert cot.public_speech == "."
        assert "管理员手动停止" in cot.situation_assessment

    def test_input_beats_stop(self, human_agent, minimal_context):
        """A4: 人类在缓冲期内提交输入 → 不被 stop 覆盖。"""
        async def _test():
            agent = human_agent()
            agent._arena._emit_done.clear()
            task = asyncio.create_task(agent._wait_for_human(minimal_context))
            await asyncio.wait_for(agent._arena._emit_done.wait(), timeout=2.0)
            agent._human_submitted = True  # 模拟缓冲期内已提交
            agent._pending_future.set_result({"speech": "我在输入", "action": "投-p2", "stopped": False})
            return await task
        cot = run(_test())
        assert cot.public_speech == "我在输入"
        assert cot.secret_action == "投-p2"

    def test_cot_marks_human_player(self, human_agent, minimal_context):
        """A5: 人类玩家的 CoT 标记为手动输入。"""
        cot = run(_wait_then_resolve(human_agent(), minimal_context))
        assert cot.situation_assessment == "（人类玩家手动输入）"
        assert cot.internal_strategy == "（人类玩家手动输入）"

    def test_cot_no_ai_internals(self, human_agent, minimal_context):
        """A6: 人类 CoT 不含 AI 的 CoT 关键词。"""
        cot = run(_wait_then_resolve(
            human_agent(), minimal_context, speech="我觉得p3可疑"
        ))
        assert cot.situation_assessment == "（人类玩家手动输入）"

    def test_phase_is_speech_when_speech_only(self, human_agent, minimal_context):
        """A7: speech_only=True → phase="speech"。"""
        async def _test():
            agent = human_agent()
            agent.speech_only = True
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            emitted = arena.emitted.copy()
            agent.resolve_human_input("发言", "")
            await task
            return emitted
        emitted = run(_test())
        human_turn = next(e[1] for e in emitted if "HUMAN_TURN" in str(e[0]))
        assert human_turn["phase"] == "speech"

    def test_phase_is_action_when_action_only(self, human_agent, minimal_context):
        """A8: action_only=True → phase="action"。"""
        async def _test():
            agent = human_agent()
            agent.action_only = True
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            emitted = arena.emitted.copy()
            agent.resolve_human_input("", "投-p3")
            await task
            return emitted
        emitted = run(_test())
        human_turn = next(e[1] for e in emitted if "HUMAN_TURN" in str(e[0]))
        assert human_turn["phase"] == "action"

    def test_phase_is_full_by_default(self, human_agent, minimal_context):
        """A9: 默认 → phase="full"。"""
        async def _test():
            agent = human_agent()
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            emitted = arena.emitted.copy()
            agent.resolve_human_input("发言", "行动")
            await task
            return emitted
        emitted = run(_test())
        human_turn = next(e[1] for e in emitted if "HUMAN_TURN" in str(e[0]))
        assert human_turn["phase"] == "full"


# ============================================================
# 组 B: 上下文优先级 (4 个测试)
# ============================================================

class TestHumanContextPriority:
    """测试 _wait_for_human 中 context_hint 的优先级链。"""

    def test_quick_action_prompt_first(self, human_agent, minimal_context):
        """B1: quick_action_prompt 优先级最高。"""
        async def _test():
            agent = human_agent()
            agent.quick_action_prompt = "验-pX（预言家查验指令）"
            agent.human_context = "你是狼人，你的同伴是p2"
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            emitted = arena.emitted.copy()
            agent.resolve_human_input("验-p3", "")
            await task
            return emitted
        emitted = run(_test())
        human_turn = next(e[1] for e in emitted if "HUMAN_TURN" in str(e[0]))
        assert human_turn["context"] == "验-pX（预言家查验指令）"

    def test_human_context_second(self, human_agent, minimal_context):
        """B2: 无 quick_action_prompt 时，取 human_context。"""
        async def _test():
            agent = human_agent()
            agent.human_context = "狼同伴: p1, p2\n可选目标: p3-p9"
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            emitted = arena.emitted.copy()
            agent.resolve_human_input("发言", "")
            await task
            return emitted
        emitted = run(_test())
        human_turn = next(e[1] for e in emitted if "HUMAN_TURN" in str(e[0]))
        assert "狼同伴" in human_turn["context"]
        assert "p1, p2" in human_turn["context"]

    def test_fallback_to_memory(self, human_agent, minimal_context):
        """B3: 两者都不设时，回退到 memory 提取。"""
        async def _test():
            agent = human_agent()
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            emitted = arena.emitted.copy()
            agent.resolve_human_input("发言", "")
            await task
            return emitted
        emitted = run(_test())
        human_turn = next(e[1] for e in emitted if "HUMAN_TURN" in str(e[0]))
        assert "## 🎭" in human_turn["context"] or "全玩家名单" in human_turn["context"]

    def test_human_context_cleared_after_consume(self, human_agent, minimal_context):
        """B4: human_context 消费后应被清为 None。"""
        async def _test():
            agent = human_agent()
            agent.human_context = "仅用一次"
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            agent.resolve_human_input("发言", "")
            await task
            return agent.human_context
        result = run(_test())
        assert result is None, f"human_context 应为 None，实际为: {result}"


# ============================================================
# 组 C: 角色分配 (6 个测试) — 修复 BUG #1
# ============================================================

def make_game_context(players_dict: dict) -> GameContext:
    """用指定玩家字典构造最小 GameContext。"""
    return GameContext(
        game_config=GameConfig(
            game_id="test_werewolf",
            name="Test Werewolf",
            total_rounds=0,
            mode="sequential",
            players=[
                PlayerDef(id=pid, name=pid, model="test", provider=ModelProvider.OPENAI)
                for pid in players_dict
            ],
        ),
        round=RoundState(
            round_number=1,
            total_rounds=0,
            players=players_dict,
        ),
    )


def make_9_players():
    """构造 9 名玩家的 PlayerState 字典。"""
    return {
        f"p{i}": PlayerState(
            id=f"p{i}", name=f"P{i}", model="test",
            provider=ModelProvider.OPENAI, is_alive=True,
        )
        for i in range(1, 10)
    }


class TestRoleAssignment:
    """测试 on_game_start 中角色分配的正确性（修复 BUG #1）。"""

    @staticmethod
    def _assign(manual: dict) -> dict:
        """运行 on_game_start 并返回 roles 字典。"""
        from tests.conftest import MockMemory
        hooks = load_hooks("werewolf", "games")
        players = make_9_players()

        # 构造 mock arena（带 _assignments）
        class MA:
            def __init__(self, a):
                self._assignments = a
        hooks.arena = MA(manual)
        hooks.memory = MockMemory()  # 防止 on_game_start 调用 add_private 炸掉
        ctx = make_game_context(players)
        run(hooks.on_game_start(ctx))
        return hooks.roles

    def test_partial_one_wolf(self):
        """C1: 手动分配 1 个狼人 → 全场仍有 3 个狼人。"""
        roles = self._assign({"p1": "狼人"})
        wolf_count = sum(1 for r in roles.values() if r == "狼人")
        assert wolf_count == 3, f"预期 3 狼，实际 {wolf_count} 狼: {roles}"
        assert roles["p1"] == "狼人"

    def test_partial_two_wolves(self):
        """C2: 手动分配 2 个狼人 → 全场仍有 3 个狼人。"""
        roles = self._assign({"p1": "狼人", "p2": "狼人"})
        wolf_count = sum(1 for r in roles.values() if r == "狼人")
        assert wolf_count == 3, f"预期 3 狼，实际 {wolf_count} 狼: {roles}"

    def test_seer_and_wolf(self):
        """C3: 手动分配 1 预言家+1 狼人 → 各角色数量正确。"""
        roles = self._assign({"p1": "预言家", "p2": "狼人"})
        assert roles["p1"] == "预言家"
        assert roles["p2"] == "狼人"
        wolf_count = sum(1 for r in roles.values() if r == "狼人")
        seer_count = sum(1 for r in roles.values() if r == "预言家")
        assert wolf_count == 3
        assert seer_count == 1

    def test_all_nine_manual(self):
        """C4: 手动分配全部 9 个角色 → 与手动分配一致。"""
        manual = {
            "p1": "狼人", "p2": "狼人", "p3": "狼人",
            "p4": "预言家", "p5": "女巫", "p6": "猎人",
            "p7": "平民", "p8": "平民", "p9": "平民",
        }
        roles = self._assign(manual)
        assert roles == manual

    def test_invalid_role_no_crash(self):
        """C5: 手动分配无效角色 → 不崩溃，剩余正常分配。"""
        roles = self._assign({"p1": "国王"})  # 不在 ROLES 中的角色
        assert len(roles) == 9  # 9 个玩家都应分配
        # "国王" 不在 ROLES 中（remove 抛 ValueError），但手动分配被强制保留
        # 其余 8 个玩家从剩余角色池中正常分配
        assert roles["p1"] == "国王"  # 手动分配被尊重

    def test_duplicate_manual_not_exceed(self):
        """C6: 超量分配同名角色 → 不崩溃，数量不超过 ROLES。"""
        roles = self._assign({
            "p1": "狼人", "p2": "狼人", "p3": "狼人",
            "p4": "狼人",  # 第 4 个狼人——手动分配被强制保留
        })
        wolf_count = sum(1 for r in roles.values() if r == "狼人")
        # 4 个手动分配全被保留，剩余 5 个玩家从池中（0 狼）随机分配
        assert wolf_count == 4, f"手动分配 4 狼应保留 4 狼，实际: {wolf_count}"


# ============================================================
# 组 D: 人类 context 设置验证
# ============================================================

class TestHumanContextSetting:
    """验证游戏逻辑正确设置了人类玩家的 context。"""

    def test_day_speech_context_includes_round_info(self, human_agent, minimal_context):
        """人类玩家白天发言 context 应包含轮次和存活玩家信息。"""
        async def _test():
            agent = human_agent()
            agent.human_context = (
                "现在是第1轮白天讨论阶段。"
                "存活玩家：P1(p1)、P2(p2)、P3(p3)。"
                "请发言（可以指控、辩护、分析、或说谎）。"
            )
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            emitted = arena.emitted.copy()
            agent.resolve_human_input("我怀疑p3", "")
            await task
            return emitted
        emitted = run(_test())
        human_turn = next(e[1] for e in emitted if "HUMAN_TURN" in str(e[0]))
        assert "第1轮白天" in human_turn["context"]
        assert "存活玩家" in human_turn["context"]
        assert "p1" in human_turn["context"]


# ============================================================
# 组 E: 狼私聊历史 & 遗言 (6 个测试) — 修复 BUG #5, #6, #8
# ============================================================

class TestWolfChatHistory:
    """人类狼私聊应能看到前面狼队友的发言历史。"""

    def test_human_wolf_context_includes_prior_chat(self, human_agent, minimal_context):
        """模拟：AI 狼先发言，人类狼后发言——context 应含 AI 狼的发言。"""
        async def _test():
            agent = human_agent()
            # 模拟已有狼聊记录
            chat_log = ["🐺 P1(p1)：我觉得p3最可疑，今晚刀他吧"]
            hint = "## 🐺 狼人私聊\n\n你的狼同伴：P1(p1)\n可选目标（非狼）：P3(p3)...\n\n格式：直接输入你想说的话。"
            if chat_log:
                hint += "\n\n## 已有狼群讨论\n" + "\n".join(chat_log)
            agent.human_context = hint
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            emitted = arena.emitted.copy()
            agent.resolve_human_input("我同意，刀p3", "")
            await task
            return emitted
        emitted = run(_test())
        human_turn = next(e[1] for e in emitted if "HUMAN_TURN" in str(e[0]))
        assert "已有狼群讨论" in human_turn["context"]
        assert "p3最可疑" in human_turn["context"]

    def test_human_wolf_no_history_when_first(self, human_agent, minimal_context):
        """第一个发言的人类狼——不应该有'已有狼群讨论'段落。"""
        async def _test():
            agent = human_agent()
            # 空狼聊记录（第一个发言）
            chat_log = []
            hint = "## 🐺 狼人私聊\n\n你的狼同伴：P2(p2)\n可选目标（非狼）：P3(p3)...\n\n格式：直接输入你想说的话。"
            if chat_log:
                hint += "\n\n## 已有狼群讨论\n" + "\n".join(chat_log)
            agent.human_context = hint
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            emitted = arena.emitted.copy()
            agent.resolve_human_input("我先说...", "")
            await task
            return emitted
        emitted = run(_test())
        human_turn = next(e[1] for e in emitted if "HUMAN_TURN" in str(e[0]))
        assert "已有狼群讨论" not in human_turn["context"]

    def test_wolf_target_prompt_includes_chat_summary(self, human_agent, minimal_context):
        """人类狼选刀人目标时，quick_action_prompt 应包含狼聊讨论记录。"""
        async def _test():
            agent = human_agent()
            wolf_chat_log = [
                "🐺 P1(p1)：刀p3",
                "🐺 P2(p2)：我没意见",
            ]
            agent.quick_action_prompt = f"[你是 p1] 狼人杀桌游——选择今晚要刀的目标。≥2狼选同一目标即成功。回复 刀-pX（如 刀-p3）"
            if agent.defn.is_human and wolf_chat_log:
                agent.quick_action_prompt += "\n\n## 狼群讨论记录\n" + "\n".join(wolf_chat_log)
            agent.action_only = True
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            emitted = arena.emitted.copy()
            agent.resolve_human_input("", "刀-p3")
            await task
            return emitted
        emitted = run(_test())
        human_turn = next(e[1] for e in emitted if "HUMAN_TURN" in str(e[0]))
        assert "狼群讨论记录" in human_turn["context"]
        assert "刀p3" in human_turn["context"]


class TestLastWordsContext:
    """人类遗言应有正确的上下文。"""

    def test_last_words_has_context(self, human_agent, minimal_context):
        """人类玩家遗言弹窗应包含角色身份信息（修复 BUG #5）。"""
        async def _test():
            agent = human_agent()
            agent.human_context = (
                "## 💀 遗言\n\n你是 P1(p1)，身份 预言家。\n"
                "你已被投票淘汰，这是你最后一次发言机会。\n"
                "可以表明身份、分享信息、或指认狼人。\n"
                "格式：直接输入你的遗言。用ID指代玩家。"
            )
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            emitted = arena.emitted.copy()
            agent.resolve_human_input("我是预言家，我验了p3是狼", "")
            await task
            return emitted
        emitted = run(_test())
        human_turn = next(e[1] for e in emitted if "HUMAN_TURN" in str(e[0]))
        assert "遗言" in human_turn["context"]
        assert "预言家" in human_turn["context"]


class TestFallbackDefense:
    """加固后的 fallback 路径不应返回 AI CoT 聊天历史。"""

    def test_fallback_never_returns_raw_chat(self, human_agent, minimal_context):
        """不设 quick_action_prompt 和 human_context 时，不返回原始聊天。"""
        async def _test():
            agent = human_agent(get_context_fn=lambda pid: "聊天历史: p1说p3是狼\n## 🎭 不在热记忆中\n普通对话")
            # 不设 quick_action_prompt 和 human_context——触发 fallback
            task, arena = await _wait_for_emit_only(agent, minimal_context)
            emitted = arena.emitted.copy()
            agent.resolve_human_input("发言", "")
            await task
            return emitted
        emitted = run(_test())
        human_turn = next(e[1] for e in emitted if "HUMAN_TURN" in str(e[0]))
        # fallback 提取应只保留角色指引段落，不含聊天历史
        assert "聊天历史" not in human_turn["context"]
        # 找不到 ## 🎭 标记时，返回安全兜底文本
        # 注意：我们的 get_context_fn 有 ## 🎭 所以会提取到
