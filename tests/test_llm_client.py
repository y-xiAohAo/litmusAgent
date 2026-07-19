"""Tests for OpenAIClient retry, timeout, and env-based configuration."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from agent.llm.client import OpenAIClient


def _make_success_response(content: str = "ok") -> MagicMock:
    """构造一个表示 HTTP 200 的 mock 响应对象。"""
    return MagicMock(
        raise_for_status=MagicMock(),
        json=MagicMock(
            return_value={
                "choices": [
                    {"message": {"content": content, "tool_calls": None}}
                ]
            }
        ),
    )


def _make_error_response(status_code: int) -> httpx.HTTPStatusError:
    """构造一个表示 HTTP 错误的 httpx.HTTPStatusError。"""
    request = MagicMock()
    response = MagicMock(status_code=status_code)
    return httpx.HTTPStatusError("error", request=request, response=response)


class TestOpenAIClientInit:
    """Tests for OpenAIClient constructor configuration."""

    def test_default_timeout(self):
        """默认超时应为 60 秒。"""
        client = OpenAIClient(api_key="test")
        assert client.timeout == 60.0

    def test_custom_timeout(self):
        """构造函数应接受自定义超时。"""
        client = OpenAIClient(api_key="test", timeout=10.0)
        assert client.timeout == 10.0

    def test_negative_max_retries_raises(self):
        """max_retries 为负数时应抛出 ValueError。"""
        with pytest.raises(ValueError, match="max_retries"):
            OpenAIClient(api_key="test", max_retries=-1)

    def test_zero_timeout_raises(self):
        """timeout 为零或负数时应抛出 ValueError。"""
        with pytest.raises(ValueError, match="timeout"):
            OpenAIClient(api_key="test", timeout=0)



    def test_base_url_strips_trailing_slash(self):
        """base_url 末尾斜杠应被自动去掉。"""
        client = OpenAIClient(api_key="test", base_url="https://api.example.com/v1/")
        assert client.base_url == "https://api.example.com/v1"


class TestOpenAIClientRetry:
    """Tests for retry behavior on transient failures.

    注意：这些测试通过打桩 `client._client.post` 来模拟 HTTP 响应。
    `_client` 是 OpenAIClient 的私有属性，若未来重构内部 HTTP 客户端实现，
    需要同步更新这些测试。
    """

    @pytest.mark.asyncio
    async def test_retries_on_503_and_succeeds(self):
        """遇到 503 时应重试，最终成功时返回结果。"""
        client = OpenAIClient(api_key="test", max_retries=2, backoff_factor=0.0)
        client._client.post = AsyncMock(
            side_effect=[
                _make_error_response(503),
                _make_error_response(503),
                _make_success_response("finally ok"),
            ]
        )

        result = await client.chat([{"role": "user", "content": "hi"}])

        assert result["content"] == "finally ok"
        assert client._client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_retries_on_timeout_and_succeeds(self):
        """遇到超时异常时应重试，最终成功时返回结果。"""
        client = OpenAIClient(api_key="test", max_retries=1, backoff_factor=0.0)
        client._client.post = AsyncMock(
            side_effect=[
                httpx.TimeoutException("timeout"),
                _make_success_response("ok after timeout"),
            ]
        )

        result = await client.chat([{"role": "user", "content": "hi"}])

        assert result["content"] == "ok after timeout"
        assert client._client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_network_error_and_succeeds(self):
        """遇到网络错误时应重试，最终成功时返回结果。"""
        client = OpenAIClient(api_key="test", max_retries=1, backoff_factor=0.0)
        client._client.post = AsyncMock(
            side_effect=[
                httpx.ConnectError("connection refused"),
                _make_success_response("ok after connect error"),
            ]
        )

        result = await client.chat([{"role": "user", "content": "hi"}])

        assert result["content"] == "ok after connect error"
        assert client._client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_no_retry_on_4xx(self):
        """4xx 客户端错误不应触发重试。"""
        client = OpenAIClient(api_key="test", max_retries=2, backoff_factor=0.0)
        client._client.post = AsyncMock(side_effect=_make_error_response(400))

        with pytest.raises(httpx.HTTPStatusError):
            await client.chat([{"role": "user", "content": "hi"}])

        assert client._client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_zero_max_retries_no_retry(self):
        """max_retries=0 时遇到 5xx 应直接抛出，不重试。"""
        client = OpenAIClient(api_key="test", max_retries=0, backoff_factor=0.0)
        client._client.post = AsyncMock(side_effect=_make_error_response(503))

        with pytest.raises(httpx.HTTPStatusError):
            await client.chat([{"role": "user", "content": "hi"}])

        assert client._client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_raises_last_error_after_retries_exhausted(self):
        """重试次数耗尽后，应抛出最后一次遇到的异常。"""
        client = OpenAIClient(api_key="test", max_retries=1, backoff_factor=0.0)
        client._client.post = AsyncMock(
            side_effect=[
                _make_error_response(503),
                _make_error_response(503),
            ]
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await client.chat([{"role": "user", "content": "hi"}])

        assert exc_info.value.response.status_code == 503
        assert client._client.post.call_count == 2


class TestOpenAIClientFromEnv:
    """Tests for OpenAIClient.from_env() factory method."""

    def test_from_env_reads_api_key(self):
        """应读取 OPENAI_API_KEY 环境变量。"""
        env = {
            "OPENAI_API_KEY": "env-key",
            "OPENAI_BASE_URL": "https://env.example.com/v1",
            "OPENAI_MODEL": "env-model",
        }
        with patch.dict(os.environ, env, clear=False):
            client = OpenAIClient.from_env()
            assert client.api_key == "env-key"
            assert client.base_url == "https://env.example.com/v1"
            assert client.model == "env-model"

    def test_from_env_uses_defaults(self):
        """环境变量缺失时，应使用合理默认值。"""
        # 先清除相关环境变量，避免其他测试或外部设置影响
        keys = ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"]
        with patch.dict(os.environ, {}, clear=False):
            for key in keys:
                os.environ.pop(key, None)
            client = OpenAIClient.from_env()
            assert client.api_key == ""
            assert client.base_url == "https://api.openai.com/v1"
            assert client.model == "gpt-4o"

    def test_from_env_kwargs_override_env(self):
        """kwargs 优先级应高于环境变量。"""
        env = {"OPENAI_MODEL": "env-model"}
        with patch.dict(os.environ, env, clear=False):
            client = OpenAIClient.from_env(model="override-model")
            assert client.model == "override-model"

    def test_from_env_api_key_override(self):
        """显式传入 api_key 应覆盖环境变量。"""
        env = {"OPENAI_API_KEY": "env-key"}
        with patch.dict(os.environ, env, clear=False):
            client = OpenAIClient.from_env(api_key="explicit-key")
            assert client.api_key == "explicit-key"


class TestOpenAIClientClose:
    """Tests for client lifecycle."""

    @pytest.mark.asyncio
    async def test_close_releases_resources(self):
        """close() 应调用底层 httpx 客户端的 aclose()。"""
        client = OpenAIClient(api_key="test")
        client._client.aclose = AsyncMock()

        await client.close()

        client._client.aclose.assert_awaited_once()


class TestOpenAIClientChat:
    """Tests for basic chat functionality preserved during enhancement."""

    @pytest.mark.asyncio
    async def test_chat_returns_content_and_tool_calls(self):
        """正常请求应返回 content 和 tool_calls。"""
        client = OpenAIClient(api_key="test")
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "add", "arguments": '{"a": 1, "b": 2}'},
            }
        ]
        client._client.post = AsyncMock(
            return_value=MagicMock(
                raise_for_status=MagicMock(),
                json=MagicMock(
                    return_value={
                        "choices": [
                            {"message": {"content": "result", "tool_calls": tool_calls}}
                        ]
                    }
                ),
            )
        )

        result = await client.chat([{"role": "user", "content": "add 1 and 2"}])

        assert result["content"] == "result"
        assert result["tool_calls"] == tool_calls


class TestOpenAIClientUsageTotals:
    """EVAL-015：token 用量累计（usage_totals）。"""

    @pytest.mark.asyncio
    async def test_usage_accumulates_across_calls(self):
        """每次成功响应的 usage 字段应累加到 usage_totals。"""
        client = OpenAIClient(api_key="test", backoff_factor=0.0)
        response = MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(
                return_value={
                    "choices": [{"message": {"content": "ok", "tool_calls": None}}],
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 5,
                        "total_tokens": 15,
                    },
                }
            ),
        )
        client._client.post = AsyncMock(return_value=response)

        await client.chat([{"role": "user", "content": "hi"}])
        await client.chat([{"role": "user", "content": "hi again"}])

        assert client.usage_totals == {
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "total_tokens": 30,
        }

    @pytest.mark.asyncio
    async def test_usage_missing_field_tolerated(self):
        """响应缺少 usage 字段时 usage_totals 保持为零。"""
        client = OpenAIClient(api_key="test", backoff_factor=0.0)
        client._client.post = AsyncMock(return_value=_make_success_response("ok"))

        await client.chat([{"role": "user", "content": "hi"}])

        assert client.usage_totals["total_tokens"] == 0
