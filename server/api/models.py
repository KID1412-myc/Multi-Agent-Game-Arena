"""
模型管理 API
=============
- GET  /api/models           — 列出所有可选模型
- GET  /api/models/providers — 列出所有厂商
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(prefix="/api/models", tags=["models"])

MODELS_FILE = Path("config/models.json")


@router.get("")
async def list_models():
    """列出所有可用模型（按厂商分组）"""
    if not MODELS_FILE.exists():
        return {"models": {}, "providers": ["relay", "openai", "anthropic", "gemini", "deepseek", "doubao", "zhipu", "qwen"]}

    with open(MODELS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "models": data.get("models", {}),
        "providers": list(data.get("models", {}).keys()),
    }


@router.get("/flat")
async def list_models_flat():
    """列出所有模型（扁平列表，方便下拉菜单）"""
    if not MODELS_FILE.exists():
        return {"models": []}

    with open(MODELS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    flat: list[dict] = []
    for provider, models in data.get("models", {}).items():
        for m in models:
            flat.append({
                "id": m["id"],
                "name": m["name"],
                "provider": provider,
                "supports_json_mode": m.get("supports_json_mode", True),
            })

    return {"models": flat}


@router.get("/providers")
async def list_providers():
    """列出所有可用厂商"""
    providers = [
        {"id": "relay", "name": "中转站 (Relay)", "description": "api2d / openai-sb / 自定义网关"},
        {"id": "openai", "name": "OpenAI", "description": "GPT-4o / GPT-5.4 / o4 系列"},
        {"id": "anthropic", "name": "Anthropic", "description": "Claude Opus / Sonnet / Haiku 系列"},
        {"id": "gemini", "name": "Google Gemini", "description": "Gemini 3.0 Pro / Flash 系列"},
        {"id": "deepseek", "name": "DeepSeek", "description": "DeepSeek-V3 / Reasoner"},
        {"id": "doubao", "name": "豆包 (火山引擎)", "description": "豆包 Pro / Lite"},
        {"id": "minimax", "name": "MiniMax", "description": "Abab7 系列"},
        {"id": "zhipu", "name": "智谱 GLM", "description": "GLM-4 Plus / Flash"},
        {"id": "qwen", "name": "通义千问 Qwen", "description": "Qwen3.7 Plus / Max"},
    ]
    return {"providers": providers}
