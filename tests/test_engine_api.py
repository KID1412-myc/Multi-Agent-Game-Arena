"""
引擎 API 单元测试
测试 Arena 暴露给游戏 hooks 使用的核心 API。
"""
import pytest
from engine.arena import Arena
from engine.schema import PlayerState, ModelProvider


# ── _normalize_vote ─────────────────────────────────────────

class TestNormalizeVote:
    """投票归一化：从 LLM 回复中提取目标 ID"""

    def test_lowercase_p(self):
        assert Arena._normalize_vote("p3") == "p3"

    def test_uppercase_P(self):
        assert Arena._normalize_vote("P5") == "p5"

    def test_in_context_text(self):
        assert Arena._normalize_vote("我认为应该选p2因为他可疑") == "p2"

    def test_leading_text_then_pick(self):
        assert Arena._normalize_vote("我选P1") == "p1"

    def test_multiple_picks_returns_first(self):
        # 取第一个匹配的 pX
        assert Arena._normalize_vote("p3和p5都很可疑，最终选p3") == "p3"

    def test_only_digit(self):
        # 没有 p 前缀 → 弃权
        assert Arena._normalize_vote("3") == "弃权"

    def test_chinese_without_p(self):
        assert Arena._normalize_vote("我选三号") == "弃权"

    def test_empty_string(self):
        assert Arena._normalize_vote("") == "弃权"

    def test_whitespace_only(self):
        assert Arena._normalize_vote("   ") == "弃权"

    def test_explicit_abstain(self):
        assert Arena._normalize_vote("弃权") == "弃权"

    def test_abstain_in_context(self):
        assert Arena._normalize_vote("我不确定，选择弃权") == "弃权"

    def test_random_text(self):
        assert Arena._normalize_vote("今天天气真好") == "弃权"

    def test_p_multi_digit_matches_first(self):
        # p99 → 正则 [pP](\d) 只匹配单个数字 → p9
        assert Arena._normalize_vote("p99") == "p9"

    def test_p_with_extra_chars(self):
        assert Arena._normalize_vote("投票：p3。") == "p3"


# ── eliminate ───────────────────────────────────────────────

class TestEliminate:
    def test_player_marked_dead(self, minimal_context):
        """淘汰后 is_alive 变为 False"""
        arena = Arena.__new__(Arena)  # 绕过 __init__
        assert minimal_context.round.players["p1"].is_alive is True
        arena.eliminate(minimal_context, "p1")
        assert minimal_context.round.players["p1"].is_alive is False

    def test_already_dead_no_error(self, minimal_context):
        """重复淘汰不抛异常"""
        arena = Arena.__new__(Arena)
        minimal_context.round.players["p1"].is_alive = False
        arena.eliminate(minimal_context, "p1")  # 应该无异常
        assert minimal_context.round.players["p1"].is_alive is False

    def test_nonexistent_player_no_error(self, minimal_context):
        """淘汰不存在的玩家不抛异常"""
        arena = Arena.__new__(Arena)
        arena.eliminate(minimal_context, "p99")  # 应该无异常


# ── config 加载边界条件 ─────────────────────────────────────

class TestConfigLoadingEdgeCases:
    def test_nonexistent_game_raises(self):
        """不存在的游戏抛 FileNotFoundError"""
        from engine.arena import load_game_config
        with pytest.raises(FileNotFoundError):
            load_game_config("__nonexistent_game__", "games")

    def test_template_config_loads(self):
        """_template 的配置能正常加载"""
        from engine.arena import load_game_config, load_hooks
        cfg = load_game_config("_template", "games")
        assert cfg.game_id == "my_game"  # _template 的 game_id 占位符
        hooks = load_hooks("_template", "games")
        assert hooks is not None
