"""
MAGA Arena — 主竞技场
========================
游戏生命周期管理的核心模块。

职责：
1. 加载游戏配置（从 games/ 目录）
2. 初始化所有组件（Router / Memory / DM / Players / StateMachine / TurnManager）
3. 主游戏循环：轮次推进 → 玩家行动 → DM 裁判 → 状态更新
4. WebSocket 事件推送（每帧状态同步到前端）
5. 优雅退出与资源清理

Usage:
    from engine.arena import Arena
    arena = Arena("business_espionage")
    result = await arena.run()
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from engine.hooks import GameHooks
from engine.memory import MemoryManager
from engine.router import ModelRouter, close_http_client
from engine.player_agent import PlayerAgent
from engine.dm_interface import DMInterface
from engine.state_machine import GameStateMachine
from engine.turn_manager import TurnManager
from engine.schema import (
    ArenaResult,
    CoTOutput,
    DMVerdict,
    GameConfig,
    GameContext,
    ModelProvider,
    PlayerDef,
    PlayerState,
    ResourceDef,
    RoundState,
    WSEvent,
    WSEventType,
)

logger = logging.getLogger("maga.arena")


def _resolve_path(relative: str) -> Path:
    """解析文件路径：PyInstaller 打包后从 _MEIPASS 读，开发时从项目根目录读。"""
    path = Path(relative)
    if not path.exists():
        import sys as _sys
        if getattr(_sys, 'frozen', False):
            path = Path(_sys._MEIPASS) / relative
    return path


# ============================================================================
# 配置加载器
# ============================================================================

def load_game_config(game_id: str, games_dir: str = "games") -> GameConfig:
    """
    从 games/<game_id>/config.json 加载游戏配置。

    Args:
        game_id: 游戏目录名
        games_dir: 游戏根目录

    Returns:
        GameConfig: 解析后的游戏配置

    Raises:
        FileNotFoundError: 游戏配置不存在
    """
    config_path = Path(games_dir) / game_id / "config.json"

    # PyInstaller 打包模式：数据文件在 _MEIPASS 临时目录
    if not config_path.exists():
        import sys as _sys
        if getattr(_sys, 'frozen', False):
            meipass = Path(_sys._MEIPASS)
            config_path = meipass / games_dir / game_id / "config.json"

    if not config_path.exists():
        raise FileNotFoundError(
            f"游戏配置不存在: {config_path}\n"
            f"请确保 games/{game_id}/config.json 文件存在。"
        )

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    # 加载全局默认模型配置
    defaults_path = _resolve_path("config/defaults.json")
    defaults = {}
    if defaults_path.exists():
        with open(defaults_path, "r", encoding="utf-8") as f:
            defaults = json.load(f)

    # 解析资源定义
    resources: list[ResourceDef] = []
    for r in raw.get("resources", []):
        resources.append(ResourceDef(
            id=r.get("id", ""),
            label=r.get("label", ""),
            unit=r.get("unit", ""),
            icon=r.get("icon", ""),
        ))

    # 解析玩家定义
    default_players = defaults.get("players", [])
    players: list[PlayerDef] = []
    for i, p in enumerate(raw.get("players", [])):
        dp = default_players[i] if i < len(default_players) else {}
        players.append(PlayerDef(
            id=p.get("id", ""),
            name=p.get("name", ""),
            model=p.get("model") or dp.get("model", "gpt-5.4"),
            provider=ModelProvider(p.get("provider") or dp.get("provider", "openai")),
            secret_identity=p.get("secret_identity", ""),
            initial_resources=p.get("initial_resources", {}),
        ))

    # 解析 DM provider
    dm_provider_raw = raw.get("dm_provider") or defaults.get("dm_provider", "openai")
    dm_model = raw.get("dm_model") or defaults.get("dm_model", "gpt-5.4")
    try:
        dm_provider = ModelProvider(dm_provider_raw)
    except ValueError:
        dm_provider = ModelProvider.OPENAI

    return GameConfig(
        game_id=raw.get("game_id", game_id),
        name=raw.get("name", game_id),
        version=raw.get("version", "1.0"),
        description=raw.get("description", ""),
        min_players=raw.get("min_players", 2),
        max_players=raw.get("max_players", len(players)),
        total_rounds=raw.get("total_rounds", 10),
        mode=raw.get("mode", "sequential"),
        language=raw.get("language", "zh-CN"),
        turn_timeout_seconds=raw.get("turn_timeout_seconds", 60),
        dm_model=dm_model,
        dm_provider=dm_provider,
        resources=resources,
        players=players,
        hooks=raw.get("hooks"),
        state_machine=raw.get("state_machine"),
        schema_override=raw.get("schema_override"),
        shuffle_order=raw.get("shuffle_order", False),
        two_phase=raw.get("two_phase", False),
        epilogue=raw.get("epilogue", False),
    )


def load_hooks(game_id: str, games_dir: str = "games") -> GameHooks:
    """
    动态加载游戏自定义的 Hooks 类。

    如果 config.json 中 hooks 字段非空，则从对应 .py 文件中加载子类。
    否则返回默认的 GameHooks 实例。

    Args:
        game_id: 游戏目录名
        games_dir: 游戏根目录

    Returns:
        GameHooks 实例
    """
    config_path = Path(games_dir) / game_id / "config.json"

    # PyInstaller 打包模式
    if not config_path.exists():
        import sys as _sys
        if getattr(_sys, 'frozen', False):
            meipass = Path(_sys._MEIPASS)
            config_path = meipass / games_dir / game_id / "config.json"

    if not config_path.exists():
        return GameHooks()

    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    hooks_file = raw.get("hooks")
    if not hooks_file:
        return GameHooks()

    # 动态加载
    hooks_path = Path(games_dir) / game_id / hooks_file
    if not hooks_path.exists():
        if getattr(_sys, 'frozen', False):
            hooks_path = meipass / games_dir / game_id / hooks_file
    if not hooks_path.exists():
        logger.warning(f"Hooks 文件不存在: {hooks_path}，使用默认 Hooks")
        return GameHooks()

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"game_hooks_{game_id}", str(hooks_path)
    )
    if spec is None or spec.loader is None:
        logger.warning(f"无法加载 Hooks 文件，使用默认 Hooks")
        return GameHooks()

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 查找 GameHooks 子类
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if (
            isinstance(attr, type)
            and issubclass(attr, GameHooks)
            and attr is not GameHooks
        ):
            return attr()

    logger.warning(f"Hooks 文件中未找到 GameHooks 子类，使用默认 Hooks")
    return GameHooks()


# ============================================================================
# 主竞技场
# ============================================================================

class Arena:
    """
    MAGA 主竞技场。

    管理一场游戏的完整生命周期：初始化 → 主循环 → 结算。

    Usage:
        arena = Arena("business_espionage", event_callback=my_handler)
        result = await arena.run()
    """

    def __init__(
        self,
        game_id: str,
        games_dir: str = "games",
        event_callback=None,  # Optional async Callable[[WSEvent], None]
        headless: bool = False,  # True = 不推送 WebSocket 事件
    ):
        """
        Args:
            game_id: 游戏目录名（games/ 下的子目录）
            games_dir: 游戏配置根目录
            event_callback: WebSocket 事件回调（可选，用于推送到前端）
            headless: 无头模式，不推送事件
        """
        self.game_id = game_id
        self.games_dir = games_dir
        self._event_callback = event_callback
        self._headless = headless

        # 组件（在 _setup() 中初始化）
        self.config: Optional[GameConfig] = None
        self.router: Optional[ModelRouter] = None
        self.memory: Optional[MemoryManager] = None
        self.hooks: Optional[GameHooks] = None
        self.state_machine: Optional[GameStateMachine] = None
        self.turn_manager: Optional[TurnManager] = None
        self.dm: Optional[DMInterface] = None
        self.players: dict[str, PlayerAgent] = {}

        # 运行时状态
        self._ctx: Optional[GameContext] = None
        self._round_history: list[DMVerdict] = []
        self._errors: list[str] = []
        self._start_time: float = 0.0
        self._total_tokens: int = 0
        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # 初始状态：不暂停（event 已 set = 可以通行）
        self._step_mode: bool = False  # True = 单步模式，每步后自动暂停
        self._round_pause: bool = True  # True = 每轮结束后自动暂停（默认启用，手动控轮）

    # ── 控制信号 ─────────────────────────────────────────────────

    def request_stop(self) -> None:
        """外部调用：请求停止游戏。主循环会在下一轮开始前检测并退出。"""
        self._stop_event.set()
        # 停止时自动取消暂停，避免死锁
        self._pause_event.set()
        logger.warning("停止信号已发送")

    def request_pause(self) -> None:
        """外部调用：暂停游戏。当前玩家完成行动后暂停。"""
        self._pause_event.clear()
        self._step_mode = False
        logger.info("暂停信号已发送")

    def request_resume(self) -> None:
        """外部调用：恢复游戏。"""
        self._pause_event.set()
        self._step_mode = False
        logger.info("恢复信号已发送")

    def request_step(self) -> None:
        """外部调用：单步推进（暂停状态下推进一步）。"""
        self._step_mode = True
        self._pause_event.set()
        logger.info("单步推进信号已发送")

    def request_next_round(self) -> None:
        """外部调用：推进一整轮（本轮跑完，下轮开始前暂停）。"""
        self._round_pause = True
        self._step_mode = False
        self._pause_event.set()
        logger.info("推进整轮信号已发送")

    def request_auto_mode(self) -> None:
        """外部调用：切换为自动模式（轮间不暂停）。"""
        self._round_pause = False
        self._step_mode = False
        self._pause_event.set()
        logger.info("已切换为自动模式")

    async def _wait_if_paused(self) -> None:
        """如果暂停，等待恢复或单步信号；单步模式推进后自动暂停。"""
        was_step = self._step_mode
        await self._pause_event.wait()
        if was_step:
            # 单步完成，自动恢复暂停
            self._pause_event.clear()
            self._step_mode = False

    def _fmt_action(self, pid: str, ctx) -> str:
        """把 hooks 解析出的行动翻译成前端可读的规范格式"""
        hooks = self.hooks
        if not hasattr(hooks, 'actions'):
            return ""
        act, target = hooks.actions.get(pid, (None, None))
        if act == "DEV":
            return "发育（挖矿 +2）"
        elif act == "DEF":
            return "防御（架盾 -1）"
        elif act == "LOOT" and target:
            tname = ctx.round.players[target].name if target in ctx.round.players else target
            return f"掠夺 → {tname}"
        return ""

    @property
    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    # ── 主入口 ───────────────────────────────────────────────────

    async def run(self) -> ArenaResult:
        """
        运行一场完整游戏。

        流程：
        1. _setup() —— 加载配置、初始化组件
        2. 主循环 —— 轮次推进，直到游戏结束
        3. _teardown() —— 清理资源
        4. 返回 ArenaResult
        """
        logger.info(f"🎮 MAGA Arena 启动: {self.game_id}")
        self._start_time = time.monotonic()

        try:
            # 1. 初始化
            await self._setup()
            ctx = self._ctx
            assert ctx is not None

            # 触发 on_game_start 钩子
            ctx = await self.hooks.on_game_start(ctx)
            self._ctx = ctx

            # 发送完整 GameContext，让前端立即渲染全部卡片
            await self._emit(WSEventType.GAME_INIT, {
                "ctx": ctx.model_dump(mode="json"),
            })

            # 2. 主循环
            round_num = 0
            winner_id = None
            while True:
                # 检查停止信号
                if self._stop_event.is_set():
                    logger.info("收到停止信号，退出主循环")
                    break

                # 检查暂停信号（轮间暂停 或 手动暂停）
                if self._round_pause and round_num > 0:
                    # 每轮结束后自动暂停，等用户按"下一轮"
                    await self._emit(WSEventType.STATE_UPDATE, {
                        "phase": "round_paused",
                        "round": round_num,
                        "message": f'第 {round_num} 轮已完成。点击"下一轮"继续。',
                    })
                    self._pause_event.clear()
                await self._wait_if_paused()

                if self._stop_event.is_set():
                    break

                round_num += 1

                # 设置轮次
                self.memory.set_round(round_num)
                ctx.round.round_number = round_num
                ctx.round.phase = "player_turn"

                logger.info(f"🔄 第 {round_num} 轮开始")

                # ── 阶段 1: 玩家行动 ──
                await self._emit(WSEventType.ROUND_START, {
                    "round": round_num,
                    "phase": "player_turn",
                })

                # 触发 on_round_start 钩子
                ctx = await self.hooks.on_round_start(ctx, round_num)

                # 新路径：hook 自行编排回合（跳过旧逻辑）
                if type(self.hooks).run_round is not GameHooks.run_round:
                    keep_going = await self.hooks.run_round(ctx, round_num)
                    if not keep_going:
                        winner_id = await self.hooks.check_win_condition(ctx) or ""
                        await self._emit_game_over(ctx, winner_id)
                        break
                    await self.state_machine.next_phase(ctx)
                    if self.state_machine.current_phase.value == "game_over":
                        winner_id = await self.hooks.check_win_condition(ctx) or ""
                        await self._emit_game_over(ctx, winner_id)
                        break
                    ctx = await self.hooks.on_round_end(ctx, round_num)
                    continue

                # 收集所有玩家行动（旧路径）
                player_states = list(ctx.round.players.values())

                # 两阶段模式：先全员发言（完整 CoT）→ 再全员决定行动（极简调用）
                if self.config.two_phase:
                    # Phase A: 全员发言，完整 CoT
                    self.hooks.skip_parse = True
                    for agent in self.players.values():
                        agent.speech_only = True
                    await self._collect_actions(ctx, player_states)

                    # 保存 speech 阶段的 CoT（self 上挂，闭包可访问）
                    self._speech_cots = {
                        pid: p.last_cot.model_dump(mode="json") if p.last_cot else {}
                        for pid, p in ctx.round.players.items() if p.is_alive
                    }

                    # Phase B: 全员决定行动，极简三选一
                    self.hooks.skip_parse = False
                    for agent in self.players.values():
                        agent.speech_only = False
                        agent.action_only = True
                    player_states = [p for p in ctx.round.players.values() if p.is_alive]
                    actions = await self._collect_actions(ctx, player_states)
                    # 恢复 + 规范化 CoT（ID → 名字，标准格式）
                    for agent in self.players.values():
                        agent.action_only = False
                    for pid, p in ctx.round.players.items():
                        if p.is_alive and pid in self._speech_cots and p.last_cot:
                            old = self._speech_cots[pid]
                            # 标准化 secret_action 显示
                            action_display = self._fmt_action(pid, ctx)
                            p.last_cot = p.last_cot.model_copy(update={
                                "situation_assessment": old.get("situation_assessment", ""),
                                "internal_strategy": old.get("internal_strategy", ""),
                                "public_speech": old.get("public_speech", ""),
                                "secret_action": action_display,
                            })
                else:
                    self._speech_cots = {}
                    actions = await self._collect_actions(ctx, player_states)

                # ── 阶段 2: DM 裁判 ──
                ctx.round.phase = "dm_judgment"
                await self._emit(WSEventType.STATE_UPDATE, {
                    "phase": "dm_judgment",
                    "round": round_num,
                })

                # 触发 before_dm_judge 钩子
                ctx = await self.hooks.before_dm_judge(ctx)

                verdict = await self.dm.judge(ctx, actions)
                self._round_history.append(verdict)

                # 修正 DM 可能搞错的 round_number（fallback 写死成 0）
                verdict.round_number = round_num

                await self._emit(WSEventType.DM_JUDGMENT, {
                    "verdict": verdict.model_dump(mode="json"),
                })

                # 触发 after_dm_judge 钩子
                ctx = await self.hooks.after_dm_judge(ctx, verdict)

                # ── 阶段 3: 状态更新 ──
                self._apply_verdict(ctx, verdict)

                # 更新 L2 温记忆
                self.memory.update_warm_summary(verdict.round_summary)

                # 归档 L3 关键事件
                for ce in verdict.critical_events:
                    self.memory.add_critical_event(ce)

                ctx.dm_last_verdict = verdict
                self._ctx = ctx

                # 推送状态更新
                await self._emit(WSEventType.STATE_UPDATE, {
                    "ctx": ctx.model_dump(mode="json"),
                })

                # ── 阶段 4: 胜负检查 ──
                # 先检查自定义钩子
                winner_id = await self.hooks.check_win_condition(ctx)
                if not winner_id:
                    winner_id = verdict.winner_id

                if winner_id:
                    await self._emit_game_over(ctx, winner_id)
                    break

                # 状态机检查（最大轮数等）
                await self.state_machine.next_phase(ctx)
                if self.state_machine.current_phase.value == "game_over":
                    winner_id = await self.hooks.check_win_condition(ctx) or ""
                    await self._emit_game_over(ctx, winner_id)
                    break

                # 触发 on_round_end 钩子
                ctx = await self.hooks.on_round_end(ctx, round_num)

            # 3. 游戏结束
            winner_id = winner_id if 'winner_id' in locals() else None
            if winner_id:
                wids = winner_id.split(",")
                wname = "、".join(ctx.round.players[wid].name if wid in ctx.round.players else wid for wid in wids)
            else:
                wname = ""

            # 最终感言：全员发表赛后总结（含淘汰者复活发言）
            if self.config.epilogue and winner_id:
                for agent in self.players.values():
                    agent.speech_only = True
                for pid in list(self.players.keys()):
                    p = ctx.round.players.get(pid)
                    if p:
                        tag = "（已淘汰）" if not p.is_alive else ""
                        self.memory.add_private(pid,
                            f"## 游戏结束\n胜者是 {wname}。{tag}\n"
                            f"请发表你的最终感言——对这场博弈的总结、对赢家的评价、或对其他玩家的喊话。"
                        )
                        p.last_cot = None
                        p.is_alive = True  # 临时复活以参与发言
                all_players = [s for s in ctx.round.players.values()]
                await self._collect_actions(ctx, all_players)
                for agent in self.players.values():
                    agent.speech_only = False

            await self.hooks.on_game_end(ctx, winner_id)

            duration = time.monotonic() - self._start_time

            result = ArenaResult(
                game_id=self.game_id,
                game_name=ctx.game_config.name,
                winner_id=winner_id,
                winner_name=winner.name if winner else None,
                total_rounds_played=round_num,
                final_state=ctx,
                round_history=self._round_history,
                total_tokens=self.router.stats["total_tokens"],
                total_cost_usd=-1.0,  # TODO: 根据实际费率计算
                duration_seconds=duration,
                errors=self._errors,
            )

            logger.info(f"✅ 游戏结束: {result.winner_name or '平局'} ({duration:.1f}s)")
            return result

        finally:
            await self._teardown()

    # ── 初始化 ───────────────────────────────────────────────────

    async def _setup(self) -> None:
        """初始化所有组件"""
        # 1. 加载配置
        self.config = load_game_config(self.game_id, self.games_dir)
        logger.info(f"📋 加载游戏配置: {self.config.name} v{self.config.version}")
        logger.info(f"   玩家: {len(self.config.players)} 人 | 轮数: {self.config.total_rounds} | 模式: {self.config.mode}")

        # 2. 初始化 Router
        self.router = ModelRouter()

        # 3. 初始化记忆管理器
        self.memory = MemoryManager(global_hot_window=3, player_hot_window=120)

        # 4. 加载自定义 Hooks，注入 memory
        self.hooks = load_hooks(self.game_id, self.games_dir)
        self.hooks.memory = self.memory
        self.hooks.arena = self

        # 5. 初始化状态机
        self.state_machine = GameStateMachine(self.config)

        # 6. 初始化回合管理器
        self.turn_manager = TurnManager(self.config)

        # 7. 初始化 DM
        self.dm = DMInterface(
            config=self.config,
            router=self.router,
            get_context_fn=self.memory.build_context_for_dm,
        )

        # 8. 初始化玩家
        for pdef in self.config.players:
            self.memory.register_player(pdef.id)
            agent = PlayerAgent(
                player_def=pdef,
                router=self.router,
                get_context_fn=self.memory.build_context_for_player,
                game_id=self.game_id,
            )
            self.players[pdef.id] = agent

        # 9. 初始化游戏上下文
        player_states: dict[str, PlayerState] = {}
        for pdef in self.config.players:
            player_states[pdef.id] = PlayerState(
                id=pdef.id,
                name=pdef.name,
                model=pdef.model,
                provider=pdef.provider,
                resources=dict(pdef.initial_resources),
                is_alive=True,
            )

        round_state = RoundState(
            round_number=0,
            total_rounds=self.config.total_rounds,
            phase="init",
            players=player_states,
        )

        self._ctx = GameContext(
            game_config=self.config,
            round=round_state,
        )

    # ── 引擎 API（供 hook 调用）────────────────────────────────────

    async def collect_speeches(self, ctx: GameContext, player_states: list, parallel: bool = False) -> list:
        """引擎 API：收集全员发言，推送到前端。返回 CoT 列表。"""
        self.hooks.skip_parse = True
        for agent in self.players.values():
            agent.speech_only = True
        result = await self._collect_actions(ctx, player_states, parallel=parallel)
        for agent in self.players.values():
            agent.speech_only = False
        return result

    async def collect_actions(self, ctx: GameContext, player_states: list, parallel: bool = False) -> list:
        """引擎 API：收集全员行动，不推送到前端。返回 CoT 列表。parallel=True 则并发。"""
        self.hooks.skip_parse = False
        for agent in self.players.values():
            agent.action_only = True
        result = await self._collect_actions(ctx, player_states, parallel=parallel)
        for agent in self.players.values():
            agent.action_only = False
        return result

    async def dm_judge(self, ctx: GameContext, actions: list) -> DMVerdict:
        """引擎 API：调用 DM 裁判，返回 verdict。"""
        verdict = await self.dm.judge(ctx, actions)
        verdict.round_number = ctx.round.round_number
        self._round_history.append(verdict)
        await self._emit(WSEventType.DM_JUDGMENT, {
            "verdict": verdict.model_dump(mode="json"),
        })
        return verdict

    def apply_delta(self, ctx: GameContext, deltas: dict[str, int], resource: str = "gold") -> None:
        """引擎 API：应用资源变动。"""
        for pid, delta in deltas.items():
            p = ctx.round.players.get(pid)
            if p and p.is_alive and delta != 0:
                p.resources[resource] = max(0, p.resources.get(resource, 0) + delta)

    def eliminate(self, ctx: GameContext, player_id: str) -> None:
        """引擎 API：淘汰玩家。"""
        p = ctx.round.players.get(player_id)
        if p:
            p.is_alive = False

    def save_speech_cots(self, ctx: GameContext) -> dict:
        """引擎 API：保存当前 speech CoT，供 action 阶段合并用。"""
        self._speech_cots = {
            pid: p.last_cot.model_dump(mode="json") if p.last_cot else {}
            for pid, p in ctx.round.players.items() if p.is_alive
        }
        return self._speech_cots

    async def emit_state(self, ctx: GameContext) -> None:
        """引擎 API：推送完整游戏状态到前端。"""
        await self._emit(WSEventType.STATE_UPDATE, {
            "ctx": ctx.model_dump(mode="json"),
        })

    async def private_msg(self, player_id: str, text: str) -> None:
        """引擎 API：向单个玩家发送私密信息。"""
        if self.memory:
            self.memory.add_private(player_id, text)

    async def vote(self, title: str, ctx: GameContext, targets: list,
                   prompt: str = "", parallel: bool = False) -> dict:
        """
        引擎 API：发起投票。向所有存活玩家私密询问投票意向。
        parallel=True 时并发投票（适用于白天投票等独立决策场景）。
        返回 {"passed": bool, "target": str|None, "votes": {pid: choice}}
        """
        alive = [(pid, p) for pid, p in ctx.round.players.items() if p.is_alive]
        if not alive:
            return {"passed": False, "target": None, "votes": {}}

        threshold = len(alive) // 2 + 1  # 过半

        # 预先给所有投票者发私密提示
        for pid, p in alive:
            target_list = "\n".join(
                f"- {t}" if isinstance(t, str) else f"- {t.id} {t.name}"
                for t in targets)
            self.memory.add_private(pid,
                "## " + title + "\n" + prompt + "\n\n可选目标（回复ID或弃权）：\n" + target_list)

        ballot: dict[str, str] = {}

        async def _vote_one(pid: str, p) -> tuple[str, str]:
            agent = self.players.get(pid)
            if not agent:
                return (pid, "弃权")
            # ⏸️ 暂停检查：每个投票者投票前检查（并发模式下在各自 task 内检查）
            await self._wait_if_paused()
            agent.quick_action_prompt = f"[你是 {pid}] 投票：{title}。只回复目标ID或弃权。"
            agent.action_only = True
            try:
                logger.info(f"▶ {p.name}（{pid}）投票中...")
                await self._emit(WSEventType.PLAYER_THINKING, {
                    "player_id": pid,
                    "player_name": p.name,
                })
                cot = await agent.act(ctx)
                choice = cot.secret_action.strip()
                logger.info(f"✓ {p.name}（{pid}）投票完成 → {choice[:30]}")
            except Exception:
                choice = "弃权"
                logger.info(f"✗ {p.name}（{pid}）投票异常，按弃权处理")
            agent.action_only = False
            agent.quick_action_prompt = None
            return (pid, self._normalize_vote(choice))

        if parallel:
            tasks = []
            for i, (pid, p) in enumerate(alive):
                tasks.append(_vote_one(pid, p))
                if i < len(alive) - 1:
                    await asyncio.sleep(0.3)  # 错开发送防 429
            results = await asyncio.gather(*tasks)
            for pid, choice in results:
                ballot[pid] = choice
        else:
            for pid, p in alive:
                _, choice = await _vote_one(pid, p)
                ballot[pid] = choice
                await asyncio.sleep(0.3)

        # 计票
        tally: dict[str, int] = {}
        for choice in ballot.values():
            if choice and choice != "弃权":
                tally[choice] = tally.get(choice, 0) + 1

        winner = max(tally, key=tally.get) if tally else None
        passed = tally.get(winner, 0) >= threshold if winner else False

        # 公开投票结果
        result_text = f"投票结果：{'通过' if passed else '未通过'}（{tally.get(winner,0)}/{len(alive)}）"
        self.memory.add_private("dm", result_text)
        logger.info(f"投票: {result_text}")

        return {"passed": passed, "target": winner, "votes": ballot}

    @staticmethod
    def _normalize_vote(raw: str) -> str:
        """从各种回复中提取目标 ID：'我选P1' → 'p1'，'我同意' → '弃权'"""
        import re
        text = raw.strip()
        if not text or "弃权" in text:
            return "弃权"
        # 匹配 p1-p6（不区分大小写）
        m = re.search(r'[pP](\d)', text)
        if m:
            return f"p{m.group(1)}"
        return "弃权"

    # ── 玩家行动收集（内部）───────────────────────────────────────

    async def _collect_actions(
        self, ctx: GameContext, player_states: list[PlayerState], parallel: bool = False
    ) -> list[tuple[PlayerState, CoTOutput]]:
        """收集所有玩家的行动（通过 TurnManager）。parallel=True 并发执行。"""
        # 随机起始顺位发言：每轮随机选一个起点，然后按固定顺序轮转
        # 如起点=3 → [3,4,5,6,1,2]。每轮轮换，信息优势均摊。
        if self.config.shuffle_order:
            import random
            n = len(player_states)
            start = random.randrange(n)
            player_states = player_states[start:] + player_states[:start]

        async def player_act_callback(ctx: GameContext, player: PlayerState) -> CoTOutput:
            """单个玩家的行动回调（暂停检查已由 turn_manager 在 timeout 外完成）"""
            phase_label = "发言" if getattr(self.hooks, 'skip_parse', False) else "行动"
            logger.info(f"▶ {player.name}（{player.id}）{phase_label}中...")

            # 触发 before_player_act 钩子
            ctx = await self.hooks.before_player_act(ctx, player)
            self._ctx = ctx

            agent = self.players.get(player.id)
            if agent is None:
                raise ValueError(f"未找到玩家 Agent: {player.id}")

            # 注入私密消息到上下文（DM 上一轮塞的）
            notebook = self.memory.get_player_notebook(player.id)
            player.private_notebook = notebook

            return await agent.act(ctx)

        async def on_thinking_start(player: PlayerState) -> None:
            await self._emit(WSEventType.PLAYER_THINKING, {
                "player_id": player.id,
                "player_name": player.name,
            })

        async def on_action_done(player: PlayerState, action: Optional[CoTOutput]) -> None:
            if action:
                # 判断阶段
                is_real_speech = action.public_speech.strip() and action.public_speech != "."
                skip = getattr(self.hooks, 'skip_parse', False)
                is_speech_phase = self.config.two_phase and skip
                is_action_phase = self.config.two_phase and not skip

                if is_real_speech:
                    self.memory.add_public(player.id, action.public_speech)
                    await self._emit(WSEventType.PLAYER_SPEECH, {
                        "player_id": player.id,
                        "player_name": player.name,
                        "speech": action.public_speech,
                        "round": ctx.round.round_number,
                    })

                if is_speech_phase:
                    # Speech 阶段：推完整 CoT，隐藏 secret_action
                    cot_data = action.model_dump(mode="json")
                    cot_data["secret_action"] = ""
                    await self._emit(WSEventType.PLAYER_COT, {
                        "player_id": player.id,
                        "player_name": player.name,
                        "cot": cot_data,
                    })

                elif is_action_phase:
                    # Action 阶段：只更新 secret_action（规范化格式），保留 speech 分析
                    old = getattr(self, '_speech_cots', {}).get(player.id, {})
                    merged = {
                        "situation_assessment": old.get("situation_assessment", ""),
                        "internal_strategy": old.get("internal_strategy", ""),
                        "public_speech": old.get("public_speech", ""),
                        "secret_action": self._fmt_action(player.id, ctx),
                    }
                    await self._emit(WSEventType.PLAYER_COT, {
                        "player_id": player.id,
                        "player_name": player.name,
                        "cot": merged,
                    })

                elif not self.config.two_phase:
                    # 非两阶段游戏：正常推送
                    await self._emit(WSEventType.PLAYER_COT, {
                        "player_id": player.id,
                        "player_name": player.name,
                        "cot": action.model_dump(mode="json"),
                    })

                # 触发 after_player_act 钩子（先填 actions，后续 CoT 推送需要用到）
                self._ctx = await self.hooks.after_player_act(self._ctx, player, action)

                # 秘密行动进入私密记忆
                if action.secret_action.strip():
                    self.memory.add_private(
                        player.id,
                        f"🔐 你的秘密行动已提交: {action.secret_action}",
                    )

        return await self.turn_manager.collect_player_actions(
            ctx=ctx,
            player_states=player_states,
            action_callback=player_act_callback,
            on_thinking_start=on_thinking_start,
            on_action_done=on_action_done,
            should_stop=lambda: self._stop_event.is_set(),
            check_pause=self._wait_if_paused,
            parallel=parallel,
        )

    # ── 状态应用 ─────────────────────────────────────────────────

    def _apply_verdict(self, ctx: GameContext, verdict: DMVerdict) -> None:
        """
        将 DM 裁定结果应用到游戏状态。

        包括：
        - 更新玩家资源
        - 发送私密消息到记忆
        - 更新公共看板
        """
        # 1. 应用资源变化
        for rd in verdict.resource_delta:
            player = ctx.round.players.get(rd.player_id)
            if player:
                for resource_id, delta in rd.changes.items():
                    current = player.resources.get(resource_id, 0)
                    player.resources[resource_id] = current + delta

        # 2. 发送私密消息
        for pm in verdict.private_messages:
            self.memory.add_private(pm.player_id, f"📨 DM 私密消息: {pm.message}")
            if pm.player_id in ctx.round.players:
                ctx.round.players[pm.player_id].private_notebook.append(
                    f"第{verdict.round_number}轮 DM: {pm.message}"
                )

        # 3. 更新公共看板
        if verdict.global_narrative:
            ctx.round.public_log.append(
                f"📢 第{verdict.round_number}轮全局动态: {verdict.global_narrative}"
            )

    # ── 事件推送 ─────────────────────────────────────────────────

    async def night_action(self, action: str, player_id: str, player_name: str,
                           detail: str, target_id: str = "", round_num: int = 0):
        """引擎 API：推送夜晚行动到前端（仅供 hooks 使用，不入玩家上下文）"""
        await self._emit(WSEventType.NIGHT_ACTION, {
            "action": action,
            "player_id": player_id,
            "player_name": player_name,
            "detail": detail,
            "target_id": target_id,
            "round": round_num,
        })

    async def _emit(self, event_type: WSEventType, payload: dict[str, Any]) -> None:
        """推送 WebSocket 事件"""
        if self._headless or self._event_callback is None:
            return

        event = WSEvent(event_type=event_type, payload=payload)
        try:
            await self._event_callback(event)
        except Exception as e:
            logger.error(f"事件推送失败: {e}")

    # ── 清理 ─────────────────────────────────────────────────────

    async def _emit_game_over(self, ctx: GameContext, winner_id: str) -> None:
        """发送 GAME_OVER 事件，含排名列表"""
        wids = winner_id.split(",")
        wnames = [ctx.round.players[wid].name if wid in ctx.round.players else wid for wid in wids]
        # 构建排名列表（按分数降序）
        all_players = sorted(
            ctx.round.players.values(),
            key=lambda p: p.resources.get("gold", p.resources.get("points", 0)),
            reverse=True,
        )
        ranking = [{"name": p.name, "score": p.resources.get("gold", p.resources.get("points", 0))} for p in all_players]
        logger.info(f"🏆 游戏结束！胜者: {', '.join(wnames)}")
        await self._emit(WSEventType.GAME_OVER, {
            "winner_id": winner_id,
            "winner_name": "、".join(wnames),
            "ranking": ranking,
        })

    async def _teardown(self) -> None:
        """清理资源"""
        await close_http_client()
        logger.info("🧹 资源清理完成")


# ============================================================================
# 便捷函数
# ============================================================================

async def run_game(
    game_id: str,
    games_dir: str = "games",
    event_callback=None,
) -> ArenaResult:
    """
    运行一场游戏的便捷函数。

    Usage:
        result = await run_game("business_espionage")
        print(f"胜者: {result.winner_name}")
    """
    arena = Arena(
        game_id=game_id,
        games_dir=games_dir,
        event_callback=event_callback,
    )
    return await arena.run()
