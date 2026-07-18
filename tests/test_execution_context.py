"""ExecutionContext 工具注入机制测试（TD-004）。

覆盖：
  - 声明 execution_context 参数的 handler 收到 Agent 持有的同一实例
  - 未声明该参数的 handler 行为完全不变
  - call.arguments 已提供 execution_context 时不覆盖（保留参数名冲突规则）
  - 状态跨 tool call 保留（session 级生命周期）
  - Agent.reset() 清空 ExecutionContext
"""

from __future__ import annotations

import pytest

from agent.core.engine import Agent, ToolRegistry
from agent.core.state import ExecutionContext
from agent.core.types import ToolCall, ToolResult, ToolSpec
from agent.llm.base import EchoClient


def make_call(name: str, arguments: dict) -> ToolCall:
    return ToolCall(id="call-1", name=name, arguments=arguments)


class TestContextInjection:
    """ToolRegistry 的 ExecutionContext 注入行为。"""

    @pytest.mark.asyncio
    async def test_ctx_aware_handler_receives_same_instance(self) -> None:
        """声明 execution_context 的 handler 收到 registry 持有的同一实例。"""
        ctx = ExecutionContext()
        registry = ToolRegistry(execution_context=ctx)
        received: list[ExecutionContext] = []

        def probe(execution_context: ExecutionContext) -> str:
            received.append(execution_context)
            return "ok"

        registry.register(
            ToolSpec(name="probe", description="p", parameters={}, handler=probe)
        )
        result = await registry.execute(make_call("probe", {}))
        assert result.success is True
        assert received == [ctx]
        assert received[0] is ctx

    @pytest.mark.asyncio
    async def test_plain_handler_unchanged(self) -> None:
        """未声明 execution_context 的 handler 不收到额外参数。"""
        ctx = ExecutionContext()
        registry = ToolRegistry(execution_context=ctx)
        registry.register(
            ToolSpec(
                name="echo",
                description="e",
                parameters={},
                handler=lambda code: f"echo:{code}",
            )
        )
        result = await registry.execute(make_call("echo", {"code": "hi"}))
        assert result.success is True
        assert result.content == "echo:hi"

    @pytest.mark.asyncio
    async def test_arguments_provided_not_overridden(self) -> None:
        """call.arguments 已含 execution_context 时不注入（保留参数冲突规则）。"""
        ctx = ExecutionContext()
        registry = ToolRegistry(execution_context=ctx)
        received: list[object] = []

        def probe(execution_context: object) -> str:
            received.append(execution_context)
            return "ok"

        registry.register(
            ToolSpec(name="probe", description="p", parameters={}, handler=probe)
        )
        sentinel = object()
        await registry.execute(make_call("probe", {"execution_context": sentinel}))
        assert received == [sentinel]

    @pytest.mark.asyncio
    async def test_state_persists_across_calls(self) -> None:
        """第一次调用 set 的值，第二次调用 get 能读到（跨 tool call 保留）。"""
        ctx = ExecutionContext()
        registry = ToolRegistry(execution_context=ctx)

        def writer(execution_context: ExecutionContext) -> str:
            execution_context.set("packages_installed", ["pandas"])
            return "written"

        def reader(execution_context: ExecutionContext) -> str:
            return ",".join(execution_context.get("packages_installed", []))

        registry.register(
            ToolSpec(name="writer", description="w", parameters={}, handler=writer)
        )
        registry.register(
            ToolSpec(name="reader", description="r", parameters={}, handler=reader)
        )
        await registry.execute(make_call("writer", {}))
        result = await registry.execute(make_call("reader", {}))
        assert result.content == "pandas"

    @pytest.mark.asyncio
    async def test_async_ctx_handler_supported(self) -> None:
        """异步 ctx 感知 handler 同样被注入并 await。"""
        ctx = ExecutionContext()
        registry = ToolRegistry(execution_context=ctx)

        async def aprobe(execution_context: ExecutionContext) -> ToolResult:
            execution_context.set("flag", True)
            return ToolResult(tool_call_id="", content="async-ok", success=True)

        registry.register(
            ToolSpec(name="aprobe", description="a", parameters={}, handler=aprobe)
        )
        result = await registry.execute(make_call("aprobe", {}))
        assert result.success is True
        assert result.content == "async-ok"
        assert ctx.get("flag") is True

    @pytest.mark.asyncio
    async def test_no_ctx_configured_no_injection(self) -> None:
        """registry 未配置 execution_context 时，ctx 感知 handler 收到 None。"""
        registry = ToolRegistry()
        received: list[object] = []

        def probe(execution_context: object = None) -> str:
            received.append(execution_context)
            return "ok"

        registry.register(
            ToolSpec(name="probe", description="p", parameters={}, handler=probe)
        )
        await registry.execute(make_call("probe", {}))
        assert received == [None]


