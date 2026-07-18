"""Tool 层的单元测试（sandbox_exec / file_read / file_list / finish）。"""

from __future__ import annotations

import json

import pytest

from agent.core.engine import Agent, ToolRegistry
from agent.core.types import ToolCall
from agent.llm.base import BaseLLMClient
from agent.sandbox.docker_backend import DockerSandboxBackend, ExecutionResult
from agent.tools import register_default_tools


class MockSandboxBackend(DockerSandboxBackend):
    """用于测试的沙箱后端桩。

    继承自 DockerSandboxBackend 只是为了通过类型检查，
    实际不会连接真实 Docker daemon。
    """

    def __init__(
        self,
        execute_responses: list[ExecutionResult] | None = None,
        files: dict[str, bytes] | None = None,
        put_fail_paths: set[str] | None = None,
    ) -> None:
        self.execute_responses = execute_responses or []
        self.files = dict(files) if files is not None else {}
        self.put_fail_paths = put_fail_paths or set()
        self.execute_count = 0
        self.execute_codes: list[str] = []
        self.put_paths: list[str] = []

    async def execute_code(
        self,
        code: str,
        timeout: int | None = None,
    ) -> ExecutionResult:
        """按顺序返回预设结果，并记录调用次数与代码内容。"""
        self.execute_codes.append(code)
        response = self.execute_responses[self.execute_count]
        self.execute_count += 1
        return response

    async def get_file(self, path: str) -> bytes | None:
        """按路径返回预设的文件内容。"""
        return self.files.get(path)

    async def put_file(self, path: str, content: bytes) -> bool:
        """将文件内容写入内部字典，并记录写入路径。"""
        self.put_paths.append(path)
        if path in self.put_fail_paths:
            return False
        self.files[path] = content
        return True


class TestSandboxExecTool:
    """sandbox_exec Tool 的核心行为测试。"""

    @pytest.mark.asyncio
    async def test_success_returns_stdout(self) -> None:
        """代码成功执行时，应返回 stdout 内容。"""
        backend = MockSandboxBackend(
            execute_responses=[
                ExecutionResult(exit_code=0, stdout="hello", stderr="", success=True)
            ]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="c1", name="sandbox_exec", arguments={"code": "print('hello')"})
        )

        assert result.success is True
        assert result.content == "hello"
        assert result.tool_call_id == "c1"
        assert backend.execute_count == 1
        assert backend.execute_codes == ["print('hello')"]

    @pytest.mark.asyncio
    async def test_failure_returns_stderr(self) -> None:
        """代码执行失败时，应返回 stderr 内容并标记失败。"""
        backend = MockSandboxBackend(
            execute_responses=[
                ExecutionResult(
                    exit_code=1,
                    stdout="",
                    stderr="SyntaxError: invalid syntax",
                    success=False,
                )
            ]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="c2", name="sandbox_exec", arguments={"code": "bad code"})
        )

        assert result.success is False
        assert "SyntaxError" in result.content
        assert result.tool_call_id == "c2"

    def test_tool_spec_schema(self) -> None:
        """sandbox_exec 的参数 schema 应只要求 code 字段。"""
        registry = ToolRegistry()
        backend = MockSandboxBackend()
        register_default_tools(registry, backend)

        spec = registry.get("sandbox_exec")
        assert spec is not None
        assert spec.name == "sandbox_exec"

        schema = spec.to_openai_format()
        parameters = schema["function"]["parameters"]
        assert parameters["required"] == ["code"]
        assert "code" in parameters["properties"]
        assert parameters["additionalProperties"] is False


class TestFileReadTool:
    """file_read Tool 的核心行为测试。"""

    @pytest.mark.asyncio
    async def test_file_read_success(self) -> None:
        """文件存在时，应返回文件内容。"""
        backend = MockSandboxBackend(files={"/tmp/result.txt": b"hello world"})
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="c3", name="file_read", arguments={"path": "/tmp/result.txt"})
        )

        assert result.success is True
        assert result.content == "hello world"
        assert result.tool_call_id == "c3"

    @pytest.mark.asyncio
    async def test_file_read_not_found(self) -> None:
        """文件不存在时，应返回失败并说明路径。"""
        backend = MockSandboxBackend(files={})
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="c4", name="file_read", arguments={"path": "/tmp/missing.txt"})
        )

        assert result.success is False
        assert "/tmp/missing.txt" in result.content


