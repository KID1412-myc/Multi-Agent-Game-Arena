"""
狼人杀纯逻辑单元测试
测试 WerewolfHooks 中不依赖 LLM 调用的核心逻辑：
角色分配、_parse_pick、胜负判定、投票平票。
"""
import pytest
import asyncio
from engine.schema import PlayerState, ModelProvider


# ── 工具函数 ────────────────────────────────────────────────

def run(coro):
    """同步运行 async 方法"""
    return asyncio.run(coro)


def make_players(ids_and_roles: list[tuple[str, str, bool]]):
    """
    快速构造 PlayerState 列表。
    ids_and_roles: [(id, role, is_alive), ...]
    """
    players = []
    for pid, role, alive in ids_and_roles:
        p = PlayerState(id=pid, name=pid.upper(), model="test", provider=ModelProvider.OPENAI)
        p.is_alive = alive
        players.append(p)
    return players


# ── _parse_pick ─────────────────────────────────────────────

class TestParsePick:
    """从 LLM 回复中提取目标玩家 ID"""

    def test_simple_pX(self, ww_with_roles, alive_players):
        assert ww_with_roles._parse_pick("p5", alive_players) == "p5"

    def test_pX_in_text(self, ww_with_roles, alive_players):
        assert ww_with_roles._parse_pick("我要选p3因为他最像狼人", alive_players) == "p3"

    def test_chinese_number(self, ww_with_roles, alive_players):
        assert ww_with_roles._parse_pick("p三", alive_players) == "p3"

    def test_chinese_eight(self, ww_with_roles, alive_players):
        assert ww_with_roles._parse_pick("p八", alive_players) == "p8"

    def test_dead_player_ignored(self, ww_with_roles, alive_players):
        """p3 已死亡，不能选中"""
        alive_players[2].is_alive = False  # p3
        assert ww_with_roles._parse_pick("p3", alive_players) is None

    def test_alive_player_over_dead(self, ww_with_roles, alive_players):
        """p3 死亡时选 p4，应返回 p4"""
        alive_players[2].is_alive = False
        assert ww_with_roles._parse_pick("p4", alive_players) == "p4"

    def test_empty_text(self, ww_with_roles, alive_players):
        assert ww_with_roles._parse_pick("", alive_players) is None

    def test_whitespace_only(self, ww_with_roles, alive_players):
        assert ww_with_roles._parse_pick("   ", alive_players) is None

    def test_no_match(self, ww_with_roles, alive_players):
        assert ww_with_roles._parse_pick("你好，我不知道选谁", alive_players) is None

    def test_multi_digit_matches_first(self, ww_with_roles, alive_players):
        r"""p99 → 正则 p(\d) 只匹配单个数字 → p9"""
        assert ww_with_roles._parse_pick("p99", alive_players) == "p9"

    def test_first_valid_match(self, ww_with_roles, alive_players):
        """文本中出现多个 pX，取第一个有效的"""
        assert ww_with_roles._parse_pick("p3和p5都很可疑决定p3", alive_players) == "p3"

    def test_uppercase_P_supported(self, ww_with_roles, alive_players):
        """P3（大写）正常匹配"""
        assert ww_with_roles._parse_pick("P3", alive_players) == "p3"

    def test_uppercase_P_in_text(self, ww_with_roles, alive_players):
        """我选P5 → p5"""
        assert ww_with_roles._parse_pick("我选P5", alive_players) == "p5"

    def test_single_player_alive(self, ww_with_roles, alive_players):
        """只剩 1 人存活时仍能正常解析"""
        for p in alive_players:
            p.is_alive = False
        alive_players[0].is_alive = True  # 只有 p1 存活
        assert ww_with_roles._parse_pick("p1", alive_players) == "p1"


# ── _check_win ──────────────────────────────────────────────

