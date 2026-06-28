# 🏟️ MAGA — Multi-Agent Game Arena

> **让 AI 大模型同台博弈的沙盒引擎。换一份配置文件 = 换一个游戏。**

9 个不同厂商的 LLM（ChatGPT、Claude、豆包、通义千问、混元、Gemini、DeepSeek、Kimi、MiniMax）戴着不同的"面具"在同一场游戏里发言、结盟、欺骗、背叛。你坐在浏览器前观战——看它们的内心算计、秘密行动、互相投票。

<p align="center">
  <em>发言 → 策略 → 行动 → DM 裁判 → 循环</em>
</p>

---

## 🎮 游戏列表

| 游戏 | 人数 | 回合 | 简介 | 状态 |
|------|------|------|------|------|
| 🪙 **贪婪矿场 v2** | 6 人 | 6 | 三选一（挖矿/防御/掠夺），末位淘汰，围殴破盾 | ✅ 可玩 |
| 💣 **炸弹项圈·简化版** | 6 人 | 10 | 1 名欺诈师混入 5 名平民，猜颜色、指认审判、环形可见 | ✅ 可玩 |
| 🙈 **盲投暗标** | 6 人 | 6 | 每轮暗标出价 0-10，唯一最高者赢走奖池，平票全废 | ✅ 可玩 |
| 💰 **分赃** | 6 人 | 6 | 6 种秘密目标，3 轮盲盒后信息逐轮公开，出价超赃款全员 0 分 | ✅ 可玩 |
| 🐺 **狼人杀** | 9 人 | 不限 | 3 狼 + 预言家 + 女巫 + 猎人 + 3 平民，昼夜交替，刀验毒投票 | ✅ 可玩 |
| 🏇 **赛马博弈** | 6 人 | 1 | 竞猜哪匹马得票最少——逆向博弈，N 阶推理 | 🔒 锁定 |
| 🔬 **商业谍战** | 6 人 | 12 | 量子芯片专利争夺，5 种资源，安插内鬼、窃取数据、秘密结盟 | 🔒 锁定 |
| 🪙 贪婪矿场 v1 | 6 人 | 6 | 旧版（旧引擎路径） | 🔒 锁定 |
| 💣 炸弹项圈 v1 | 6 人 | 10 | 旧版（三局制 + 审判 + 手枪） | 🔒 锁定 |

> **🔒 锁定** = 仅开发者可见。修改 `games/<game>/config.json` 中 `"locked": false` 即可解锁。

---

## ⚡ 快速开始

### 方式一：下载 EXE（推荐，无需 Python / Node.js）

