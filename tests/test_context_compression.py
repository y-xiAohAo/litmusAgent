"""Phase 7 上下文压缩测试（Task 7.1 起）。"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from agent.config import AgentConfig, load_config
from agent.core.context_cache import CacheEntry, ContextCache
from agent.core.token_estimator import (
    CharTokenEstimator,
    TiktokenEstimator,
    TokenEstimator,
)
from agent.core.tool_result_externalizer import ToolResultExternalizer
from agent.core.types import Message, ToolCall, ToolSpec
from agent.llm.base import BaseLLMClient


class TestTokenEstimatorABC:
    """TokenEstimator 抽象基类的基础约束。"""

    def test_abstract_class_cannot_be_instantiated(self) -> None:
        """抽象基类不能直接实例化。"""
        with pytest.raises(TypeError):
            TokenEstimator()  # type: ignore[abstract]


class TestCharTokenEstimator:
    """CharTokenEstimator 的单元测试。"""

    def test_estimate_simple_messages(self) -> None:
        """按字符数估算简单消息列表的 token。"""
        estimator = CharTokenEstimator(chars_per_token=4)
        messages = [
            Message(role="system", content="hello"),
            Message(role="user", content="world"),
        ]
        # 总字符 10，每 4 字符 1 token => 2
        assert estimator.estimate(messages) == 2

    def test_default_chars_per_token(self) -> None:
        """默认每 4 字符估算 1 token。"""
        estimator = CharTokenEstimator()
        messages = [Message(role="user", content="a" * 8)]
        assert estimator.estimate(messages) == 2

    def test_custom_chars_per_token(self) -> None:
        """自定义 chars_per_token 生效。"""
        estimator = CharTokenEstimator(chars_per_token=2)
        messages = [Message(role="user", content="abcd")]
        assert estimator.estimate(messages) == 2

    def test_handles_empty_content(self) -> None:
        """空 content 应被安全处理为 0 token。"""
        estimator = CharTokenEstimator()
        messages = [Message(role="assistant", content="")]
        assert estimator.estimate(messages) == 0

    def test_counts_tool_calls(self) -> None:
        """估算时应把 tool_calls 的名字和参数也计入。"""
        estimator = CharTokenEstimator(chars_per_token=4)
        messages = [
            Message(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(id="call_1", name="sandbox_exec", arguments={"code": "print(1)"}),
                ],
            ),
        ]
        # name "sandbox_exec" = 12, args str 长度约 22，合计 34，//4 = 8
        assert estimator.estimate(messages) == 8

    def test_invalid_chars_per_token(self) -> None:
        """chars_per_token 必须大于 0。"""
        with pytest.raises(ValueError, match="chars_per_token"):
            CharTokenEstimator(chars_per_token=0)


class TestTiktokenEstimator:
    """TiktokenEstimator 的单元测试（tiktoken 可选）。"""

    def test_estimate_if_tiktoken_available(self) -> None:
        """如果安装了 tiktoken，应能精确估算。"""
        pytest.importorskip("tiktoken")
        estimator = TiktokenEstimator(model="gpt-4o")
        messages = [Message(role="user", content="hello world")]
        assert estimator.estimate(messages) > 0

    def test_raises_without_tiktoken(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """未安装 tiktoken 时实例化应抛出 ImportError。"""
        import builtins

        # 模拟 import tiktoken 失败
        original_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "tiktoken":
                raise ImportError("No module named 'tiktoken'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)
        with pytest.raises(ImportError, match="tiktoken"):
            TiktokenEstimator(model="gpt-4o")


class TestContextCompressionConfig:
    """上下文压缩配置的单元测试。"""

    def test_compression_disabled_by_default(self) -> None:
        """默认情况下压缩功能关闭，避免影响现有行为。"""
        config = AgentConfig()
        assert config.agent.compression.enabled is False
        assert config.agent.compression.context_window == 8192
        assert config.agent.compression.reserve_tokens == 1024

    def test_load_compression_from_yaml(self) -> None:
        """YAML 中可显式开启并覆盖压缩参数。"""
        yaml_content = """
