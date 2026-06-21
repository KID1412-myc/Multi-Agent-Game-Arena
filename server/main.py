"""
MAGA Server — FastAPI 主入口
================================
启动: uv run uvicorn server.main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

# 🔧 必须在所有第三方库之前：强制 socket 只走 IPv4
import socket as _socket
_orig = _socket.getaddrinfo
_socket.getaddrinfo = lambda h, p, f=0, *a, **kw: _orig(h, p, _socket.AF_INET, *a, **kw)

# 🔑 加载 .env
from dotenv import load_dotenv
load_dotenv()

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.api import arena, events, games, models

app = FastAPI(
    title="MAGA Arena API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(games.router)
app.include_router(arena.router)
app.include_router(events.router)
app.include_router(models.router)


@app.get("/")
async def root():
    return {"name": "MAGA", "version": "1.0.0", "status": "running", "docs": "/docs"}


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/models/test-connection")
async def test_connection(body: dict | None = None):
    """
    测试模型连接。接受 JSON body:
      provider: 厂商名（如 relay, openai, deepseek, doubao 等）
      model: 模型名或接入点 ID
      api_key: 可选，不传则从环境变量读取
      api_base: 可选，不传则从环境变量或默认值读取
    不传 body 时默认测试 relay。
    """
    import os
    from engine.schema import ModelProvider
    from engine.router import API_KEY_ENV_VARS, BASE_URL_ENV_VARS, DEFAULT_BASE_URLS

    body = body or {}
    provider_str = body.get("provider", "relay")
    model = body.get("model", "gpt-4o").strip()
    api_key = (body.get("api_key") or "").strip()
    api_base = (body.get("api_base") or "").strip()

    # 解析 provider
    try:
        provider = ModelProvider(provider_str)
    except ValueError:
        return {"ok": False, "error": f"不支持的厂商: {provider_str}"}

    # 回退到环境变量
    if not api_key:
        api_key = os.getenv(API_KEY_ENV_VARS.get(provider, ""), "").strip()
    if not api_base:
        api_base = os.getenv(BASE_URL_ENV_VARS.get(provider, ""), "").strip()
    if not api_base:
        api_base = DEFAULT_BASE_URLS.get(provider, "")

    if not api_base:
        return {"ok": False, "error": f"未找到 {provider_str} 的 API Base URL，请在 .env 中设置对应环境变量"}
    if not api_key:
        return {"ok": False, "error": f"未找到 {provider_str} 的 API Key，请设置环境变量 {API_KEY_ENV_VARS.get(provider, '')}"}
    if not model:
        return {"ok": False, "error": "model 不能为空"}

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key, base_url=api_base, timeout=10, max_retries=0)
        try:
            await client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": "ping"}], max_tokens=1)
            return {"ok": True, "detail": f"{provider_str} / {model} — 连接成功"}
        except Exception as e:
            msg = str(e)
            if any(k in msg.lower() for k in ["401", "403", "invalid", "unauthorized"]):
                return {"ok": False, "error": f"Key 无效 — 请检查 .env 中 {API_KEY_ENV_VARS.get(provider, '')} 是否正确"}
            return {"ok": False, "error": f"{type(e).__name__}: {msg[:300]}"}
        finally:
            await client.close()
    except Exception as e:
        return {"ok": False, "error": str(e)}


frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
