"""grep / glob 工具（TD-014）的单元测试。"""

from __future__ import annotations

import json

import pytest

from agent.core.engine import ToolRegistry
from agent.core.security import PolicyEngine
from agent.core.types import ToolCall
from agent.sandbox.docker_backend import ExecutionResult
from agent.tools import register_default_tools
from tests.test_tools import MockSandboxBackend


def _ok(payload: dict[str, object]) -> ExecutionResult:
    """把脚本 JSON 输出包装为成功的 ExecutionResult。"""
    return ExecutionResult(exit_code=0, stdout=json.dumps(payload), stderr="", success=True)


class TestGrepTool:
    """grep 工具的核心行为测试。"""

    @pytest.mark.asyncio
    async def test_grep_hit_multiple_files_and_lines(self) -> None:
        """多文件多行命中时，输出为 相对路径:行号:匹配行 列表。"""
        backend = MockSandboxBackend(
            execute_responses=[
                _ok({
                    "matches": ["a.py:1:def foo():", "sub/b.py:3:foo()"],
                    "truncated": False,
                })
            ]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="g1", name="grep", arguments={"pattern": "foo", "path": "/workspace"})
        )

        assert result.success is True
        assert result.content == "a.py:1:def foo():\nsub/b.py:3:foo()"
        assert result.tool_call_id == "g1"
        assert backend.execute_count == 1
        # 参数经 json.dumps 转义后进入脚本
        assert '"foo"' in backend.execute_codes[0]
        assert '"/workspace"' in backend.execute_codes[0]

    @pytest.mark.asyncio
    async def test_grep_no_match(self) -> None:
        """无命中时成功返回提示文本。"""
        backend = MockSandboxBackend(
            execute_responses=[_ok({"matches": [], "truncated": False})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="g2", name="grep", arguments={"pattern": "zzz", "path": "/workspace"})
        )

        assert result.success is True
        assert "无匹配" in result.content

    @pytest.mark.asyncio
    async def test_grep_include_filter_passed_to_script(self) -> None:
        """include 过滤参数应传入沙箱脚本。"""
        backend = MockSandboxBackend(
            execute_responses=[_ok({"matches": ["a.py:1:x"], "truncated": False})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(
                id="g3",
                name="grep",
                arguments={"pattern": "x", "path": "/workspace", "include": "*.py"},
            )
        )

        assert result.success is True
        assert "'*.py'" in backend.execute_codes[0]

    @pytest.mark.asyncio
    async def test_grep_ignore_case_passed_to_script(self) -> None:
        """ignore_case=True 应传入沙箱脚本。"""
        backend = MockSandboxBackend(
            execute_responses=[_ok({"matches": ["a.py:1:FOO"], "truncated": False})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(
                id="g4",
                name="grep",
                arguments={"pattern": "foo", "path": "/workspace", "ignore_case": True},
            )
        )

        assert result.success is True
        assert "ignore_case = True" in backend.execute_codes[0]

    @pytest.mark.asyncio
    async def test_grep_max_results_truncation(self) -> None:
        """达到条数上限时，输出应附带 ... (truncated) 标记。"""
        backend = MockSandboxBackend(
            execute_responses=[_ok({"matches": ["a.py:1:x", "a.py:2:x"], "truncated": True})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(
                id="g5",
                name="grep",
                arguments={"pattern": "x", "path": "/workspace", "max_results": 2},
            )
        )

        assert result.success is True
        assert result.content.endswith("... (truncated)")

    @pytest.mark.asyncio
    async def test_grep_max_results_hard_cap(self) -> None:
        """max_results 超过硬顶 1000 时应被钳制到 1000。"""
        backend = MockSandboxBackend(
            execute_responses=[_ok({"matches": [], "truncated": False})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        await registry.execute(
            ToolCall(
                id="g6",
                name="grep",
                arguments={"pattern": "x", "path": "/workspace", "max_results": 99999},
            )
        )

        assert "max_results = 1000" in backend.execute_codes[0]

    @pytest.mark.asyncio
    async def test_grep_byte_truncation(self) -> None:
        """输出超过 8KB 时应按字节截断并注明。"""
        long_line = "a.py:1:" + "x" * 9000
        backend = MockSandboxBackend(
            execute_responses=[_ok({"matches": [long_line], "truncated": False})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="g7", name="grep", arguments={"pattern": "x", "path": "/workspace"})
        )

        assert result.success is True
        assert result.content.endswith("... (truncated)")
        assert len(result.content.encode("utf-8")) < len(long_line.encode("utf-8"))

    @pytest.mark.asyncio
    async def test_grep_invalid_regex(self) -> None:
        """非法正则时返回 re.error 前缀的失败结果。"""
        backend = MockSandboxBackend(
            execute_responses=[_ok({"error": "re.error: missing ), unterminated subpattern"})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="g8", name="grep", arguments={"pattern": "(", "path": "/workspace"})
        )

        assert result.success is False
        assert result.content.startswith("re.error: ")

    @pytest.mark.asyncio
    async def test_grep_single_file_path(self) -> None:
        """path 为单文件时同样可搜索。"""
        backend = MockSandboxBackend(
            execute_responses=[_ok({"matches": ["main.py:2:hit"], "truncated": False})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(
                id="g9",
                name="grep",
                arguments={"pattern": "hit", "path": "/workspace/main.py"},
            )
        )

        assert result.success is True
        assert result.content == "main.py:2:hit"
        assert '"/workspace/main.py"' in backend.execute_codes[0]

    @pytest.mark.asyncio
    async def test_grep_execute_code_failure_passthrough(self) -> None:
        """execute_code 失败时透传 stderr。"""
        backend = MockSandboxBackend(
            execute_responses=[
                ExecutionResult(exit_code=1, stdout="", stderr="boom", success=False)
            ]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="g10", name="grep", arguments={"pattern": "x", "path": "/workspace"})
        )

        assert result.success is False
        assert result.content == "boom"

    @pytest.mark.asyncio
    async def test_grep_policy_denied(self) -> None:
        """策略拒绝敏感路径时返回 策略拒绝，且不触达沙箱。"""
        registry = ToolRegistry(policy=PolicyEngine.default())
        backend = MockSandboxBackend()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="g11", name="grep", arguments={"pattern": "root", "path": "/etc/passwd"})
        )

        assert result.success is False
        assert "策略拒绝" in result.content
        assert backend.execute_count == 0


class TestGlobTool:
    """glob 工具的核心行为测试。"""

    @pytest.mark.asyncio
    async def test_glob_recursive_star_star(self) -> None:
        """** 递归模式返回每行一个相对路径。"""
        backend = MockSandboxBackend(
            execute_responses=[
                _ok({"matches": ["a.py", "sub/b.py", "sub/deep/c.py"], "truncated": False})
            ]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="b1", name="glob", arguments={"pattern": "**/*.py"})
        )

        assert result.success is True
        assert result.content == "a.py\nsub/b.py\nsub/deep/c.py"
        assert '"**/*.py"' in backend.execute_codes[0]
        assert "recursive=True" in backend.execute_codes[0]

    @pytest.mark.asyncio
    async def test_glob_default_path(self) -> None:
        """未传 path 时默认搜索根为 /workspace。"""
        backend = MockSandboxBackend(
            execute_responses=[_ok({"matches": ["a.py"], "truncated": False})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="b2", name="glob", arguments={"pattern": "*.py"})
        )

        assert result.success is True
        assert '"/workspace"' in backend.execute_codes[0]

    @pytest.mark.asyncio
    async def test_glob_no_match(self) -> None:
        """无命中时成功返回提示文本。"""
        backend = MockSandboxBackend(
            execute_responses=[_ok({"matches": [], "truncated": False})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="b3", name="glob", arguments={"pattern": "*.zzz"})
        )

        assert result.success is True
        assert "无匹配" in result.content

    @pytest.mark.asyncio
    async def test_glob_max_results_truncation(self) -> None:
        """达到条数上限时，输出应附带 ... (truncated) 标记。"""
        backend = MockSandboxBackend(
            execute_responses=[_ok({"matches": ["a.py", "b.py"], "truncated": True})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="b4", name="glob", arguments={"pattern": "*.py", "max_results": 2})
        )

        assert result.success is True
        assert result.content.endswith("... (truncated)")

    @pytest.mark.asyncio
    async def test_glob_byte_truncation(self) -> None:
        """输出超过 8KB 时应按字节截断并注明。"""
        long_name = "d" * 9000 + ".py"
        backend = MockSandboxBackend(
            execute_responses=[_ok({"matches": [long_name], "truncated": False})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="b5", name="glob", arguments={"pattern": "*.py"})
        )

        assert result.success is True
        assert result.content.endswith("... (truncated)")
        assert len(result.content.encode("utf-8")) < len(long_name.encode("utf-8"))

    @pytest.mark.asyncio
    async def test_glob_missing_directory(self) -> None:
        """目录不存在时返回 NotADirectoryError 前缀的失败结果。"""
        backend = MockSandboxBackend(
            execute_responses=[_ok({"error": "NotADirectoryError: 目录不存在：/nope"})]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="b6", name="glob", arguments={"pattern": "*.py", "path": "/nope"})
        )

        assert result.success is False
        assert result.content.startswith("NotADirectoryError: ")

    @pytest.mark.asyncio
    async def test_glob_execute_code_failure_passthrough(self) -> None:
        """execute_code 失败时透传 stderr。"""
        backend = MockSandboxBackend(
            execute_responses=[
                ExecutionResult(exit_code=1, stdout="", stderr="boom", success=False)
            ]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="b7", name="glob", arguments={"pattern": "*.py"})
        )

        assert result.success is False
        assert result.content == "boom"

    @pytest.mark.asyncio
    async def test_glob_policy_denied(self) -> None:
        """策略拒绝敏感路径时返回 策略拒绝，且不触达沙箱。"""
        registry = ToolRegistry(policy=PolicyEngine.default())
        backend = MockSandboxBackend()
        register_default_tools(registry, backend)

        # 默认规则集只 deny 敏感路径（/etc/passwd、.ssh 等），用 /etc/passwd
        # 验证参数级卡口确实接入。
        result = await registry.execute(
            ToolCall(id="b8", name="glob", arguments={"pattern": "*", "path": "/etc/passwd"})
        )

        assert result.success is False
        assert "策略拒绝" in result.content
        assert backend.execute_count == 0


