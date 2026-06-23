"""
记忆系统测试（增强版）
"""
import pytest
from engine.memory import MemoryManager
from engine.schema import CriticalEvent


class TestMemoryManager:
    # ── 基础功能（保留）──────────────────────────────────────

    def test_register_player(self):
        mm = MemoryManager()
        mm.register_player("p1")
        ctx = mm.build_context_for_player("p1")
        assert ctx == ""

    def test_add_public_message(self):
        mm = MemoryManager(global_hot_window=3, player_hot_window=5)
        mm.register_player("p1")
        mm.register_player("p2")
        mm.set_round(1)
        mm.add_public("p1", "Hello everyone")
        ctx = mm.build_context_for_player("p2")
        assert "Hello everyone" in ctx

    def test_add_private_message(self):
        mm = MemoryManager()
        mm.register_player("p1")
        mm.register_player("p2")
        mm.set_round(1)
        mm.add_private("p2", "Secret: You are the traitor")
        ctx_p2 = mm.build_context_for_player("p2")
        assert "Secret" in ctx_p2

    def test_update_warm_summary(self):
        mm = MemoryManager()
        mm.register_player("p1")
        mm.update_warm_summary("Round 1: Intense negotiation")
        ctx = mm.build_context_for_player("p1")
        assert "Round 1: Intense negotiation" in ctx

    def test_critical_events(self):
        mm = MemoryManager()
        mm.register_player("p1")
        mm.set_round(2)
        event = CriticalEvent(
            round_number=2,
            event="P1 stole data from P2",
            related_players=["p1"],
        )
        mm.add_critical_event(event)
        events = mm.get_critical_events()
        assert len(events) == 1
        assert "P1 stole data" in events[0].content

    def test_build_context_for_dm(self):
        mm = MemoryManager()
        mm.set_round(1)
        mm.add_public("p1", "I propose an alliance")
        mm.add_public("p2", "I agree")
        mm.update_warm_summary("Peaceful round")
        ctx = mm.build_context_for_dm()
        assert "I propose" in ctx
        assert "Peaceful round" in ctx

    def test_notebook(self):
        mm = MemoryManager()
        mm.register_player("p1")
        mm.set_round(1)
        mm.add_private("p1", "DM私密消息: You found a clue")
        nb = mm.get_player_notebook("p1")
        assert len(nb) >= 1

    def test_unknown_player(self):
        mm = MemoryManager()
        ctx = mm.build_context_for_player("unknown")
        assert ctx == ""
        nb = mm.get_player_notebook("unknown")
        assert nb == []

    def test_reset(self):
        mm = MemoryManager()
        mm.register_player("p1")
        mm.set_round(1)
        mm.add_public("p1", "test")
        mm.reset()
        ctx = mm.build_context_for_player("p1")
        assert ctx == ""

    # ── 新增：上下文隔离 ─────────────────────────────────────

    def test_private_messages_isolated(self):
        """p2 的私密消息对 p1 不可见"""
        mm = MemoryManager()
        mm.register_player("p1")
        mm.register_player("p2")
        mm.set_round(1)
        mm.add_private("p2", "TOP SECRET: p2 is the mole")
        ctx_p1 = mm.build_context_for_player("p1")
        assert "TOP SECRET" not in ctx_p1

    def test_private_messages_visible_to_owner(self):
        """私密消息对本人可见"""
        mm = MemoryManager()
        mm.register_player("p1")
        mm.set_round(1)
        mm.add_private("p1", "Your secret mission")
        ctx = mm.build_context_for_player("p1")
        assert "secret mission" in ctx

    def test_public_messages_visible_to_all(self):
        """公开消息对所有玩家可见"""
        mm = MemoryManager()
        mm.register_player("p1")
        mm.register_player("p2")
        mm.register_player("p3")
        mm.set_round(1)
        mm.add_public("p1", "Hello everyone!")
        for pid in ["p1", "p2", "p3"]:
            ctx = mm.build_context_for_player(pid)
            assert "Hello everyone!" in ctx

    # ── 新增：多轮消息 ───────────────────────────────────────

    def test_multiple_rounds_indexed(self):
        """多轮消息不互相覆盖"""
        mm = MemoryManager()
        mm.register_player("p1")
        mm.set_round(1)
        mm.add_public("p1", "Round 1 speech")
        mm.set_round(2)
        mm.add_public("p2", "Round 2 speech")
        ctx = mm.build_context_for_player("p1")
        assert "Round 1 speech" in ctx
        assert "Round 2 speech" in ctx

    # ── 新增：空记忆边界 ─────────────────────────────────────

    def test_empty_context_for_new_player(self):
        """未注册的玩家上下文为空"""
        mm = MemoryManager()
        assert mm.build_context_for_player("ghost") == ""

    def test_notebook_starts_empty(self):
        """新玩家 notebook 为空"""
        mm = MemoryManager()
        mm.register_player("p1")
        nb = mm.get_player_notebook("p1")
        assert nb == []