agent:
  compression:
    enabled: true
    context_window: 16000
    reserve_tokens: 2048
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as f:
            f.write(yaml_content)
            path = f.name

        try:
            config = load_config(path)
            assert config.agent.compression.enabled is True
            assert config.agent.compression.context_window == 16000
            assert config.agent.compression.reserve_tokens == 2048
        finally:
            os.unlink(path)


class TestContextCache:
    """ContextCache 的单元测试。"""

    def test_store_creates_file_and_returns_entry(self, tmp_path: Path) -> None:
        """store 应创建缓存文件并返回包含 URI 的 CacheEntry。"""
        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        entry = cache.store(run_id="run_1", tool_name="sandbox_exec", content="hello world")

        assert isinstance(entry, CacheEntry)
        assert entry.session_id == "sess_1"
        assert entry.run_id == "run_1"
        assert entry.tool_name == "sandbox_exec"
        assert entry.uri.startswith("hermes://context/sess_1/run_1/")
        assert entry.file_path.exists()
        assert entry.file_path.read_text(encoding="utf-8") == "hello world"

    def test_read_valid_uri_returns_content(self, tmp_path: Path) -> None:
        """通过 URI 能读回缓存内容。"""
        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        entry = cache.store(run_id="run_1", tool_name="file_read", content="file content")

        assert cache.read(entry.uri) == "file content"

    def test_read_invalid_uri_returns_none(self, tmp_path: Path) -> None:
        """无效 URI 应返回 None，不抛异常。"""
        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        assert cache.read("hermes://context/other_sess/run_1/xxx.md") is None
        assert cache.read("not-a-uri") is None
        assert cache.read("") is None

    def test_cleanup_removes_session_files(self, tmp_path: Path) -> None:
        """cleanup 应删除当前 session 的缓存文件。"""
        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        entry = cache.store(run_id="run_1", tool_name="sandbox_exec", content="x")
        assert entry.file_path.exists()

        removed = cache.cleanup()
        assert removed >= 1
        assert not entry.file_path.exists()

    def test_store_unicode_content(self, tmp_path: Path) -> None:
        """缓存应正确保存 Unicode 内容。"""
        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        content = "中文字符 🚀"
        entry = cache.store(run_id="run_1", tool_name="sandbox_exec", content=content)
        assert cache.read(entry.uri) == content

    def test_invalid_session_id_raises(self, tmp_path: Path) -> None:
        """session_id 含非法字符时应抛出 ValueError。"""
        with pytest.raises(ValueError):
            ContextCache(root_dir=tmp_path, session_id="sess/../1")

    def test_invalid_run_id_raises(self, tmp_path: Path) -> None:
        """run_id 含非法字符时应抛出 ValueError。"""
        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        with pytest.raises(ValueError):
            cache.store(run_id="run/1", tool_name="sandbox_exec", content="x")


