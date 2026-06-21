"""
记忆系统测试
"""
import pytest
from engine.memory import MemoryManager
from engine.schema import CriticalEvent


class TestMemoryManager:
    def test_register_player(self):
        mm = MemoryManager()
        mm.register_player("p1")
        ctx = mm.build_context_for_player("p1")
        assert ctx == ""  # No messages yet

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
