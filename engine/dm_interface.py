"""
MAGA DM Interface — 上帝裁判接口
====================================
DM (Dungeon Master) 由大模型扮演，是整个游戏的裁判。

职责：
1. 每轮收集所有玩家的行动（公开发言 + 秘密行动）
2. 根据游戏规则 + 历史，判定结果
3. 返回严格结构化的 JSON（DMVerdict）
4. 生成全局战局摘要（用于 L2 温记忆）
5. 标记关键事件（进入 L3 冷记忆）

三层防御机制：
- Layer 1: JSON Schema 校验（Pydantic）
- Layer 2: 自修复重试（解析失败 → 错误信息发回 DM → DM 自己修复）
- Layer 3: 兜底降级（连续失败 → 引擎自动介入，最小状态更新 + 告警日志）

Usage:
    from engine.dm_interface import DMInterface
    dm = DMInterface(config, router, memory_manager)
    verdict = await dm.judge(ctx, player_actions)
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.schema import (
    CoTOutput,
    CriticalEvent,
    DMVerdict,
    GameConfig,
    GameContext,
    ModelMessage,
    ModelProvider,
    PlayerState,
    PrivateMessage,
    ResourceDef,
    ResourceDelta,
)
from engine.router import ModelRouter

logger = logging.getLogger("maga.dm")

# ============================================================================
# DM 的 System Prompt 模板
# ============================================================================

DM_SYSTEM_PROMPT_TEMPLATE = """
# 你是游戏上帝裁判 (Dungeon Master)

你正在主持一场名为 "{game_name}" 的多人博弈游戏。

## 游戏规则
{game_rules}

## 你的职责
1. 审阅本轮所有玩家的公开发言和秘密行动
2. 根据游戏规则判定结果：资源变化、胜负、特殊事件
3. 输出严格结构化的 JSON

## 资源系统
游戏中存在以下资源，你需要根据玩家行为调整这些资源：
{resource_definitions}

## 输出格式（必须严格遵守）
你必须返回以下 JSON 结构，不要输出任何其他内容：

```json
{{
    "round_number": <当前轮次数字>,
    "round_summary": "<本轮全局摘要：发生了什么，关键冲突，资源变动概要>",
    "global_narrative": "<上帝视角的全局叙事：市场反应、舆论变化等，所有玩家可见>",
    "resource_delta": [
        {{
            "player_id": "<玩家ID>",
            "changes": {{ "resource_id": <变化量> }}
        }}
    ],
    "private_messages": [
        {{
            "player_id": "<玩家ID>",
            "message": "<仅该玩家可见的秘密消息>"
        }}
    ],
    "winner_id": null,
    "critical_events": [
        {{
            "round_number": <当前轮次>,
            "event": "<关键事件描述>",
            "related_players": ["<相关玩家ID>"],
            "timestamp": "<ISO 时间戳>"
        }}
    ],
    "next_round_phase": "player_turn"
}}
```

