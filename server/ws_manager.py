"""
MAGA WebSocket 连接管理器
============================
管理所有前端 WebSocket 连接，负责广播引擎事件。

Usage:
    from server.ws_manager import WebSocketManager
    manager = WebSocketManager()
    await manager.broadcast(event)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from engine.schema import WSEvent

logger = logging.getLogger("maga.ws")


class WebSocketManager:
    """
    WebSocket 连接管理器。

    - 维护所有活跃连接
    - 支持广播和单播
    - 自动处理断线和重连
    """

    def __init__(self):
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        """接受新的 WebSocket 连接"""
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
        logger.info(f"WebSocket 连接已建立 (当前连接数: {len(self._connections)})")

    async def disconnect(self, ws: WebSocket) -> None:
        """断开 WebSocket 连接"""
        async with self._lock:
            self._connections.discard(ws)
        logger.info(f"WebSocket 连接已断开 (当前连接数: {len(self._connections)})")

    async def broadcast(self, event: WSEvent) -> None:
        """
        向所有连接的客户端广播事件。

        Args:
            event: 要广播的 WSEvent
        """
        data = json.dumps(
            {
                "event_type": event.event_type.value,
                "payload": event.payload,
                "timestamp": event.timestamp.isoformat(),
            },
            ensure_ascii=False,
        )

        async with self._lock:
            dead: list[WebSocket] = []
            for ws in self._connections:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.append(ws)

            # 清理断开的连接
            for ws in dead:
                self._connections.discard(ws)

        if dead:
            logger.info(f"清理了 {len(dead)} 个死连接")

    async def send_to(self, ws: WebSocket, event: WSEvent) -> None:
        """向单个客户端发送事件"""
        data = json.dumps(
            {
                "event_type": event.event_type.value,
                "payload": event.payload,
                "timestamp": event.timestamp.isoformat(),
            },
            ensure_ascii=False,
        )
        try:
            await ws.send_text(data)
        except Exception:
            await self.disconnect(ws)

    @property
    def active_connections(self) -> int:
        return len(self._connections)


# 全局单例
manager = WebSocketManager()