class TestToolResultExternalizer:
    """ToolResultExternalizer 的单元测试。"""

    def test_short_content_not_externalized(self, tmp_path: Path) -> None:
        """短内容应原样返回，不写入缓存。"""
        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        externalizer = ToolResultExternalizer(cache=cache, threshold=100)

        content = "short"
        result, entry = externalizer.externalize_if_needed(
            run_id="run_1", tool_name="sandbox_exec", content=content, success=True
        )

        assert result == content
        assert entry is None

    def test_long_success_sandbox_exec_externalized(self, tmp_path: Path) -> None:
        """sandbox_exec 长成功输出应被外迁。"""
        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        externalizer = ToolResultExternalizer(cache=cache, threshold=10, exec_success_preview=5)

        content = "this is a long successful output"
        result, entry = externalizer.externalize_if_needed(
            run_id="run_1", tool_name="sandbox_exec", content=content, success=True
        )

        assert entry is not None
        assert entry.tool_name == "sandbox_exec"
        assert "hermes://context/" in result
        assert "context_read" in result
        assert "this " in result  # 预览部分
        assert cache.read(entry.uri) == content

    def test_long_file_read_externalized_with_longer_preview(self, tmp_path: Path) -> None:
        """file_read 长内容应使用更长的预览。"""
        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        externalizer = ToolResultExternalizer(
            cache=cache, threshold=10, file_read_preview=20, exec_success_preview=5
        )

        content = "line1\nline2\nline3\nline4\nline5"
        result, entry = externalizer.externalize_if_needed(
            run_id="run_1", tool_name="file_read", content=content, success=True
        )

        assert entry is not None
        # 预览长度为 20，应包含更多行
        assert "line1\nline2" in result
        assert cache.read(entry.uri) == content

    def test_failure_traceback_kept_full_by_default(self, tmp_path: Path) -> None:
        """失败 traceback 默认完整保留（D1），不外迁。"""
        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        externalizer = ToolResultExternalizer(
            cache=cache, threshold=10, exec_error_preview=100
        )

        content = "Traceback (most recent call last):\nNameError: x"
        result, entry = externalizer.externalize_if_needed(
            run_id="run_1", tool_name="sandbox_exec", content=content, success=False
        )

        assert result == content
        assert entry is None

    def test_extremely_long_failure_truncated_with_link(self, tmp_path: Path) -> None:
        """极长失败输出超过 exec_error_preview 时截断并给出缓存链接。"""
        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        externalizer = ToolResultExternalizer(
            cache=cache, threshold=10, exec_error_preview=20
        )

        content = "A" * 200
        result, entry = externalizer.externalize_if_needed(
            run_id="run_1", tool_name="sandbox_exec", content=content, success=False
        )

        assert entry is not None
        assert "失败" in result
        assert "hermes://context/" in result
        assert "context_read" in result
        # 结果不应等于原始内容，且预览只包含 20 个 A
        assert result != content
        assert result.count("A") == 20
        assert "..." in result
        assert cache.read(entry.uri) == content


class TestStaticSummarizer:
    """StaticSummarizer 的单元测试。"""

    @pytest.mark.asyncio
    async def test_keeps_leading_lines_and_errors(self) -> None:
        """保留前若干行和错误行，最终按 max_length 截断。"""
        from agent.core.summarizer import StaticSummarizer

        summarizer = StaticSummarizer()
        content = (
            "line 1\nline 2\nline 3\nline 4\nline 5\n"
            "some normal log\n"
            "Traceback (most recent call last):\nNameError: name 'x' is not defined"
        )
        result = await summarizer.summarize(content, max_length=100)

        assert result.startswith("line 1")
        assert "Traceback" in result
        assert "NameError" in result
        assert "..." in result
        assert len(result) <= 100 + len("\n...")

    @pytest.mark.asyncio
    async def test_short_content_unchanged(self) -> None:
        """短于 max_length 时原样返回。"""
        from agent.core.summarizer import StaticSummarizer

        summarizer = StaticSummarizer()
        content = "short"
        result = await summarizer.summarize(content, max_length=100)
        assert result == content

    @pytest.mark.asyncio
    async def test_empty_content(self) -> None:
        """空内容返回空字符串。"""
        from agent.core.summarizer import StaticSummarizer

        summarizer = StaticSummarizer()
        assert await summarizer.summarize("") == ""

    @pytest.mark.asyncio
    async def test_long_single_line_truncated(self) -> None:
        """单行超长内容直接截断。"""
        from agent.core.summarizer import StaticSummarizer

        summarizer = StaticSummarizer()
        content = "a" * 200
        result = await summarizer.summarize(content, max_length=20)
        assert result.startswith("a" * 20)
        assert "..." in result


