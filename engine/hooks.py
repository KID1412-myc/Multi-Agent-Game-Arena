"""
MAGA Hooks — 游戏生命周期钩子系统
===================================
引擎在 8 个关键时间点调用这些钩子。
80% 的游戏使用默认空实现，15% 的游戏通过子类覆写注入自定义逻辑。

钩子调用顺序（单轮）：
    on_round_start → before_player_act → after_player_act（每个玩家）
    → before_dm_judge → after_dm_judge → check_win_condition → on_round_end

Usage:
    # 游戏自定义 hooks.py
    from engine.hooks import GameHooks
    class MyGameHooks(GameHooks):
        async def on_game_start(self, ctx):
            # 随机分配身份...
            return ctx
"""

from __future__ import annotations

from typing import Optional

from engine.schema import CoTOutput, DMVerdict, GameContext, PlayerState


class GameHooks:
    """
    引擎生命周期钩子基类。

    每个钩子都有默认空实现。
    游戏可继承此类并覆写需要的钩子，通过 config.json 的 "hooks" 字段指定。

    memory 属性在引擎初始化时自动注入，可在钩子中通过 self.memory 访问。
    """

    def __init__(self):
        self.memory = None  # MemoryManager，由引擎注入

    # ── 游戏级钩子 ───────────────────────────────────────────────

    async def on_game_start(self, ctx: GameContext) -> GameContext:
        """
        游戏开始时的初始化钩子。
        可用于：随机分配秘密身份、发放初始道具、设置自定义变量等。

        Returns:
            可能被修改的 GameContext
        """
        return ctx

    async def on_game_end(self, ctx: GameContext, winner_id: Optional[str]) -> None:
        """
        游戏结束钩子。
        可用于：打印奖状、计算最终得分、写入日志等。
        """
        pass

    # ── 轮次级钩子 ───────────────────────────────────────────────

    async def on_round_start(self, ctx: GameContext, round_num: int) -> GameContext:
        """
        每轮开始前的钩子。
        可用于：触发周期性事件（如市场波动、天气变化等）。
        """
        return ctx

    async def on_round_end(self, ctx: GameContext, round_num: int) -> GameContext:
        """
        每轮结束后的钩子。
        可用于：资源自然衰减/增长（如"每轮获得 5 基础资金"）。
        """
        return ctx

    # ── 玩家级钩子 ───────────────────────────────────────────────

    async def before_player_act(self, ctx: GameContext, player: PlayerState) -> GameContext:
        """
        某个玩家开始行动前的钩子。
        可用于：向玩家注入额外的秘密信息（如预言家验人结果）。
        """
        return ctx

    async def after_player_act(
        self, ctx: GameContext, player: PlayerState, action: CoTOutput
    ) -> GameContext:
        """
        某个玩家完成行动后的钩子。
        可用于：实时触发特殊事件（如"玩家 A 发言包含关键词 X，触发隐藏任务"）。
        """
        return ctx

    # ── DM 级钩子 ────────────────────────────────────────────────

    async def before_dm_judge(self, ctx: GameContext) -> GameContext:
        """
        DM 开始判定前的钩子。
        可用于：过滤/篡改玩家行动再喂给 DM（如"隐藏某些秘密行动不让 DM 全知"）。
        """
        return ctx

    async def after_dm_judge(self, ctx: GameContext, verdict: DMVerdict) -> GameContext:
        """
        DM 判定完成后的钩子。
        可用于：追加额外的资源变化、注入隐藏事件等。
        """
        return ctx

    # ── 胜负判定钩子 ─────────────────────────────────────────────

    async def check_win_condition(self, ctx: GameContext) -> Optional[str]:
        """
        自定义胜负判定。

        默认返回 None（由 DM 判定胜负）。
        覆写后可用于硬规则兜底判定，如：
        - "所有狼人出局 → 村民赢"
        - "某个玩家资金 ≥ 500 → 该玩家获胜"
        - "某个玩家 is_alive == False → 其余存活者中分最高者获胜"

        Returns:
            玩家 ID（游戏结束）或 None（继续游戏）
        """
        return None
