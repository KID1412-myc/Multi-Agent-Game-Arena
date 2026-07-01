"""
共享测试 fixtures
"""
import pytest
from engine.schema import (
    PlayerState, PlayerDef, GameConfig, GameContext,
    RoundState, ModelProvider
)
from engine.arena import load_hooks


# ── 玩家 fixtures ──────────────────────────────────────────

@pytest.fixture(scope="module")
def sample_player_states():
    """9 名玩家——匹配狼人杀标准局"""
    names = ["ChatGPT", "Claude", "豆包", "通义千问", "智谱GLM",
             "Gemini", "Deepseek", "Qwen2", "GLM2"]
    return [
        PlayerState(
            id=f"p{i+1}", name=name, model="test-model",
            provider=ModelProvider.OPENAI, is_alive=True
        )
        for i, name in enumerate(names)
    ]


@pytest.fixture
def alive_players(sample_player_states):
    """所有玩家全部存活（独立副本）"""
    return [
        PlayerState(
            id=p.id, name=p.name, model=p.model,
            provider=p.provider, is_alive=True
        )
        for p in sample_player_states
    ]


# ── 狼人杀 fixtures ────────────────────────────────────────

@pytest.fixture(scope="module")
def werewolf_hooks():
    """加载 WerewolfHooks 实例（模块级，只加载一次）"""
    return load_hooks("werewolf", "games")


@pytest.fixture
def ww_with_roles(sample_player_states):
    """
    WerewolfHooks 实例，已手动设置标准角色：
    p1-p3=狼人, p4=预言家, p5=女巫, p6=猎人, p7-p9=平民
    """
    hooks = load_hooks("werewolf", "games")
    hooks.roles = {
        "p1": "狼人", "p2": "狼人", "p3": "狼人",
        "p4": "预言家", "p5": "女巫", "p6": "猎人",
        "p7": "平民", "p8": "平民", "p9": "平民",
    }
    hooks.witch_antidote = True
    hooks.witch_poison = True
    hooks.hunter_alive = True
    return hooks


# ── 人类玩家模拟 fixtures ───────────────────────────────────

class MockArena:
    """最小桩：只提供 _emit 和 _stop_event，用于测试人类玩家路径。"""
    def __init__(self):
        import asyncio as _asyncio
        self._stop_event = _asyncio.Event()
        self._emit_done = _asyncio.Event()  # 每次 emit 后触发，消除竞态
        self.emitted: list[tuple] = []

    async def _emit(self, event_type, data):
        self.emitted.append((str(event_type), dict(data)))
        self._emit_done.set()


class MockMemory:
    """最小桩：提供 add_private / add_public / register_player 空操作。"""
    def add_private(self, player_id, content): pass
    def add_public(self, content): pass
    def register_player(self, player_id): pass
    def update_warm_summary(self, summary): pass


@pytest.fixture
def mock_arena():
    return MockArena()


@pytest.fixture
def human_player_def():
    """is_human=True 的 PlayerDef"""
    return PlayerDef(id="p_human", name="人类测试", is_human=True,
                     model="test", provider=ModelProvider.OPENAI)


@pytest.fixture
def human_agent(human_player_def, mock_arena):
    """
    is_human=True 的 PlayerAgent 工厂函数。
    挂载 MockArena + 默认假 context 回调。
    用法: agent = human_agent() 或 agent = human_agent(get_context_fn=custom_fn)
    """
    from engine.player_agent import PlayerAgent

    def _make(get_context_fn=None):
        if get_context_fn is None:
            get_context_fn = lambda pid: "## 🎭 测试角色\n全玩家名单: p1,p2,p3\n"
        agent = PlayerAgent(
            player_def=human_player_def,
            router=None,  # 人类玩家不调用 router
            get_context_fn=get_context_fn,
            game_id="test",
        )
        agent._arena = mock_arena
        return agent
    return _make


# ── Arena fixtures ──────────────────────────────────────────

@pytest.fixture
def minimal_config():
    """最小化的 GameConfig（3 人局）"""
    return GameConfig(
        game_id="test",
        name="Test Game",
        total_rounds=10,
        mode="sequential",
        players=[
            PlayerDef(id="p1", name="P1", model="test", provider=ModelProvider.OPENAI),
            PlayerDef(id="p2", name="P2", model="test", provider=ModelProvider.OPENAI),
            PlayerDef(id="p3", name="P3", model="test", provider=ModelProvider.OPENAI),
        ],
    )


@pytest.fixture
def minimal_context(minimal_config):
    """最小化的 GameContext（3 人存活）"""
    players_dict = {
        f"p{i+1}": PlayerState(
            id=f"p{i+1}", name=f"P{i+1}", model="test",
            provider=ModelProvider.OPENAI, is_alive=True
        )
        for i in range(3)
    }
    return GameContext(
        game_config=minimal_config,
        round=RoundState(
            round_number=1,
            total_rounds=10,
            players=players_dict,
        ),
    )
