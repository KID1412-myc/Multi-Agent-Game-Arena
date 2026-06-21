"""
MAGA State Machine — 通用有限状态机
======================================
驱动游戏阶段流转。v1 默认线性阶段推进。
复杂游戏可通过 config.json 的 "state_machine" 字段注入子类。

默认阶段流转：
    init → player_turn → dm_judgment → player_turn → ... → game_over

其中 player_turn 内部按配置的 mode 分流：
    - sequential: 顺位发言（一个玩家完成后再到下一个）
    - parallel: 所有玩家同时行动（暗标模式）
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Optional

from engine.schema import GameConfig, GameContext, RoundState


class Phase(StrEnum):
    """游戏阶段枚举"""
    INIT = "init"
    PLAYER_TURN = "player_turn"
    DM_JUDGMENT = "dm_judgment"
    GAME_OVER = "game_over"


class GameStateMachine:
    """
    默认游戏状态机 —— 线性阶段推进。

    子类可覆写 next_phase() 实现自定义阶段流转。
    """

    def __init__(self, config: GameConfig):
        self.config = config
        self._current_phase: Phase = Phase.INIT
        self._phase_history: list[Phase] = []

    # ── 公共 API ─────────────────────────────────────────────────

    @property
    def current_phase(self) -> Phase:
        return self._current_phase

    def transition_to(self, phase: Phase) -> None:
        """强制转换到指定阶段"""
        self._phase_history.append(self._current_phase)
        self._current_phase = phase

    async def next_phase(self, ctx: GameContext) -> Phase:
        """
        计算下一个阶段。

        默认逻辑（线性）：
            init → player_turn → dm_judgment → player_turn → ... → game_over

        子类可覆写以实现复杂的阶段流转（如狼人杀的夜晚子步骤）。
        """
        current = self._current_phase

        if current == Phase.INIT:
            next_p = Phase.PLAYER_TURN
        elif current == Phase.PLAYER_TURN:
            next_p = Phase.DM_JUDGMENT
        elif current == Phase.DM_JUDGMENT:
            # 检查是否结束
            if self._is_game_over(ctx):
                next_p = Phase.GAME_OVER
            else:
                next_p = Phase.PLAYER_TURN
        elif current == Phase.GAME_OVER:
            next_p = Phase.GAME_OVER  # 终态
        else:
            next_p = Phase.PLAYER_TURN

        self._phase_history.append(self._current_phase)
        self._current_phase = next_p
        return next_p

    # ── 内部方法 ─────────────────────────────────────────────────

    def _is_game_over(self, ctx: GameContext) -> bool:
        """检查游戏是否应该结束"""
        # 1. DM 已经判定胜者
        if ctx.dm_last_verdict and ctx.dm_last_verdict.winner_id:
            return True

        # 2. 达到最大轮数
        if self.config.total_rounds > 0:
            if ctx.round.round_number >= self.config.total_rounds:
                return True

        # 3. 所有玩家出局
        alive_count = sum(
            1 for p in ctx.round.players.values() if p.is_alive
        )
        if alive_count <= 1:
            return True

        return False

    def get_phase_history(self) -> list[Phase]:
        """获取阶段历史"""
        return list(self._phase_history)
