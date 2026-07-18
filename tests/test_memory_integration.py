"""Phase 8.3 集成测试：长期记忆与 Agent 主循环的集成。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent.config import AgentConfig
from agent.core.engine import Agent
from agent.core.memory import MemoryCategory, MemoryEntry, StructuredMemoryStore
from agent.core.types import ToolCall
from agent.llm.base import BaseLLMClient
from agent.sandbox.docker_backend import DockerSandboxBackend, ExecutionResult

# ---------------------------------------------------------------------------
# Mock 沙箱后端
# ---------------------------------------------------------------------------


class MockSandboxBackend(DockerSandboxBackend):
    """按顺序返回预设执行结果的沙箱后端桩。"""

    def __init__(self, responses: list[ExecutionResult]) -> None:
        self.responses = responses
        self.call_count = 0

    async def execute_code(
        self,
        code: str,
        timeout: int | None = None,
    ) -> ExecutionResult:
        response = self.responses[self.call_count]
        self.call_count += 1
        return response


# ---------------------------------------------------------------------------
# Mock LLM 客户端
# ---------------------------------------------------------------------------


class SimpleTextClient(BaseLLMClient):
    """只返回纯文本回复的 Mock LLM。"""

    def __init__(self, content: str = "Done.") -> None:
        self.content = content

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        return {"content": self.content, "tool_calls": None}


class ExecThenFinishClient(BaseLLMClient):
    """第一轮调 sandbox_exec，第二轮调 finish 的 Mock LLM。"""

    def __init__(self) -> None:
        self.turn = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        self.turn += 1
        if self.turn == 1:
            return {
                "content": "I'll run the analysis.",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": json.dumps(
                                {"code": "import pandas; print('/workspace/report.md')"}
                            ),
                        },
                    }
                ],
            }
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": "c2",
                    "type": "function",
                    "function": {"name": "finish", "arguments": '{"result": "done"}'},
                }
            ],
        }


class SystemPromptInspectorClient(BaseLLMClient):
    """记录收到消息中的 system prompt，然后返回纯文本结束运行。"""

    def __init__(self) -> None:
        self.system_contents: list[str] = []

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        if messages and messages[0].get("role") == "system":
            self.system_contents.append(messages[0].get("content", ""))
        return {"content": "Done.", "tool_calls": None}


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_memory_disabled_does_not_affect_run(tmp_path: Path) -> None:
    """记忆未启用时，运行行为与无记忆一致，不产生 memory_recorded 事件。"""
    config = AgentConfig()
    config.agent.memory.enabled = False

    backend = MockSandboxBackend([
        ExecutionResult(success=True, exit_code=0, stdout="ok", stderr=""),
    ])
    agent = Agent(llm_client=SimpleTextClient("hello"), config=config, sandbox_backend=backend)
    result = await agent.run("hi")
    assert result == "hello"

    trace = agent.get_trace().to_dict()
    events = [
        e for step in trace.get("steps", []) for e in step.get("events", [])
    ]
    assert not any(e["event_type"] == "memory_recorded" for e in events)


@pytest.mark.anyio
async def test_memory_enabled_records_and_injects(tmp_path: Path) -> None:
    """启用记忆后，Agent 能记录历史并在新运行中注入。"""
    memory_root = tmp_path / "memory"
    config = AgentConfig()
    config.agent.memory.enabled = True
    config.agent.memory.memory_root = str(memory_root)

    backend = MockSandboxBackend([
        ExecutionResult(
            success=True,
            exit_code=0,
            stdout="Successfully installed pandas\nReport saved to /workspace/report.md",
            stderr="",
        ),
    ])

    # 第一次运行：产生 environment + artifacts 记忆
    agent1 = Agent(
        llm_client=ExecThenFinishClient(),
        config=config,
        sandbox_backend=backend,
    )
    await agent1.run("analyze sales.csv")

    trace1 = agent1.get_trace().to_dict()
    events1 = [
        e for step in trace1.get("steps", []) for e in step.get("events", [])
    ]
    assert any(e["event_type"] == "memory_recorded" for e in events1)

    store = StructuredMemoryStore(memory_root)
    entries = store.list_entries()
    categories = {e.category for e in entries}
    assert MemoryCategory.ENVIRONMENT in categories
    assert MemoryCategory.ARTIFACTS in categories

    # 第二次运行：system prompt 中应包含历史记忆
    inspector = SystemPromptInspectorClient()
    agent2 = Agent(llm_client=inspector, config=config, sandbox_backend=MockSandboxBackend([]))
    await agent2.run("convert report to pdf")

    assert len(inspector.system_contents) >= 1
    system_content = inspector.system_contents[0]
    assert "[历史记忆]" in system_content
    assert "/workspace/report.md" in system_content


@pytest.mark.anyio
async def test_memory_read_tool_returns_entry(tmp_path: Path) -> None:
    """memory_read 工具应能返回完整记忆 JSON。"""
    memory_root = tmp_path / "memory"
    config = AgentConfig()
    config.agent.memory.enabled = True
    config.agent.memory.memory_root = str(memory_root)

    agent = Agent(
        llm_client=SimpleTextClient("ok"),
        config=config,
        sandbox_backend=MockSandboxBackend([]),
    )
    assert agent.memory_manager is not None

    entry = MemoryEntry(
        entry_id="report-1",
        category=MemoryCategory.ARTIFACTS,
        content={"path": "/workspace/report.md", "type": "markdown"},
        summary="sales report",
        tags=["report"],
    )
    agent.memory_manager._store.save(entry)

    result = await agent.tools.execute(
        ToolCall(id="c1", name="memory_read", arguments={"uri": entry.uri})
    )
    assert result.success
    assert "/workspace/report.md" in result.content
    assert "report-1" in result.content


@pytest.mark.anyio
async def test_memory_read_tool_rejects_invalid_uri(tmp_path: Path) -> None:
    """memory_read 工具对非法 URI 返回失败。"""
    config = AgentConfig()
    config.agent.memory.enabled = True
    config.agent.memory.memory_root = str(tmp_path)

    agent = Agent(
        llm_client=SimpleTextClient("ok"),
        config=config,
        sandbox_backend=MockSandboxBackend([]),
    )

    result = await agent.tools.execute(
        ToolCall(
            id="c1",
            name="memory_read",
            arguments={"uri": "hermes://context/something.jsonl"},
        )
    )
    assert not result.success
    assert "URI 无效" in result.content


# ---------------------------------------------------------------------------
# 补充 Mock LLM 客户端
# ---------------------------------------------------------------------------


class FatalAfterSuccessClient(BaseLLMClient):
    """第一轮成功产生产物，第二轮触发 FATAL 错误的 Mock LLM。"""

    def __init__(self) -> None:
        self.turn = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        self.turn += 1
        if self.turn == 1:
            return {
                "content": "run analysis",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": json.dumps(
                                {
                                    "code": (
                                        "print('Successfully installed pandas');"
                                        " print('/workspace/report.md')"
                                    ),
                                }
                            ),
                        },
                    }
                ],
            }
        return {
            "content": "try privileged operation",
            "tool_calls": [
                {
                    "id": "c2",
                    "type": "function",
                    "function": {
                        "name": "sandbox_exec",
                        "arguments": json.dumps({"code": "touch /root/file"}),
                    },
                }
            ],
        }


class AlwaysExecClient(BaseLLMClient):
    """每轮都调 sandbox_exec 的 Mock LLM。"""

    def __init__(self) -> None:
        self.turn = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        self.turn += 1
        return {
            "content": "run",
            "tool_calls": [
                {
                    "id": f"c{self.turn}",
                    "type": "function",
                    "function": {
                        "name": "sandbox_exec",
                        "arguments": json.dumps({"code": "print('ok')"}),
                    },
                }
            ],
        }


# ---------------------------------------------------------------------------
# 补充测试
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_memory_records_on_fatal(tmp_path: Path) -> None:
    """FATAL 退出路径下仍应记录 memory_recorded 事件。"""
    memory_root = tmp_path / "memory"
    config = AgentConfig()
    config.agent.memory.enabled = True
    config.agent.memory.memory_root = str(memory_root)

    backend = MockSandboxBackend([
        ExecutionResult(
            success=True,
            exit_code=0,
            stdout="Successfully installed pandas\nReport saved to /workspace/report.md",
            stderr="",
        ),
        ExecutionResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="PermissionError: [Errno 13] Permission denied",
        ),
    ])
    agent = Agent(
        llm_client=FatalAfterSuccessClient(),
        config=config,
        sandbox_backend=backend,
    )
    await agent.run("write file")

    trace = agent.get_trace().to_dict()
    events = [
        e for step in trace.get("steps", []) for e in step.get("events", [])
    ]
    recorded = [e for e in events if e["event_type"] == "memory_recorded"]
    assert recorded
    categories = recorded[0]["payload"]["categories"]
    assert "environment" in categories
    assert "artifacts" in categories


@pytest.mark.anyio
async def test_memory_records_on_max_turns(tmp_path: Path) -> None:
    """达到 max_turns 时仍应记录 memory_recorded 事件。"""
    memory_root = tmp_path / "memory"
    config = AgentConfig()
    config.agent.memory.enabled = True
    config.agent.memory.memory_root = str(memory_root)
    config.agent.max_turns = 1

    backend = MockSandboxBackend([
        ExecutionResult(
            success=True,
            exit_code=0,
            stdout="Successfully installed pandas\nReport saved to /workspace/report.md",
            stderr="",
        ),
    ])
    agent = Agent(
        llm_client=AlwaysExecClient(),
        config=config,
        sandbox_backend=backend,
    )
    await agent.run("analyze sales.csv")

    trace = agent.get_trace().to_dict()
    events = [
        e for step in trace.get("steps", []) for e in step.get("events", [])
    ]
    recorded = [e for e in events if e["event_type"] == "memory_recorded"]
    assert recorded
    assert "environment" in recorded[0]["payload"]["categories"]


@pytest.mark.anyio
async def test_memory_read_not_registered_when_disabled(tmp_path: Path) -> None:
    """register_memory_read=False 时不应注册 memory_read 工具。"""
    config = AgentConfig()
    config.agent.memory.enabled = True
    config.agent.memory.memory_root = str(tmp_path)
    config.agent.memory.register_memory_read = False

    agent = Agent(
        llm_client=SimpleTextClient("ok"),
        config=config,
        sandbox_backend=MockSandboxBackend([]),
    )
    assert agent.memory_manager is not None
    tool_names = {s["function"]["name"] for s in agent.tools.list_schemas()}
    assert "memory_read" not in tool_names


@pytest.mark.anyio
async def test_memory_read_result_not_externalized(tmp_path: Path) -> None:
    """memory_read 结果不应被 ToolResultExternalizer 二次外迁。"""
    memory_root = tmp_path / "memory"
    config = AgentConfig()
    config.agent.memory.enabled = True
    config.agent.memory.memory_root = str(memory_root)
    config.agent.compression.enabled = True
    config.agent.compression.externalize_threshold = 10

    agent = Agent(
        llm_client=SimpleTextClient("ok"),
        config=config,
        sandbox_backend=MockSandboxBackend([]),
    )
    entry = MemoryEntry(
        entry_id="big-entry",
        category=MemoryCategory.ARTIFACTS,
        content={"path": "/workspace/very_long_report_name.md"},
        summary="long report",
        tags=["report"],
    )
    agent.memory_manager._store.save(entry)

    result = await agent.tools.execute(
        ToolCall(id="c1", name="memory_read", arguments={"uri": entry.uri})
    )
    assert result.success
    # 如果结果被外迁，这里只会看到缓存预览，看不到完整路径
    assert "/workspace/very_long_report_name.md" in result.content