class TestFileListTool:
    """file_list Tool 的核心行为测试。"""

    @pytest.mark.asyncio
    async def test_file_list_success(self) -> None:
        """目录存在时，应返回文件列表。"""
        backend = MockSandboxBackend(
            execute_responses=[
                ExecutionResult(
                    exit_code=0,
                    stdout='["a.py", "b.py"]',
                    stderr="",
                    success=True,
                )
            ]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="c5", name="file_list", arguments={"path": "/tmp"})
        )

        assert result.success is True
        assert result.content == "a.py\nb.py"
        assert backend.execute_count == 1
        assert "/tmp" in backend.execute_codes[0]

    @pytest.mark.asyncio
    async def test_file_list_failure(self) -> None:
        """目录不存在或执行失败时，应返回 stderr 内容。"""
        backend = MockSandboxBackend(
            execute_responses=[
                ExecutionResult(
                    exit_code=1,
                    stdout="",
                    stderr="FileNotFoundError: [Errno 2] No such file",
                    success=False,
                )
            ]
        )
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="c6", name="file_list", arguments={"path": "/notexist"})
        )

        assert result.success is False
        assert "FileNotFoundError" in result.content


class TestFileToolsSpec:
    """file_read / file_list 的 ToolSpec schema 测试。"""

    def test_file_read_spec_schema(self) -> None:
        """file_read 的参数 schema 应只要求 path 字段。"""
        registry = ToolRegistry()
        backend = MockSandboxBackend()
        register_default_tools(registry, backend)

        spec = registry.get("file_read")
        assert spec is not None
        assert spec.name == "file_read"

        schema = spec.to_openai_format()
        parameters = schema["function"]["parameters"]
        assert parameters["required"] == ["path"]
        assert "path" in parameters["properties"]
        assert parameters["additionalProperties"] is False

    def test_file_list_spec_schema(self) -> None:
        """file_list 的参数 schema 应只要求 path 字段。"""
        registry = ToolRegistry()
        backend = MockSandboxBackend()
        register_default_tools(registry, backend)

        spec = registry.get("file_list")
        assert spec is not None
        assert spec.name == "file_list"

        schema = spec.to_openai_format()
        parameters = schema["function"]["parameters"]
        assert parameters["required"] == ["path"]
        assert "path" in parameters["properties"]
        assert parameters["additionalProperties"] is False


class TestFileWriteTool:
    """file_write Tool 的核心行为测试。"""

    @pytest.mark.asyncio
    async def test_file_write_creates_file(self) -> None:
        """file_write 应把内容写入沙箱并可在后续读取。"""
        backend = MockSandboxBackend()
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(
                id="c7",
                name="file_write",
                arguments={"path": "/workspace/main.py", "content": "print(1)"},
            )
        )

        assert result.success is True
        assert "/workspace/main.py" in result.content
        assert backend.files.get("/workspace/main.py") == b"print(1)"
        assert backend.put_paths == ["/workspace/main.py"]

    @pytest.mark.asyncio
    async def test_file_write_overwrites_existing_file(self) -> None:
        """file_write 应覆盖已存在的文件。"""
        backend = MockSandboxBackend(files={"/workspace/main.py": b"old"})
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(
                id="c8",
                name="file_write",
                arguments={"path": "/workspace/main.py", "content": "new"},
            )
        )

        assert result.success is True
        assert backend.files.get("/workspace/main.py") == b"new"

    @pytest.mark.asyncio
    async def test_file_write_returns_failure_on_backend_error(self) -> None:
        """后端写入失败时，file_write 应返回失败。"""
        backend = MockSandboxBackend(put_fail_paths={"/workspace/main.py"})
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(
                id="c9",
                name="file_write",
                arguments={"path": "/workspace/main.py", "content": "x"},
            )
        )

        assert result.success is False
        assert "写入失败" in result.content