class TestAgentContextLifecycle:
    """Agent 持有 ExecutionContext 的生命周期（session 级 + reset 清空）。"""

    def test_agent_holds_execution_context(self) -> None:
        """Agent 实例化后持有 ExecutionContext，且注册到 ToolRegistry。"""
        agent = Agent(llm_client=EchoClient())
        try:
            assert isinstance(agent.execution_context, ExecutionContext)
        finally:
            agent._sandbox_backend.close()

    def test_reset_clears_execution_context(self) -> None:
        """reset() 清空 ExecutionContext 中的状态。"""
        agent = Agent(llm_client=EchoClient())
        try:
            agent.execution_context.set("packages_installed", ["pandas"])
            agent.reset()
            assert agent.execution_context.get("packages_installed", []) == []
        finally:
            agent._sandbox_backend.close()


class _FakeExecBackend:
    """返回预设 ExecutionResult 的假沙箱后端（不执行真实代码）。"""

    def __init__(self, success: bool) -> None:
        self._success = success

    async def execute_code(self, code: str, timeout: int | None = None):  # noqa: ANN202
        from agent.sandbox.base import ExecutionResult

        if self._success:
            return ExecutionResult(exit_code=0, stdout="ok", stderr="", success=True)
        return ExecutionResult(exit_code=1, stdout="", stderr="boom", success=False)


class TestSandboxExecPipTracking:
    """sandbox_exec 的 pip 安装包记录示例（TD-004 真实使用示例）。"""

    @pytest.mark.asyncio
    async def test_pip_install_recorded_on_success(self) -> None:
        """成功执行含 pip install 的代码后，包名记入 packages_installed。"""
        from agent.tools import sandbox_exec

        ctx = ExecutionContext()
        backend = _FakeExecBackend(success=True)
        result = await sandbox_exec(
            "pip install requests numpy\nprint('done')\n",
            backend=backend,
            execution_context=ctx,
        )
        assert result.success is True
        packages = ctx.get("packages_installed", [])
        assert "requests" in packages
        assert "numpy" in packages

    @pytest.mark.asyncio
    async def test_pip_install_not_recorded_on_failure(self) -> None:
        """执行失败时不记录。"""
        from agent.tools import sandbox_exec

        ctx = ExecutionContext()
        backend = _FakeExecBackend(success=False)
        result = await sandbox_exec(
            "pip install requests", backend=backend, execution_context=ctx
        )
        assert result.success is False
        assert ctx.get("packages_installed", []) == []

    @pytest.mark.asyncio
    async def test_no_pip_code_no_record(self) -> None:
        """不含 pip install 的代码不记录。"""
        from agent.tools import sandbox_exec

        ctx = ExecutionContext()
        backend = _FakeExecBackend(success=True)
        await sandbox_exec("print('hello')", backend=backend, execution_context=ctx)
        assert ctx.get("packages_installed", []) == []

    @pytest.mark.asyncio
    async def test_options_and_comments_ignored(self) -> None:
        """pip 选项（-r 等）与纯注释行不产生误报包名。"""
        from agent.tools.sandbox_exec import _extract_pip_packages

        code = (
            "pip install -r requirements.txt\n"
            "# pip install fake-package\n"
            "pip install real-pkg\n"
        )
        packages = _extract_pip_packages(code)
        assert packages == ["real-pkg"]

    @pytest.mark.asyncio
    async def test_no_ctx_param_backward_compatible(self) -> None:
        """不传 execution_context 时行为与之前一致（向后兼容）。"""
        from agent.tools import sandbox_exec

        backend = _FakeExecBackend(success=True)
        result = await sandbox_exec("pip install requests", backend=backend)
        assert result.success is True


