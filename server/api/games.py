"""
游戏管理 API
=============
- GET  /api/games           — 列出所有可用游戏
- GET  /api/games/{id}      — 获取游戏详情
- GET  /api/games/{id}/config — 获取游戏配置（JSON）
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/games", tags=["games"])

# PyInstaller 打包兼容：EXE 模式下优先使用 exe 同目录下的持久副本
_GAMES_DIR = Path("games")
_WRITABLE_DIR: Path | None = None
if not _GAMES_DIR.exists():
    import sys as _sys
    if getattr(_sys, 'frozen', False):
        _frozen_games = Path(_sys._MEIPASS) / "games"
        _persist_games = Path(_sys.executable).parent / "games"
        if _frozen_games.exists():
            _GAMES_DIR = _frozen_games
            # 首次启动时把 _MEIPASS 的游戏复制到 exe 同目录，后续优先读那里
            if not _persist_games.exists():
                import shutil as _shutil
                _shutil.copytree(_frozen_games, _persist_games)
            _GAMES_DIR = _persist_games
        _WRITABLE_DIR = _persist_games
GAMES_DIR = _GAMES_DIR


@router.get("")
async def list_games():
    """列出所有可用游戏"""
    if not GAMES_DIR.exists():
        return {"games": []}

    games: list[dict] = []
    for d in sorted(GAMES_DIR.iterdir()):
        if d.is_dir() and not d.name.startswith("_") and not d.name.startswith("."):
            config_path = d / "config.json"
            if config_path.exists():
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    games.append({
                        "id": cfg.get("game_id", d.name),
                        "name": cfg.get("name", d.name),
                        "version": cfg.get("version", "1.0"),
                        "description": cfg.get("description", ""),
                        "players": len(cfg.get("players", [])),
                        "rounds": cfg.get("total_rounds", 0),
                        "mode": cfg.get("mode", "sequential"),
                        "locked": cfg.get("locked", False),
                    })
                except Exception:
                    games.append({
                        "id": d.name,
                        "name": d.name,
                        "version": "?",
                        "description": "配置读取失败",
                        "players": 0,
                        "rounds": 0,
                        "mode": "?",
                    })

    return {"games": games}


@router.get("/{game_id}")
async def get_game(game_id: str):
    """获取游戏详情"""
    config_path = GAMES_DIR / game_id / "config.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"游戏 {game_id} 不存在")

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 读取规则文件
    rules = ""
    rules_path = GAMES_DIR / game_id / "rules.md"
    if rules_path.exists():
        with open(rules_path, "r", encoding="utf-8") as f:
            rules = f.read()

    return {
        "config": cfg,
        "rules": rules,
    }


@router.get("/{game_id}/config")
async def get_game_config(game_id: str):
    """获取游戏原始配置 JSON"""
    config_path = GAMES_DIR / game_id / "config.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"游戏 {game_id} 不存在")

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/{game_id}/rules")
async def get_game_rules(game_id: str):
    """获取游戏规则文档（RULES.md）"""
    for name in ("RULES.md", "rules.md", "README.md", "readme.md"):
        rules_path = GAMES_DIR / game_id / name
        if rules_path.exists():
            return {"game_id": game_id, "rules": rules_path.read_text(encoding="utf-8")}
    raise HTTPException(status_code=404, detail=f"游戏 {game_id} 暂无规则文档")


@router.put("/{game_id}/config")
async def save_game_config(game_id: str, config: dict):
    """
    保存游戏配置 JSON。

    前端编辑模型/玩家配置后调用此接口写回 config.json。
    只允许修改：dm_model, dm_provider, players 的 model/provider/name
    """
    config_path = GAMES_DIR / game_id / "config.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail=f"游戏 {game_id} 不存在")

    # 读取现有配置
    with open(config_path, "r", encoding="utf-8") as f:
        existing = json.load(f)

    # 只更新允许的字段
    allowed_fields = ["dm_model", "dm_provider", "players"]
    for key in allowed_fields:
        if key in config:
            existing[key] = config[key]

    # 写回
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=4)

    return {"status": "ok", "message": f"游戏 '{game_id}' 配置已保存"}
