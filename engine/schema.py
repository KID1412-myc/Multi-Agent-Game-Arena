"""
MAGA Schema — 整个项目的"通用语"
===================================
所有模块间的数据传递都使用此文件中定义的 Pydantic 模型。
字段级类型安全，IDE 自动补全，运行时自动校验。

Usage:
    from engine.schema import GameContext, CoTOutput, DMVerdict, ModelMessage, ...
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# 一、模型提供商枚举
# ============================================================================

class ModelProvider(str, Enum):
    """支持的模型厂商"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    DOUBAO = "doubao"
    MINIMAX = "minimax"
    ZHIPU = "zhipu"
    QWEN = "qwen"
    # 通用兼容 OpenAI 协议的厂商（本地模型 / vLLM / Ollama 等）
    OPENAI_COMPATIBLE = "openai_compatible"
    # 中转站模式：统一 API Base + 单一 Key，模型名自由指定
    # 适用于 api2d、openai-sb、自定义网关等中转服务
    RELAY = "relay"


# ============================================================================
# 二、模型通信层数据结构（router.py 用）
# ============================================================================

class ModelMessage(BaseModel):
    """统一的聊天消息格式，与厂商无关"""
    role: str = Field(..., description="system | user | assistant")
    content: str = Field(..., description="消息文本内容")


class ModelRequest(BaseModel):
    """向模型发送的请求"""
    messages: list[ModelMessage] = Field(..., min_length=1)
    model: str = Field(..., description="模型名称，如 gpt-5.4, claude-opus-4-8")
    provider: ModelProvider
    max_tokens: int = Field(default=8192, ge=1, le=128000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    timeout: float = Field(default=120.0, ge=1.0)
    api_key: Optional[str] = Field(default=None, description="API Key，不传则从环境变量读取")
    api_base: Optional[str] = Field(default=None, description="自定义 API 地址")
    extra: dict[str, Any] = Field(default_factory=dict, description="厂商特有参数")


class ModelResponse(BaseModel):
    """统一的模型返回格式"""
    content: str = Field(..., description="模型返回的文本内容")
    model: str = Field(..., description="实际使用的模型名")
    provider: ModelProvider
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    latency_ms: float = Field(default=0.0, ge=0.0)
    finish_reason: str = Field(default="stop")
    raw_response: Any = Field(default=None, description="原始响应（调试用）")


# ============================================================================
# 三、强制伪思维链（Forced CoT）—— 玩家层核心数据结构
# ============================================================================

class CoTOutput(BaseModel):
    """
    强制伪思维链输出格式。

    无论使用什么模型（包括 Flash 型轻量模型），都必须以此 JSON 格式输出。
    利用自回归特性：模型在输出 public_speech 之前，必须先生成
    situation_assessment 和 internal_strategy，从而强制拔高博弈智商。

    字段说明：
    - situation_assessment: 对当前局势的客观分析（内心读盘）
    - internal_strategy: 基于局势分析制定的策略（内心算计）
    - public_speech: 实际对其他玩家说出口的话（可能是真话也可能是谎言）
    - secret_action: 只有 DM 能看到的秘密行动（如暗中收购股权）
    """
    situation_assessment: str = Field(
        ...,
        min_length=10,
        description="局势评估：当前场上发生了什么，各玩家的状态和意图"
    )
    internal_strategy: str = Field(
        ...,
        min_length=10,
        description="内心策略：基于局势分析，我打算采取什么策略，为什么"
    )
    public_speech: str = Field(
        ...,
        min_length=1,
        description="公开发言：实际对其他玩家说出的内容"
    )
    secret_action: str = Field(
        default="",
        description="秘密行动：仅 DM 可见，如暗中调查、秘密交易等"
    )

    @field_validator("public_speech")
    @classmethod
    def speech_not_too_short(cls, v: str) -> str:
        if len(v.strip()) < 1:
            raise ValueError("公开发言不能为空")
        return v.strip()


# ============================================================================
# 四、DM 裁判层数据结构（dm_interface.py 用）
# ============================================================================

class ResourceDelta(BaseModel):
    """单个玩家的资源变化"""
    player_id: str
    changes: dict[str, float] = Field(
        default_factory=dict,
        description="资源变化量，正数为增加，负数为减少，如 {'capital': -10, 'reputation': 5}"
    )


class PrivateMessage(BaseModel):
    """DM 发给单个玩家的私密消息"""
    player_id: str
    message: str = Field(..., description="仅该玩家可见的消息")


class CriticalEvent(BaseModel):
    """
    关键事件标记 —— 进入 L3 冷记忆永久保留。
    由 DM 在每轮判定时标记，引擎自动归档。
    """
    round_number: int
    event: str = Field(..., description="事件描述，如 'A 公司秘密收购了 B 公司 15% 股权'")
    related_players: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.now)


