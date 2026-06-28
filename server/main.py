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

# 🔑 加载 .env（exe 模式下存 exe 同目录，开发模式存项目根目录）
from pathlib import Path
from dotenv import load_dotenv
import sys as _sys
def _env_path() -> Path:
    if getattr(_sys, 'frozen', False):
        return Path(_sys.executable).parent / ".env"
    return Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_env_path())

import json
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.api import arena, events, games, models

app = FastAPI(
    title="MAGA Arena API",
    version="2.3.1",
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


# ── 回放 API ──
def _replay_games_root() -> Path:
    """EXE 模式优先用持久目录"""
    p = Path("games")
    if getattr(_sys, 'frozen', False):
        exe_games = Path(_sys.executable).parent / "games"
        if exe_games.exists():
            return exe_games
    return p


@app.get("/api/replays")
async def list_replays(game_id: str = ""):
    """列出所有回放文件，可按游戏筛选"""
    replays = []
    games_root = _replay_games_root()
    pattern = f"{game_id}/replays/*.json" if game_id else "*/replays/*.json"
    for f in sorted(games_root.glob(pattern), reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            replays.append({
                "id": str(f.relative_to(games_root)).replace("\\", "/"),
                "game_id": data.get("game_id", ""),
                "game_name": data.get("game_name", ""),
                "timestamp": data.get("timestamp", ""),
                "size": f.stat().st_size,
            })
        except Exception:
            pass
    return {"replays": replays[:50]}


class BatchDeleteBody(BaseModel):
    paths: list[str]

@app.post("/api/replays/batch-delete")
async def batch_delete_replays(body: BatchDeleteBody):
    """批量删除回放文件"""
    paths = body.paths
    if not paths:
        raise HTTPException(status_code=400, detail="paths 不能为空")
    games_root = _replay_games_root()
    deleted = []
    failed = []
    for path in paths:
        replay_path = games_root / path
        if not replay_path.exists():
            failed.append({"path": path, "reason": "文件不存在"})
            continue
        try:
            replay_path.resolve().relative_to(games_root.resolve())
        except ValueError:
            failed.append({"path": path, "reason": "非法的文件路径"})
            continue
        try:
            replay_path.unlink()
            deleted.append(path)
        except Exception as e:
            failed.append({"path": path, "reason": str(e)})
    return {"deleted": deleted, "failed": failed}


@app.get("/api/replays/{path:path}")
async def get_replay(path: str):
    """获取回放文件完整内容"""
    games_root = _replay_games_root()
    replay_path = games_root / path
    if not replay_path.exists():
        raise HTTPException(status_code=404, detail="回放文件不存在")
    with open(replay_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.delete("/api/replays/{path:path}")
async def delete_replay(path: str):
    """删除指定回放文件"""
    games_root = _replay_games_root()
    replay_path = games_root / path
    if not replay_path.exists():
        raise HTTPException(status_code=404, detail="回放文件不存在")
    try:
        replay_path.resolve().relative_to(games_root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="非法的文件路径")
    replay_path.unlink()
    return {"status": "deleted", "path": path}


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


@app.post("/api/setup/save-env")
async def save_env(body: dict):
    """首次启动保存 .env 配置"""
    env_path = _env_path()
    lines = []
    for key, val in body.items():
        if val and isinstance(val, str) and val.strip():
            lines.append(f"{key}={val.strip()}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 重新加载环境变量
    load_dotenv(override=True)
    return {"ok": True, "message": "配置已保存，刷新页面即可开始"}


# 检测是否有 .env，没有则返回首次配置标记
@app.get("/api/setup/status")
async def setup_status():
    env_path = _env_path()
    from engine.router import API_KEY_ENV_VARS
    has_env = env_path.exists()
    providers = [
        {"id": "relay", "name": "中转站 (Relay)", "env_key": "RELAY_API_KEY"},
        {"id": "openai", "name": "OpenAI", "env_key": "OPENAI_API_KEY"},
        {"id": "anthropic", "name": "Anthropic", "env_key": "ANTHROPIC_API_KEY"},
        {"id": "gemini", "name": "Google Gemini", "env_key": "GEMINI_API_KEY"},
        {"id": "deepseek", "name": "DeepSeek", "env_key": "DEEPSEEK_API_KEY"},
        {"id": "doubao", "name": "豆包", "env_key": "DOUBAO_API_KEY"},
        {"id": "zhipu", "name": "智谱 GLM", "env_key": "ZHIPU_API_KEY"},
        {"id": "qwen", "name": "通义千问 Qwen", "env_key": "QWEN_API_KEY"},
        {"id": "minimax", "name": "MiniMax", "env_key": "MINIMAX_API_KEY"},
        {"id": "hunyuan", "name": "腾讯混元", "env_key": "HUNYUAN_API_KEY"},
    ]
    return {"has_env": has_env, "providers": providers}


# 前端静态文件：打包后从 PyInstaller 临时目录读取，开发时从项目目录读取
import sys as _sys
_frontend_dist = None
if getattr(_sys, 'frozen', False):
    # PyInstaller 打包模式 — 搜索 _MEIPASS 下的 frontend/dist
    _meipass = Path(_sys._MEIPASS)
    for _candidate in [
        _meipass / "frontend" / "dist",
        _meipass / "dist",
    ]:
        if (_candidate / "index.html").exists():
            _frontend_dist = _candidate
            break
    if not _frontend_dist:
        # 兜底：遍历查找 index.html
        for _f in _meipass.rglob("index.html"):
            if "frontend" in str(_f) or "dist" in str(_f):
                _frontend_dist = _f.parent
                break
else:
    _frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"

if _frontend_dist and _frontend_dist.exists():
    print(f"[MAGA] 前端静态文件: {_frontend_dist}")
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")
else:
    print(f"[MAGA] ⚠️ 前端文件未找到，仅提供 API 服务。_MEIPASS={getattr(_sys, '_MEIPASS', 'N/A')}")