class TestCheckWin:
    """胜负判定"""

    def test_all_wolves_dead_villagers_win(self, ww_with_roles):
        """所有狼人阵亡 → 好人获胜"""
        alive = make_players([
            ("p4", "预言家", True),
            ("p5", "女巫", True),
            ("p7", "平民", True),
        ])
        assert run(ww_with_roles._check_win(alive)) is True

    def test_wolves_equal_half_win(self, ww_with_roles):
        """狼人数 = 存活人数一半 → 狼获胜"""
        alive = make_players([
            ("p1", "狼人", True),
            ("p2", "狼人", True),
            ("p4", "预言家", True),
            ("p7", "平民", True),
        ])
        assert run(ww_with_roles._check_win(alive)) is True

    def test_wolves_majority_win(self, ww_with_roles):
        """狼人过半 → 狼获胜"""
        alive = make_players([
            ("p1", "狼人", True),
            ("p2", "狼人", True),
            ("p3", "狼人", True),
            ("p4", "预言家", True),
        ])
        assert run(ww_with_roles._check_win(alive)) is True

    def test_no_winner_yet(self, ww_with_roles):
        """游戏应继续"""
        alive = make_players([
            ("p1", "狼人", True),
            ("p2", "狼人", True),
            ("p4", "预言家", True),
            ("p5", "女巫", True),
            ("p7", "平民", True),
            ("p8", "平民", True),
        ])
        assert run(ww_with_roles._check_win(alive)) is False

    def test_last_wolves_dead(self, ww_with_roles):
        """最后一狼死亡 → 好人获胜"""
        alive = make_players([
            ("p1", "狼人", True),
            ("p4", "预言家", True),
            ("p7", "平民", True),
        ])
        # 狼人 1/3 < 1.5，还未过半，但还没全灭
        assert run(ww_with_roles._check_win(alive)) is False

        # 狼人全灭
        alive2 = make_players([
            ("p4", "预言家", True),
            ("p7", "平民", True),
        ])
        assert run(ww_with_roles._check_win(alive2)) is True

    def test_only_wolves_alive(self, ww_with_roles):
        """只剩狼人 → 狼获胜"""
        alive = make_players([
            ("p1", "狼人", True),
            ("p2", "狼人", True),
            ("p3", "狼人", True),
        ])
        assert run(ww_with_roles._check_win(alive)) is True


# ── check_win_condition ─────────────────────────────────────

class TestCheckWinCondition:
    """旧钩子接口：返回获胜方 ID 列表"""

    def test_returns_none_when_no_winner(self, ww_with_roles, minimal_context):
        ctx = minimal_context
        # 3 人全部存活，p1 是狼人（通过 fixture roles）
        # minimal_context 只有 p1-p3
        ww_with_roles.roles = {"p1": "狼人", "p2": "平民", "p3": "平民"}
        result = run(ww_with_roles.check_win_condition(ctx))
        assert result is None

    def test_returns_villagers_when_wolves_dead(self, ww_with_roles, minimal_context):
        ctx = minimal_context
        ww_with_roles.roles = {"p1": "平民", "p2": "平民", "p3": "平民"}
        # 所有玩家存活但没有狼人 → 应该立刻判定（虽然这配置不合法）
        # 实际上角色分配不会全是平民，这里只测逻辑
        result = run(ww_with_roles.check_win_condition(ctx))
        # 所有狼人死亡 → 返回好人列表
        assert result is not None
        assert "p1" in result

    def test_returns_wolves_when_majority(self, ww_with_roles, minimal_context):
        ctx = minimal_context
        ww_with_roles.roles = {"p1": "狼人", "p2": "狼人", "p3": "平民"}
        # 狼人 2/3 > 1.5，狼获胜
        result = run(ww_with_roles.check_win_condition(ctx))
        assert result is not None
        assert "p1" in result
        assert "p2" in result


# ── 角色分配 ────────────────────────────────────────────────