class DMVerdict(BaseModel):
    """
    DM 每轮判定的固定输出格式。
    这是整个引擎最重要的数据结构之一 —— DM 必须严格按照此 Schema 返回 JSON。
    """
    round_number: int
    round_summary: str = Field(
        ...,
        min_length=20,
        description="本轮全局摘要：发生了什么、关键冲突、资源变动概要"
    )
    global_narrative: str = Field(
        default="",
        description="上帝视角的全局叙事：市场反应、舆论变化等（进入公共看板）"
    )
    resource_delta: list[ResourceDelta] = Field(
        default_factory=list,
        description="本轮所有玩家的资源变化列表"
    )
    private_messages: list[PrivateMessage] = Field(
        default_factory=list,
        description="DM 发给特定玩家的私密消息（进入各自私密本子）"
    )
    winner_id: Optional[str] = Field(
        default=None,
        description="如果非空，游戏结束，此 ID 为获胜者"
    )
    critical_events: list[CriticalEvent] = Field(
        default_factory=list,
        description="本轮产生的关键事件（进入 L3 冷记忆永久保留）"
    )
    next_round_phase: str = Field(
        default="player_turn",
        description="下一轮阶段：player_turn | dm_judgment | game_over"
    )


# ============================================================================
# 五、游戏状态数据结构（引擎 + 前端共用）
# ============================================================================

class PlayerDef(BaseModel):
    """玩家定义（来自 config.json）"""
    id: str
    name: str
    model: str
    provider: ModelProvider
    secret_identity: str = Field(default="", description="秘密人设 / 隐藏目标")
    initial_resources: dict[str, float] = Field(default_factory=dict)


class ResourceDef(BaseModel):
    """资源类型定义（来自 config.json，直接驱动前端图表）"""
    id: str
    label: str
    unit: str = ""
    icon: str = ""


class PlayerState(BaseModel):
    """单个玩家的运行时状态快照"""
    id: str
    name: str
    model: str
    provider: ModelProvider
    resources: dict[str, float] = Field(default_factory=dict)
    is_alive: bool = True
    is_current_speaker: bool = False
    is_thinking: bool = False
    last_public_speech: str = ""
    last_cot: Optional[CoTOutput] = None
    private_notebook: list[str] = Field(
        default_factory=list,
        description="私密本子：DM 塞给该玩家的秘密消息历史"
    )
    color_tag: str = ""
    fraud_tag: str = ""
    see_tag: str = ""


class RoundState(BaseModel):
    """单轮的状态快照"""
    round_number: int
    total_rounds: int
    phase: str = Field(default="player_turn", description="player_turn | dm_judgment | game_over")
    current_speaker_id: Optional[str] = None
    players: dict[str, PlayerState] = Field(default_factory=dict)
    public_log: list[str] = Field(
        default_factory=list,
        description="公共看板上所有玩家的发言记录"
    )


