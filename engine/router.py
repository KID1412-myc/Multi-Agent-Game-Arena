"""
MAGA Router — 统一多协议模型路由适配器
=========================================
支持 2026 年主流模型厂商的异步调用，对外暴露统一接口。

支持的厂商：
- OpenAI (GPT-5.4, GPT-4o, o4 等)
- Anthropic (Claude Opus 4.8, Claude Sonnet 4.6, Claude Haiku 4.5)
- Google Gemini (Gemini 3.0 Pro, Gemini 3.0 Flash 等)
- DeepSeek (DeepSeek-V3, DeepSeek-Reasoner)
- 豆包 (Doubao) / 火山引擎
- MiniMax
- 智谱 (GLM 系列)
- 通用 OpenAI 兼容协议 (local LLM / vLLM / Ollama)

Usage:
    from engine.router import ModelRouter
    router = ModelRouter()
    response = await router.chat(messages=[...], model="gpt-5.4", provider=ModelProvider.OPENAI)
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Optional

# 🔧 在 httpx 导入之前，强制 socket 只走 IPv4
#    linkapi.pro 等国内服务器没有 IPv6，httpx/anyio 默认先试 IPv6 会报 getaddrinfo failed
import socket as _socket
_orig_getaddrinfo = _socket.getaddrinfo
def _ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, _socket.AF_INET, type, proto, flags)
_socket.getaddrinfo = _ipv4_getaddrinfo

import httpx

from engine.schema import (
    ModelMessage,
    ModelProvider,
    ModelRequest,
    ModelResponse,
)


# ============================================================================
# 配置常量
# ============================================================================

# 各厂商默认 API 地址
DEFAULT_BASE_URLS: dict[ModelProvider, str] = {
    ModelProvider.OPENAI:           "https://api.openai.com/v1",
    ModelProvider.ANTHROPIC:        "https://api.anthropic.com/v1",
    ModelProvider.GEMINI:           "https://generativelanguage.googleapis.com/v1beta",
    ModelProvider.DEEPSEEK:         "https://api.deepseek.com/v1",
    ModelProvider.DOUBAO:           "https://ark.cn-beijing.volces.com/api/v3",
    ModelProvider.MINIMAX:          "https://api.minimax.chat/v1",
    ModelProvider.ZHIPU:            "https://open.bigmodel.cn/api/paas/v4",
    ModelProvider.OPENAI_COMPATIBLE: "http://localhost:11434/v1",
    ModelProvider.RELAY:             "https://your-relay-api.com/v1",
}

# 环境变量 Key 名映射
API_KEY_ENV_VARS: dict[ModelProvider, str] = {
    ModelProvider.OPENAI:           "OPENAI_API_KEY",
    ModelProvider.ANTHROPIC:        "ANTHROPIC_API_KEY",
    ModelProvider.GEMINI:           "GEMINI_API_KEY",
    ModelProvider.DEEPSEEK:         "DEEPSEEK_API_KEY",
    ModelProvider.DOUBAO:           "DOUBAO_API_KEY",
    ModelProvider.MINIMAX:          "MINIMAX_API_KEY",
    ModelProvider.ZHIPU:            "ZHIPU_API_KEY",
    ModelProvider.OPENAI_COMPATIBLE: "OPENAI_API_KEY",
    ModelProvider.RELAY:            "RELAY_API_KEY",
}

# 环境变量 Base URL 映射（用于覆盖默认 API 地址）
BASE_URL_ENV_VARS: dict[ModelProvider, str] = {
    ModelProvider.RELAY:            "RELAY_API_BASE",
    ModelProvider.OPENAI_COMPATIBLE: "OPENAI_COMPATIBLE_API_BASE",
}

# 各厂商默认模型
DEFAULT_MODELS: dict[ModelProvider, str] = {
    ModelProvider.OPENAI:    "gpt-5.4",
    ModelProvider.ANTHROPIC: "claude-sonnet-4-6",
    ModelProvider.GEMINI:    "gemini-3.0-flash",
    ModelProvider.DEEPSEEK:  "deepseek-v3",
    ModelProvider.DOUBAO:    "doubao-pro-32k",
    ModelProvider.MINIMAX:   "abab7-chat",
    ModelProvider.ZHIPU:     "glm-4-plus",
    ModelProvider.RELAY:     "gpt-5.4",
}


# ============================================================================
# 全局 HTTP 客户端（连接复用）
# ============================================================================

_client: Optional[httpx.AsyncClient] = None


async def get_http_client() -> httpx.AsyncClient:
    """获取或创建全局异步 HTTP 客户端（连接池复用）"""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            http2=False,
            follow_redirects=True,
        )
    return _client


async def close_http_client() -> None:
    """关闭全局 HTTP 客户端"""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


# ============================================================================
# 主路由器
# ============================================================================

class ModelRouter:
    """
    统一模型路由器。

    对外暴露唯一的 chat() 方法，内部根据 provider 分发到对应的适配器。
    所有适配器均返回统一的 ModelResponse 格式。

    Features:
    - 自动从环境变量读取 API Key
    - 连接池复用（httpx.AsyncClient）
    - 统一超时、重试、错误处理
    - 统一的 Token 用量统计
    """

    def __init__(self):
        self._retries: int = 2
        self._retry_delay: float = 2.0
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._total_requests: int = 0

    # ── 公开 API ─────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[ModelMessage],
        model: Optional[str] = None,
        provider: ModelProvider = ModelProvider.OPENAI,
        max_tokens: int = 8192,
        temperature: float = 0.7,
        timeout: float = 120.0,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        json_mode: bool = False,
        extra: Optional[dict[str, Any]] = None,
    ) -> ModelResponse:
        """
        统一聊天接口。

        Args:
            messages: 对话消息列表
            model: 模型名，不传则用该 provider 的默认模型
            provider: 模型厂商
            max_tokens: 最大输出 token 数
            temperature: 温度
            timeout: 超时秒数
            api_key: API Key，不传从环境变量读取
            api_base: 自定义 API 地址
            json_mode: 是否启用 JSON 模式（强制返回合法 JSON）
            extra: 厂商特有参数

        Returns:
            ModelResponse: 统一的模型返回
        """
        if model is None:
            model = DEFAULT_MODELS.get(provider, "gpt-5.4")

        api_key = api_key or os.getenv(API_KEY_ENV_VARS.get(provider, ""))
        if not api_key:
            raise ValueError(
                f"未找到 {provider.value} 的 API Key。"
                f"请设置环境变量 {API_KEY_ENV_VARS.get(provider, '')}"
            )

        base_url = api_base or os.getenv(BASE_URL_ENV_VARS.get(provider, "")) or DEFAULT_BASE_URLS.get(provider, "")

        request = ModelRequest(
            messages=messages,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout,
            api_key=api_key,
            api_base=base_url,
            extra=extra or {},
        )

        # 重试逻辑
        last_error: Optional[Exception] = None
        for attempt in range(self._retries + 1):
            try:
                response = await self._dispatch(request, json_mode)
                self._total_input_tokens += response.input_tokens
                self._total_output_tokens += response.output_tokens
                self._total_requests += 1
                return response
            except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < self._retries:
                    delay = self._retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
            except Exception as e:
                last_error = e
                break

        # 所有重试失败
        raise RuntimeError(
            f"模型 {model} ({provider.value}) 调用失败（重试 {self._retries} 次）: {last_error}"
        )

    # ── 分发 ─────────────────────────────────────────────────────

    async def _dispatch(self, req: ModelRequest, json_mode: bool) -> ModelResponse:
        """根据 provider 分发到对应适配器"""
        dispatchers = {
            ModelProvider.OPENAI:            self._call_openai,
            ModelProvider.ANTHROPIC:         self._call_anthropic,
            ModelProvider.GEMINI:            self._call_gemini,
            ModelProvider.DEEPSEEK:          self._call_openai,       # DeepSeek 兼容 OpenAI 协议
            ModelProvider.DOUBAO:            self._call_openai,       # 豆包兼容 OpenAI 协议
            ModelProvider.MINIMAX:           self._call_openai,       # MiniMax 兼容 OpenAI 协议
            ModelProvider.ZHIPU:             self._call_openai,       # 智谱兼容 OpenAI 协议
            ModelProvider.OPENAI_COMPATIBLE: self._call_openai,
            ModelProvider.RELAY:             self._call_openai,       # 中转站走 OpenAI 协议
        }

        handler = dispatchers.get(req.provider)
        if handler is None:
            raise ValueError(f"不支持的模型厂商: {req.provider}")

        return await handler(req, json_mode)

    # ── OpenAI 协议适配器（用官方 SDK，绕过一切 DNS/HTTP 问题）───

    async def _call_openai(self, req: ModelRequest, json_mode: bool) -> ModelResponse:
        """调用 OpenAI 兼容 API —— 使用 openai 官方 SDK"""
        from openai import AsyncOpenAI

        t0 = time.monotonic()

        msgs = []
        for m in req.messages:
            msgs.append({"role": m.role, "content": m.content})

        client = AsyncOpenAI(
            api_key=req.api_key,
            base_url=req.api_base,
            timeout=req.timeout,
            max_retries=0,
        )

        extra_body = dict(req.extra)

        # json_mode：思考型/推理型模型（o1/o3/DeepSeek-R1 等）不支持
        # response_format，先尝试标准方式，失败则回退到 prompt 内嵌 JSON 指令
        try:
            if json_mode:
                kwargs: dict[str, Any] = {
                    "model": req.model,
                    "messages": msgs,
                    "max_tokens": req.max_tokens,
                    "temperature": req.temperature,
                    "extra_body": {**extra_body, "response_format": {"type": "json_object"}},
                }
                completion = await client.chat.completions.create(**kwargs)
            else:
                completion = await client.chat.completions.create(
                    model=req.model,
                    messages=msgs,
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                    extra_body=extra_body if extra_body else None,
                )
        except Exception:
            # 模型可能不支持 response_format（如推理模型），回退：prompt 内嵌 JSON 指令
            if json_mode:
                if msgs and msgs[0]["role"] == "system":
                    msgs[0]["content"] += "\n\n你必须严格以 JSON 格式输出。不要输出其他内容。"
            completion = await client.chat.completions.create(
                model=req.model,
                messages=msgs,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
                extra_body=extra_body if extra_body else None,
            )
        finally:
            await client.close()

        latency = (time.monotonic() - t0) * 1000

        choice = completion.choices[0]
        content = choice.message.content or ""
        finish_reason = choice.finish_reason or "stop"

        input_tokens = completion.usage.prompt_tokens if completion.usage else 0
        output_tokens = completion.usage.completion_tokens if completion.usage else 0

        return ModelResponse(
            content=content,
            model=req.model,
            provider=req.provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency,
            finish_reason=finish_reason,
        )

    # ── Anthropic 适配器 ─────────────────────────────────────────

    async def _call_anthropic(self, req: ModelRequest, json_mode: bool) -> ModelResponse:
        """调用 Anthropic Messages API"""
        client = await get_http_client()
        t0 = time.monotonic()

        # 分离 system 消息
        system_prompts: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []

        for m in req.messages:
            if m.role == "system":
                system_prompts.append({"type": "text", "text": m.content})
            else:
                messages.append({"role": m.role, "content": [{"type": "text", "text": m.content}]})

        body: dict[str, Any] = {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "messages": messages,
        }

        if system_prompts:
            body["system"] = system_prompts

        if req.temperature > 0:
            body["temperature"] = req.temperature

        body.update(req.extra)

        headers = {
            "x-api-key": req.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        url = f"{req.api_base}/messages"
        http_resp = await client.post(
            url, json=body, headers=headers,
            timeout=req.timeout,
        )
        http_resp.raise_for_status()
        data = http_resp.json()

        latency = (time.monotonic() - t0) * 1000

        # Anthropic 返回 content 是列表
        content_blocks = data.get("content", [])
        text_parts = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block["text"])

        content = "\n".join(text_parts)
        finish_reason = data.get("stop_reason", "stop")

        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        return ModelResponse(
            content=content,
            model=req.model,
            provider=req.provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency,
            finish_reason=finish_reason,
            raw_response=data if req.extra.get("debug") else None,
        )

    # ── Google Gemini 适配器（原生异步） ──────────────────────────

    async def _call_gemini(self, req: ModelRequest, json_mode: bool) -> ModelResponse:
        """调用 Google Gemini API（generateContent）"""
        client = await get_http_client()
        t0 = time.monotonic()

        # Gemini 的消息格式转换
        contents: list[dict[str, Any]] = []
        system_instruction: Optional[str] = None

        for m in req.messages:
            if m.role == "system":
                system_instruction = m.content
            elif m.role == "user":
                contents.append({
                    "role": "user",
                    "parts": [{"text": m.content}],
                })
            elif m.role == "assistant":
                contents.append({
                    "role": "model",
                    "parts": [{"text": m.content}],
                })

        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": req.max_tokens,
                "temperature": req.temperature,
                "topP": 0.95,
            },
        }

        if system_instruction:
            body["systemInstruction"] = {
                "role": "system",
                "parts": [{"text": system_instruction}],
            }

        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"

        body.update(req.extra)

        headers = {
            "x-goog-api-key": req.api_key,
            "Content-Type": "application/json",
        }

        url = f"{req.api_base}/models/{req.model}:generateContent"
        http_resp = await client.post(
            url, json=body, headers=headers,
            timeout=req.timeout,
        )
        http_resp.raise_for_status()
        data = http_resp.json()

        latency = (time.monotonic() - t0) * 1000

        # 解析 Gemini 响应
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Gemini 返回空候选列表")

        candidate = candidates[0]
        content_parts = candidate.get("content", {}).get("parts", [])
        content = "".join(part.get("text", "") for part in content_parts)

        finish_reason_map = {
            "STOP": "stop",
            "MAX_TOKENS": "length",
            "SAFETY": "content_filter",
        }
        finish_reason_str = candidate.get("finishReason", "STOP")
        finish_reason = finish_reason_map.get(finish_reason_str, finish_reason_str.lower())

        usage = data.get("usageMetadata", {})
        input_tokens = usage.get("promptTokenCount", 0)
        output_tokens = usage.get("candidatesTokenCount", 0)

        return ModelResponse(
            content=content,
            model=req.model,
            provider=req.provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency,
            finish_reason=finish_reason,
            raw_response=data if req.extra.get("debug") else None,
        )

    # ── 统计信息 ─────────────────────────────────────────────────

    @property
    def stats(self) -> dict[str, Any]:
        """返回路由器统计信息"""
        return {
            "total_requests": self._total_requests,
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_tokens": self._total_input_tokens + self._total_output_tokens,
        }


# ============================================================================
# 便捷工厂函数
# ============================================================================

def create_router() -> ModelRouter:
    """创建路由器实例的便捷函数"""
    return ModelRouter()
