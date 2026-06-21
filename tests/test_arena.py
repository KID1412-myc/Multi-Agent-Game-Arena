"""
竞技场模块测试（集成测试）
"""
import pytest
import json
from pathlib import Path
from engine.arena import load_game_config, load_hooks
from engine.schema import GameConfig, ModelProvider


class TestLoadGameConfig:
    def test_load_business_espionage(self):
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
        assert len(p1.name) > 0  # 玩家名存在
        assert len(p1.model) > 0  # 模型名存在（用户可自定义）
        assert p1.initial_resources["capital"] == 150

    def test_resource_details(self):
        cfg = load_game_config("business_espionage", "games")
        resources = {r.id: r for r in cfg.resources}
        assert "capital" in resources
        assert "patent_progress" in resources
        assert resources["capital"].label == "资金"
        assert resources["capital"].unit == "亿元"


class TestLoadHooks:
    def test_default_hooks(self):
        hooks = load_hooks("business_espionage", "games")
        assert hooks is not None
        # Should return default GameHooks (no hooks file specified)

    def test_template_hooks(self):
        hooks = load_hooks("_template", "games")
        assert hooks is not None


class TestArenaConfig:
    def test_config_players_count(self):
        cfg = load_game_config("business_espionage", "games")
        assert len(cfg.players) == 6
        assert cfg.min_players == 4
        assert cfg.max_players == 8

    def test_config_dm(self):
        cfg = load_game_config("business_espionage", "games")
        assert len(cfg.dm_model) > 0  # DM 模型名存在（用户可自定义）
        assert cfg.dm_provider is not None