class TestGrepGlobSpec:
    """grep / glob 的 ToolSpec schema 测试。"""

    def test_grep_spec_schema(self) -> None:
        """grep 的参数 schema 应要求 pattern 与 path。"""
        registry = ToolRegistry()
        backend = MockSandboxBackend()
        register_default_tools(registry, backend)

        spec = registry.get("grep")
        assert spec is not None
        assert spec.name == "grep"

        schema = spec.to_openai_format()
        parameters = schema["function"]["parameters"]
        assert set(parameters["required"]) == {"pattern", "path"}
        assert "pattern" in parameters["properties"]
        assert "path" in parameters["properties"]
        assert "include" in parameters["properties"]
        assert "ignore_case" in parameters["properties"]
        assert "max_results" in parameters["properties"]
        assert parameters["additionalProperties"] is False

    def test_glob_spec_schema(self) -> None:
        """glob 的参数 schema 应只要求 pattern。"""
        registry = ToolRegistry()
        backend = MockSandboxBackend()
        register_default_tools(registry, backend)

        spec = registry.get("glob")
        assert spec is not None
        assert spec.name == "glob"

        schema = spec.to_openai_format()
        parameters = schema["function"]["parameters"]
        assert parameters["required"] == ["pattern"]
        assert "pattern" in parameters["properties"]
        assert "path" in parameters["properties"]
        assert "max_results" in parameters["properties"]
        assert parameters["additionalProperties"] is False
