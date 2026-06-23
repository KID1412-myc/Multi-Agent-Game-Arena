"""
游戏配置加载 & 钩子加载测试
覆盖所有 games/ 目录下的游戏。
"""
import pytest
import json
from pathlib import Path
from engine.arena import load_game_config, load_hooks
from engine.schema import GameConfig, ModelProvider


# ── 已激活的游戏 ID 列表 ────────────────────────────────────

ACTIVE_GAMES = [
    "greedy_mine_v2",
    "bomb_collar_v2",
    "blind_bidding",
    "loot_share",
    "werewolf",
    "business_espionage",
]

V2_GAMES = ["greedy_mine_v2", "bomb_collar_v2", "blind_bidding", "loot_share", "werewolf"]


# ── 配置加载 ────────────────────────────────────────────────

class TestAllGameConfigs:
    """所有游戏配置都应能正常加载"""

    @pytest.mark.parametrize("game_id", ACTIVE_GAMES)
    def test_config_loads_without_error(self, game_id):
        """每个游戏的 config.json 都能成功解析"""
        cfg = load_game_config(game_id, "games")
        assert isinstance(cfg, GameConfig)
        assert cfg.game_id == game_id

    @pytest.mark.parametrize("game_id", ACTIVE_GAMES)
    def test_player_count_in_range(self, game_id):
        """玩家数在 min_players 和 max_players 之间"""
        cfg = load_game_config(game_id, "games")
        n = len(cfg.players)
        assert cfg.min_players <= n <= cfg.max_players, (
            f"{game_id}: {n} 玩家不在 [{cfg.min_players}, {cfg.max_players}]"
        )

    @pytest.mark.parametrize("game_id", ACTIVE_GAMES)
    def test_total_rounds_non_negative(self, game_id):
        """total_rounds >= 0（0 表示不限轮数）"""
        cfg = load_game_config(game_id, "games")
        assert cfg.total_rounds >= 0

    @pytest.mark.parametrize("game_id", ACTIVE_GAMES)
    def test_dm_model_configured(self, game_id):
        """DM 模型已配置（来自游戏 config 或全局 defaults）"""
        cfg = load_game_config(game_id, "games")
        assert len(cfg.dm_model) > 0
        assert cfg.dm_provider is not None

    @pytest.mark.parametrize("game_id", ACTIVE_GAMES)
    def test_players_have_model_and_provider(self, game_id):
        """每个玩家的 model 和 provider 不为空"""
        cfg = load_game_config(game_id, "games")
        for p in cfg.players:
            assert len(p.model) > 0, f"{game_id}/{p.id}: model 为空"
            assert len(p.provider.value) > 0, f"{game_id}/{p.id}: provider 为空"


# ── 默认模型继承 ────────────────────────────────────────────

class TestDefaultModelInheritance:
    """游戏不写 model/provider 时，自动从 config/defaults.json 继承"""

    def test_defaults_file_exists(self):
        """全局默认配置存在"""
        assert Path("config/defaults.json").exists()

    def test_defaults_has_nine_players(self):
        """默认配置有 9 个站位"""
        with open("config/defaults.json", "r", encoding="utf-8") as f:
            defaults = json.load(f)
        assert len(defaults["players"]) == 9

    def test_werewolf_inherits_defaults(self):
        """狼人杀 config 不写 model/provider，应从 defaults 继承第 1 个站位"""
        cfg = load_game_config("werewolf", "games")
        # 第 1 个玩家没写 model → 从 defaults[0] 继承
        p1 = cfg.players[0]
        assert p1.model != ""  # 应该已被填充
        assert p1.provider is not None

    def test_business_espionage_inherits_defaults(self):
        """商业谍战也不写 model，应从 defaults 继承"""
        cfg = load_game_config("business_espionage", "games")
        p1 = cfg.players[0]
        assert len(p1.model) > 0
        assert p1.provider is not None


# ── V2 钩子加载 ─────────────────────────────────────────────

class TestV2HookLoading:
    """所有 v2 游戏都应正确加载自定义 hooks"""

    @pytest.mark.parametrize("game_id", V2_GAMES)
    def test_hooks_loads_successfully(self, game_id):
        """hooks.py 能成功加载并返回实例"""
        hooks = load_hooks(game_id, "games")
        assert hooks is not None

    @pytest.mark.parametrize("game_id", V2_GAMES)
    def test_hooks_has_run_round(self, game_id):
        """v2 hooks 必须覆写 run_round"""
        hooks = load_hooks(game_id, "games")
        assert hasattr(hooks, "run_round")


# ── 商业谍战（保留旧测试的精髓）─────────────────────────────

class TestBusinessEspionage:
    def test_config_basics(self):
        cfg = load_game_config("business_espionage", "games")
        assert isinstance(cfg, GameConfig)
        assert cfg.name == "商业谍战：量子芯片之争"
        assert len(cfg.players) == 6
        assert cfg.total_rounds == 12
        assert cfg.mode == "sequential"
        assert len(cfg.resources) == 5

    def test_player_details(self):
        cfg = load_game_config("business_espionage", "games")
        p1 = cfg.players[0]
        assert p1.id == "p1"
        assert len(p1.name) > 0
        assert len(p1.model) > 0
        assert p1.initial_resources["capital"] == 150

    def test_resource_details(self):
        cfg = load_game_config("business_espionage", "games")
        resources = {r.id: r for r in cfg.resources}
        assert "capital" in resources
        assert "patent_progress" in resources
        assert resources["capital"].label == "资金"
        assert resources["capital"].unit == "亿元"


# ── _template ───────────────────────────────────────────────

class TestTemplate:
    def test_template_hooks_is_default(self):
        """_template 没有自定义 hooks，应返回默认 GameHooks"""
        hooks = load_hooks("_template", "games")
        assert hooks is not None
        # 默认 GameHooks 的 run_round 返回 True
        assert hasattr(hooks, "run_round")