1. 打开 [Releases](https://github.com/KID1412-myc/Multi-Agent-Game-Arena/releases) 页面
2. 下载最新版 `MAGA.exe`（~20MB）
3. 双击运行，首次启动弹出配置页填写 API Key
4. 之后每次双击即可

### 方式二：源码启动（开发者）

前提：Python 3.11+、Node.js 18+

```bash
git clone https://github.com/KID1412-myc/Multi-Agent-Game-Arena.git
cd Multi-Agent-Game-Arena
# 双击 start.bat
```

首次启动自动：检查环境 → 安装依赖 → 复制 `.env.example` → 弹出记事本填 API Key → 启动。

### 自行打包

```bash
cd frontend && npm run build && cd ..
python -m PyInstaller maga.spec --noconfirm
# 输出：dist/MAGA.exe
```

或推送 tag（`git tag v1.0.0 && git push origin v1.0.0`）让 GitHub Actions 自动构建并发布到 Releases。

---

## 🏗️ 架构

```
engine/              # 核心引擎（零游戏逻辑——只提供基础设施）
  arena.py            主竞技场、引擎 API（hooks 通过 self.arena 调用）
  player_agent.py     玩家 Agent、CoT 强制思维链、_act_quick 极简决策
  router.py           多厂商统一路由（11 个 provider）
  memory.py           热 / 温 / 冷三层记忆系统
  dm_interface.py     DM 裁判接口（3 层防御：校验→自修复→兜底）
  hooks.py            生命周期钩子基类（8 个切入点）
  state_machine.py    有限状态机
  turn_manager.py     回合管理（顺序 / 并发）
  schema.py           全项目通用数据模型（Pydantic v2）

games/               # 游戏 = 配置 + 规则（每个文件夹一个游戏）
  _template/          新游戏模板（从这里开始创建新游戏）
  greedy_mine_v2/     贪婪矿场 v2 ← 最稳定的参考实现
  bomb_collar_v2/     炸弹项圈 v2
  blind_bidding/      盲投暗标
  loot_share/         分赃
  werewolf/           狼人杀
  horse_race/         赛马博弈
  business_espionage/ 商业谍战
  greedy_mine/        贪婪矿场 v1（旧路径）
  bomb_collar/        炸弹项圈 v1（旧路径）

frontend/            # React 19 + TypeScript + Zustand + Tailwind v4
server/              # FastAPI + WebSocket
config/              # 全局默认配置
  defaults.json       默认 9 个模型站位
tests/               # pytest（136 个纯逻辑单元测试）
```

### 两种游戏开发路径

| 路径 | 特点 | 使用场景 |
|------|------|----------|
| **v2**（推荐） | Hook 覆写 `run_round()`，完全自主编排回合。通过 `self.arena` 调用引擎 API | 所有新游戏 |
| **v1**（旧） | 引擎主循环写死"发言→行动→DM"，Hook 只能通过 8 个生命周期钩子介入 | 不再使用 |

### 引擎 API（v2 Hook 可用）

| API | 说明 |
|------|------|
| `arena.collect_speeches(ctx, players)` | 全员顺序发言 |
| `arena.collect_actions(ctx, players, parallel=True)` | 全员行动（并发） |
| `arena.dm_judge(ctx, actions)` | 调用 DM 裁判 |
| `arena.vote(title, ctx, targets, prompt, parallel=True)` | 发起投票（过半制） |
| `arena.eliminate(ctx, player_id)` | 淘汰玩家 |
| `arena.emit_state(ctx)` | 推送完整状态到前端 |
| `arena.save_speech_cots(ctx)` | 保存发言阶段思维链 |
| `arena.private_msg(player_id, text)` | 向玩家发送私密消息 |
| `arena.night_action(...)` | 推送夜晚行动到前端（狼人杀专用） |

---

## 🧠 核心机制

### 强制思维链（Forced CoT）

每个玩家在发言前必须输出 4 段 JSON：

```json
{
  "situation_assessment": "对当前局势的客观分析……",
  "internal_strategy": "基于局势的内心策略……",
  "public_speech": "实际说出口的话（可能是谎言）",
  "secret_action": "只给 DM 看的秘密行动"
}
```

利用 LLM 的自回归特性——在输出 `public_speech` 前必须先完成 `situation_assessment` 和 `internal_strategy`，从而**强制拔高博弈智商**。

### 两阶段模式

1. **发言阶段**：全员顺序发言，写完整 CoT
2. **行动阶段**：全员并发提交秘密行动（`_act_quick` 极简模式），温度 0.1，只返回必要信息

发言阶段的分析被保存下来，合并到最终展示中——前端可以看到每个人的"嘴上说的"和"心里想的"。

### 三级记忆

| 层级 | 窗口 | 内容 | 可见范围 |
|------|------|------|----------|
| L1 热记忆 | 120 条 | 近期完整对话 | 玩家上下文 |
| L2 温记忆 | 1 条 | DM 每轮摘要 | 玩家上下文（部分游戏已禁用） |
| L3 冷记忆 | 不限 | `#CRITICAL` 关键事件 | 仅 DM 上下文 |
| 私密笔记本 | 不限 | `add_private` 私密消息 | 仅指定玩家 |

> ⚠️ `public_log` ≠ 热记忆。`public_log` 只决定前端显示，不进 LLM 上下文。要让玩家知道某件事，必须用 `add_private` 或 `add_public`。

---

## 🎨 创建新游戏

```bash
# 1. 从模板复制
cp -r games/_template games/my_game

# 2. 编辑 config.json
#    - game_id, name, total_rounds
#    - players（名字、模型、初始资源）
#    - resources（资源类型定义）

# 3. 编写 hooks.py
#    覆写 run_round(ctx, round_num) → bool
#    在方法中调用 arena API 编排回合

# 4. 编写提示词
#    dm_prompt.jinja2   — DM 裁判提示词
#    player_prompt.jinja2 — 玩家提示词

# 5. 编写规则（可选）
#    RULES.md — 前端"规则"按钮可查看
```

最小示例（`hooks.py`）：

```python
from engine.hooks import GameHooks

class MyGameHooks(GameHooks):
    async def run_round(self, ctx, round_num):
        a = self.arena
        alive = [p for p in ctx.round.players.values() if p.is_alive]

        # 1. 发言
        await a.collect_speeches(ctx, alive)

        # 2. 行动
        actions = await a.collect_actions(ctx, alive, parallel=True)

        # 3. 裁判
        verdict = await a.dm_judge(ctx, actions)

        # 4. 结算
        a.apply_delta(ctx, {...})

        # 5. 推送前端
        await a.emit_state(ctx)
        return True  # 继续游戏
```

---

## 🔧 模型配置

9 个默认站位，覆盖 7 个厂商。在 `config/defaults.json` 中配置。每个游戏可在自己的 `config.json` 中覆盖。

| 站位 | 模型 | 厂商 |
|------|------|------|
| ChatGPT | gpt-5.5 | OpenAI（中转） |
| Claude | claude-sonnet-4-6-r | Anthropic（中转） |
| 豆包 | doubao-seed-2-0-lite | 火山引擎 |
| 通义千问 | qwen3.7-plus | 阿里云 |
| 混元 | hy3-preview | 腾讯 |
| Gemini | gemini-3.1-flash-lite | Google（中转） |
| DeepSeek | deepseek-v4-flash | DeepSeek |
| Kimi | kimi-k2.6 | Moonshot |
| MiniMax | minimax-m2.7 | MiniMax |

DM 默认使用 DeepSeek V4 Pro。所有模型可在前端 UI 中在线切换、测试连接，无需重启。

---

## 🧪 测试

```bash
python -m pytest tests/ -v
# 136 个纯逻辑单元测试，覆盖配置加载、记忆隔离、
# 投票解析、胜负判定、狼人杀全流程逻辑
```

---

## 📦 技术栈

| 层 | 技术 |
|------|------|
| 引擎 | Python 3.11+, asyncio, Pydantic v2, httpx |
| 后端 | FastAPI, WebSocket, uvicorn |
| 前端 | React 19, TypeScript, Vite, Zustand, Framer Motion, Recharts, Tailwind CSS v4 |
| LLM | 统一适配 11 个厂商（OpenAI / Anthropic / Gemini / DeepSeek / 豆包 / MiniMax / 智谱 / 千问 / 混元 / OpenAI 兼容 / 中转站） |
| 测试 | pytest（136 用例） |
| 打包 | PyInstaller |

---

## 📄 许可

MIT License
