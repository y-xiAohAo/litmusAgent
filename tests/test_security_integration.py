"""Phase 9 安全策略主循环集成测试。

这些测试验证：当 Agent 启用安全策略后，危险工具调用会在主循环中被拦截，
拒绝原因会返回给 LLM，且不会阻塞后续执行。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agent.config import (
    AgentConfig,
    AgentRuntimeConfig,
    MemoryConfig,
    SecurityConfig,
)
from agent.core.engine import Agent
from agent.core.memory import MemoryCategory, MemoryEntry, StructuredMemoryStore
from agent.llm.base import BaseLLMClient
from agent.sandbox.docker_backend import DockerSandboxBackend, ExecutionResult


class RecordingMockBackend(DockerSandboxBackend):
    """记录调用并返回预设结果的沙箱后端桩。

    如果某个方法被调用到会触发 ``RuntimeError``，说明策略拦截没有生效。
    """

    def __init__(self) -> None:
        self.execute_calls: list[str] = []
        self.get_file_calls: list[str] = []

    async def execute_code(
        self,
        code: str,
        timeout: int | None = None,
    ) -> ExecutionResult:
        """记录调用并返回空成功结果。"""
        self.execute_calls.append(code)
        return ExecutionResult(
            exit_code=0, stdout="ok", stderr="", success=True
        )

    async def get_file(self, path: str) -> bytes | None:
        """记录调用并返回空内容。"""
        self.get_file_calls.append(path)
        return b"dummy"


class DangerousFileReadClient(BaseLLMClient):
    """第一次调 file_read 读敏感文件，第二次直接文本回复。"""

    def __init__(self) -> None:
        self.turn = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        self.turn += 1
        if self.turn == 1:
            return {
                "content": "Let me read the sensitive file.",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "file_read",
                            "arguments": json.dumps({"path": "/etc/passwd"}),
                        },
                    }
                ],
            }
        return {"content": "Blocked.", "tool_calls": None}


class DangerousSandboxExecClient(BaseLLMClient):
    """第一次调 sandbox_exec 执行危险代码，第二次直接文本回复。"""

    def __init__(self) -> None:
        self.turn = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        self.turn += 1
        if self.turn == 1:
            return {
                "content": "Let me run system command.",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": json.dumps(
                                {"code": "import os\nos.system('ls')"}
                            ),
                        },
                    }
                ],
            }
        return {"content": "Blocked.", "tool_calls": None}


class DangerousMemoryReadClient(BaseLLMClient):
    """第一次调 memory_read 读取被禁止的 category，第二次直接文本回复。"""

    def __init__(self, uri: str) -> None:
        self.turn = 0
        self.uri = uri

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        self.turn += 1
        if self.turn == 1:
            return {
                "content": "Let me read the memory.",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "memory_read",
                            "arguments": json.dumps({"uri": self.uri}),
                        },
                    }
                ],
            }
        return {"content": "Blocked.", "tool_calls": None}


class RecoverAfterBlockClient(BaseLLMClient):
    """第一次被策略拒绝后，第二次换安全路径重试。"""

    def __init__(self) -> None:
        self.turn = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        self.turn += 1
        if self.turn == 1:
            return {
                "content": "Try sensitive path.",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "file_read",
                            "arguments": json.dumps({"path": "/ETC/PASSWD"}),
                        },
                    }
                ],
            }
        if self.turn == 2:
            return {
                "content": "Try safe path.",
                "tool_calls": [
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {
                            "name": "file_read",
                            "arguments": json.dumps(
                                {"path": "/workspace/result.txt"}
                            ),
                        },
                    }
                ],
            }
        return {"content": "Recovered.", "tool_calls": None}


def _security_config_with_memory_read_deny() -> SecurityConfig:
    """构建一个禁止读取 preferences 类别的安全策略配置。"""
    return SecurityConfig(
        enabled=True,
        rules=[
            {
                "resource": "memory/category",
                "operation": "read",
                "pattern": "preferences",
                "action": "deny",
                "reason": "禁止读取 preferences 记忆",
                "priority": 100,
                "use_regex": False,
            },
        ],
    )


class TestAgentSecurityPolicyIntegration:
    """验证 Agent 主循环中的安全策略拦截。"""

    @pytest.mark.asyncio
    async def test_file_read_sensitive_path_blocked(self) -> None:
        """`file_read` 读取敏感路径时，Agent 应返回策略拒绝且不调用后端。"""
        backend = RecordingMockBackend()
        config = AgentConfig(security=SecurityConfig(enabled=True))
        agent = Agent(
            llm_client=DangerousFileReadClient(),
            config=config,
            sandbox_backend=backend,
            max_turns=5,
        )

        response = await agent.run("读取敏感文件")

        # 后端不应被调用
        assert backend.get_file_calls == []
        # LLM 应该收到策略拒绝信息
        tool_results = [msg for msg in agent.messages if msg.role == "tool"]
        assert len(tool_results) == 1
        assert "策略拒绝" in tool_results[0].content
        assert "/etc/passwd" in tool_results[0].content or "系统用户" in tool_results[0].content
        # Agent 最终返回第二轮的文本回复
        assert response == "Blocked."

    @pytest.mark.asyncio
    async def test_sandbox_exec_dangerous_code_blocked(self) -> None:
        """`sandbox_exec` 执行高危代码时，Agent 应返回策略拒绝且不调用后端。"""
        backend = RecordingMockBackend()
        config = AgentConfig(security=SecurityConfig(enabled=True))
        agent = Agent(
            llm_client=DangerousSandboxExecClient(),
            config=config,
            sandbox_backend=backend,
            max_turns=5,
        )

        response = await agent.run("执行危险代码")

        # 后端不应被调用
        assert backend.execute_calls == []
        tool_results = [msg for msg in agent.messages if msg.role == "tool"]
        assert len(tool_results) == 1
        assert "策略拒绝" in tool_results[0].content
        assert "禁止" in tool_results[0].content
        assert response == "Blocked."

    @pytest.mark.asyncio
    async def test_memory_read_blocked_category(self, tmp_path: Path) -> None:
        """`memory_read` 读取被禁止的 category 时，Agent 应返回策略拒绝。"""
        memory_root = tmp_path / "memory"
        store = StructuredMemoryStore(memory_root)
        entry = MemoryEntry(
            entry_id="pref1",
            category=MemoryCategory.PREFERENCES,
            content={"key": "theme", "value": "dark"},
            summary="theme preference",
            tags=["preference"],
        )
        store.save(entry)

        config = AgentConfig(
            security=_security_config_with_memory_read_deny(),
            agent=AgentRuntimeConfig(
                memory=MemoryConfig(enabled=True, memory_root=str(memory_root))
            ),
        )
        agent = Agent(
            llm_client=DangerousMemoryReadClient(entry.uri),
            config=config,
            max_turns=5,
        )

        response = await agent.run("读取记忆")

        tool_results = [msg for msg in agent.messages if msg.role == "tool"]
        assert len(tool_results) == 1
        assert "策略拒绝" in tool_results[0].content
        assert "禁止读取 preferences 记忆" in tool_results[0].content
        assert response == "Blocked."

    @pytest.mark.asyncio
    async def test_agent_without_security_allows_normal_operations(self) -> None:
        """未启用安全策略时，Agent 应正常执行工具调用。"""
        backend = RecordingMockBackend()
        config = AgentConfig(security=SecurityConfig(enabled=False))
        agent = Agent(
            llm_client=DangerousFileReadClient(),
            config=config,
            sandbox_backend=backend,
            max_turns=5,
        )

        response = await agent.run("读取文件")

        # 后端应被正常调用
        assert backend.get_file_calls == ["/etc/passwd"]
        tool_results = [msg for msg in agent.messages if msg.role == "tool"]
        assert len(tool_results) == 1
        assert "策略拒绝" not in tool_results[0].content
        assert response == "Blocked."

    @pytest.mark.asyncio
    async def test_blocked_then_safe_path_recover(self) -> None:
        """策略拒绝后，LLM 改用安全路径应能继续执行。"""
        backend = RecordingMockBackend()
        config = AgentConfig(security=SecurityConfig(enabled=True))
        agent = Agent(
            llm_client=RecoverAfterBlockClient(),
            config=config,
            sandbox_backend=backend,
            max_turns=5,
        )

        response = await agent.run("尝试读取")

        # 第一次敏感路径被拒绝，不应调用后端
        # 第二次安全路径应调用后端
        assert backend.get_file_calls == ["/workspace/result.txt"]
        tool_results = [msg for msg in agent.messages if msg.role == "tool"]
        assert len(tool_results) == 2
        assert "策略拒绝" in tool_results[0].content
        assert "策略拒绝" not in tool_results[1].content
        assert response == "Recovered."