class TestAgentEndToEndContext:
    """Agent 主循环内 ExecutionContext 跨 tool call 共享（TD-004 集成）。"""

    @pytest.mark.asyncio
    async def test_context_shared_across_tool_calls_in_one_run(self) -> None:
        """同一 run 内：第一个工具 set，第二个工具 get 读到同一状态。"""
        from agent.llm.base import BaseLLMClient

        class TwoStepClient(BaseLLMClient):
            """脚本化客户端：先调 writer，再调 reader，最后交付文本。"""

            def __init__(self) -> None:
                self._step = 0

            async def chat(self, messages, tools=None, **kwargs):  # noqa: ANN001, ANN202
                self._step += 1
                if self._step == 1:
                    return {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {"name": "ctx_write", "arguments": "{}"},
                            }
                        ],
                    }
                if self._step == 2:
                    return {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "c2",
                                "function": {"name": "ctx_read", "arguments": "{}"},
                            }
                        ],
                    }
                return {"content": "done", "tool_calls": None}

        agent = Agent(llm_client=TwoStepClient())
        try:
            def ctx_write(execution_context: ExecutionContext) -> str:
                execution_context.set("marker", "shared-state")
                return "ok"

            def ctx_read(execution_context: ExecutionContext) -> str:
                return str(execution_context.get("marker", "missing"))

            agent.tools.register(
                ToolSpec(
                    name="ctx_write",
                    description="w",
                    parameters={"type": "object", "properties": {}},
                    handler=ctx_write,
                )
            )
            agent.tools.register(
                ToolSpec(
                    name="ctx_read",
                    description="r",
                    parameters={"type": "object", "properties": {}},
                    handler=ctx_read,
                )
            )

            result = await agent.run("test")
            assert result == "done"
            # 第二个工具通过注入的 ctx 读到了第一个工具写入的状态
            tool_results = [
                m.content for m in agent.messages if m.role == "tool"
            ]
            assert "shared-state" in tool_results
        finally:
            agent._sandbox_backend.close()


class TestPipExtractSubprocessStyle:
    """_extract_pip_packages 的 subprocess 风格匹配增强（FAST 收尾）。"""

    def test_list_form_pip_install(self) -> None:
        """["pip", "install", "pkg"] 列表形态被提取。"""
        from agent.tools.sandbox_exec import _extract_pip_packages

        code = 'import subprocess\nsubprocess.run(["pip", "install", "requests"])\n'
        assert _extract_pip_packages(code) == ["requests"]

    def test_sys_executable_m_pip_form(self) -> None:
        """[sys.executable, "-m", "pip", "install", ...] 形态被提取。"""
        from agent.tools.sandbox_exec import _extract_pip_packages

        code = (
            "import subprocess, sys\n"
            'subprocess.run([sys.executable, "-m", "pip", "install", "numpy", "pandas"])\n'
        )
        assert _extract_pip_packages(code) == ["numpy", "pandas"]

    def test_list_form_options_filtered(self) -> None:
        """列表形态中的 - 选项被过滤。"""
        from agent.tools.sandbox_exec import _extract_pip_packages

        code = 'subprocess.run(["pip", "install", "--quiet", "flask"])\n'
        assert _extract_pip_packages(code) == ["flask"]

    def test_version_pins_normalized(self) -> None:
        """版本钉与 extras 被归一化为包名。"""
        from agent.tools.sandbox_exec import _extract_pip_packages

        code = 'subprocess.run(["pip", "install", "requests==2.31.0", "uvicorn[standard]"])\n'
        assert _extract_pip_packages(code) == ["requests", "uvicorn"]

    def test_os_system_string_form(self) -> None:
        """os.system("pip install pkg") 字符串形态被提取。"""
        from agent.tools.sandbox_exec import _extract_pip_packages

        code = 'import os\nos.system("pip install rich")\n'
        assert _extract_pip_packages(code) == ["rich"]

    def test_subprocess_success_records_packages(self) -> None:
        """端到端：subprocess 风格代码成功执行后记录到 ctx。"""
        import asyncio

        from agent.core.state import ExecutionContext
        from agent.tools import sandbox_exec

        async def run() -> None:
            ctx = ExecutionContext()
            backend = _FakeExecBackend(success=True)
            code = (
                "import subprocess, sys\n"
                "subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests'])\n"
            )
            result = await sandbox_exec(code, backend=backend, execution_context=ctx)
            assert result.success is True
            assert ctx.get("packages_installed", []) == ["requests"]

        asyncio.run(run())
