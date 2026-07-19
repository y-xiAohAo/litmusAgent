"""OpenAI-compatible LLM client adapter with retry and timeout."""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx

from agent.llm.base import BaseLLMClient


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
        return {
            "content": msg.get("content", ""),
            "tool_calls": msg.get("tool_calls"),
        }

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

    async def close(self) -> None:
        """关闭底层 httpx 客户端，释放连接资源。"""
        await self._client.aclose()
