"""
WebSocket 事件路由
====================
- WS   /ws                 — 主 WebSocket 连接
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from server.ws_manager import manager

router = APIRouter()
logger = logging.getLogger("maga.ws")


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    主 WebSocket 端点。

    客户端连接后保持长连接，引擎事件通过此通道实时推送。
    客户端可发送心跳 ping，服务端回复 pong。
    """
    await manager.connect(ws)

    try:
        while True:
            # 等待客户端消息（心跳 / 控制命令）
            data = await asyncio.wait_for(
                ws.receive_text(),
                timeout=30.0,
            )
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "message": "无效 JSON"}))
                continue

            msg_type = msg.get("type", "")

            if msg_type == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))

            elif msg_type == "subscribe":
                # 未来可扩展：订阅特定玩家的事件
                pass

            elif msg_type == "command":
                # 未来可扩展：前端控制命令（暂停/加速等）
                pass

            else:
                await ws.send_text(json.dumps({
                    "type": "ack",
                    "received": msg_type,
                }))

    except asyncio.TimeoutError:
        # 心跳超时，保持连接
        pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket 异常: {e}")
    finally:
        await manager.disconnect(ws)
