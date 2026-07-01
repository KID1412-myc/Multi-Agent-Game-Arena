"""
MAGA Player Agent — 博弈玩家抽象
====================================
每个博弈玩家是一个独立的 Agent，拥有：
- 公共人设（其他玩家可见）
- 秘密身份/隐藏目标（只有自己知道）
- 私密本子（DM 塞的私聊消息）

玩家的行动流程：
    1. 接收上下文（公共看板 + 私密本子 + 自己的历史）
    2. 生成强制 CoT JSON（局势评估 → 内心策略 → 公开发言 → 秘密行动）
    3. 公开发言进入公共看板，秘密行动仅 DM 可见

Usage:
    from engine.player_agent import PlayerAgent
    agent = PlayerAgent(player_def, router, memory_manager)
    action = await agent.act(ctx)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import os
from pathlib import Path

from engine.schema import (
    CoTOutput,
    GameContext,
    ModelMessage,
    ModelProvider,
    PlayerDef,
    PlayerState,
)
from engine.router import ModelRouter

logger = logging.getLogger("maga.player")

# ============================================================================
# CoT 输出格式声明（注入到每个 Prompt 中）
# ============================================================================

COT_JSON_SCHEMA_DECLARATION = """
你必须严格按照以下 JSON Schema 格式输出，不得输出任何其他内容：

```json
{
    "situation_assessment": "对当前局势的客观分析：各玩家状态、意图、威胁、机会",
    "internal_strategy": "基于局势分析制定的内心策略：你打算怎么做，为什么",
    "public_speech": "你实际对其他玩家说出口的话（可能是真话也可能是谎言）",
    "secret_action": "只有 DM 能看到的秘密行动，如无则填空字符串"
}
```