class MockSummarizerClient:
    """模拟一个 LLM client，返回固定摘要。"""

    def __init__(self, response_content: str) -> None:
        self.response_content = response_content
        self.last_messages: list[dict[str, object]] | None = None
        self.last_kwargs: dict[str, object] | None = None

    async def chat(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        self.last_messages = messages
        self.last_kwargs = kwargs
        return {"content": self.response_content, "tool_calls": None}


class TestLLMSummarizer:
    """LLMSummarizer 的单元测试。"""

    @pytest.mark.asyncio
    async def test_calls_llm_with_summary_prompt(self) -> None:
        """使用正确的 system/user prompt 调用小模型。"""
        from agent.core.summarizer import LLMSummarizer

        mock_client = MockSummarizerClient("这是摘要。")
        summarizer = LLMSummarizer(llm_client=mock_client, model="gpt-4o-mini", max_tokens=256)

        content = "这是一段需要摘要的长文本。" * 10
        result = await summarizer.summarize(content, max_length=100)

        assert result == "这是摘要。"
        assert mock_client.last_messages is not None
        assert mock_client.last_messages[0]["role"] == "system"
        assert "摘要" in mock_client.last_messages[0]["content"]
        assert mock_client.last_messages[1]["role"] == "user"
        assert content in mock_client.last_messages[1]["content"]
        assert mock_client.last_kwargs.get("max_tokens") == 256

    @pytest.mark.asyncio
    async def test_truncates_overlong_response(self) -> None:
        """模型返回超过 max_length 时自动截断。"""
        from agent.core.summarizer import LLMSummarizer

        mock_client = MockSummarizerClient("a" * 200)
        summarizer = LLMSummarizer(llm_client=mock_client, model="gpt-4o-mini")

        result = await summarizer.summarize("content", max_length=50)
        assert len(result) == 50

    @pytest.mark.asyncio
    async def test_handles_empty_response(self) -> None:
        """模型返回空内容时返回空字符串。"""
        from agent.core.summarizer import LLMSummarizer

        mock_client = MockSummarizerClient("")
        summarizer = LLMSummarizer(llm_client=mock_client, model="gpt-4o-mini")

        result = await summarizer.summarize("content", max_length=100)
        assert result == ""

    @pytest.mark.asyncio
    async def test_falls_back_to_static_on_exception(self) -> None:
        """小模型调用失败时降级为 StaticSummarizer。"""
        from agent.core.summarizer import LLMSummarizer

        class FailingClient:
            async def chat(self, **kwargs: object) -> dict[str, object]:
                raise RuntimeError("model unavailable")

        summarizer = LLMSummarizer(llm_client=FailingClient(), model="gpt-4o-mini")
        content = "line 1\nline 2\nline 3"
        result = await summarizer.summarize(content, max_length=15)

        # 降级为静态摘要：保留第一行并按 max_length 截断
        assert result.startswith("line 1")
        assert "..." in result


class TestContextReadTool:
    """context_read 工具的单元测试。"""

    @pytest.mark.asyncio
    async def test_reads_valid_uri(self, tmp_path: Path) -> None:
        """有效 URI 返回缓存内容。"""
        from agent.core.context_cache import ContextCache
        from agent.tools.context_read import context_read

        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        entry = cache.store(run_id="run_1", tool_name="sandbox_exec", content="cached data")

        result = await context_read(entry.uri, cache)
        assert result.success is True
        assert result.content == "cached data"

    @pytest.mark.asyncio
    async def test_invalid_uri_returns_error(self, tmp_path: Path) -> None:
        """无效 URI 返回失败 ToolResult。"""
        from agent.core.context_cache import ContextCache
        from agent.tools.context_read import context_read

        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        result = await context_read("hermes://context/other_sess/run_1/xxx.md", cache)
        assert result.success is False
        assert "不存在" in result.content or "无效" in result.content

    @pytest.mark.asyncio
    async def test_non_hermes_uri_returns_error(self, tmp_path: Path) -> None:
        """非 hermes URI 返回失败。"""
        from agent.core.context_cache import ContextCache
        from agent.tools.context_read import context_read

        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        result = await context_read("file:///etc/passwd", cache)
        assert result.success is False


class TestRegisterContextTools:
    """context_read 工具注册测试。"""

    def test_register_context_tools_adds_context_read(self, tmp_path: Path) -> None:
        """register_context_tools 向 ToolRegistry 注入 context_read。"""
        from agent.core.context_cache import ContextCache
        from agent.core.engine import ToolRegistry
        from agent.tools import register_context_tools

        registry = ToolRegistry()
        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        register_context_tools(registry, cache)

        spec = registry.get("context_read")
        assert spec is not None
        assert spec.name == "context_read"
        schema = spec.to_openai_format()
        assert "uri" in schema["function"]["parameters"]["properties"]


class TestAgentContextReadIntegration:
    """Agent 与 context_read 的集成测试。"""

    def test_agent_creates_default_cache_when_compression_enabled(
        self, tmp_path: Path
    ) -> None:
        """压缩启用时 Agent 自动创建 ContextCache 并注册 context_read。"""
        from agent.config import AgentConfig
        from agent.core.engine import Agent
        from agent.llm.base import EchoClient

        config = AgentConfig(
            agent={
                "compression": {
                    "enabled": True,
                    "cache_root": str(tmp_path / "cache"),
                }
            }
        )
        agent = Agent(llm_client=EchoClient(), config=config)

        assert agent.context_cache is not None
        assert agent.tools.get("context_read") is not None

    def test_agent_no_cache_when_compression_disabled(self) -> None:
        """压缩关闭时 Agent 不创建缓存、不注册 context_read。"""
        from agent.config import AgentConfig
        from agent.core.engine import Agent
        from agent.llm.base import EchoClient

        config = AgentConfig()
        assert config.agent.compression.enabled is False

        agent = Agent(llm_client=EchoClient(), config=config)

        assert agent.context_cache is None
        assert agent.tools.get("context_read") is None

    def test_agent_respects_register_context_read_false(self, tmp_path: Path) -> None:
        """register_context_read=False 时只创建缓存，不注册工具。"""
        from agent.config import AgentConfig
        from agent.core.engine import Agent
        from agent.llm.base import EchoClient

        config = AgentConfig(
            agent={
                "compression": {
                    "enabled": True,
                    "cache_root": str(tmp_path / "cache"),
                    "register_context_read": False,
                }
            }
        )
        agent = Agent(llm_client=EchoClient(), config=config)

        assert agent.context_cache is not None
        assert agent.tools.get("context_read") is None

    @pytest.mark.asyncio
    async def test_context_read_tool_execution(self, tmp_path: Path) -> None:
        """通过 ToolRegistry 执行 context_read 能读回缓存内容。"""
        from agent.config import AgentConfig
        from agent.core.engine import Agent
        from agent.core.types import ToolCall
        from agent.llm.base import EchoClient

        config = AgentConfig(
            agent={
                "compression": {
                    "enabled": True,
                    "cache_root": str(tmp_path / "cache"),
                }
            }
        )
        agent = Agent(llm_client=EchoClient(), config=config)
        entry = agent.context_cache.store(
            run_id="run_1", tool_name="sandbox_exec", content="exec output"
        )

        result = await agent.tools.execute(
            ToolCall(id="c1", name="context_read", arguments={"uri": entry.uri})
        )

        assert result.success is True
        assert result.content == "exec output"


class TestToolResultExternalizerDoesNotReexternalizeContextRead:
    """防止 context_read 结果被二次外迁。"""

    def test_context_read_results_not_externalized(self, tmp_path: Path) -> None:
        """context_read 的长结果应原样返回，不再外迁。"""
        from agent.core.context_cache import ContextCache
        from agent.core.tool_result_externalizer import ToolResultExternalizer

        cache = ContextCache(root_dir=tmp_path, session_id="sess_1")
        externalizer = ToolResultExternalizer(cache=cache, threshold=10)

        long_content = "A" * 200
        result, entry = externalizer.externalize_if_needed(
            run_id="run_1", tool_name="context_read", content=long_content, success=True
        )

        assert result == long_content
        assert entry is None


class TestHybridCompressor:
    """HybridCompressor 的单元测试。"""

    @pytest.fixture
    def estimator(self) -> CharTokenEstimator:
        return CharTokenEstimator(chars_per_token=4)

    @pytest.mark.asyncio
    async def test_no_compression_when_under_budget(
        self, estimator: CharTokenEstimator
    ) -> None:
        """未超预算时返回原列表，策略为 none。"""
        from agent.core.compressor import HybridCompressor
        from agent.core.summarizer import StaticSummarizer

        compressor = HybridCompressor(
            StaticSummarizer(), protect_first_n=1, protect_last_n_turns=1
        )
        messages = [
            Message(role="user", content="hi"),
            Message(role="assistant", content="hello"),
        ]
        result = await compressor.compress(messages, budget=100, token_estimator=estimator)

        assert result.strategy == "none"
        assert result.messages is messages
        assert result.original_token_count == result.compressed_token_count

    @pytest.mark.asyncio
    async def test_protects_head_and_tail_and_summarizes_middle(
        self, estimator: CharTokenEstimator
    ) -> None:
        """保护头部和尾部，中间区域被摘要成一条消息。"""
        from agent.core.compressor import HybridCompressor
        from agent.core.summarizer import StaticSummarizer

        compressor = HybridCompressor(
            StaticSummarizer(), protect_first_n=1, protect_last_n_turns=1
        )
        messages = [
            Message(role="user", content="start"),
            Message(
                role="assistant",
                content="a",
                tool_calls=[ToolCall(id="c1", name="echo", arguments={"x": "a" * 500})],
            ),
            Message(role="tool", content="A" * 500, tool_call_id="c1", name="echo"),
            Message(
                role="assistant",
                content="b",
                tool_calls=[ToolCall(id="c2", name="echo", arguments={"x": "b"})],
            ),
            Message(role="tool", content="B", tool_call_id="c2", name="echo"),
        ]
        result = await compressor.compress(messages, budget=80, token_estimator=estimator)

        # head(1) + summary(1) + tail(2) = 4
        assert result.compressed_message_count == 4
        assert result.compressed_token_count <= 80
        assert result.messages[0].content == "start"
        assert result.messages[1].role == "user"
        assert "[上下文摘要]" in result.messages[1].content
        assert result.messages[2].role == "assistant"
        assert result.messages[2].tool_calls is not None
        assert result.messages[3].role == "tool"
        assert result.messages[3].tool_call_id == "c2"

    @pytest.mark.asyncio
    async def test_fallback_when_middle_empty(
        self, estimator: CharTokenEstimator
    ) -> None:
        """没有中间区域时，对尾部最旧消息做 fallback 截断，最后一条完整保留。"""
        from agent.core.compressor import HybridCompressor
        from agent.core.summarizer import StaticSummarizer

        compressor = HybridCompressor(
            StaticSummarizer(), protect_first_n=2, protect_last_n_turns=1
        )
        messages = [
            Message(role="user", content="U" * 100),
            Message(role="assistant", content="A" * 100),
        ]
        result = await compressor.compress(messages, budget=30, token_estimator=estimator)

        assert result.strategy == "fallback_truncate"
        assert result.compressed_token_count <= 30
        assert len(result.messages) == 2
        # 最后一条 assistant 应被完整保留
        assert result.messages[1].content == "A" * 100
        # 第一条 user 应被截断
        assert len(result.messages[0].content) < 100

    @pytest.mark.asyncio
    async def test_head_boundary_aligns_with_tool_call_pairs(
        self, estimator: CharTokenEstimator
    ) -> None:
        """protect_first_n 落在 assistant 与其 tool 结果之间时，应自动扩展头部。"""
        from agent.core.compressor import HybridCompressor
        from agent.core.summarizer import StaticSummarizer

        compressor = HybridCompressor(
            StaticSummarizer(), protect_first_n=2, protect_last_n_turns=1
        )
        messages = [
            Message(role="user", content="start"),
            Message(
                role="assistant",
                content="call tools",
                tool_calls=[
                    ToolCall(id="c1", name="echo", arguments={"x": "a"}),
                    ToolCall(id="c2", name="echo", arguments={"x": "b"}),
                ],
            ),
            Message(role="tool", content="A", tool_call_id="c1", name="echo"),
            Message(role="tool", content="B", tool_call_id="c2", name="echo"),
            Message(role="assistant", content="final"),
        ]
        result = await compressor.compress(messages, budget=10, token_estimator=estimator)

        # 头部应包含 assistant + 其全部 tool 结果，不能拆分到中间区域
        assert result.messages[0].content == "start"
        assert result.messages[1].role == "assistant"
        assert result.messages[2].role == "tool"
        assert result.messages[3].role == "tool"
        # 最后一条 assistant 受尾部保护
        assert result.messages[-1].content == "final"
        # 中间区域为空，因此摘要为空且策略为 fallback
        assert result.strategy == "fallback_truncate"
        assert result.removed_ranges == []

    @pytest.mark.asyncio
    async def test_shortens_summary_when_still_over_budget(
        self, estimator: CharTokenEstimator
    ) -> None:
        """摘要后仍超预算，应逐步缩短摘要。"""
        from agent.core.compressor import HybridCompressor
        from agent.core.summarizer import StaticSummarizer

        compressor = HybridCompressor(
            StaticSummarizer(),
            protect_first_n=1,
            protect_last_n_turns=1,
            default_summary_max_chars=300,
            min_summary_max_chars=50,
        )
        messages = [
            Message(role="user", content="start"),
            Message(role="assistant", content="a"),
            Message(role="tool", content="T" * 400, tool_call_id="c1", name="echo"),
            Message(role="assistant", content="b"),
        ]
        result = await compressor.compress(messages, budget=40, token_estimator=estimator)

        assert result.compressed_token_count <= 40
        # 尾部被保护，中间被摘要或丢弃
        assert result.strategy in ("hybrid_summary", "hybrid_drop_middle", "hybrid_truncate_tail")


class EchoThenTextClient(BaseLLMClient):
    """第一次返回 tool_call（调用 echo），第二次返回纯文本。"""

    def __init__(self, tool_name: str = "echo", arguments: dict[str, object] | None = None):
        self.call_count = 0
        self.tool_name = tool_name
        self.arguments = arguments or {"x": "A" * 200}

    async def chat(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        self.call_count += 1
        if self.call_count == 1:
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": self.tool_name,
                            "arguments": __import__("json").dumps(self.arguments),
                        },
                    }
                ],
            }
        return {"content": "done", "tool_calls": None}