class GameConfig(BaseModel):
    """游戏配置（从 config.json 解析后得到）"""
    game_id: str
    name: str
    version: str = "1.0"
    description: str = ""
    min_players: int = 2
    max_players: int = 12
    total_rounds: int = Field(default=10, ge=0, description="0 表示不限轮数，直到胜负条件触发")
    mode: str = Field(default="sequential", description="sequential | parallel")
    language: str = "zh-CN"
    turn_timeout_seconds: int = 60
    dm_model: str = "gpt-5.4"
    dm_provider: ModelProvider = ModelProvider.OPENAI
    resources: list[ResourceDef] = Field(default_factory=list)
    players: list[PlayerDef] = Field(default_factory=list, min_length=2)
    hooks: Optional[str] = None
    state_machine: Optional[str] = None
    schema_override: Optional[str] = None
    shuffle_order: bool = False
    two_phase: bool = False  # True = 每轮分两阶段：先全员发言，再全员行动
    epilogue: bool = False    # True = 游戏结束后每人发表最终感言


class GameContext(BaseModel):
    """
    每一帧的完整状态快照。

    这个对象在引擎、DM、前端之间流转。
    前端拿到一个 GameContext 就能渲染整个竞技场画面。

    注意：这个对象会通过 WebSocket 推送给前端，
    所以只包含当前帧需要展示的信息，不包含完整历史。
    """
    game_config: GameConfig
    round: RoundState
    dm_last_verdict: Optional[DMVerdict] = None
    total_tokens_spent: int = 0
    total_cost_usd: float = 0.0
    elapsed_time_seconds: float = 0.0
    errors: list[str] = Field(default_factory=list, description="本轮发生的错误/警告")


# ============================================================================
# 六、WebSocket 事件类型（server → frontend）
# ============================================================================

class WSEventType(str, Enum):
    """WebSocket 事件类型枚举"""
    GAME_INIT = "GAME_INIT"               # 游戏初始化完成
    ROUND_START = "ROUND_START"           # 新一轮开始
    PLAYER_THINKING = "PLAYER_THINKING"   # 玩家开始思考
    PLAYER_SPEECH = "PLAYER_SPEECH"       # 玩家公开发言
    PLAYER_COT = "PLAYER_COT"             # 玩家思维链（可选展示）
    DM_JUDGMENT = "DM_JUDGMENT"           # DM 裁判结果
    STATE_UPDATE = "STATE_UPDATE"         # 全局状态更新（包含完整 GameContext）
    PLAYER_ERROR = "PLAYER_ERROR"         # 某个玩家出错
    GAME_OVER = "GAME_OVER"               # 游戏结束
    ENGINE_ERROR = "ENGINE_ERROR"         # 引擎级错误


class WSEvent(BaseModel):
    """WebSocket 推送事件"""
    event_type: WSEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


# ============================================================================
# 七、引擎运行结果
# ============================================================================

class ArenaResult(BaseModel):
    """一场游戏的完整结果"""
    game_id: str
    game_name: str
    winner_id: Optional[str] = None
    winner_name: Optional[str] = None
    total_rounds_played: int
    final_state: GameContext
    round_history: list[DMVerdict] = Field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    duration_seconds: float = 0.0
    errors: list[str] = Field(default_factory=list)


# ============================================================================
# 八、记忆系统数据结构
# ============================================================================

class MemoryEntry(BaseModel):
    """单条记忆条目"""
    round_number: int
    content: str
    is_critical: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)


class TieredMemory(BaseModel):
    """
    分级记忆：热 / 温 / 冷三层
    - L1 热记忆：最近 3 轮完整对话 + 私密本子（不进摘要）
    - L2 温记忆：DM 生成的全局摘要（每轮更新）
    - L3 冷记忆：标记为 #CRITICAL 的事件（永久保留，按需检索）
    """
    player_id: Optional[str] = None  # None 表示全局记忆，有值表示玩家私密记忆
    hot_memory: list[MemoryEntry] = Field(default_factory=list, max_length=50)
    warm_summary: str = ""
    cold_memory: list[MemoryEntry] = Field(default_factory=list)
