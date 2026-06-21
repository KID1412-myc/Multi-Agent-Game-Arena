# 🏟️ MAGA v1.0 — Multi-Agent Game Arena

通用多 Agent 异步博弈沙盒引擎。换配置文件 = 换游戏，零代码。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 当前状态

| 游戏 | 状态 |
|------|------|
| 🪙 **贪婪矿场：零和掠夺** | ✅ 可玩 |
| 💣 炸弹项圈·积分欺诈赛 | 🔒 开发中 |
| 🔬 商业谍战：量子芯片之争 | 🔒 开发中 |

---

## 快速开始

### 1. 配置 .env

```bash
cp .env.example .env
# 编辑 .env，填入 API Keys
```

### 2. 启动

```bash
# 双击 start.bat（Windows）
# 或
python start.py
```

自动杀掉旧进程、清缓存、启动后端（8000）+ 前端（5173）、打开浏览器。

### 3. 开始

选 "贪婪矿场" → 启动。游戏自动每轮暂停，点 **下一轮** 推进，或点 **自动** 连续跑。

---

## 游戏机制

### 贪婪矿场：零和掠夺

6 名矿工，每人 10 金币，5 轮。每轮先公开发言，再暗箱行动（三选一）：

| 编码 | 行动 |
|------|------|
| `DEV` | 发育：挖矿 |
| `DEF` | 防御：架盾 |
| `LOOT-pX` | 掠夺：抢玩家 pX |

结算矩阵纯 Python 计算，不依赖 LLM。**3 人以上围殴破盾**——攻守平衡靠博弈。

---

## 项目结构

```
├── engine/              # 核心引擎
│   ├── schema.py        # Pydantic 数据类型
│   ├── router.py        # 8 厂商统一路由（含 json_mode 自动回退）
│   ├── dm_interface.py  # DM 裁判
│   ├── player_agent.py  # 玩家 Agent（完整 CoT + 极简决策双模式）
│   ├── memory.py        # 热/温/冷三层记忆
│   ├── hooks.py         # 生命周期钩子（支持 memory 注入）
│   ├── state_machine.py # 阶段状态机
│   ├── turn_manager.py  # 回合管理器
│   └── arena.py         # 主循环（两阶段/暂停/单步/最终感言）
├── games/
│   ├── greedy_mine/     # 🪙 贪婪矿场（可用）
│   ├── bomb_collar/     # 💣 炸弹项圈（开发中）
│   ├── business_espionage/ # 🔬 商业谍战（开发中）
│   └── _template/       # 新游戏模板
├── frontend/            # React + TypeScript，白底简约风格
├── server/              # FastAPI + WebSocket
│   ├── api/             # games / arena / events / models
│   └── ws_manager.py    # WebSocket 广播
├── config/              # 全局设置 + 模型列表
├── tests/               # 36 个测试，100% 通过
├── start.bat            # 一键启动
├── start.py             # 启动器
└── run.py               # 后端 wrapper（杀旧进程 + 清缓存）
```

---

## 创建新游戏

```bash
cp -r games/_template games/my_game
# 编辑 config.json → 定义玩家、资源、轮数
# 编辑 hooks.py → 自定义游戏逻辑
# 编辑 dm_prompt.jinja2 → DM 提示词
# 编辑 player_prompt.jinja2 → 玩家提示词
# 刷新前端，自动出现
```

Hooks 可覆写 8 个生命周期节点——颜色分配、行动解析、矩阵结算、胜负判定均可由 hooks 实现，引擎不碰游戏逻辑。

---

## 技术栈

| 层 | 技术 |
|------|------|
| 后端 | Python 3.13, asyncio, Pydantic v2, httpx, openai SDK |
| API | FastAPI, WebSocket |
| 前端 | React 19, TypeScript, Vite, Zustand, Framer Motion, Recharts |
| 测试 | pytest 36 用例 |

---

## 路线图

- 炸弹项圈完成（审判/手枪/三局结算）
- 并发流（暗标模式）
- 跨局积分排行
- 游戏录像回放
- Docker 部署
