"""OpenAI-compatible LLM client adapter with retry and timeout."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import httpx

from agent.llm.base import BaseLLMClient, StreamEvents

logger = logging.getLogger(__name__)


def _safe_stream_callback(callback: Any, *args: Any) -> None:
    """安全触发流式渲染回调（TD-020 评审 R1）。

    渲染层回调抛出的异常只记 warning，不中断 SSE 分片聚合与主流；
    与引擎 ``_emit_stream_event`` 的兜底语义对齐。
    """
    try:
        callback(*args)
    except Exception:  # noqa: BLE001 —— 渲染层异常不中断流
        logger.warning("流式渲染回调异常", exc_info=True)


class _StreamProgress:
    """流式请求的进度标记：是否已收到首个 data chunk / 产出过任何分片。

    用于重试判定——已渲染（已回调）的内容不可收回，一旦产出过分片
    或收到首个 data chunk，后续异常直接抛出，不再重试（TD-020）。
    """

    def __init__(self) -> None:
        self.produced = False


class OpenAIClient(BaseLLMClient):
    """Client for any OpenAI-compatible API endpoint.

    设计特点：
      1. 直接用 httpx 发送请求，不依赖 openai 官方 SDK，保持对其他兼容端点的通用性。
      2. 支持可配置超时，避免单个请求挂死导致整个 Agent 卡住。
      3. 支持指数退避重试，提高对临时网络抖动和服务端 5xx 的容忍度。
      4. 提供 from_env() 类方法，便于从环境变量读取配置。

    重试策略：
      - 重试对象：5xx 状态码、请求超时、连接错误、网络错误
      - 不重试：4xx 客户端错误（请求本身有问题，重试无意义）
      - 退避：backoff_factor * (2 ** attempt)，默认 0.5s 起
    """

    def __init__(  # noqa: PLR0913
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        thinking: bool = False,
    ) -> None:
        """初始化 OpenAI 兼容客户端。

        参数：
          api_key:         API 密钥
          model:           模型名称
          base_url:        API 端点地址（会自动去掉末尾斜杠）
          max_tokens:      每次回复的最大 token 数
          temperature:     生成温度（0-1）
          timeout:         单次请求超时时间（秒）
          max_retries:     最大重试次数（不含首次请求）
          backoff_factor:  指数退避基数（秒）
          thinking:        DeepSeek V4 思考模式开关（TD-020）；开启后请求体
                           携带 ``thinking: {"type": "enabled"}``，响应中的
                           ``reasoning_content`` 会被解析并随结果返回
        """
        if max_retries < 0:
            raise ValueError(f"max_retries 不能为负数：{max_retries}")
        if timeout <= 0:
            raise ValueError(f"timeout 必须为正数：{timeout}")

        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.thinking = thinking
        self._client = httpx.AsyncClient(timeout=timeout)
        # 累计 token 用量（EVAL-015）：每次成功响应后按 API 返回的 usage 字段累加，
        # 供批量评测等场景统计成本；不影响 chat() 返回契约。
        self.usage_totals: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    @classmethod
    def from_env(
        cls,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        **kwargs: Any,
    ) -> OpenAIClient:
        """从环境变量创建客户端。

        读取的环境变量：
          OPENAI_API_KEY   → api_key
          OPENAI_BASE_URL  → base_url
          OPENAI_MODEL     → model

        参数 api_key/model/base_url 和 kwargs 可覆盖环境变量读取的值，例如：
          OpenAIClient.from_env(timeout=30.0)

        注意：如果环境变量不存在且未显式传入，api_key 默认为空字符串，
              实际调用时会由服务端返回 401 错误。这是预期行为。
        """
        # 风险点：若环境变量未设置且未显式传入，api_key 默认为空字符串，
        # 实际调用时会由服务端返回 401 错误。这是预期行为。
        final_api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        final_model = model if model is not None else os.environ.get("OPENAI_MODEL", "gpt-4o")
        final_base_url = (
            base_url if base_url is not None
            else os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        )
        return cls(
            api_key=final_api_key,
            model=final_model,
            base_url=final_base_url,
            **kwargs,
        )

    def _should_retry(self, exc: Exception, attempt: int) -> bool:
        """判断当前异常是否应该触发重试。

        参数：
          exc:     捕获到的异常
          attempt: 当前是第几次尝试（从 0 开始）

        返回：
          True = 应该重试；False = 直接抛出
        """
        if attempt >= self.max_retries:
            return False

        # 5xx 服务端错误：可能临时不可用，值得重试
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
            return True

        # 超时、连接错误、网络错误：通常是暂时的
        if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
            return True

        return False

    async def _do_chat_request(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """发送一次 chat completion 请求并解析响应。

        参数：
          messages: OpenAI 格式的消息列表
          tools:    可选的工具 schema 列表
          kwargs:   透传给 LLM 的额外参数

        返回：
          {"content": str, "tool_calls": list | None}
        """
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            **kwargs,
        }
        if tools:
            body["tools"] = tools
        if self.thinking:
            # DeepSeek V4 思考模式（TD-020）
            body["thinking"] = {"type": "enabled"}

        resp = await self._client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage") or {}
        for key in self.usage_totals:
            self.usage_totals[key] += int(usage.get(key, 0) or 0)
        choice = data["choices"][0]
        msg = choice["message"]
        result: dict[str, Any] = {
            "content": msg.get("content", ""),
            "tool_calls": msg.get("tool_calls"),
        }
        # TD-020：思考链内容（DeepSeek V4 thinking 模式）随结果返回，
        # 仅用于渲染层展示；多轮对话按官方口径不回传，故不进消息历史。
        reasoning = msg.get("reasoning_content")
        if reasoning:
            result["reasoning_content"] = reasoning
        return result

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """发送聊天完成请求，带重试机制。

        参数：
          messages: OpenAI 格式的消息列表
          tools:    可选的工具 schema 列表
          kwargs:   透传给 LLM 的额外参数

        返回：
          {"content": str, "tool_calls": list | None}

        抛出：
          httpx.HTTPStatusError: 4xx 错误或重试耗尽后的最后一次 5xx 错误
          httpx.TimeoutException: 重试耗尽后的最后一次超时
          httpx.NetworkError:     重试耗尽后的最后一次网络错误
        """
        for attempt in range(self.max_retries + 1):
            try:
                return await self._do_chat_request(messages, tools, **kwargs)
            except Exception as exc:
                if self._should_retry(exc, attempt):
                    wait_time = self.backoff_factor * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
                raise

        # 循环正常不应走到这里，_should_retry 会在最后一次 raise
        raise RuntimeError("Unexpected exit from retry loop")

    def _accumulate_tool_call_chunk(
        self, tool_acc: dict[int, dict[str, Any]], tc: dict[str, Any]
    ) -> None:
        """把一片 tool_calls 流式分片聚合进 tool_acc（按 index 分槽）。

        首片携带 id / function.name，后续分片的 function.arguments 为
        字符串增量，逐片拼接；index 非法的坏分片跳过并记 warning。
        """
        try:
            idx = int(tc.get("index", 0))
        except (TypeError, ValueError):
            logger.warning("tool_calls 分片 index 非法，已跳过：%r", tc.get("index"))
            return
        slot = tool_acc.setdefault(
            idx,
            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
        )
        if tc.get("id"):
            slot["id"] = tc["id"]
        if tc.get("type"):
            slot["type"] = tc["type"]
        function = tc.get("function") or {}
        if function.get("name"):
            slot["function"]["name"] += function["name"]
        if function.get("arguments"):
            slot["function"]["arguments"] += function["arguments"]

    async def _do_chat_stream_request(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        events: StreamEvents | None,
        progress: _StreamProgress,
        *,
        include_usage: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """发送一次流式（SSE）chat completion 请求并聚合分片（TD-020）。

        协议要点：
          - 请求体带 ``stream: True``；``include_usage=True`` 时附加
            ``stream_options.include_usage``，使最后一个 chunk 携带 usage
            （与非流式同口径累加）；降级为 False 时（端点不支持
            stream_options）不带该字段，**usage 口径：降级请求不计 usage**；
          - ``data: [DONE]`` 结束；空行跳过；坏 JSON 行 warning 跳过；
          - delta.content / delta.reasoning_content 分片即时回调 events，
            回调异常只记 warning，不中断流（R1）；
          - delta.tool_calls 按 index 聚合，arguments 字符串拼接。

        参数：
          progress:      进度标记，收到首个 data chunk 后置 produced=True，
                         供 chat_stream 判定"已产出内容，不可再重试"。
          include_usage: 是否在请求体携带 stream_options.include_usage。

        返回：
          {"content": str, "tool_calls": list | None}，
          有思考链时附加 "reasoning_content": str。
        """
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True,
            **kwargs,
        }
        if include_usage:
            body["stream_options"] = {"include_usage": True}
        if tools:
            body["tools"] = tools
        if self.thinking:
            body["thinking"] = {"type": "enabled"}

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_acc: dict[int, dict[str, Any]] = {}

        async with self._client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload == "[DONE]":
                    break
                progress.produced = True
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    logger.warning("SSE 坏行已跳过：%s", payload[:100])
                    continue

                usage = chunk.get("usage")
                if usage:
                    for key in self.usage_totals:
                        self.usage_totals[key] += int(usage.get(key, 0) or 0)

                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}

                content_piece = delta.get("content")
                if content_piece:
                    content_parts.append(content_piece)
                    if events is not None and events.on_token is not None:
                        _safe_stream_callback(events.on_token, content_piece)

                reasoning_piece = delta.get("reasoning_content")
                if reasoning_piece:
                    reasoning_parts.append(reasoning_piece)
                    if events is not None and events.on_reasoning is not None:
                        _safe_stream_callback(events.on_reasoning, reasoning_piece)

                for tc in delta.get("tool_calls") or []:
                    self._accumulate_tool_call_chunk(tool_acc, tc)

        result: dict[str, Any] = {
            "content": "".join(content_parts),
            "tool_calls": [tool_acc[i] for i in sorted(tool_acc)] or None,
        }
        if reasoning_parts:
            result["reasoning_content"] = "".join(reasoning_parts)
        return result

    @staticmethod
    def _is_stream_options_400(exc: Exception) -> bool:
        """判断异常是否为"端点拒绝 stream_options"的特定 400（TD-020 评审 O3）。

        仅当 HTTP 400 且响应体提到 stream_options 时返回 True。
        """
        return (
            isinstance(exc, httpx.HTTPStatusError)
            and exc.response.status_code == 400
            and "stream_options" in exc.response.text
        )

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        events: StreamEvents | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """流式聊天完成请求，带受限重试机制（TD-020）。

        重试策略与 chat() 相同，但**只允许在产出任何分片前重试**：
        一旦收到首个 data chunk（内容可能已被渲染层展示，不可收回），
        后续异常直接抛出，不再重试。

        include_usage 降级（O3）：端点对 ``stream_options`` 返回 400 时，
        在产出任何分片前去掉该字段重试一次；降级请求不计 usage
        （端点不返回 usage chunk）。降级后仍失败则抛出 RuntimeError，
        明确提示"该端点可能不支持 include_usage"。

        参数 / 返回 / 抛出：同 chat()，另见 _do_chat_stream_request。
        """
        for attempt in range(self.max_retries + 1):
            progress = _StreamProgress()
            try:
                return await self._do_chat_stream_request(
                    messages, tools, events, progress, **kwargs
                )
            except Exception as exc:
                if not progress.produced and self._is_stream_options_400(exc):
                    logger.warning(
                        "端点对 stream_options 返回 400，降级去掉该字段重试一次；"
                        "本次请求不计 usage"
                    )
                    progress = _StreamProgress()
                    try:
                        return await self._do_chat_stream_request(
                            messages, tools, events, progress,
                            include_usage=False, **kwargs,
                        )
                    except httpx.HTTPStatusError as exc2:
                        raise RuntimeError(
                            f"流式请求失败（已去掉 stream_options 仍返回 "
                            f"{exc2.response.status_code}）："
                            f"该端点可能不支持 include_usage，请检查端点兼容性"
                        ) from exc2
                if not progress.produced and self._should_retry(exc, attempt):
                    wait_time = self.backoff_factor * (2 ** attempt)
                    await asyncio.sleep(wait_time)
                    continue
                raise

        # 循环正常不应走到这里，_should_retry 会在最后一次 raise
        raise RuntimeError("Unexpected exit from retry loop")

    async def close(self) -> None:
        """关闭底层 httpx 客户端，释放连接资源。"""
        await self._client.aclose()
