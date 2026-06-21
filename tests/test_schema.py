"""
Schema 模块测试
"""
import pytest
from engine.schema import (
    ModelProvider, ModelMessage, ModelResponse,
    CoTOutput, DMVerdict, ResourceDelta, PrivateMessage, CriticalEvent,
    PlayerDef, ResourceDef, PlayerState, RoundState, GameConfig, GameContext,
    WSEvent, WSEventType, ArenaResult, MemoryEntry, TieredMemory,
)


class TestModelEnums:
    def test_providers(self):
        assert ModelProvider.OPENAI == "openai"
        assert ModelProvider.ANTHROPIC == "anthropic"
        assert ModelProvider.GEMINI == "gemini"
        assert ModelProvider.DEEPSEEK == "deepseek"
        assert ModelProvider.DOUBAO == "doubao"
        assert ModelProvider.MINIMAX == "minimax"
        assert ModelProvider.ZHIPU == "zhipu"


class TestModelMessages:
    def test_basic_message(self):
        msg = ModelMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_empty_content(self):
        msg = ModelMessage(role="system", content="")
        assert msg.content == ""

    def test_messages_list(self):
        msgs = [
            ModelMessage(role="system", content="You are a player"),
            ModelMessage(role="user", content="What is your move?"),
        ]
        assert len(msgs) == 2


class TestModelResponse:
    def test_basic_response(self):
        resp = ModelResponse(
            content="Hello",
            model="gpt-5.4",
            provider=ModelProvider.OPENAI,
        )
        assert resp.content == "Hello"
        assert resp.model == "gpt-5.4"
        assert resp.input_tokens == 0
        assert resp.output_tokens == 0

    def test_with_tokens(self):
        resp = ModelResponse(
            content="test",
            model="gpt-5.4",
            provider=ModelProvider.OPENAI,
            input_tokens=100,
            output_tokens=50,
            latency_ms=1200.5,
        )
        assert resp.input_tokens == 100
        assert resp.output_tokens == 50
        assert resp.latency_ms == 1200.5


class TestCoTOutput:
    def test_valid_cot(self):
        cot = CoTOutput(
            situation_assessment="The market is volatile",
            internal_strategy="I will invest secretly",
            public_speech="Let us cooperate",
            secret_action="Buy stocks quietly",
        )
        assert cot.situation_assessment == "The market is volatile"
        assert cot.public_speech == "Let us cooperate"

    def test_default_secret_action(self):
        cot = CoTOutput(
            situation_assessment="当前局势非常复杂，需要仔细分析各方动向",
            internal_strategy="我决定暂时观望，等局势明朗再做决策",
            public_speech="大家好，我们合作吧",
        )
        assert cot.secret_action == ""

    def test_empty_public_speech(self):
        with pytest.raises(Exception):
            CoTOutput(
                situation_assessment="分析",
                internal_strategy="策略",
                public_speech="   ",
            )


class TestDMVerdict:
    def test_basic_verdict(self):
        v = DMVerdict(
            round_number=3,
            round_summary="A round of intense negotiation",
        )
        assert v.round_number == 3
        assert v.winner_id is None
        assert v.resource_delta == []
        assert v.private_messages == []
        assert v.critical_events == []

    def test_verdict_with_winner(self):
        v = DMVerdict(
            round_number=5,
            round_summary="The game has concluded after an intense and hard-fought battle",
            winner_id="p1",
        )
        assert v.winner_id == "p1"

    def test_verdict_with_resource_delta(self):
        v = DMVerdict(
            round_number=2,
            round_summary="A major trade agreement was reached between the two competing companies",
            resource_delta=[
                ResourceDelta(player_id="p1", changes={"gold": -10}),
                ResourceDelta(player_id="p2", changes={"gold": 10}),
            ],
        )
        assert len(v.resource_delta) == 2
        assert v.resource_delta[0].changes["gold"] == -10


class TestPlayerState:
    def test_default_state(self):
        ps = PlayerState(
            id="p1", name="Player 1", model="gpt-5.4",
            provider=ModelProvider.OPENAI,
        )
        assert ps.is_alive is True
        assert ps.is_current_speaker is False
        assert ps.is_thinking is False
        assert ps.resources == {}


class TestGameConfig:
    def test_minimal_config(self):
        cfg = GameConfig(
            game_id="test",
            name="Test",
            players=[
                PlayerDef(id="p1", name="P1", model="gpt-5.4", provider=ModelProvider.OPENAI),
                PlayerDef(id="p2", name="P2", model="claude-sonnet-4-6", provider=ModelProvider.ANTHROPIC),
            ],
        )
        assert cfg.total_rounds == 10
        assert cfg.mode == "sequential"
        assert len(cfg.players) == 2

    def test_config_with_resources(self):
        cfg = GameConfig(
            game_id="test",
            name="Test",
            resources=[
                ResourceDef(id="gold", label="金币", unit="枚", icon="🪙"),
            ],
            players=[
                PlayerDef(id="p1", name="P1", model="gpt-5.4", provider=ModelProvider.OPENAI,
                          initial_resources={"gold": 100}),
                PlayerDef(id="p2", name="P2", model="gpt-5.4", provider=ModelProvider.OPENAI,
                          initial_resources={"gold": 50}),
            ],
        )
        assert len(cfg.resources) == 1
        assert cfg.players[0].initial_resources["gold"] == 100


class TestGameContext:
    def test_full_context(self):
        cfg = GameConfig(
            game_id="test",
            name="Test Game",
            players=[
                PlayerDef(id="p1", name="P1", model="gpt-5.4", provider=ModelProvider.OPENAI),
                PlayerDef(id="p2", name="P2", model="claude-sonnet-4-6", provider=ModelProvider.ANTHROPIC),
            ],
        )
        round_state = RoundState(
            round_number=1,
            total_rounds=10,
            players={
                "p1": PlayerState(
                    id="p1", name="P1", model="gpt-5.4",
                    provider=ModelProvider.OPENAI,
                ),
            },
        )
        ctx = GameContext(game_config=cfg, round=round_state)
        assert ctx.game_config.name == "Test Game"
        assert ctx.round.round_number == 1
        assert ctx.total_tokens_spent == 0


class TestWSEvent:
    def test_event_creation(self):
        evt = WSEvent(
            event_type=WSEventType.ROUND_START,
            payload={"round": 1},
        )
        assert evt.event_type == WSEventType.ROUND_START
        assert evt.payload["round"] == 1

    def test_event_timestamp_auto(self):
        evt = WSEvent(event_type=WSEventType.GAME_INIT)
        assert evt.timestamp is not None


class TestMemory:
    def test_memory_entry(self):
        e = MemoryEntry(round_number=1, content="Test event")
        assert e.round_number == 1
        assert e.is_critical is False

    def test_tiered_memory(self):
        tm = TieredMemory(player_id="p1")
        assert tm.player_id == "p1"
        assert tm.hot_memory == []
        assert tm.warm_summary == ""
