"""TD-020 流式输出与可观测渲染测试。

覆盖：
  - OpenAIClient SSE 解析（content / reasoning_content / tool_calls 分片、usage chunk）
  - tool_calls 分片聚合（乱序 index、坏 JSON 行跳过、arguments 拼接）
  - 流式中途断连不重试（已产出分片后异常直接抛出）
  - EchoClient.chat_stream 逐词回调
  - BaseLLMClient.chat_stream 默认回退实现
  - 引擎 stream_events 注入与工具进度回调
  - CLI plain 模式渲染输出
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from agent.config import AgentConfig
from agent.core.engine import Agent
from agent.llm.base import BaseLLMClient, EchoClient, StreamEvents
from agent.llm.client import OpenAIClient


def _sse_chunk(delta: dict[str, Any], usage: dict[str, Any] | None = None) -> str:
    """构造一行 SSE data 载荷。"""
    chunk: dict[str, Any] = {"choices": [{"delta": delta}]}
    if usage is not None:
        chunk["usage"] = usage
    return f"data: {json.dumps(chunk)}"


def _make_stream_response(lines: list[str]) -> MagicMock:
    """构造一个可作为 ``_client.stream(...)`` 异步上下文管理器的 mock。

    返回的 response 支持 raise_for_status() 与 aiter_lines()。
    """
    response = MagicMock()
    response.raise_for_status = MagicMock()

    async def _aiter_lines():
        for line in lines:
            yield line

    response.aiter_lines = _aiter_lines

    stream_ctx = MagicMock()
    # MagicMock 预建 __aenter__/__aexit__ 为 AsyncMock，直接配 return_value 即可
    stream_ctx.__aenter__.return_value = response
    stream_ctx.__aexit__.return_value = False
    return stream_ctx


def _patch_stream(client: OpenAIClient, lines: list[str]) -> MagicMock:
    """把 client._client.stream 替换为返回伪造 SSE 行的 mock。"""
    stream_mock = MagicMock(return_value=_make_stream_response(lines))
    client._client.stream = stream_mock
    return stream_mock


class TestSSEParsing:
    """SSE 分片解析与聚合。"""

    async def test_content_chunks_aggregated_and_callbacked(self):
        """content 分片应累积为完整文本，且逐片回调 on_token。"""
        client = OpenAIClient(api_key="test")
        lines = [
            _sse_chunk({"content": "Hello"}),
            "",  # 空行应跳过
            _sse_chunk({"content": " world"}),
            "data: [DONE]",
        ]
        _patch_stream(client, lines)
        tokens: list[str] = []
        events = StreamEvents(on_token=tokens.append)

        result = await client.chat_stream(
            [{"role": "user", "content": "hi"}], events=events
        )

        assert result["content"] == "Hello world"
        assert result["tool_calls"] is None
        assert "reasoning_content" not in result
        assert tokens == ["Hello", " world"]

    async def test_reasoning_content_chunks(self):
        """reasoning_content 分片应累积并回调 on_reasoning。"""
        client = OpenAIClient(api_key="test")
        lines = [
            _sse_chunk({"reasoning_content": "先想"}),
            _sse_chunk({"reasoning_content": "再想"}),
            _sse_chunk({"content": "答案"}),
            "data: [DONE]",
        ]
        _patch_stream(client, lines)
        reasoning: list[str] = []
        events = StreamEvents(on_reasoning=reasoning.append)

        result = await client.chat_stream(
            [{"role": "user", "content": "hi"}], events=events
        )

        assert result["content"] == "答案"
        assert result["reasoning_content"] == "先想再想"
        assert reasoning == ["先想", "再想"]

    async def test_tool_calls_chunks_aggregated(self):
        """tool_calls 分片应按 index 聚合：首片带 id/name，arguments 拼接。"""
        client = OpenAIClient(api_key="test")
        lines = [
            _sse_chunk({
                "tool_calls": [{
                    "index": 0, "id": "call_1", "type": "function",
                    "function": {"name": "file_write", "arguments": '{"path":'},
                }],
            }),
            _sse_chunk({
                "tool_calls": [{
                    "index": 0,
                    "function": {"arguments": '"/workspace/a.py"}'},
                }],
            }),
            "data: [DONE]",
        ]
        _patch_stream(client, lines)

        result = await client.chat_stream([{"role": "user", "content": "hi"}])

        assert result["content"] == ""
        assert result["tool_calls"] == [{
            "id": "call_1",
            "type": "function",
            "function": {"name": "file_write", "arguments": '{"path":"/workspace/a.py"}'},
        }]

    async def test_tool_calls_out_of_order_indexes(self):
        """乱序 index 的分片应各自归入正确槽位，最终按 index 排序输出。"""
        client = OpenAIClient(api_key="test")
        lines = [
            _sse_chunk({
                "tool_calls": [{
                    "index": 1, "id": "call_b", "type": "function",
                    "function": {"name": "grep", "arguments": '{"p":1}'},
                }],
            }),
            _sse_chunk({
                "tool_calls": [{
                    "index": 0, "id": "call_a", "type": "function",
                    "function": {"name": "glob", "arguments": '{"p":'},
                }],
            }),
            _sse_chunk({
                "tool_calls": [{"index": 0, "function": {"arguments": '2}'}}],
            }),
            "data: [DONE]",
        ]
        _patch_stream(client, lines)

        result = await client.chat_stream([{"role": "user", "content": "hi"}])

        assert [tc["id"] for tc in result["tool_calls"]] == ["call_a", "call_b"]
        assert result["tool_calls"][0]["function"]["arguments"] == '{"p":2}'

    async def test_bad_json_line_skipped_with_warning(self, caplog):
        """坏 JSON 行应跳过并记 warning，不影响其余分片。"""
        client = OpenAIClient(api_key="test")
        lines = [
            _sse_chunk({"content": "a"}),
            "data: {not-json",
            _sse_chunk({"content": "b"}),
            "data: [DONE]",
        ]
        _patch_stream(client, lines)

        with caplog.at_level("WARNING", logger="agent.llm.client"):
            result = await client.chat_stream([{"role": "user", "content": "hi"}])

        assert result["content"] == "ab"
        assert any("SSE 坏行" in rec.message for rec in caplog.records)

    async def test_bad_tool_call_index_skipped(self, caplog):
        """index 非法的 tool_calls 分片应跳过并记 warning。"""
        client = OpenAIClient(api_key="test")
        lines = [
            _sse_chunk({
                "tool_calls": [{"index": "bad", "function": {"arguments": "x"}}],
            }),
            _sse_chunk({
                "tool_calls": [{
                    "index": 0, "id": "call_1",
                    "function": {"name": "glob", "arguments": "{}"},
                }],
            }),
            "data: [DONE]",
        ]
        _patch_stream(client, lines)

        with caplog.at_level("WARNING", logger="agent.llm.client"):
            result = await client.chat_stream([{"role": "user", "content": "hi"}])

        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["id"] == "call_1"
        assert any("index 非法" in rec.message for rec in caplog.records)

    async def test_usage_chunk_accumulates(self):
        """流式 usage chunk 应累加进 usage_totals（与非流式同口径）。"""
        client = OpenAIClient(api_key="test")
        lines = [
            _sse_chunk({"content": "ok"}),
            _sse_chunk({}, usage={
                "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
            }),
            "data: [DONE]",
        ]
        _patch_stream(client, lines)

        await client.chat_stream([{"role": "user", "content": "hi"}])

        assert client.usage_totals == {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
        }

    async def test_usage_null_middle_chunk_last_non_null_wins(self):
        """中间 chunk 带 ``"usage": null`` 时应忽略，取末帧完整 usage。

        真实端点实测（DeepSeek v4-flash）：流式中间帧携带 null usage，
        只有最后一个 chunk 带完整 usage 对象。
        """
        client = OpenAIClient(api_key="test")
        usage_final = {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
        }
        lines = [
            'data: {"choices": [{"delta": {"content": "a"}}], "usage": null}',
            'data: {"choices": [{"delta": {"content": "b"}}], "usage": null}',
            _sse_chunk({}, usage=usage_final),
            "data: [DONE]",
        ]
        _patch_stream(client, lines)

        result = await client.chat_stream([{"role": "user", "content": "hi"}])

        assert result["content"] == "ab"
        assert client.usage_totals == usage_final

    async def test_request_body_has_stream_and_thinking(self):
        """流式请求体应带 stream/stream_options；thinking 开启时带 thinking 参数。"""
        client = OpenAIClient(api_key="test", thinking=True)
        lines = [_sse_chunk({"content": "ok"}), "data: [DONE]"]
        stream_mock = _patch_stream(client, lines)

        await client.chat_stream([{"role": "user", "content": "hi"}])

        body = stream_mock.call_args.kwargs["json"]
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        assert body["thinking"] == {"type": "enabled"}

    async def test_thinking_off_by_default(self):
        """thinking 默认关闭，请求体不含 thinking 字段。"""
        client = OpenAIClient(api_key="test")
        lines = [_sse_chunk({"content": "ok"}), "data: [DONE]"]
        stream_mock = _patch_stream(client, lines)

        await client.chat_stream([{"role": "user", "content": "hi"}])

        assert "thinking" not in stream_mock.call_args.kwargs["json"]


class TestStreamRetry:
    """流式重试限制：产出任何分片后不再重试。"""

    async def test_no_retry_after_first_chunk(self):
        """已收到 data chunk 后发生网络错误：直接抛出，只调用一次。"""
        client = OpenAIClient(api_key="test", max_retries=3, backoff_factor=0.0)

        response = MagicMock()
        response.raise_for_status = MagicMock()

        async def _aiter_lines():
            yield _sse_chunk({"content": "partial"})
            raise httpx.NetworkError("connection dropped")

        response.aiter_lines = _aiter_lines
        stream_ctx = MagicMock()
        stream_ctx.__aenter__.return_value = response
        stream_ctx.__aexit__.return_value = False
        stream_mock = MagicMock(return_value=stream_ctx)
        client._client.stream = stream_mock

        tokens: list[str] = []
        events = StreamEvents(on_token=tokens.append)
        with pytest.raises(httpx.NetworkError):
            await client.chat_stream([{"role": "user", "content": "hi"}], events=events)

        assert stream_mock.call_count == 1
        assert tokens == ["partial"]  # 已渲染内容保留

    async def test_retry_before_any_chunk(self):
        """首个 chunk 前的失败（如连接错误）仍按原策略重试。"""
        client = OpenAIClient(api_key="test", max_retries=2, backoff_factor=0.0)

        ok_lines = [_sse_chunk({"content": "ok"}), "data: [DONE]"]
        stream_mock = MagicMock(
            side_effect=[
                httpx.ConnectError("refused"),
                _make_stream_response(ok_lines),
            ]
        )
        client._client.stream = stream_mock

        result = await client.chat_stream([{"role": "user", "content": "hi"}])

        assert result["content"] == "ok"
        assert stream_mock.call_count == 2


class TestEchoClientStream:
    """EchoClient.chat_stream 逐词模拟流式。"""

    async def test_word_by_word_callback(self):
        """应按空格逐词回调（词+空格），返回结构与 chat() 一致。"""
        client = EchoClient()
        tokens: list[str] = []
        events = StreamEvents(on_token=tokens.append)

        result = await client.chat_stream(
            [{"role": "user", "content": "hello world"}], events=events
        )

        assert result == {"content": "You said: hello world", "tool_calls": None}
        assert "".join(tokens) == "You said: hello world "
        assert len(tokens) > 1  # 确实逐词而非一次性

    async def test_no_events_no_callback(self):
        """events 为 None 时正常返回，不回调。"""
        client = EchoClient()
        result = await client.chat_stream([{"role": "user", "content": "hi"}])
        assert result["content"] == "You said: hi"


class RecordingClient(BaseLLMClient):
    """只实现 chat() 的最小 client，用于验证基类默认回退与引擎路由。"""

    def __init__(self, content: str = "done") -> None:
        self.content = content
        self.chat_calls = 0
        self.chat_stream_calls = 0

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.chat_calls += 1
        return {"content": self.content, "tool_calls": None}


class ToolCallingClient(BaseLLMClient):
    """第一轮要求调用工具、第二轮返回文本的测试 client。"""

    def __init__(self) -> None:
        self.chat_calls = 0
        self.chat_stream_calls = 0

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.chat_calls += 1
        return self._response()

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        events: StreamEvents | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.chat_stream_calls += 1
        return self._response()

    def _response(self) -> dict[str, Any]:
        if self.chat_calls + self.chat_stream_calls == 1:
            return {
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "glob", "arguments": '{"pattern": "*.py"}'},
                }],
            }
        return {"content": "finished", "tool_calls": None}


class TestBaseDefaultFallback:
    """基类 chat_stream 默认回退实现。"""

    async def test_default_fallback_once_callback(self):
        """只实现 chat() 的 client，chat_stream 应回退并一次性回调。"""
        client = RecordingClient(content="hello stream")
        tokens: list[str] = []
        events = StreamEvents(on_token=tokens.append)

        result = await client.chat_stream(
            [{"role": "user", "content": "hi"}], events=events
        )

        assert result["content"] == "hello stream"
        assert tokens == ["hello stream"]
        assert client.chat_calls == 1


class TestEngineStreaming:
    """引擎 stream_events 注入与路由。"""

    def _make_config(self, stream: bool) -> AgentConfig:
        config = AgentConfig()
        config.llm.stream = stream
        return config

    async def test_stream_on_uses_chat_stream(self):
        """config.llm.stream 开启且注入 events 时，主循环应走 chat_stream。"""
        client = ToolCallingClient()
        agent = Agent(
            llm_client=client,
            config=self._make_config(stream=True),
            stream_events=StreamEvents(),
        )

        result = await agent.run("do something")

        assert result == "finished"
        assert client.chat_stream_calls == 2
        assert client.chat_calls == 0

    async def test_stream_off_uses_chat(self):
        """默认（stream 关）走 chat()，零回归。"""
        client = ToolCallingClient()
        agent = Agent(llm_client=client, config=self._make_config(stream=False))

        await agent.run("do something")

        assert client.chat_calls == 2
        assert client.chat_stream_calls == 0

    async def test_stream_on_without_events_uses_chat(self):
        """stream 开但未注入 events 时仍走 chat()。"""
        client = ToolCallingClient()
        agent = Agent(llm_client=client, config=self._make_config(stream=True))

        await agent.run("do something")

        assert client.chat_calls == 2
        assert client.chat_stream_calls == 0

    async def test_tool_progress_callbacks(self):
        """工具执行前后应触发 on_tool_start / on_tool_end。"""
        client = ToolCallingClient()
        starts: list[tuple[str, str]] = []
        ends: list[tuple[str, bool]] = []
        events = StreamEvents(
            on_tool_start=lambda name, args: starts.append((name, args)),
            on_tool_end=lambda name, ok: ends.append((name, ok)),
        )
        agent = Agent(
            llm_client=client,
            config=self._make_config(stream=True),
            stream_events=events,
        )

        await agent.run("do something")

        assert starts == [("glob", '{"pattern": "*.py"}')]
        assert ends == [("glob", True)]

    async def test_tool_start_args_summary_truncated(self):
        """on_tool_start 的参数摘要应在引擎真实调用路径上截断到 100 字符。"""

        class _LongArgsClient(BaseLLMClient):
            """第一轮返回超长参数的工具调用，第二轮返回文本。"""

            def __init__(self) -> None:
                self.calls = 0

            async def chat(
                self,
                messages: list[dict[str, Any]],
                tools: list[dict[str, Any]] | None = None,
                **kwargs: Any,
            ) -> dict[str, Any]:
                self.calls += 1
                if self.calls == 1:
                    return {
                        "content": "",
                        "tool_calls": [{
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "glob",
                                "arguments": json.dumps({"pattern": "x" * 200}),
                            },
                        }],
                    }
                return {"content": "done", "tool_calls": None}

        client = _LongArgsClient()
        starts: list[str] = []
        events = StreamEvents(on_tool_start=lambda name, args: starts.append(args))
        agent = Agent(
            llm_client=client,
            config=self._make_config(stream=True),
            stream_events=events,
        )

        await agent.run("do something")

        assert starts, "应触发 on_tool_start"
        assert len(starts[0]) == 100

    async def test_tool_progress_gated_by_stream_config(self):
        """Y2：stream 关闭时即使注入了 events，工具进度事件也不应发送。"""
        client = ToolCallingClient()
        starts: list[str] = []
        ends: list[bool] = []
        events = StreamEvents(
            on_tool_start=lambda name, args: starts.append(name),
            on_tool_end=lambda name, ok: ends.append(ok),
        )
        agent = Agent(
            llm_client=client,
            config=self._make_config(stream=False),
            stream_events=events,
        )

        result = await agent.run("do something")

        assert result == "finished"
        assert starts == []
        assert ends == []

    async def test_invalid_arguments_json_self_heals(self):
        """O4：arguments 为非法 JSON 时不穿透 run()，构造失败 ToolResult 回喂 LLM。"""

        class _BadArgsClient(BaseLLMClient):
            """第一轮返回 arguments 非法 JSON 的工具调用，第二轮返回文本。"""

            def __init__(self) -> None:
                self.calls = 0

            async def chat(
                self,
                messages: list[dict[str, Any]],
                tools: list[dict[str, Any]] | None = None,
                **kwargs: Any,
            ) -> dict[str, Any]:
                self.calls += 1
                if self.calls == 1:
                    return {
                        "content": "",
                        "tool_calls": [{
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "glob", "arguments": "{bad json"},
                        }],
                    }
                return {"content": "recovered", "tool_calls": None}

        agent = Agent(llm_client=_BadArgsClient(), config=self._make_config(stream=False))

        result = await agent.run("do something")

        assert result == "recovered"
        tool_msgs = [m for m in agent.messages if m.role == "tool"]
        assert len(tool_msgs) == 1
        assert "工具参数解析失败" in tool_msgs[0].content
        assert "JSONDecodeError" in tool_msgs[0].content

    async def test_stream_disconnect_marks_trace_partial(self):
        """O2：流式中途断连时，当前 trace step 应记录 stream_partial 事件。"""

        class _StreamBoomClient(BaseLLMClient):
            async def chat(
                self,
                messages: list[dict[str, Any]],
                tools: list[dict[str, Any]] | None = None,
                **kwargs: Any,
            ) -> dict[str, Any]:
                raise AssertionError("stream 开启时不应走 chat()")

            async def chat_stream(
                self,
                messages: list[dict[str, Any]],
                tools: list[dict[str, Any]] | None = None,
                *,
                events: StreamEvents | None = None,
                **kwargs: Any,
            ) -> dict[str, Any]:
                if events is not None and events.on_token is not None:
                    events.on_token("partial")
                raise httpx.NetworkError("connection dropped")

        agent = Agent(
            llm_client=_StreamBoomClient(),
            config=self._make_config(stream=True),
            stream_events=StreamEvents(on_token=lambda text: None),
        )

        with pytest.raises(httpx.NetworkError):
            await agent.run("do something")

        step = agent.trace.current_step()
        assert step is not None
        partial_events = [e for e in step.events if e.event_type == "stream_partial"]
        assert len(partial_events) == 1
        assert "NetworkError" in partial_events[0].payload["error"]

    async def test_callback_exception_does_not_break_engine(self):
        """渲染回调抛异常不应炸引擎主流程。"""
        client = ToolCallingClient()

        def _boom(name: str, args: str) -> None:
            raise RuntimeError("renderer broken")

        events = StreamEvents(on_tool_start=_boom)
        agent = Agent(
            llm_client=client,
            config=self._make_config(stream=True),
            stream_events=events,
        )

        result = await agent.run("do something")
        assert result == "finished"


class TestCliPlainRendering:
    """CLI plain 模式流式渲染输出。"""

    def test_plain_renderer_output(self, capsys):
        """plain 渲染器应直出 token、思考链前缀与工具进度行（ASCII 标记）。"""
        from agent.cli.chat import CliStreamRenderer

        renderer = CliStreamRenderer(plain=True)
        renderer.events.on_reasoning("想一下")
        renderer.events.on_token("你好")
        renderer.events.on_token("世界")
        renderer.events.on_tool_start("file_write", '{"path": "/workspace/a.py"}')
        renderer.events.on_tool_end("file_write", True)
        renderer.events.on_tool_end("file_read", False)
        renderer.finish()

        out = capsys.readouterr().out
        assert "[thinking] 想一下" in out
        assert "你好世界" in out
        assert "→ file_write" in out
        assert "[OK] file_write" in out
        assert "[FAIL] file_read" in out


class TestCliRichRendering:
    """CLI rich 模式流式渲染（TD-020 评审 O1：此前 rich 零覆盖）。"""

    def _make_renderer(self):
        """构造 rich 渲染器，console 输出重定向到内存文件。"""
        import io

        from rich.console import Console

        from agent.cli.chat import CliStreamRenderer

        renderer = CliStreamRenderer(plain=False)
        assert renderer._console is not None
        renderer._console = Console(
            file=io.StringIO(), width=80, force_terminal=True,
        )
        return renderer

    def test_rich_multiturn_buffer_reset(self):
        """工具调用后新一轮 content 分片不应混入上一轮已渲染文本（O1）。"""
        renderer = self._make_renderer()
        renderer.events.on_token("第一轮")
        renderer.events.on_token("内容")
        renderer.events.on_tool_start("glob", "{}")
        # on_tool_start 应清空上一轮 buffer
        assert renderer._buffer == []
        renderer.events.on_tool_end("glob", True)
        renderer.events.on_token("第二轮")
        renderer.finish()

        out = renderer._console.file.getvalue()
        assert "第二轮" in out

    def test_rich_reasoning_and_tool_progress(self):
        """rich 模式思考链弱化直出与工具进度行正常渲染。"""
        renderer = self._make_renderer()
        renderer.events.on_reasoning("想一下")
        renderer.events.on_token("答案")
        renderer.events.on_tool_start("file_read", '{"path": "/a.py"}')
        renderer.events.on_tool_end("file_read", True)
        renderer.finish()

        out = renderer._console.file.getvalue()
        assert "思考链" in out
        assert "→ file_read" in out
        assert "✓ file_read" in out


def _make_http_400(text: str) -> httpx.HTTPStatusError:
    """构造一个带响应体的 400 HTTPStatusError。"""
    request = httpx.Request("POST", "http://test.local/chat/completions")
    response = httpx.Response(400, text=text, request=request)
    return httpx.HTTPStatusError("bad request", request=request, response=response)


def _make_raising_stream_ctx(exc: Exception) -> MagicMock:
    """构造一个 stream 上下文管理器：raise_for_status 抛指定异常。"""
    response = MagicMock()
    response.raise_for_status = MagicMock(side_effect=exc)
    stream_ctx = MagicMock()
    stream_ctx.__aenter__.return_value = response
    stream_ctx.__aexit__.return_value = False
    return stream_ctx


class TestStreamCallbackGuard:
    """R1：客户端流式回调异常兜底，不中断分片聚合。"""

    async def test_callback_exception_does_not_break_stream(self, caplog):
        """on_token / on_reasoning 抛异常时流式仍完成，异常记 warning。"""
        client = OpenAIClient(api_key="test")
        lines = [
            _sse_chunk({"reasoning_content": "想"}),
            _sse_chunk({"content": "a"}),
            _sse_chunk({"content": "b"}),
            "data: [DONE]",
        ]
        _patch_stream(client, lines)

        def _boom(text: str) -> None:
            raise RuntimeError("renderer broken")

        events = StreamEvents(on_token=_boom, on_reasoning=_boom)
        with caplog.at_level("WARNING", logger="agent.llm.client"):
            result = await client.chat_stream(
                [{"role": "user", "content": "hi"}], events=events
            )

        assert result["content"] == "ab"
        assert result["reasoning_content"] == "想"
        assert any("回调异常" in rec.message for rec in caplog.records)


class TestIncludeUsageFallback:
    """O3：端点不支持 stream_options 时的 include_usage 降级。"""

    async def test_stream_options_400_falls_back_without_it(self):
        """首个 400（提到 stream_options）→ 去掉 stream_options 重试成功。"""
        client = OpenAIClient(api_key="test", max_retries=0)
        err = _make_http_400('{"error": "stream_options is not supported"}')
        ok_lines = [_sse_chunk({"content": "ok"}), "data: [DONE]"]
        stream_mock = MagicMock(side_effect=[
            _make_raising_stream_ctx(err),
            _make_stream_response(ok_lines),
        ])
        client._client.stream = stream_mock

        result = await client.chat_stream([{"role": "user", "content": "hi"}])

        assert result["content"] == "ok"
        assert stream_mock.call_count == 2
        first_body = stream_mock.call_args_list[0].kwargs["json"]
        second_body = stream_mock.call_args_list[1].kwargs["json"]
        assert first_body["stream_options"] == {"include_usage": True}
        assert "stream_options" not in second_body

    async def test_stream_options_400_fallback_still_fails(self):
        """降级重试仍 400 时，抛出明确提示 include_usage 兼容性的 RuntimeError。"""
        client = OpenAIClient(api_key="test", max_retries=0)
        err = _make_http_400('{"error": "stream_options is not supported"}')
        stream_mock = MagicMock(side_effect=[
            _make_raising_stream_ctx(err),
            _make_raising_stream_ctx(err),
        ])
        client._client.stream = stream_mock

        with pytest.raises(RuntimeError, match="include_usage"):
            await client.chat_stream([{"role": "user", "content": "hi"}])

    async def test_unrelated_400_does_not_fallback(self):
        """与 stream_options 无关的 400 不触发降级，原样抛出。"""
        client = OpenAIClient(api_key="test", max_retries=0)
        err = _make_http_400('{"error": "invalid model"}')
        stream_mock = MagicMock(side_effect=[_make_raising_stream_ctx(err)])
        client._client.stream = stream_mock

        with pytest.raises(httpx.HTTPStatusError):
            await client.chat_stream([{"role": "user", "content": "hi"}])

        assert stream_mock.call_count == 1