class TestRoleAssignment:
    """ROLES 常量 & 角色分配一致性"""

    def test_roles_list_has_nine_entries(self, werewolf_hooks):
        """9 人局有 9 个角色"""
        from games.werewolf.hooks import ROLES
        assert len(ROLES) == 9

    def test_correct_role_distribution(self, werewolf_hooks):
        """3 狼 + 1 预言家 + 1 女巫 + 1 猎人 + 3 平民"""
        from games.werewolf.hooks import ROLES
        assert ROLES.count("狼人") == 3
        assert ROLES.count("预言家") == 1
        assert ROLES.count("女巫") == 1
        assert ROLES.count("猎人") == 1
        assert ROLES.count("平民") == 3

    def test_roles_dict_empty_by_default(self, werewolf_hooks):
        """初始化后 roles 为空，on_game_start 才填充"""
        assert werewolf_hooks.roles == {}

    def test_witch_potions_available_by_default(self, werewolf_hooks):
        """女巫解药和毒药初始可用"""
        assert werewolf_hooks.witch_antidote is True
        assert werewolf_hooks.witch_poison is True

    def test_role_assignment_no_manual_runs(self, sample_player_states):
        """无手动分配时 on_game_start 不抛异常，9 个角色全部分配。"""
        from games.werewolf.hooks import WerewolfHooks
        from engine.schema import GameConfig, GameContext, RoundState, PlayerDef, ModelProvider
        from tests.conftest import MockMemory

        hooks = WerewolfHooks()
        hooks.arena = type('obj', (object,), {'_assignments': {}})()
        hooks.memory = MockMemory()  # 防止 on_game_start 调用 add_private 炸掉
        players_dict = {
            p.id: p for p in sample_player_states
        }
        ctx = GameContext(
            game_config=GameConfig(
                game_id="test",
                name="Test",
                total_rounds=0,
                mode="sequential",
                players=[
                    PlayerDef(id=p.id, name=p.name, model="test", provider=ModelProvider.OPENAI)
                    for p in sample_player_states
                ],
            ),
            round=RoundState(
                round_number=1,
                total_rounds=0,
                players=players_dict,
            ),
        )
        import asyncio
        asyncio.run(hooks.on_game_start(ctx))
        assert len(hooks.roles) == 9
        # 验证角色分布正确
        from games.werewolf.hooks import ROLES
        assert list(hooks.roles.values()).count("狼人") == ROLES.count("狼人")


# ── 投票平票 ────────────────────────────────────────────────

class TestVoteTally:
    """白天投票计票 & 平票检测"""

    def _tally_and_check_tie(self, votes: dict[str, str]):
        """
        复制 _day_phase 中的计票 + 平票检测逻辑。
        返回 (top_candidates, max_votes)。
        """
        tally: dict[str, int] = {}
        for choice in votes.values():
            if choice and choice != "弃权":
                tally[choice] = tally.get(choice, 0) + 1
        max_votes = max(tally.values()) if tally else 0
        top = [pid for pid, cnt in tally.items() if cnt == max_votes]
        return top, max_votes

    def test_simple_winner(self):
        """单一人选获胜"""
        votes = {"p1": "p3", "p2": "p3", "p3": "p5", "p4": "p3"}
        top, mv = self._tally_and_check_tie(votes)
        assert top == ["p3"]
        assert mv == 3

    def test_tie_detected(self):
        """平票 → 多个候选人"""
        votes = {"p1": "p3", "p2": "p3", "p3": "p5", "p4": "p5"}
        top, mv = self._tally_and_check_tie(votes)
        assert len(top) == 2
        assert set(top) == {"p3", "p5"}
        assert mv == 2

    def test_three_way_tie(self):
        """三方平票"""
        votes = {"p1": "p3", "p2": "p4", "p3": "p5"}
        top, mv = self._tally_and_check_tie(votes)
        assert len(top) == 3
        assert mv == 1

    def test_all_abstain(self):
        """全员弃权 → 无人得票"""
        votes = {"p1": "弃权", "p2": "弃权", "p3": "弃权"}
        top, mv = self._tally_and_check_tie(votes)
        assert top == []
        assert mv == 0

    def test_mixed_abstain_and_votes(self):
        """部分弃权，部分投票"""
        votes = {"p1": "p3", "p2": "弃权", "p3": "弃权", "p4": "p3"}
        top, mv = self._tally_and_check_tie(votes)
        assert top == ["p3"]
        assert mv == 2

    def test_unanimous_winner(self):
        """全票通过"""
        votes = {"p1": "p3", "p2": "p3", "p3": "p3", "p4": "p3",
                 "p5": "p3", "p6": "p3"}
        top, mv = self._tally_and_check_tie(votes)
        assert top == ["p3"]
        assert mv == 6

    def test_single_vote_decides(self):
        """只有一票有效，其余弃权 → 该票决定结果"""
        votes = {"p1": "p3", "p2": "弃权", "p3": "弃权"}
        top, mv = self._tally_and_check_tie(votes)
        assert top == ["p3"]
        assert mv == 1