## 判定原则
- 保持中立公正，严格按照游戏规则判定
- 资源变化必须有明确的理由（玩家做了什么导致资源变化）
- 关键事件会影响后续游戏，需标记为 critical
- 如果有玩家达成胜利条件，设置 winner_id
- 私密消息只发给相关玩家，其他玩家不可见
- global_narrative 是公开的，所有玩家都能看到
"""

# ============================================================================
# DM Interface
# ============================================================================

class DMInterface:
    """
    上帝裁判接口。

    每轮调用一次 judge()，DM 审阅所有行动并返回结构化的 DMVerdict。
    """

    def __init__(
        self,
        config: GameConfig,
        router: ModelRouter,
        get_context_fn,  # Callable[[], str] — 获取 DM 视角的全局上下文
    ):
        self.config = config
        self._router = router
        self._get_context = get_context_fn
        self._max_retries: int = 2  # DM 自修复重试次数
        self._judgment_history: list[DMVerdict] = []

    # ── 公共 API ─────────────────────────────────────────────────

    async def judge(
        self,
        ctx: GameContext,
        player_actions: list[tuple[PlayerState, CoTOutput]],
    ) -> DMVerdict:
        """
        DM 判定回合。

        Args:
            ctx: 当前游戏上下文
            player_actions: 本回合所有玩家的 (PlayerState, CoTOutput)

        Returns:
            DMVerdict: 结构化的裁判结果
        """
        # 1. 构建 DM Prompt
        system_prompt = self._build_dm_system_prompt()
        user_prompt = await self._build_dm_user_prompt(ctx, player_actions)

        messages = [
            ModelMessage(role="system", content=system_prompt),
            ModelMessage(role="user", content=user_prompt),
        ]

        # 2. 调用 DM 模型（带自修复重试）
        verdict = await self._call_dm_with_repair(messages)

        # 3. 记录
        self._judgment_history.append(verdict)

        return verdict

    # ── Prompt 构建 ─────────────────────────────────────────────

    def _build_dm_system_prompt(self) -> str:
        """构建 DM 的 System Prompt。如果游戏目录下有 dm_prompt.txt，优先使用。"""
        # 尝试加载游戏专属 DM 提示词
        custom_prompt = self._load_custom_prompt()
        if custom_prompt:
            return custom_prompt

        # 回退：默认通用模板
        resource_lines: list[str] = []
        for r in self.config.resources:
            resource_lines.append(
                f"  - {r.id} ({r.label}): 单位 {r.unit}，图标 {r.icon}"
            )
        resource_desc = "\n".join(resource_lines) if resource_lines else "无"

        return DM_SYSTEM_PROMPT_TEMPLATE.format(
            game_name=self.config.name,
            game_rules=f"游戏共 {self.config.total_rounds} 轮，"
                       f"共 {len(self.config.players)} 名玩家。"
                       f"行动模式：{self.config.mode}。",
            resource_definitions=resource_desc,
        )

    def _load_custom_prompt(self) -> str | None:
        """从游戏目录加载自定义 DM 提示词（支持 .txt 和 .jinja2）"""
        candidates = [
            Path("games") / self.config.game_id / "dm_prompt.txt",
            Path("games") / self.config.game_id / "dm_prompt.jinja2",
        ]
        for path in candidates:
            if path.exists():
                try:
                    template = path.read_text(encoding="utf-8")
                    # 简单变量替换
                    return template.replace("{{ game_name }}", self.config.name) \
                                   .replace("{{ total_rounds }}", str(self.config.total_rounds)) \
                                   .replace("{{ player_count }}", str(len(self.config.players)))
                except Exception:
                    pass
        return None

    async def _build_dm_user_prompt(
        self,
        ctx: GameContext,
        player_actions: list[tuple[PlayerState, CoTOutput]],
    ) -> str:
        """构建 DM 的 User Prompt（包含本轮所有行动）"""
        parts: list[str] = []

        # 游戏信息
        parts.append(
            f"## 游戏状态\n"
            f"- 游戏：{self.config.name}\n"
            f"- 当前轮次：第 {ctx.round.round_number} / {self.config.total_rounds} 轮\n"
        )

        # 当前资源状态
        parts.append("## 玩家当前资源")
        for pid, ps in ctx.round.players.items():
            parts.append(f"- **{ps.name}** ({pid}): {ps.resources}")

        # 全局上下文
        context_text = self._get_context()
        if context_text:
            parts.append(f"## 历史上下文\n{context_text}")

        # 本轮玩家行动
        parts.append("## 本轮玩家行动")
        for i, (player, action) in enumerate(player_actions):
            if action is None:
                parts.append(f"\n### 玩家 {i+1}: {player.name} ({player.id})")
                parts.append("**状态**: 该玩家本轮未做出有效行动")
            else:
                parts.append(f"\n### 玩家 {i+1}: {player.name} ({player.id})")
                parts.append(f"**公开发言**: {action.public_speech}")
                if action.secret_action.strip():
                    parts.append(f"**🔐 秘密行动（仅你可见）**: {action.secret_action}")
                parts.append(f"**内心策略（供参考）**: {action.internal_strategy}")

        # 指令
        parts.append(
            "\n## 你的判定\n"
            "请根据以上信息，以 JSON 格式输出你的裁判结果。"
            "注意：必须严格遵守 System Prompt 中指定的 JSON Schema。"
        )

        return "\n".join(parts)

    # ── DM 调用与自修复 ───────────────────────────────────────────

    async def _call_dm_with_repair(
        self, messages: list[ModelMessage]
    ) -> DMVerdict:
        """
        调用 DM 模型，带自修复功能。

        Layer 1: 正常调用 + Pydantic 校验
        Layer 2: 解析失败 → 错误信息发回 DM → DM 自修复
        Layer 3: 连续失败 → 引擎兜底
        """
        last_error: Optional[str] = None

        for attempt in range(self._max_retries + 1):
            try:
                # 如果是重试，在消息中添加错误信息
                if attempt > 0 and last_error:
                    repair_message = ModelMessage(
                        role="user",
                        content=(
                            f"你上一次返回的 JSON 格式有误，解析失败。\n"
                            f"错误信息: {last_error}\n"
                            f"请重新输出正确的 JSON。务必：\n"
                            f"1. 确保 JSON 格式完整，所有花括号和引号正确闭合\n"
                            f"2. 确保字符串中的特殊字符（如双引号）被正确转义\n"
                            f"3. 不要输出 JSON 以外的任何内容\n"
                        ),
                    )
                    # 重试时追加修复提示
                    repair_messages = list(messages)
                    # 把上次 DM 的原始响应也加进去
                    if hasattr(self, "_last_raw_response"):
                        repair_messages.append(ModelMessage(
                            role="assistant",
                            content=self._last_raw_response[:2000],
                        ))
                    repair_messages.append(repair_message)
                    current_messages = repair_messages
                else:
                    current_messages = messages

                # 调用 DM
                response = await self._router.chat(
                    messages=current_messages,
                    model=self.config.dm_model,
                    provider=self.config.dm_provider,
                    max_tokens=16384,
                    temperature=0.4,  # DM 用较低温度，减少幻觉
                    json_mode=True,
                )

                self._last_raw_response = response.content

                # 解析并校验
                verdict = self._parse_verdict(response.content)
                return verdict

            except Exception as e:
                last_error = str(e)
                logger.warning(f"DM 判定失败 (attempt {attempt+1}): {last_error}")

        # Layer 3: 兜底降级
        logger.error(f"DM 连续 {self._max_retries + 1} 次失败，启用兜底降级")
        return self._fallback_verdict()

    def _parse_verdict(self, raw_text: str) -> DMVerdict:
        """解析 DM 返回的 JSON 为 DMVerdict"""
        text = raw_text.strip()

        # 策略 1: 直接解析
        try:
            data = json.loads(text)
            return self._to_verdict(data)
        except (json.JSONDecodeError, Exception):
            pass

        # 策略 2: 提取 ```json 代码块
        match = re.search(r"```json\s*([\s\S]*?)```", text)
        if match:
            try:
                data = json.loads(match.group(1))
                return self._to_verdict(data)
            except (json.JSONDecodeError, Exception):
                pass

        # 策略 3: 尝试找第一个 { 到最后一个 }
        brace_match = re.search(r"\{[\s\S]*\}", text)
        if brace_match:
            try:
                data = json.loads(brace_match.group(0))
                return self._to_verdict(data)
            except (json.JSONDecodeError, Exception):
                pass

        raise ValueError(f"无法解析 DM 返回的 JSON")

    def _to_verdict(self, data: dict[str, Any]) -> DMVerdict:
        """将原始 dict 转换为 DMVerdict"""
        # 转换 resource_delta
        resource_deltas: list[ResourceDelta] = []
        for rd in data.get("resource_delta", []):
            resource_deltas.append(ResourceDelta(
                player_id=rd.get("player_id", ""),
                changes=rd.get("changes", {}),
            ))

        # 转换 private_messages
        private_msgs: list[PrivateMessage] = []
        for pm in data.get("private_messages", []):
            private_msgs.append(PrivateMessage(
                player_id=pm.get("player_id", ""),
                message=pm.get("message", ""),
            ))

        # 转换 critical_events
        critical_events: list[CriticalEvent] = []
        for ce in data.get("critical_events", []):
            ts = ce.get("timestamp")
            if ts and isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except Exception:
                    ts = datetime.now()
            else:
                ts = datetime.now()

            critical_events.append(CriticalEvent(
                round_number=ce.get("round_number", 0),
                event=ce.get("event", ""),
                related_players=ce.get("related_players", []),
                timestamp=ts if isinstance(ts, datetime) else datetime.now(),
            ))

        return DMVerdict(
            round_number=data.get("round_number", 0),
            round_summary=data.get("round_summary", ""),
            global_narrative=data.get("global_narrative", ""),
            resource_delta=resource_deltas,
            private_messages=private_msgs,
            winner_id=data.get("winner_id"),
            critical_events=critical_events,
            next_round_phase=data.get("next_round_phase", "player_turn"),
        )

    # ── 兜底降级 ─────────────────────────────────────────────────

    def _fallback_verdict(self) -> DMVerdict:
        """引擎自动介入的最小状态更新（所有 DM 重试失败后的最终兜底）"""
        logger.critical("⚠️ DM 兜底降级：引擎自动生成最小化裁定")
        return DMVerdict(
            round_number=0,
            round_summary="【系统警告】DM 裁判系统异常，本轮由引擎自动生成最小化裁定。所有玩家资源保持不变。",
            global_narrative="裁判系统正在恢复中，请等待...",
            resource_delta=[],
            private_messages=[],
            winner_id=None,
            critical_events=[
                CriticalEvent(
                    round_number=0,
                    event="DM 裁判系统异常，引擎兜底降级模式激活",
                    related_players=[],
                    timestamp=datetime.now(),
                )
            ],
            next_round_phase="player_turn",
        )