重要规则：
1. 先分析局势，再制定策略，最后才输出公开发言。这是你的思考过程。
2. public_speech 是你唯一说出口的话，其他玩家只能看到这段。
3. secret_action 只有上帝裁判 (DM) 能看到，用于暗中操作。
4. 保持角色一致性，不要暴露你的秘密身份。
"""


# ============================================================================
# Player Agent
# ============================================================================

class PlayerAgent:
    """
    博弈玩家 Agent。

    每个实例对应一个 LLM 驱动的博弈玩家。
    拥有完整的上下文构建、CoT 强制输出、以及错误恢复能力。
    """

    def __init__(
        self,
        player_def: PlayerDef,
        router: ModelRouter,
        get_context_fn,  # Callable[[str], str] — 获取该玩家的上下文文本
        game_id: str = "",
    ):
        """
        Args:
            player_def: 玩家定义（来自 config.json）
            router: 统一模型路由器
            get_context_fn: 异步回调，输入玩家 ID，返回构建好的上下文字符串
            game_id: 游戏 ID，用于加载游戏专属提示词模板
        """
        self.defn = player_def
        self._router = router
        self._get_context = get_context_fn
        self._game_id = game_id
        self._arena = None  # 由 Arena._setup 注入
        self._pending_future: asyncio.Future | None = None  # 人类玩家等待输入
        self._human_submitted: bool = False  # 标记人类是否已提交（防 stop 抢跑）
        self.speech_only: bool = False  # True = 只发言不决定行动
        self.action_only: bool = False  # True = 极简决策模式（只问三选一，不走 CoT）
        self.quick_action_prompt: str | None = None  # 游戏自定义 action 提示（替代 DEV/DEF/LOOT）
        self._history: list[dict[str, str]] = []  # 该玩家最近的消息历史

    # ── 公共 API ─────────────────────────────────────────────────

    async def act(self, ctx: GameContext) -> CoTOutput:
        """
        玩家行动主入口。人类玩家通过前端输入，AI 通过 LLM 调用。

        Returns:
            CoTOutput: 结构化的玩家行动
        """
        # 人类玩家：发射事件等待前端输入
        if self.defn.is_human:
            return await self._wait_for_human(ctx)

        # 极简决策模式：不发 CoT，只问一句话
        if self.action_only:
            return await self._act_quick(ctx)

        # 1. 构建上下文
        context_text = self._get_context(self.defn.id)

        # 2. 构建消息
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(ctx, context_text)

        messages = [
            ModelMessage(role="system", content=system_prompt),
            ModelMessage(role="user", content=user_prompt),
        ]

        # 调试：打印完整上下文（MAGA_DEBUG=1 时启用）
        if os.environ.get("MAGA_DEBUG"):
            logger.info(f"━━━ {self.defn.name}({self.defn.id}) 发言阶段 ━━━\n{system_prompt[:500]}\n...\n{user_prompt[:500]}")

        # 3. 调用模型（强制 JSON 模式）
        try:
            response = await self._router.chat(
                messages=messages,
                model=self.defn.model,
                provider=self.defn.provider,
                max_tokens=16384,
                temperature=0.8,
                json_mode=True,
            )

            # 4. 解析 CoT JSON
            cot = self._parse_cot(response.content)

            # 5. 记录历史
            self._history.append({
                "round": str(ctx.round.round_number),
                "speech": cot.public_speech,
                "secret": cot.secret_action,
            })

            return cot

        except Exception as e:
            logger.error(f"玩家 {self.defn.name} 行动失败: {e}")
            # 回退：返回一个保守的默认行动
            return self._fallback_action(str(e))

    async def _wait_for_human(self, ctx: GameContext) -> CoTOutput:
        """人类玩家：发送事件到前端，等待用户提交输入。"""
        from engine.schema import WSEventType
        phase = "speech" if self.speech_only else ("action" if self.action_only else "full")
        # 构建人类玩家上下文提示：只取角色+行动格式，不含聊天记录
        context_hint = ""
        if self._arena and self._get_context:
            try:
                raw_ctx = self._get_context(self.defn.id)
                # 只保留角色指引段落（以 ## 🎭 开头），去掉聊天历史
                lines = raw_ctx.split('\n')
                hint_lines = []
                in_hint = False
                for line in lines:
                    if '## 🎭' in line or '游戏声明' in line or '全玩家名单' in line:
                        in_hint = True
                    if in_hint:
                        hint_lines.append(line)
                    if in_hint and line.strip() == '' and len(hint_lines) > 5:
                        break  # 角色指引结束后停止
                context_hint = '\n'.join(hint_lines) if hint_lines else raw_ctx[:800]
            except Exception:
                pass
        if self._arena:
            await self._arena._emit(WSEventType.HUMAN_TURN, {
                "player_id": self.defn.id,
                "player_name": self.defn.name,
                "phase": phase,
                "context": context_hint,
            })
        # 创建 Future，等待前端通过 WS 提交；同时监控停止信号
        self._pending_future = asyncio.get_event_loop().create_future()
        self._human_submitted = False  # 标记人类是否已提交（防止 stop 抢跑）
        async def _check_stop():
            while not self._pending_future.done():
                if self._arena and self._arena._stop_event.is_set():
                    # 给人类 1.5 秒缓冲时间提交输入，不立刻抢跑
                    await asyncio.sleep(1.5)
                    if not self._human_submitted:
                        self._pending_future.set_result({"speech": "", "action": "", "stopped": True})
                    return
                await asyncio.sleep(0.5)
        stop_task = asyncio.ensure_future(_check_stop())
        try:
            result = await self._pending_future
        except Exception:
            return self._fallback_action("人类玩家未响应")
        finally:
            stop_task.cancel()
        # 被停止信号触发（带了 stopped 标记）
        if result.get("stopped"):
            return CoTOutput(
                situation_assessment="（游戏已被管理员手动停止）",
                internal_strategy="（游戏已被管理员手动停止）",
                public_speech=".",
                secret_action="",
            )
        speech = result.get("speech", "").strip()
        action = result.get("action", "").strip()
        # 防止空 speech 触发 CoTOutput 校验崩溃——用 "." 因为引擎会忽略它（不推送到看板）
        if not speech:
            speech = "."
        try:
            return CoTOutput(
                situation_assessment="（人类玩家手动输入）",
                internal_strategy="（人类玩家手动输入）",
                public_speech=speech,
                secret_action=action,
            )
        except Exception:
            # CoTOutput 校验失败时的绝对兜底（正常不应走到这里）
            return CoTOutput(
                situation_assessment="（人类玩家输入兜底）",
                internal_strategy="（人类玩家输入兜底）",
                public_speech=speech if speech else ".",
                secret_action="",
            )

    def resolve_human_input(self, speech: str, action: str):
        """接收前端提交的人类输入，唤醒 _wait_for_human。"""
        self._human_submitted = True
        if self._pending_future and not self._pending_future.done():
            self._pending_future.set_result({"speech": speech, "action": action})

    # ── Prompt 构建 ──────────────────────────────────────────────

    def _build_system_prompt(self) -> str:
        """构建玩家的 System Prompt。如果游戏目录下有 player_prompt.txt，优先使用。"""
        # 尝试加载游戏专属玩家提示词
        custom_prompt = self._load_custom_prompt()
        if custom_prompt:
            return custom_prompt

        # 回退：默认通用模板
        parts: list[str] = []

        # 游戏角色人设
        parts.append(f"# 你是 {self.defn.name}（{self.defn.id}）\n{self.defn.secret_identity}\n")

        # 游戏规则
        parts.append(
            "# 游戏规则\n"
            "你正在参与一场多 Agent 博弈游戏。你需要通过谈判、结盟、欺骗、"
            "暗中操作等手段达成你的目标。你的公开发言将对所有其他玩家可见，"
            "你的秘密行动仅 DM 可见。\n"
        )

        # 两阶段模式
        if self.speech_only:
            parts.append(
                "## ⚠️ 这是发言阶段\n"
                "你现在只需要发表自己的看法、试探其他玩家。**不要决定你的最终行动**。\n"
                "secret_action 字段写：待定\n"
                "你会在听到所有人的发言后，再决定你的行动。"
            )
        else:
            parts.append(
                "## ⚠️ 这是行动阶段\n"
                "你已经听到了所有人的发言。现在基于全部信息，**决定你的最终行动**。\n"
                "secret_action 是你的最终选择。"
            )

        # CoT 输出格式
        parts.append(COT_JSON_SCHEMA_DECLARATION)

        return "\n\n".join(parts)

    def _load_custom_prompt(self) -> str | None:
        """从游戏目录加载自定义玩家提示词（支持 .txt 和 .jinja2）"""
        if not self._game_id:
            return None
        # PyInstaller 打包兼容
        base = Path("games")
        if not base.exists():
            import sys as _sys
            if getattr(_sys, 'frozen', False):
                base = Path(_sys._MEIPASS) / "games"
        candidates = [
            base / self._game_id / "player_prompt.txt",
            base / self._game_id / "player_prompt.jinja2",
        ]
        for path in candidates:
            if path.exists():
                try:
                    template = path.read_text(encoding="utf-8")
                    prompt = template.replace("{{ secret_identity }}", self.defn.secret_identity) \
                                     .replace("{{ player_name }}", self.defn.name) \
                                     .replace("{{ player_id }}", self.defn.id)
                    # 确保 ID 显眼
                    prompt = f"## 你是 {self.defn.name}（{self.defn.id}）\n\n" + prompt
                    # 追加阶段提示
                    if self.speech_only:
                        prompt += "\n\n## 发言阶段\n你现在只需公开发言。secret_action 写：待定。听到所有人发言后再决定行动。"
                    elif self.action_only:
                        prompt += "\n\n## 行动阶段\n你已经听到所有人的发言。现在只回复你的最终行动：发育 / 防御 / 掠夺-目标名。不解释。"
                    return prompt
                except Exception:
                    pass
        return None

    def _build_user_prompt(self, ctx: GameContext, context_text: str) -> str:
        """构建玩家的 User Prompt"""
        parts: list[str] = []

        # 当前轮次
        parts.append(
            f"## 当前状态\n"
            f"- 当前轮次：第 {ctx.round.round_number} / {ctx.game_config.total_rounds} 轮\n"
            f"- 你的资源：{ctx.round.players.get(self.defn.id, PlayerState(id='', name='', model='', provider=ModelProvider.OPENAI)).resources}\n"
        )

        # 历史上下文
        if context_text:
            parts.append(f"## 历史上下文\n{context_text}")

        # 当前局势
        parts.append(
            "## 本轮指令\n"
            "请根据以上信息，以 JSON 格式输出你的局势分析、内心策略、公开发言和秘密行动。\n"
            "记住："
            "- 公开发言要对其他玩家说的，要符合你的人设\n"
            "- 如果有秘密行动，写在 secret_action 字段中，DM 会处理\n"
        )

        return "\n\n".join(parts)

    # ── CoT 解析 ─────────────────────────────────────────────────

    def _parse_cot(self, raw_text: str) -> CoTOutput:
        """
        从模型原始输出中提取并解析 CoT JSON。

        容错策略：
        0. Qwen 格式解包：[{"type":"text","text":"{...}"}] → 提取 text 再解析
        1. 先尝试直接解析整段 JSON
        2. 尝试从文本中提取 { ... } JSON 对象（处理"闲聊+JSON"混合输出）
        3. 如果失败，尝试提取 ```json ... ``` 代码块
        4. 如果仍失败，尝试用正则提取关键字段
        5. 都失败则抛出异常，由 act() 兜底
        """
        text = raw_text.strip()

        # 策略 0: 解包 text 格式响应 [{"type":"text","text":"{...}"}]
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list) and len(parsed) > 0 and isinstance(parsed[0], dict):
                if parsed[0].get("type") == "text" and "text" in parsed[0]:
                    text = parsed[0]["text"].strip()
        except (json.JSONDecodeError, Exception):
            pass

        # 策略 1: 直接解析
        try:
            data = json.loads(text)
            return CoTOutput(**data)
        except (json.JSONDecodeError, Exception):
            pass

        # 策略 2: 从文本中提取 { ... } JSON 对象（处理模型在 JSON 前后写闲聊）
        json_object = self._extract_json_object(text)
        if json_object:
            try:
                data = json.loads(json_object)
                return CoTOutput(**data)
            except (json.JSONDecodeError, Exception):
                pass

        # 策略 3: 提取 ```json 代码块
        json_block = self._extract_json_block(text)
        if json_block:
            try:
                data = json.loads(json_block)
                return CoTOutput(**data)
            except (json.JSONDecodeError, Exception):
                pass

        # 策略 4: 正则提取关键字段
        try:
            return self._regex_extract_cot(text)
        except Exception:
            pass

        # 策略 5: 失败
        raise ValueError(f"无法解析 CoT JSON，原始输出: {text[:500]}...")

    def _extract_json_object(self, text: str) -> Optional[str]:
        """从包含非 JSON 文本的混合输出中提取第一个完整 JSON 对象"""
        start = text.find('{')
        if start == -1:
            return None
        # 从第一个 { 开始，找到匹配的 }
        depth = 0
        in_string = False
        escape = False
        for i, ch in enumerate(text[start:], start):
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i+1]
        return None

    def _extract_json_block(self, text: str) -> Optional[str]:
        """从文本中提取 ```json ... ``` 代码块"""
        patterns = [
            r"```json\s*([\s\S]*?)```",
            r"```\s*([\s\S]*?)```",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return None

    def _regex_extract_cot(self, text: str) -> CoTOutput:
        """用正则表达式紧急提取 CoT 各字段"""
        fields: dict[str, str] = {}

        patterns = {
            "situation_assessment": r'"(?:situation_assessment|situation_analysis|analysis)"\s*:\s*"([^"]*)"',
            "internal_strategy": r'"(?:internal_strategy|inner_strategy|strategy|internal_plan)"\s*:\s*"([^"]*)"',
            "public_speech": r'"(?:public_speech|speech|public_statement|statement)"\s*:\s*"([^"]*)"',
            "secret_action": r'"(?:secret_action|action|hidden_action)"\s*:\s*"([^"]*)"',
        }

        for field_name, pattern in patterns.items():
            match = re.search(pattern, text, re.DOTALL)
            if match:
                fields[field_name] = match.group(1)
            else:
                fields[field_name] = ""

        # 确保 public_speech 不为空
        if not fields.get("public_speech", "").strip():
            # 从原文中找看起来像发言的部分
            fields["public_speech"] = "（保持观望，暂无发言）"

        return CoTOutput(**fields)

    # ── 极简决策 ─────────────────────────────────────────────────

    async def _act_quick(self, ctx: GameContext) -> CoTOutput:
        """极简决策模式：只发演讲列表 + 三选一问题，不生成完整 CoT"""
        context_text = self._get_context(self.defn.id)

        # 取自己之前的分析（措辞避免让模型以为行动已提交）
        my_state = ctx.round.players.get(self.defn.id)
        prev_thought = ""
        if my_state and my_state.last_cot:
            sa = my_state.last_cot.situation_assessment or ""
            si = my_state.last_cot.internal_strategy or ""
            if sa or si:
                prev_thought = f"\n\n你之前的思考：\n{sa}\n{si}"

        if self.quick_action_prompt:
            action_instruction = self.quick_action_prompt
        else:
            action_instruction = (
                "现在是决定行动的阶段。只回复一个编码：\n"
                "DEV\n"
                "DEF\n"
                f"LOOT-p1 / LOOT-p2 / LOOT-p3 / LOOT-p4 / LOOT-p5 / LOOT-p6"
            )

        prompt = (
            f"你的ID: {self.defn.id}。以上是本轮所有人的发言。{prev_thought}\n\n"
            f"{action_instruction}"
        )

        # 调试：打印完整上下文
        if os.environ.get("MAGA_DEBUG"):
            logger.info(f"━━━ {self.defn.name}({self.defn.id}) 行动阶段 ━━━\n{prompt[:500]}\n...\n{context_text[:500]}")

        messages = [
            ModelMessage(role="system", content=prompt),
            ModelMessage(role="user", content=context_text),
        ]

        try:
            response = await self._router.chat(
                messages=messages,
                model=self.defn.model,
                provider=self.defn.provider,
                max_tokens=4096,
                temperature=0.1,
                json_mode=False,
            )
            raw = response.content.strip()
            # 解包 [{"type":"text","text":"..."}] 格式响应
            try:
                import json as _json
                _parsed = _json.loads(raw)
                if isinstance(_parsed, list) and len(_parsed) > 0 and isinstance(_parsed[0], dict):
                    if _parsed[0].get("type") == "text" and "text" in _parsed[0]:
                        raw = _parsed[0]["text"].strip()
            except Exception:
                pass
            # 取最后一行，去掉多余符号
            secret_action = raw.split("\n")[-1].strip().rstrip("。，.!,；;：:") if raw else ""
            if self.quick_action_prompt:
                # 通用模式：取回复中最后一段有意义的内容
                if not secret_action or len(secret_action) > 20:
                    for line in reversed(raw.split("\n")):
                        line = line.strip().rstrip("。，.!,；;：:)\"' ")
                        if line and len(line) <= 10:
                            secret_action = line
                            break
                if not secret_action:
                    secret_action = ""
            else:
                # 贪婪矿场模式
                if not secret_action or len(secret_action) > 20:
                    for line in raw.split("\n"):
                        line = line.strip().rstrip("。，.!,；;：:")
                        if line in ("DEV", "DEF") or line.startswith("LOOT-p"):
                            secret_action = line
                            break
                if not secret_action:
                    secret_action = "DEV"
        except Exception:
            secret_action = ""

        # 返回占位 CoT（满足最小长度校验，frontend 不显示）
        return CoTOutput(
            situation_assessment="极简决策，无需分析。",
            internal_strategy="基于发言做出最优选择。",
            public_speech=".",
            secret_action=secret_action[:100],
        )

    # ── 回退 ─────────────────────────────────────────────────────

    def _fallback_action(self, error_msg: str) -> CoTOutput:
        """当模型完全失败时的兜底行动"""
        short = error_msg[:300]
        return CoTOutput(
            situation_assessment=f"调用失败: {short}",
            internal_strategy=f"API 调用出错: {short}",
            public_speech=f"[系统] {self.defn.name} 调用失败 — {short}",
            secret_action="",
        )

    # ── 统计 ─────────────────────────────────────────────────────

    def get_history(self) -> list[dict[str, str]]:
        """获取该玩家的行动历史"""
        return list(self._history)
