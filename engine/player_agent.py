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

import json
import logging
import re
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
        self.speech_only: bool = False  # True = 只发言不决定行动
        self.action_only: bool = False  # True = 极简决策模式（只问三选一，不走 CoT）
        self._history: list[dict[str, str]] = []  # 该玩家最近的消息历史

    # ── 公共 API ─────────────────────────────────────────────────

    async def act(self, ctx: GameContext) -> CoTOutput:
        """
        玩家行动主入口。

        1. 构建完整 Prompt（System + 上下文 + CoT 指令）
        2. 调用模型生成 CoT JSON
        3. 解析并校验输出
        4. 如果解析失败，自修复（重试一次）

        Returns:
            CoTOutput: 结构化的玩家行动
        """
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

        # 3. 调用模型（强制 JSON 模式）
        try:
            response = await self._router.chat(
                messages=messages,
                model=self.defn.model,
                provider=self.defn.provider,
                max_tokens=8192,
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
        parts.append(f"# 你的身份 (ID: {self.defn.id})\n{self.defn.secret_identity}\n")

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
        candidates = [
            Path("games") / self._game_id / "player_prompt.txt",
            Path("games") / self._game_id / "player_prompt.jinja2",
        ]
        for path in candidates:
            if path.exists():
                try:
                    template = path.read_text(encoding="utf-8")
                    prompt = template.replace("{{ secret_identity }}", self.defn.secret_identity) \
                                     .replace("{{ player_name }}", self.defn.name) \
                                     .replace("{{ player_id }}", self.defn.id)
                    # 确保 ID 显眼
                    prompt = f"## 你的 ID: {self.defn.id}\n\n" + prompt
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
        1. 先尝试直接解析整段 JSON
        2. 如果失败，尝试提取 ```json ... ``` 代码块
        3. 如果仍失败，尝试用正则提取关键字段
        4. 都失败则抛出异常，由 act() 兜底
        """
        text = raw_text.strip()

        # 策略 1: 直接解析
        try:
            data = json.loads(text)
            return CoTOutput(**data)
        except (json.JSONDecodeError, Exception):
            pass

        # 策略 2: 提取 ```json 代码块
        json_block = self._extract_json_block(text)
        if json_block:
            try:
                data = json.loads(json_block)
                return CoTOutput(**data)
            except (json.JSONDecodeError, Exception):
                pass

        # 策略 3: 正则提取关键字段
        try:
            return self._regex_extract_cot(text)
        except Exception:
            pass

        # 策略 4: 失败
        raise ValueError(f"无法解析 CoT JSON，原始输出: {text[:500]}...")

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
            "situation_assessment": r'"situation_assessment"\s*:\s*"([^"]*)"',
            "internal_strategy": r'"internal_strategy"\s*:\s*"([^"]*)"',
            "public_speech": r'"public_speech"\s*:\s*"([^"]*)"',
            "secret_action": r'"secret_action"\s*:\s*"([^"]*)"',
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

        # 极简 prompt（包含自己的 ID + speech 阶段分析）
        my_id = self.defn.id
        my_name = self.defn.name
        my_state = ctx.round.players.get(my_id)
        my_analysis = ""
        if my_state and my_state.last_cot:
            sa = my_state.last_cot.situation_assessment or ""
            si = my_state.last_cot.internal_strategy or ""
            if sa or si:
                my_analysis = f"\n\n你发言阶段的分析：\n局势评估：{sa}\n内心策略：{si}"

        prompt = (
            f"你是{my_name}（{my_id}）。以上是所有人本轮的发言。{my_analysis}\n\n"
            "现在三选一，只回复编码：\n"
            "- DEV（挖矿+2，被抢-4）\n"
            "- DEF（架盾-1，格挡反伤）\n"
            "- LOOT-p1 / LOOT-p2 / LOOT-p3 / LOOT-p4 / LOOT-p5 / LOOT-p6（抢指定玩家，+5/-1/-3）"
        )

        messages = [
            ModelMessage(role="system", content=prompt),
            ModelMessage(role="user", content=context_text),
        ]

        try:
            response = await self._router.chat(
                messages=messages,
                model=self.defn.model,
                provider=self.defn.provider,
                max_tokens=1024,
                temperature=0.0,
                json_mode=False,
            )
            raw = response.content.strip()
            # 取最后一行（有些模型会先解释再输出行动）
            secret_action = raw.split("\n")[-1].strip() if raw else "发育"
            if not secret_action:
                secret_action = "发育"
        except Exception:
            secret_action = "发育"

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
