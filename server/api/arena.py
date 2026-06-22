"""
竞技场控制 API
================
- POST /api/arena/run       — 启动一场新游戏
- GET  /api/arena/status    — 获取当前游戏状态
- POST /api/arena/stop      — 停止当前游戏
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException

from engine.arena import Arena, ArenaResult
from engine.schema import WSEvent
from server.ws_manager import manager as ws_manager

router = APIRouter(prefix="/api/arena", tags=["arena"])

logger = logging.getLogger("maga.api.arena")

# 当前运行的 Arena 实例
_current_arena: Optional[Arena] = None
_current_task: Optional[asyncio.Task] = None
_last_result: Optional[ArenaResult] = None


async def _event_callback(event: WSEvent) -> None:
    """引擎事件 → WebSocket 广播"""
    await ws_manager.broadcast(event)


@router.post("/run")
async def run_game(game_id: str, background_tasks: BackgroundTasks):
    """
    启动一场新游戏（后台运行）。

    查询参数:
        game_id: 游戏目录名，如 "business_espionage"
    """
    global _current_arena, _current_task, _last_result

    if _current_task and not _current_task.done():
        raise HTTPException(status_code=409, detail="已有游戏正在运行中")

    # 快速检查：至少配了一个 API Key
    import os
    key_envs = [
        "RELAY_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY", "DEEPSEEK_API_KEY",
    ]
    has_key = any(os.getenv(k, "") for k in key_envs)
    if not has_key:
        raise HTTPException(
            status_code=400,
            detail="未检测到任何 API Key。请编辑 .env 文件，至少填入一个 API Key（如 RELAY_API_KEY）。",
        )

    arena = Arena(
        game_id=game_id,
        event_callback=_event_callback,
    )
    _current_arena = arena

    async def run_in_background():
        global _last_result
        try:
            _last_result = await arena.run()
        except Exception as e:
            logger.error(f"游戏运行异常: {e}")
            from engine.schema import WSEvent, WSEventType
            await ws_manager.broadcast(WSEvent(
                event_type=WSEventType.ENGINE_ERROR,
                payload={"message": str(e)},
            ))
            raise

    _current_task = asyncio.create_task(run_in_background())

    return {
        "status": "started",
        "game_id": game_id,
        "message": f"游戏 '{game_id}' 已启动",
    }


@router.get("/status")
async def get_status():
    """获取当前运行状态"""
    global _current_task, _last_result, _current_arena

    if _current_task is None:
        return {"status": "idle", "message": "无游戏运行"}

    if _current_task.done():
        if _current_task.exception():
            return {
                "status": "error",
                "error": str(_current_task.exception()),
            }
        result = _last_result
        if result:
            return {
                "status": "finished",
                "winner_id": result.winner_id,
                "winner_name": result.winner_name,
                "total_rounds": result.total_rounds_played,
                "duration_seconds": round(result.duration_seconds, 1),
                "total_tokens": result.total_tokens,
            }
        return {"status": "finished"}

    # 检查暂停状态
    if _current_arena is not None and not _current_arena._pause_event.is_set():
        return {
            "status": "paused",
            "message": "游戏已暂停",
        }

    return {
        "status": "running",
        "message": "游戏正在运行中...",
    }


@router.post("/stop")
async def stop_game():
    """停止当前游戏"""
    global _current_arena, _current_task

    if _current_task is None or _current_task.done():
        return {"status": "nothing_to_stop"}

    # 方式1：发送停止信号（下一轮检测后退出）
    if _current_arena is not None:
        _current_arena.request_stop()

    # 方式2：取消asyncio任务（打断当前await）
    _current_task.cancel()
    try:
        await asyncio.wait_for(_current_task, timeout=10.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass

    _current_arena = None
    _current_task = None
    return {"status": "stopped", "message": "游戏已停止"}


@router.post("/pause")
async def pause_game():
    """暂停当前游戏"""
    global _current_arena, _current_task

    if _current_task is None or _current_task.done():
        return {"status": "nothing_to_pause", "message": "无游戏运行中"}

    if _current_arena is not None:
        _current_arena.request_pause()
        return {"status": "paused", "message": "游戏已暂停（当前玩家行动完成后生效）"}
    return {"status": "error", "message": "内部错误"}


@router.post("/resume")
async def resume_game():
    """恢复暂停的游戏"""
    global _current_arena

    if _current_arena is None:
        return {"status": "nothing_to_resume", "message": "无游戏运行中"}

    _current_arena.request_resume()
    return {"status": "resumed", "message": "游戏已恢复"}


@router.post("/step")
async def step_game():
    """单步推进（暂停状态下执行一步后自动暂停）"""
    global _current_arena

    if _current_arena is None:
        return {"status": "nothing_to_step", "message": "无游戏运行中"}

    _current_arena.request_step()
    return {"status": "stepped", "message": "已推进单步"}


@router.post("/next-round")
async def next_round():
    """推进一整轮（本轮跑完，下轮开始前自动暂停）"""
    global _current_arena

    if _current_arena is None:
        return {"status": "nothing_to_advance", "message": "无游戏运行中"}

    _current_arena.request_next_round()
    return {"status": "advancing", "message": "正在推进整轮..."}


@router.post("/auto")
async def auto_mode():
    """切换为自动模式（轮间不暂停，连续跑）"""
    global _current_arena

    if _current_arena is None:
        return {"status": "nothing_to_auto", "message": "无游戏运行中"}

    _current_arena.request_auto_mode()
    return {"status": "auto", "message": "已切换为自动模式"}


@router.get("/state")
async def get_state():
    """获取当前游戏状态——前端断线重连时恢复界面"""
    global _current_arena
    if _current_arena is None or _current_arena._ctx is None:
        return {"status": "no_game", "ctx": None}
    return {
        "status": "running",
        "ctx": _current_arena._ctx.model_dump(mode="json"),
    }
