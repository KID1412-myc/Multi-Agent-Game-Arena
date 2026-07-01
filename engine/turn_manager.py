"""
MAGA Turn Manager — 回合管理器
=================================
v1 实现顺位发言模式（sequential）。
v2 支持并发行动模式（parallel）——适合纯秘密行动阶段。

Usage:
    from engine.turn_manager import TurnManager
    tm = TurnManager(config)
    await tm.collect_player_actions(ctx, players, action_callback, parallel=True)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from engine.schema import CoTOutput, GameConfig, GameContext, PlayerState

logger = logging.getLogger("maga.turn")


class TurnManager:
    """
    回合管理器 —— 支持顺序发言和并发行动两种模式。
    """

    def __init__(self, config: GameConfig):
        self.config = config
        self._turn_count: int = 0

    # ── 公共 API ─────────────────────────────────────────────────

    async def collect_player_actions(
        self,
        ctx: GameContext,
        player_states: list[PlayerState],
        action_callback,
        on_thinking_start=None,
        on_action_done=None,
        should_stop=None,
        check_pause=None,
        parallel: bool = False,
    ) -> list[tuple[PlayerState, Optional[CoTOutput]]]:
        """
        收集所有存活玩家的行动。

        Args:
            ctx: 当前游戏上下文
            player_states: 存活玩家列表
            action_callback: 异步回调
            on_thinking_start: 玩家开始思考时触发
            on_action_done: 玩家完成行动时触发
            check_pause: 暂停检查回调（在超时外调用，保证暂停不受 timeout 影响）
            parallel: True = 并发（行动阶段），False = 顺序（发言阶段）

        Returns:
            list of (PlayerState, CoTOutput or None if error)
        """
        alive_players = [p for p in player_states if p.is_alive]

        if parallel:
            return await self._collect_parallel(ctx, alive_players, action_callback, on_thinking_start, on_action_done, should_stop, check_pause)
        return await self._collect_sequential(ctx, alive_players, action_callback, on_thinking_start, on_action_done, should_stop, check_pause)

    async def _collect_sequential(self, ctx, alive_players, action_callback, on_thinking_start, on_action_done, should_stop, check_pause):
        """顺序收集：发言阶段使用"""
        results: list[tuple[PlayerState, Optional[CoTOutput]]] = []

        for i, player in enumerate(alive_players):
            if should_stop and should_stop():
                logger.info("收到停止信号，中断玩家行动收集")
                break

            # ⏸️ 暂停检查：在 timeout 外调用，保证暂停不会被超时绕过
            if check_pause:
                await check_pause()

            player.is_current_speaker = True
            player.is_thinking = True

            if on_thinking_start:
                await on_thinking_start(player)

            action: Optional[CoTOutput] = None
            timeout = None if getattr(player, 'is_human', False) else self.config.turn_timeout_seconds
            try:
                action = await asyncio.wait_for(
                    action_callback(ctx, player),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(f"玩家 {player.name} 超时，执行默认被动行动")
                action = self._default_action(player)
                ctx.errors.append(f"{player.name} 超时未响应，自动跳过")
            except Exception as e:
                logger.error(f"玩家 {player.name} 行动异常: {e}")
                ctx.errors.append(f"{player.name} 出错: {e}")
                action = self._default_action(player)

            player.is_thinking = False
            player.last_public_speech = action.public_speech if action else ""
            player.last_cot = action
            logger.info(f"✓ {player.name}（{player.id}）完成")

            if on_action_done:
                await on_action_done(player, action)

            results.append((player, action))
            await asyncio.sleep(2.0)
            player.is_current_speaker = False

        self._turn_count += 1
        return results

    async def _collect_parallel(self, ctx, alive_players, action_callback, on_thinking_start, on_action_done, should_stop, check_pause):
        """并发收集：行动阶段使用——所有人同时提交秘密行动"""
        async def one_player(player: PlayerState) -> tuple[PlayerState, Optional[CoTOutput]]:
            if should_stop and should_stop():
                return (player, None)

            # ⏸️ 暂停检查：在 timeout 外调用，保证暂停不会被超时绕过
            if check_pause:
                await check_pause()

            player.is_thinking = True
            if on_thinking_start:
                await on_thinking_start(player)

            action: Optional[CoTOutput] = None
            timeout = None if getattr(player, 'is_human', False) else self.config.turn_timeout_seconds
            try:
                action = await asyncio.wait_for(
                    action_callback(ctx, player),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(f"玩家 {player.name} 超时，执行默认被动行动")
                action = self._default_action(player)
                ctx.errors.append(f"{player.name} 超时未响应，自动跳过")
            except Exception as e:
                logger.error(f"玩家 {player.name} 行动异常: {e}")
                ctx.errors.append(f"{player.name} 出错: {e}")
                action = self._default_action(player)

            player.is_thinking = False
            player.last_public_speech = action.public_speech if action else ""
            player.last_cot = action
            logger.info(f"✓ {player.name}（{player.id}）完成")

            if on_action_done:
                await on_action_done(player, action)

            return (player, action)

        # 错开启动防 429，并发等待全部完成
        tasks = []
        for i, player in enumerate(alive_players):
            tasks.append(one_player(player))
            if i < len(alive_players) - 1:
                await asyncio.sleep(0.3)

        gathered = await asyncio.gather(*tasks)
        results = list(gathered)
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
