# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MAGA Arena — 单文件 exe，不含 .env"""

import os
from pathlib import Path

ROOT = Path('.')

# ── 收集所有游戏文件 ──
game_files = []
games_dir = ROOT / 'games'
for game in games_dir.iterdir():
    if game.is_dir() and not game.name.startswith('_') and not game.name.startswith('.'):
        for f in game.rglob('*'):
            if f.suffix in ('.json', '.jinja2', '.py', '.md'):
                src = str(f).replace('\\', '/')
                dst = str(f.parent).replace('\\', '/')
                game_files.append((src, dst))

# ── 收集前端文件 ──
frontend_dist = ROOT / 'frontend' / 'dist'
frontend_files = []
if frontend_dist.exists():
    for f in frontend_dist.rglob('*'):
        if f.is_file():
            src = str(f).replace('\\', '/')
            dst = str(f.parent).replace('\\', '/')
            frontend_files.append((src, dst))

all_data = game_files + frontend_files

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=all_data,
    hiddenimports=[
        'engine', 'engine.schema', 'engine.hooks', 'engine.arena',
        'engine.memory', 'engine.router', 'engine.player_agent',
        'engine.dm_interface', 'engine.state_machine', 'engine.turn_manager',
        'server', 'server.main', 'server.api', 'server.api.arena',
        'server.api.events', 'server.api.games', 'server.api.models',
        'dotenv', 'pydantic', 'fastapi', 'uvicorn', 'openai',
        'httpx', 'websockets', 'jinja2', 'starlette',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['numpy', 'scipy', 'pandas', 'pyarrow', 'openpyxl', 'sqlalchemy',
              'matplotlib', 'PIL', 'cv2', 'torch', 'tensorflow', 'sklearn',
              'pytest', 'psycopg2', 'psycopg', 'django', 'flask'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MAGA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