class LoopToolClient(BaseLLMClient):
    """连续返回 N 次 tool_call，然后返回纯文本。"""

    def __init__(self, tool_turns: int, tool_name: str = "echo"):
        self.tool_turns = tool_turns
        self.tool_name = tool_name
        self.call_count = 0

    async def chat(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        self.call_count += 1
        if self.call_count <= self.tool_turns:
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": f"c{self.call_count}",
                        "type": "function",
                        "function": {
                            "name": self.tool_name,
                            "arguments": '{"x": "' + "X" * 100 + '"}',
                        },
                    }
                ],
            }
        return {"content": "finished", "tool_calls": None}


def _echo_handler(x: str) -> str:
    return x


class TestAgentCompressionIntegration:
    """Agent.run() 与压缩子系统的集成测试。"""

    def _make_agent(self, tmp_path: Path, config_extra: dict[str, object] | None = None):
        from agent.core.engine import Agent

        config_extra = config_extra or {}
        config = AgentConfig(
            agent={
                "compression": {
                    "enabled": True,
                    "cache_root": str(tmp_path / "cache"),
                    "externalize_threshold": 50,
                    "file_read_preview_chars": 30,
                    "exec_success_preview_chars": 20,
                    "context_window": 300,
                    "reserve_tokens": 50,
                    **config_extra,
                }
            }
        )
        agent = Agent(llm_client=EchoThenTextClient(), config=config)
        # 注册一个轻量的 echo 工具，避免依赖 Docker
        agent.tools.register(
            ToolSpec(
                name="echo",
                description="Return the input string.",
                parameters={
                    "type": "object",
                    "properties": {"x": {"type": "string"}},
                    "required": ["x"],
                },
                handler=_echo_handler,
            )
        )
        return agent

    @pytest.mark.asyncio
    async def test_long_tool_result_gets_externalized(self, tmp_path: Path) -> None:
        """长工具结果应被外迁，并在 Trace 中记录。"""
        agent = self._make_agent(tmp_path)

        await agent.run("call echo")

        events = [e for step in agent.trace.steps for e in step.events]
        externalized_events = [e for e in events if e.event_type == "tool_result_externalized"]
        assert len(externalized_events) == 1
        payload = externalized_events[0].payload
        assert payload["tool"] == "echo"
        assert "hermes://context/" in payload["uri"]
        assert payload["original_length"] == 200

        # 缓存文件应存在且可读取
        assert agent.context_cache is not None
        assert agent.context_cache.session_dir.exists()

    @pytest.mark.asyncio
    async def test_error_classification_uses_raw_content(self, tmp_path: Path) -> None:
        """错误分类应基于原始内容，不受外迁后格式影响。"""
        from agent.core.engine import Agent
        from agent.llm.base import BaseLLMClient

        class FailingToolClient(BaseLLMClient):
            async def chat(
                self,
                messages: list[dict[str, object]],
                tools: list[dict[str, object]] | None = None,
                **kwargs: object,
            ) -> dict[str, object]:
                return {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "fail", "arguments": "{}"},
                        }
                    ],
                }

        config = AgentConfig(
            agent={
                "compression": {
                    "enabled": True,
                    "cache_root": str(tmp_path / "cache"),
                    "externalize_threshold": 10,
                }
            }
        )
        agent = Agent(llm_client=FailingToolClient(), config=config)
        agent.tools.register(
            ToolSpec(
                name="fail",
                description="Always fail.",
                parameters={"type": "object", "properties": {}},
                handler=lambda: (_ for _ in ()).throw(ValueError("something wrong")),
            )
        )

        await agent.run("call fail")

        events = [e for step in agent.trace.steps for e in step.events]
        assert any(e.event_type == "error_classification" for e in events)
        tool_exec = next(e for e in events if e.event_type == "tool_execution")
        assert "ValueError" in tool_exec.payload["content"]

    @pytest.mark.asyncio
    async def test_long_history_gets_compressed(self, tmp_path: Path) -> None:
        """长对话历史超过预算时触发 context_compression 事件。"""
        agent = self._make_agent(
            tmp_path,
            config_extra={"context_window": 180, "reserve_tokens": 20},
        )
        # 注册一个会循环调用 5 次 echo 的 client
        agent.llm = LoopToolClient(tool_turns=5)

        await agent.run("loop")

        events = [e for step in agent.trace.steps for e in step.events]
        compression_events = [e for e in events if e.event_type == "context_compression"]
        assert len(compression_events) >= 1
        payload = compression_events[0].payload
        assert payload["strategy"] != "none"
        assert payload["original_token_count"] > payload["compressed_token_count"]
