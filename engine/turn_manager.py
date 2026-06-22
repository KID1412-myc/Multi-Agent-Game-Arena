"""
MAGA Turn Manager — 回合管理器
=================================
v1 实现顺位发言模式（sequential）。
架构保留扩展接口，v2 将实现并发流（parallel / 暗标模式）。

Usage:
    from engine.turn_manager import TurnManager
    tm = TurnManager(config)
    await tm.run_turn(ctx, players, dm)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from engine.schema import CoTOutput, DMVerdict, GameConfig, GameContext, PlayerState

logger = logging.getLogger("maga.turn")


class TurnManager:
    """
    回合管理器 —— 顺位发言模式。

    每个玩家按顺序依次发言，一个完成后再到下一个。
    前端在同一时刻只高亮一张玩家卡片。
    """

    def __init__(self, config: GameConfig):
        self.config = config
        self._turn_count: int = 0

    # ── 公共 API ─────────────────────────────────────────────────

    async def collect_player_actions(
        self,
        ctx: GameContext,
        player_states: list[PlayerState],
        action_callback,  # async Callable[[GameContext, PlayerState], CoTOutput]
        on_thinking_start=None,  # Optional async Callable[[PlayerState], None]
        on_action_done=None,     # Optional async Callable[[PlayerState, CoTOutput], None]
        should_stop=None,        # Optional Callable[[], bool] — 每轮循环前检查
    ) -> list[tuple[PlayerState, Optional[CoTOutput]]]:
        """
        顺位收集所有存活玩家的行动。

        Args:
            ctx: 当前游戏上下文
            player_states: 存活玩家列表（按发言顺序排列）
            action_callback: 异步回调，签名为 async def(player_ctx, player_state) -> CoTOutput
            on_thinking_start: 可选回调，玩家开始思考时触发（用于 WebSocket 推送）
            on_action_done: 可选回调，玩家完成行动时触发

        Returns:
            list of (PlayerState, CoTOutput or None if error)
        """
        results: list[tuple[PlayerState, Optional[CoTOutput]]] = []

        alive_players = [p for p in player_states if p.is_alive]

        for i, player in enumerate(alive_players):
            # 检查停止信号
            if should_stop and should_stop():
                logger.info("收到停止信号，中断玩家行动收集")
                break

            # 标记为当前发言者
            player.is_current_speaker = True
            player.is_thinking = True

            if on_thinking_start:
                await on_thinking_start(player)

            # 等待该玩家生成行动
            action: Optional[CoTOutput] = None
            try:
                action = await asyncio.wait_for(
                    action_callback(ctx, player),
                    timeout=self.config.turn_timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning(f"玩家 {player.name} 超时，执行默认被动行动")
                action = self._default_action(player)
                ctx.errors.append(f"{player.name} 超时未响应，自动跳过")
            except Exception as e:
                logger.error(f"玩家 {player.name} 行动异常: {e}")
                ctx.errors.append(f"{player.name} 出错: {e}")
                action = self._default_action(player)

            # 完成行动
            player.is_thinking = False
            player.last_public_speech = action.public_speech if action else ""
            player.last_cot = action
            logger.info(f"✓ {player.name}（{player.id}）完成")

            if on_action_done:
                await on_action_done(player, action)

            results.append((player, action))

            # 发言间隔（防 API 速率限制 + 前端动画）
            await asyncio.sleep(2.0)

            player.is_current_speaker = False

        self._turn_count += 1
        return results

    # ── 内部方法 ─────────────────────────────────────────────────

    def _default_action(self, player: PlayerState) -> CoTOutput:
        """默认被动行动（超时或错误时使用）"""
        return CoTOutput(
            situation_assessment="暂无特别分析，处于观望状态。",
            internal_strategy="保持观望，等待下一轮再做决策。",
            public_speech=f"{player.name} 暂时保持沉默，观望局势发展。",
            secret_action="",
        )

    @property
    def turn_count(self) -> int:
        return self._turn_count