class TestFileEditTool:
    """file_edit Tool 的核心行为测试。"""

    @pytest.mark.asyncio
    async def test_file_edit_replaces_unique_string(self) -> None:
        """old_string 唯一出现时，file_edit 应成功替换。"""
        backend = MockSandboxBackend(files={"/workspace/main.py": b"def foo():\n    pass"})
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(
                id="c10",
                name="file_edit",
                arguments={
                    "path": "/workspace/main.py",
                    "old_string": "def foo():",
                    "new_string": "def foo(x: int):",
                },
            )
        )

        assert result.success is True
        assert "替换 1 处" in result.content
        assert backend.files.get("/workspace/main.py") == b"def foo(x: int):\n    pass"

    @pytest.mark.asyncio
    async def test_file_edit_fails_when_old_string_missing(self) -> None:
        """old_string 不存在时，file_edit 应返回失败。"""
        backend = MockSandboxBackend(files={"/workspace/main.py": b"def bar(): pass"})
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(
                id="c11",
                name="file_edit",
                arguments={
                    "path": "/workspace/main.py",
                    "old_string": "def foo():",
                    "new_string": "def foo(x: int):",
                },
            )
        )

        assert result.success is False
        assert "未能找到" in result.content

    @pytest.mark.asyncio
    async def test_file_edit_fails_when_old_string_ambiguous(self) -> None:
        """old_string 出现多次时，file_edit 应返回失败以避免歧义替换。"""
        backend = MockSandboxBackend(files={"/workspace/main.py": b"a\na\na"})
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(
                id="c12",
                name="file_edit",
                arguments={
                    "path": "/workspace/main.py",
                    "old_string": "a",
                    "new_string": "b",
                },
            )
        )

        assert result.success is False
        assert "不唯一" in result.content

    @pytest.mark.asyncio
    async def test_file_edit_fails_when_file_missing(self) -> None:
        """目标文件不存在时，file_edit 应返回失败。"""
        backend = MockSandboxBackend(files={})
        registry = ToolRegistry()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(
                id="c13",
                name="file_edit",
                arguments={
                    "path": "/workspace/missing.py",
                    "old_string": "x",
                    "new_string": "y",
                },
            )
        )

        assert result.success is False
        assert "文件不存在" in result.content


class TestFileWriteEditSpec:
    """file_write / file_edit 的 ToolSpec schema 测试。"""

    def test_file_write_spec_schema(self) -> None:
        """file_write 的参数 schema 应要求 path 与 content。"""
        registry = ToolRegistry()
        backend = MockSandboxBackend()
        register_default_tools(registry, backend)

        spec = registry.get("file_write")
        assert spec is not None
        assert spec.name == "file_write"

        schema = spec.to_openai_format()
        parameters = schema["function"]["parameters"]
        assert set(parameters["required"]) == {"path", "content"}
        assert "path" in parameters["properties"]
        assert "content" in parameters["properties"]
        assert parameters["additionalProperties"] is False

    def test_file_edit_spec_schema(self) -> None:
        """file_edit 的参数 schema 应要求 path、old_string 与 new_string。"""
        registry = ToolRegistry()
        backend = MockSandboxBackend()
        register_default_tools(registry, backend)

        spec = registry.get("file_edit")
        assert spec is not None
        assert spec.name == "file_edit"

        schema = spec.to_openai_format()
        parameters = schema["function"]["parameters"]
        assert set(parameters["required"]) == {"path", "old_string", "new_string"}
        assert "path" in parameters["properties"]
        assert "old_string" in parameters["properties"]
        assert "new_string" in parameters["properties"]
        assert parameters["additionalProperties"] is False

    def test_default_tools_include_write_and_edit(self) -> None:
        """默认工具集应同时包含 file_write 与 file_edit。"""
        registry = ToolRegistry()
        backend = MockSandboxBackend()
        register_default_tools(registry, backend)

        assert registry.get("file_write") is not None
        assert registry.get("file_edit") is not None


class FinishMockClient(BaseLLMClient):
    """模拟 LLM 调用 finish 工具的客户端。"""

    def __init__(self, result: str) -> None:
        self.result = result

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
                    "id": "f1",
                    "type": "function",
                    "function": {
                        "name": "finish",
                        "arguments": json.dumps({"result": self.result}),
                    },
                }
            ],
        }


class TestFinishTool:
    """finish Tool 的核心行为测试。"""

    @pytest.mark.asyncio
    async def test_finish_returns_result(self) -> None:
        """finish 应返回 result 内容并标记成功。"""
        registry = ToolRegistry()
        backend = MockSandboxBackend()
        register_default_tools(registry, backend)

        result = await registry.execute(
            ToolCall(id="f1", name="finish", arguments={"result": "任务完成"})
        )

        assert result.success is True
        assert result.content == "任务完成"
        assert result.tool_call_id == "f1"

    def test_finish_spec_schema(self) -> None:
        """finish 的参数 schema 应只要求 result 字段。"""
        registry = ToolRegistry()
        backend = MockSandboxBackend()
        register_default_tools(registry, backend)

        spec = registry.get("finish")
        assert spec is not None
        assert spec.name == "finish"

        schema = spec.to_openai_format()
        parameters = schema["function"]["parameters"]
        assert parameters["required"] == ["result"]
        assert "result" in parameters["properties"]
        assert parameters["additionalProperties"] is False

    @pytest.mark.asyncio
    async def test_agent_returns_finish_result(self) -> None:
        """Agent 收到 finish tool_call 后应立即返回结果并停止循环。"""
        agent = Agent(
            llm_client=FinishMockClient("最终交付物"),
            sandbox_backend=MockSandboxBackend(),
        )

        response = await agent.run("请完成分析")

        assert response == "最终交付物"
