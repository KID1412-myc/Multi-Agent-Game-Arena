#!/usr/bin/env python3
"""
交互式创建新游戏向导
======================
引导用户输入信息，自动生成 games/<new_game>/ 目录下的所有文件。

Usage:
    python scripts/new_game.py
"""

import json
import os
import shutil
from pathlib import Path


def main():
    print("🏟️  MAGA — 新建游戏向导")
    print("=" * 50)

    # 1. 基本信息
    game_id = input("游戏 ID（英文，用于目录名）: ").strip().lower().replace(" ", "_")
    if not game_id:
        print("❌ 游戏 ID 不能为空")
        return

    target_dir = Path("games") / game_id
    if target_dir.exists():
        overwrite = input(f"游戏 {game_id} 已存在，是否覆盖？(y/N): ").strip().lower()
        if overwrite != "y":
            print("👋 已取消")
            return
        shutil.rmtree(target_dir)

    game_name = input("游戏名称（中文）: ").strip() or game_id
    description = input("游戏描述: ").strip() or ""
    num_players = int(input("玩家数量 (2-12): ").strip() or "4")
    num_rounds = int(input("总轮数 (0=不限): ").strip() or "10")
    mode = input("行动模式 (sequential/parallel): ").strip() or "sequential"

    # 2. 资源定义
    print("\n📊 定义游戏资源（输入空行结束）")
    resources = []
    while True:
        r_id = input("  资源ID (如 capital): ").strip()
        if not r_id:
            break
        r_label = input("  资源标签 (如 资金): ").strip()
        r_unit = input("  资源单位 (如 亿元): ").strip()
        r_icon = input("  资源图标 (如 💰): ").strip() or "🪙"
        resources.append({
            "id": r_id,
            "label": r_label,
            "unit": r_unit,
            "icon": r_icon,
        })

    # 3. 玩家定义
    print(f"\n👤 定义 {num_players} 个玩家")
    players = []
    for i in range(num_players):
        print(f"\n  玩家 {i+1}:")
        p_id = input(f"    ID (如 p{i+1}): ").strip() or f"p{i+1}"
        p_name = input(f"    名称: ").strip() or f"玩家{i+1}"
        p_model = input(f"    模型 (如 gpt-5.4): ").strip() or "gpt-5.4"
        p_provider = input(f"    厂商 (openai/anthropic/gemini/deepseek): ").strip() or "openai"
        p_secret = input(f"    秘密身份描述: ").strip() or "你是这场博弈的参与者。"

        initial_resources = {}
        for r in resources:
            val = input(f"    初始{r['label']} ({r['id']}): ").strip()
            if val:
                try:
                    initial_resources[r['id']] = float(val)
                except ValueError:
                    initial_resources[r['id']] = 0

        players.append({
            "id": p_id,
            "name": p_name,
            "model": p_model,
            "provider": p_provider,
            "secret_identity": p_secret,
            "initial_resources": initial_resources,
        })

    # 4. DM 配置
    dm_model = input(f"\n🧙 DM 模型 (默认 gpt-5.4): ").strip() or "gpt-5.4"
    dm_provider = input(f"DM 厂商 (默认 openai): ").strip() or "openai"

    # 5. 生成文件
    target_dir.mkdir(parents=True, exist_ok=True)

    # config.json
    config = {
        "game_id": game_id,
        "name": game_name,
        "version": "1.0",
        "description": description,
        "min_players": max(2, num_players - 2),
        "max_players": num_players + 2,
        "total_rounds": num_rounds,
        "mode": mode,
        "language": "zh-CN",
        "turn_timeout_seconds": 60,
        "dm_model": dm_model,
        "dm_provider": dm_provider,
        "resources": resources,
        "players": players,
        "hooks": None,
        "state_machine": None,
        "schema_override": None,
    }

    with open(target_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)

    # rules.md
    rules_content = f"""# {game_name}

## 游戏概述
{description}

## 胜利条件
（在此编写胜利条件）

## 资源系统
"""
    for r in resources:
        rules_content += f"- **{r['label']}** {r['icon']}: 描述\n"
    rules_content += f"""
## 玩家列表
"""
    for p in players:
        rules_content += f"- **{p['name']}** ({p['id']}): {p['model']}\n"

    with open(target_dir / "rules.md", "w", encoding="utf-8") as f:
        f.write(rules_content)

    # Jinja2 模板
    from_dir = Path("games") / "_template"
    for tmpl_file in ["dm_prompt.jinja2", "player_prompt.jinja2"]:
        src = from_dir / tmpl_file
        if src.exists():
            shutil.copy(src, target_dir / tmpl_file)

    print(f"\n✅ 游戏 '{game_name}' 创建成功！")
    print(f"   路径: {target_dir}")
    print(f"   启动后在前端选择 '{game_name}' 即可开始")


if __name__ == "__main__":
    main()
