"""沙箱代码执行安全策略测试。"""

from __future__ import annotations

import pytest

from agent.core.engine import ToolRegistry
from agent.core.security import PolicyEngine
from agent.core.types import ToolCall, ToolSpec


def make_call(name: str, arguments: dict) -> ToolCall:
    return ToolCall(id="call-1", name=name, arguments=arguments)


class TestSandboxExecSecurity:
    """验证 sandbox_exec 的代码静态扫描策略。"""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        policy = PolicyEngine.default()
        registry = ToolRegistry(policy=policy)
        registry.register(
            ToolSpec(
                name="sandbox_exec",
                description="execute code",
                parameters={
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                },
                handler=lambda code: f"executed: {code}",
            )
        )
        return registry

    @pytest.mark.asyncio
    async def test_deny_import_os(self, registry: ToolRegistry) -> None:
        result = await registry.execute(
            make_call("sandbox_exec", {"code": "import os\nos.system('ls')"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_deny_import_subprocess(self, registry: ToolRegistry) -> None:
        result = await registry.execute(
            make_call("sandbox_exec", {"code": "import subprocess\n"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_deny_import_socket(self, registry: ToolRegistry) -> None:
        result = await registry.execute(
            make_call("sandbox_exec", {"code": "import socket\n"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_deny_from_import(self, registry: ToolRegistry) -> None:
        result = await registry.execute(
            make_call("sandbox_exec", {"code": "from os import path\n"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_deny_dynamic_import(self, registry: ToolRegistry) -> None:
        result = await registry.execute(
            make_call("sandbox_exec", {"code": "__import__('os')"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_deny_importlib(self, registry: ToolRegistry) -> None:
        result = await registry.execute(
            make_call("sandbox_exec", {"code": "import importlib\nimportlib.import_module('os')"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_deny_exec_builtin(self, registry: ToolRegistry) -> None:
        result = await registry.execute(
            make_call("sandbox_exec", {"code": "exec('print(1)')"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_deny_eval_builtin(self, registry: ToolRegistry) -> None:
        result = await registry.execute(
            make_call("sandbox_exec", {"code": "eval('1+1')"})
        )
        assert result.success is False
        assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_deny_network_import(self, registry: ToolRegistry) -> None:
        for module in ("requests", "urllib", "httpx", "socket"):
            result = await registry.execute(
                make_call("sandbox_exec", {"code": f"import {module}\n"})
            )
            assert result.success is False, module
            assert "策略拒绝" in result.content

    @pytest.mark.asyncio
    async def test_allow_safe_code(self, registry: ToolRegistry) -> None:
        result = await registry.execute(
            make_call("sandbox_exec", {"code": "print('hello world')"})
        )
        assert result.success is True
        assert "hello world" in result.content

    @pytest.mark.asyncio
    async def test_deny_reason_returned_to_llm(self, registry: ToolRegistry) -> None:
        result = await registry.execute(
            make_call("sandbox_exec", {"code": "import os"})
        )
        assert result.success is False
        # 拒绝原因应包含具体理由，便于 LLM 自我修正
        assert "禁止" in result.content or "拒绝" in result.content
