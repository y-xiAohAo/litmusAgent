"""Phase 2.7 集成测试：Agent + Planner + ErrorHandler 协同工作。

这些测试验证三个核心组件能否在一个完整的 Agent 运行流程中正确交互：
  - Planner：追踪任务进度
  - ErrorHandler：对工具执行失败进行错误分类和恢复建议
  - Agent 主循环：协调 Planner 和 ErrorHandler 的介入时机
"""

from __future__ import annotations

import ast
import json
import os
from typing import Any

import pytest

from agent.core.engine import Agent
from agent.core.planner import StepStatus, TaskPlan
from agent.core.types import ToolSpec
from agent.llm.base import BaseLLMClient
from agent.sandbox.docker_backend import DockerSandboxBackend, ExecutionResult

# ---------------------------------------------------------------------------
# Mock 沙箱后端 — 替代真实 Docker daemon
# ---------------------------------------------------------------------------


class MockSandboxBackend(DockerSandboxBackend):
    """用于集成测试的沙箱后端桩。

    继承 DockerSandboxBackend 仅为了通过类型检查，不会连接真实 daemon。
    """

    def __init__(self, responses: list[ExecutionResult]) -> None:
        self.responses = responses
        self.call_count = 0

    async def execute_code(
        self,
        code: str,
        timeout: int | None = None,
    ) -> ExecutionResult:
        """按顺序返回预设结果。"""
        response = self.responses[self.call_count]
        self.call_count += 1
        return response


# ---------------------------------------------------------------------------
# Mock LLM 客户端 — 模拟真实多轮对话场景
# ---------------------------------------------------------------------------


class MultiTurnMockClient(BaseLLMClient):
    """模拟一个多轮对话：tool_call → 看到错误 → 修正 → tool_call → 成功 → 结束。

    轮次：
      1. 调 sandbox_exec（带错误：NameError）
      2. 工具执行失败（LLM 看到错误信息），调 sandbox_exec（修正后）
      3. 工具成功，返回 columns 信息
      4. 最终文本回复
    """

    def __init__(self) -> None:
        self.turn = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        self.turn += 1

        if self.turn == 1:
            # 第一轮：请求执行含错误的代码
            return {
                "content": "I'll read the CSV.",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": '{"code": "df.head()"}',
                        },
                    }
                ],
            }
        elif self.turn == 2:
            # 第二轮：LLM 看到了错误信息（NameError），决定修正代码
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": (
                                '{"code": "import pandas; print(pandas.DataFrame().columns)"}'
                            ),
                        },
                    }
                ],
            }
        elif self.turn == 3:
            # 第三轮：LLM 看到了工具成功的结果，可以交付了
            return {
                "content": "Analysis complete. Columns: name, date, revenue.",
                "tool_calls": None,
            }
        else:
            # 安全兜底
            return {"content": "Done.", "tool_calls": None}


class PlanAwareMockClient(BaseLLMClient):
    """检查 LLM 收到消息中是否包含 Planner 生成的进度信息。"""

    def __init__(self) -> None:
        self.received_messages: list[list[dict[str, Any]]] = []

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        # 记录每次调用收到的 messages，方便测试断言
        self.received_messages.append(messages)
        return {"content": "OK, I see the plan.", "tool_calls": None}


class ErrorRecoveryMockClient(BaseLLMClient):
    """模拟 LLM 收到带恢复建议的错误信息后的行为。

    场景：
      1. 调 sandbox_exec → 工具抛 NameError
      2. Agent 用 ErrorHandler 分类 → 附加恢复建议到 tool result
      3. LLM 看到含建议的错误消息 → 决定检查环境
    """

    def __init__(self) -> None:
        self.turn = 0
        self.last_tool_result_content: str = ""

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        self.turn += 1

        # 在 turn 2 捕获第一个 tool result，即带错误分类信息的错误结果。
        # 注意：如果遍历所有 message 并覆盖，最后得到的是第二轮成功执行的结果，
        # 而不是我们想要的错误分类结果。
        if self.turn == 2:
            for msg in messages:
                if msg.get("role") == "tool":
                    self.last_tool_result_content = msg.get("content", "")
                    break

        if self.turn == 1:
            return {
                "content": "Let me check the data.",
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": '{"code": "bad_code_here"}',
                        },
                    }
                ],
            }
        elif self.turn == 2:
            # LLM 看到错误信息（含恢复建议），决定检查环境
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": '{"code": "print(dir())"}',
                        },
                    }
                ],
            }
        else:
            return {"content": "Checked. Fixed.", "tool_calls": None}


# ---------------------------------------------------------------------------
# 集成测试
# ---------------------------------------------------------------------------


class TestAgentWithPlanner:
    """测试 Agent + Planner 协同工作。"""

    @pytest.mark.asyncio
    async def test_agent_includes_plan_progress_in_prompt(self):
        """Agent 应该把 Planner 的进度信息注入到发给 LLM 的 system prompt 中。"""
        plan = TaskPlan(goal="分析 sales.csv")
        plan.add_step("load", "用 pandas 读取 sales.csv")
        plan.add_step("clean", "清理缺失值")
        plan.start_next()  # 激活第一个步骤

        client = PlanAwareMockClient()
        agent = Agent(llm_client=client, planner=plan)

        await agent.run("开始分析")

        # LLM 应该收到了包含进度信息的 system prompt
        assert len(client.received_messages) > 0
        system_msg = client.received_messages[0][0]
        assert system_msg["role"] == "system"
        assert "sales.csv" in system_msg["content"]
        assert "load" in system_msg["content"] or "pandas" in system_msg["content"]

    @pytest.mark.asyncio
    async def test_agent_runs_without_planner(self):
        """Agent 应该在没有 Planner 的情况下也能正常工作（plan=None）。"""
        agent = Agent(
            llm_client=DummyLLM("Hello"), planner=None
        )
        response = await agent.run("hi")
        assert response == "Hello"

    @pytest.mark.asyncio
    async def test_plan_steps_advance_after_successful_tool(self):
        """成功的工具执行后，计划的当前步骤应该自动标记为完成。"""
        plan = TaskPlan(goal="测试")
        plan.add_step("step1", "执行加法")
        plan.add_step("step2", "返回结果")
        plan.start_next()

        agent = Agent(
            llm_client=SingleToolThenTextClient(),
            planner=plan,
        )
        agent.tools.register(
            ToolSpec(
                name="add",
                description="加法",
                parameters={
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"},
                    },
                    "required": ["a", "b"],
                },
                handler=lambda a, b: a + b,
            )
        )

        await agent.run("calculate")

        # step1 应该被标记为完成
        assert plan.steps[0].status == StepStatus.COMPLETED


class TestAgentWithErrorHandler:
    """测试 Agent + ErrorHandler 协同工作。"""

    @pytest.mark.asyncio
    async def test_error_classification_attached_to_tool_result(self):
        """工具执行失败时，错误分类信息应该附加到 tool result 内容中。"""
        backend = MockSandboxBackend(
            [
                ExecutionResult(
                    exit_code=1,
                    stdout="",
                    stderr="NameError: name 'pd' is not defined",
                    success=False,
                ),
                ExecutionResult(
                    exit_code=0,
                    stdout="['name', 'date', 'revenue']",
                    stderr="",
                    success=True,
                ),
            ]
        )
        agent = Agent(
            llm_client=ErrorRecoveryMockClient(),
            sandbox_backend=backend,
        )

        await agent.run("Analyze data")

        # LLM 应该在第二轮调用中收到了包含恢复建议的错误信息
        assert agent.llm.last_tool_result_content  # type: ignore[union-attr]
        content = agent.llm.last_tool_result_content  # type: ignore[union-attr]
        # 错误内容应该包含原始错误信息
        assert "pd" in content or "NameError" in content

    @pytest.mark.asyncio
    async def test_fatal_error_stops_execution(self):
        """FATAL 级别的错误应该让 Agent 停止执行并报告。"""

        class DieOnFirstCallClient(BaseLLMClient):
            async def chat(self, messages, tools=None, **kwargs):
                return {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "sandbox_exec",
                                "arguments": '{"code": "test"}',
                            },
                        }
                    ],
                }

        backend = MockSandboxBackend(
            [
                ExecutionResult(
                    exit_code=1,
                    stdout="",
                    stderr="PermissionError: Access denied to /etc/shadow",
                    success=False,
                ),
            ]
        )
        agent = Agent(
            llm_client=DieOnFirstCallClient(),
            max_turns=5,
            sandbox_backend=backend,
        )

        response = await agent.run("test")
        # FATAL 错误应该直接导致 Agent 停止并返回错误信息
        assert (
            "PermissionError" in response
            or "权限" in response
            or "FATAL" in response
            or "无法继续" in response
        )


class TestFullIntegration:
    """完整的端到端集成测试：Plan → Execute → Error → Recover → Complete。"""

    @pytest.mark.asyncio
    async def test_full_flow_with_planner_and_error_recovery(self):
        """模拟完整运行：
        1. Planner 生成步骤
        2. Agent 执行步骤 1 → 出错（NameError）
        3. ErrorHandler 分类错误，附加恢复建议
        4. Agent 把含建议的错误发给 LLM
        5. LLM 修正代码，重新执行
        6. 成功 → 步骤完成 → 最终交付
        """
        plan = TaskPlan(goal="分析 data.csv")
        plan.add_step("analyze", "加载并分析 CSV 数据")
        plan.start_next()

        backend = MockSandboxBackend(
            [
                ExecutionResult(
                    exit_code=1,
                    stdout="",
                    stderr="NameError: name 'df' is not defined",
                    success=False,
                ),
                ExecutionResult(
                    exit_code=0,
                    stdout="Index([], dtype='object')",
                    stderr="",
                    success=True,
                ),
            ]
        )
        agent = Agent(
            llm_client=MultiTurnMockClient(),
            planner=plan,
            max_turns=5,
            sandbox_backend=backend,
        )

        response = await agent.run("分析 data.csv")

        # 验证最终输出
        assert "complete" in response.lower() or "column" in response.lower()
        # 验证计划步骤完成
        assert plan.steps[0].status == StepStatus.COMPLETED
        # 验证工具被调用了 2 次（第一次出错，第二次成功）
        assert backend.call_count == 2


# ---------------------------------------------------------------------------
# 辅助 Mock 类（与 test_agent_loop.py 共享行为的简化版）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 带状态的 Mock 沙箱后端 —— 支持端到端工作流中的写文件、列表、读取
# ---------------------------------------------------------------------------


class StatefulMockBackend(DockerSandboxBackend):
    """带内存文件系统的 Mock 沙箱后端，用于端到端集成测试。

    通过 AST 解析 LLM 生成的代码片段，模拟三类操作：
      1. 写文件：识别 `with open(path, 'w') as f: f.write(...)`。
      2. 列目录：识别 `os.listdir(path)` 并返回当前内存中的文件列表。
      3. 读文件：通过 `get_file(path)` 直接返回内存中记录的内容。

    全部在内存中完成，不连接真实 Docker daemon。
    """

    def __init__(self, initial_files: dict[str, bytes] | None = None) -> None:
        self.files: dict[str, bytes] = dict(initial_files or {})
        self.execute_codes: list[str] = []
        self.execute_count: int = 0

    async def execute_code(
        self,
        code: str,
        timeout: int | None = None,
    ) -> ExecutionResult:
        """解析代码意图并更新内存文件系统，返回执行结果。"""
        self.execute_codes.append(code)
        self.execute_count += 1

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return ExecutionResult(
                exit_code=1, stdout="", stderr=f"SyntaxError: {exc}", success=False,
            )

        # 处理写文件：只支持 with open(..., 'w') as f: f.write(...)
        for node in ast.walk(tree):
            if isinstance(node, ast.With):
                for item in node.items:
                    context_expr = item.context_expr
                    if isinstance(context_expr, ast.Call):
                        call = context_expr
                        if isinstance(call.func, ast.Name) and call.func.id == "open":
                            path = self._extract_constant(call.args[0])
                            mode = (
                                self._extract_constant(call.args[1])
                                if len(call.args) > 1
                                else "r"
                            )
                            if path and isinstance(mode, str) and "w" in mode:
                                content = self._find_write_content(node)
                                self.files[path] = content.encode("utf-8")
                                return ExecutionResult(
                                    exit_code=0, stdout="", stderr="", success=True,
                                )

            # 处理 os.listdir(path)：返回对应目录下的文件/子目录名
            if isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "listdir"
                ):
                    path = self._extract_constant(node.args[0]) if node.args else "."
                    entries = self._list_directory(path or ".")
                    return ExecutionResult(
                        exit_code=0,
                        stdout=json.dumps(entries),
                        stderr="",
                        success=True,
                    )

        # 默认返回成功但空输出
        return ExecutionResult(exit_code=0, stdout="", stderr="", success=True)

    async def get_file(self, path: str) -> bytes | None:
        """按路径返回内存中的文件内容。"""
        return self.files.get(path)

    def _extract_constant(self, node: ast.AST) -> str | None:
        """从 AST 节点中提取字符串常量。"""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    def _find_write_content(self, node: ast.With) -> str:
        """在 with 语句体中查找 `f.write(...)` 的内容。"""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if (
                    isinstance(child.func, ast.Attribute)
                    and child.func.attr == "write"
                ):
                    if child.args:
                        arg = child.args[0]
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                            return arg.value
        return ""

    def _list_directory(self, path: str) -> list[str]:
        """列出内存文件系统中指定目录下的条目。"""
        entries: list[str] = []
        for file_path in self.files:
            dir_name = os.path.dirname(file_path)
            # 统一根目录表示：空目录名视为当前目录
            normalized_dir = dir_name if dir_name else "."
            if normalized_dir == path:
                entries.append(os.path.basename(file_path))
        return sorted(entries)


# ---------------------------------------------------------------------------
# 端到端工作流 Mock LLM 客户端
# ---------------------------------------------------------------------------


class EndToEndMockClient(BaseLLMClient):
    """模拟无 Planner 的完整工作流：执行 → 列表 → 读取 → 交付。"""

    def __init__(self) -> None:
        self.turn = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any,
    ) -> dict[str, Any]:
        self.turn += 1

        if self.turn == 1:
            # 第 1 轮：调用 sandbox_exec 写文件
            return {
                "content": "我先创建结果文件。",
                "tool_calls": [
                    {
                        "id": "e1",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": json.dumps(
                                {
                                    "code": (
                                        "with open('/tmp/result.txt', 'w') as f:\n"
                                        "    f.write('hello world')"
                                    ),
                                }
                            ),
                        },
                    }
                ],
            }
        elif self.turn == 2:
            # 第 2 轮：调用 file_list 观察目录
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "e2",
                        "type": "function",
                        "function": {
                            "name": "file_list",
                            "arguments": json.dumps({"path": "/tmp"}),
                        },
                    }
                ],
            }
        elif self.turn == 3:
            # 第 3 轮：调用 file_read 读取文件
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "e3",
                        "type": "function",
                        "function": {
                            "name": "file_read",
                            "arguments": json.dumps({"path": "/tmp/result.txt"}),
                        },
                    }
                ],
            }
        elif self.turn == 4:
            # 第 4 轮：调用 finish 交付最终结果
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "e4",
                        "type": "function",
                        "function": {
                            "name": "finish",
                            "arguments": json.dumps(
                                {"result": "文件内容为：hello world"}
                            ),
                        },
                    }
                ],
            }
        else:
            return {"content": "Done.", "tool_calls": None}


class PlannerAwareMockClient(BaseLLMClient):
    """模拟带 Planner 的完整工作流：按步骤执行、读取、交付。"""

    def __init__(self) -> None:
        self.turn = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any,
    ) -> dict[str, Any]:
        self.turn += 1

        if self.turn == 1:
            # 步骤 write：创建文件
            return {
                "content": "开始写入文件。",
                "tool_calls": [
                    {
                        "id": "p1",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": json.dumps(
                                {
                                    "code": (
                                        "with open('/tmp/plan_result.txt', 'w') as f:\n"
                                        "    f.write('plan ok')"
                                    ),
                                }
                            ),
                        },
                    }
                ],
            }
        elif self.turn == 2:
            # 步骤 inspect：读取文件
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "p2",
                        "type": "function",
                        "function": {
                            "name": "file_read",
                            "arguments": json.dumps({"path": "/tmp/plan_result.txt"}),
                        },
                    }
                ],
            }
        else:
            # 步骤 deliver：完成任务
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "p3",
                        "type": "function",
                        "function": {
                            "name": "finish",
                            "arguments": json.dumps({"result": "Planner 流程完成"}),
                        },
                    }
                ],
            }


class TestEndToEndWorkflow:
    """Phase 4.4 端到端集成测试：计划 → 执行 → 观察 → 交付。"""

    @pytest.mark.asyncio
    async def test_full_workflow_without_planner(self) -> None:
        """无 Planner 场景：Agent 依次执行、列表、读取、交付。"""
        backend = StatefulMockBackend()
        agent = Agent(
            llm_client=EndToEndMockClient(),
            sandbox_backend=backend,
            max_turns=10,
        )

        response = await agent.run("请创建文件并读取内容")

        # 验证最终交付结果
        assert response == "文件内容为：hello world"
        # 验证 sandbox_exec 和 file_list 各调用了 1 次 execute_code
        assert backend.execute_count == 2
        # 验证文件确实被写入内存文件系统
        assert backend.files.get("/tmp/result.txt") == b"hello world"
        # 验证工具调用顺序：执行 → 列表 → 读取 → 交付
        tool_order = [
            msg.tool_calls[0].name
            for msg in agent.messages
            if msg.role == "assistant" and msg.tool_calls
        ]
        assert tool_order == ["sandbox_exec", "file_list", "file_read", "finish"]

    @pytest.mark.asyncio
    async def test_full_workflow_with_planner(self) -> None:
        """带 Planner 场景：步骤按顺序推进并最终全部完成。"""
        plan = TaskPlan(goal="创建并读取文件")
        plan.add_step("write", "创建文件")
        plan.add_step("inspect", "读取文件")
        plan.add_step("deliver", "交付结果")
        plan.start_next()

        backend = StatefulMockBackend()
        agent = Agent(
            llm_client=PlannerAwareMockClient(),
            planner=plan,
            sandbox_backend=backend,
            max_turns=10,
        )

        response = await agent.run("请按计划执行")

        # 验证最终交付结果
        assert response == "Planner 流程完成"
        # 验证三个步骤全部完成
        assert all(step.status == StepStatus.COMPLETED for step in plan.steps)
        # 验证 write 步骤确实创建了文件
        assert backend.files.get("/tmp/plan_result.txt") == b"plan ok"


# ---------------------------------------------------------------------------
# 错误注入型 Mock 沙箱后端 —— 用于错误恢复场景测试
# ---------------------------------------------------------------------------


class ErrorInjectionBackend(DockerSandboxBackend):
    """按预设序列返回执行结果的 Mock 沙箱后端。

    与 `StatefulMockBackend` 不同，本后端不关心代码语义，只按顺序返回
    `execute_responses` 中的结果。适合需要精确控制"哪一次调用成功、
    哪一次调用失败"的错误恢复测试。

    同时支持 `get_file(path)`，可与 `file_read` 工具配合使用。
    """

    def __init__(
        self,
        execute_responses: list[ExecutionResult],
        files: dict[str, bytes] | None = None,
    ) -> None:
        self.execute_responses = execute_responses
        self.files = files or {}
        self.execute_count = 0
        self.execute_codes: list[str] = []

    async def execute_code(
        self,
        code: str,
        timeout: int | None = None,
    ) -> ExecutionResult:
        """按顺序返回预设结果，并记录调用信息。"""
        self.execute_codes.append(code)
        if self.execute_count >= len(self.execute_responses):
            return ExecutionResult(
                exit_code=1,
                stdout="",
                stderr="ErrorInjectionBackend: 没有更多预设响应",
                success=False,
            )
        response = self.execute_responses[self.execute_count]
        self.execute_count += 1
        return response

    async def get_file(self, path: str) -> bytes | None:
        """按路径返回预设的文件内容。"""
        return self.files.get(path)


# ---------------------------------------------------------------------------
# 错误恢复场景 Mock LLM 客户端
# ---------------------------------------------------------------------------


class SyntaxErrorRecoveryClient(BaseLLMClient):
    """模拟 LLM 遇到 SyntaxError 后修正代码的行为。"""

    def __init__(self, planner: TaskPlan | None = None) -> None:
        self.turn = 0
        self.planner = planner

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any,
    ) -> dict[str, Any]:
        self.turn += 1

        # 错误发生后、成功修复前，验证 Planner 步骤保持 ACTIVE
        if self.turn == 2 and self.planner and self.planner.current_step:
            assert self.planner.current_step.status == StepStatus.ACTIVE

        if self.turn == 1:
            # 第一轮：提交有语法错误的代码
            return {
                "content": "Let me run the code.",
                "tool_calls": [
                    {
                        "id": "s1",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": json.dumps({"code": "print('hello"}),
                        },
                    }
                ],
            }
        elif self.turn == 2:
            # 第二轮：看到 SyntaxError 后修正代码
            return {
                "content": "I see the syntax error, let me fix it.",
                "tool_calls": [
                    {
                        "id": "s2",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": json.dumps({"code": "print('hello')"}),
                        },
                    }
                ],
            }
        else:
            # 第三轮：交付最终结果
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "s3",
                        "type": "function",
                        "function": {
                            "name": "finish",
                            "arguments": json.dumps({"result": "Syntax fixed"}),
                        },
                    }
                ],
            }


class NameErrorRecoveryClient(BaseLLMClient):
    """模拟 LLM 遇到 NameError 后先检查环境、再修正执行的行为。"""

    def __init__(self, planner: TaskPlan | None = None) -> None:
        self.turn = 0
        self.planner = planner

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any,
    ) -> dict[str, Any]:
        self.turn += 1

        # 错误发生后、环境探查前，验证 Planner 步骤保持 ACTIVE
        if self.turn == 2 and self.planner and self.planner.current_step:
            assert self.planner.current_step.status == StepStatus.ACTIVE

        if self.turn == 1:
            # 第一轮：引用未定义变量，触发 NameError
            return {
                "content": "Let me use the data.",
                "tool_calls": [
                    {
                        "id": "n1",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": json.dumps({"code": "print(data)"}),
                        },
                    }
                ],
            }
        elif self.turn == 2:
            # 第二轮：先读取环境文件确认上下文
            return {
                "content": "Let me check what data is available.",
                "tool_calls": [
                    {
                        "id": "n2",
                        "type": "function",
                        "function": {
                            "name": "file_read",
                            "arguments": json.dumps({"path": "/tmp/data.txt"}),
                        },
                    }
                ],
            }
        elif self.turn == 3:
            # 第三轮：根据探查到的环境数据修正后重新执行
            return {
                "content": "Now I know the data, let me run again.",
                "tool_calls": [
                    {
                        "id": "n3",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": json.dumps(
                                {"code": "print(open('/tmp/data.txt').read())"}
                            ),
                        },
                    }
                ],
            }
        else:
            # 第四轮：交付最终结果
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "n4",
                        "type": "function",
                        "function": {
                            "name": "finish",
                            "arguments": json.dumps({"result": "Data: sample data"}),
                        },
                    }
                ],
            }


class TimeoutRecoveryClient(BaseLLMClient):
    """模拟 LLM 遇到 TimeoutError 后简化任务的行为。"""

    def __init__(self, planner: TaskPlan | None = None) -> None:
        self.turn = 0
        self.planner = planner

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any,
    ) -> dict[str, Any]:
        self.turn += 1

        # 错误发生后、降级重试前，验证 Planner 步骤保持 ACTIVE
        if self.turn == 2 and self.planner and self.planner.current_step:
            assert self.planner.current_step.status == StepStatus.ACTIVE

        if self.turn == 1:
            # 第一轮：任务太重，触发超时
            return {
                "content": "Let me process all data.",
                "tool_calls": [
                    {
                        "id": "t1",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": json.dumps(
                                {"code": "[x for x in range(10**9)]"}
                            ),
                        },
                    }
                ],
            }
        elif self.turn == 2:
            # 第二轮：简化任务
            return {
                "content": "The task is too heavy, let me simplify.",
                "tool_calls": [
                    {
                        "id": "t2",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": json.dumps(
                                {"code": "print(sum(range(100)))"}
                            ),
                        },
                    }
                ],
            }
        else:
            # 第三轮：交付最终结果
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "t3",
                        "type": "function",
                        "function": {
                            "name": "finish",
                            "arguments": json.dumps({"result": "Task simplified"}),
                        },
                    }
                ],
            }


class FatalErrorClient(BaseLLMClient):
    """模拟 LLM 遇到 PermissionError 后无法继续的行为。"""

    def __init__(self) -> None:
        self.turn = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any,
    ) -> dict[str, Any]:
        self.turn += 1

        if self.turn == 1:
            # 第一轮：访问敏感文件，触发 PermissionError
            return {
                "content": "Let me access the file.",
                "tool_calls": [
                    {
                        "id": "f1",
                        "type": "function",
                        "function": {
                            "name": "sandbox_exec",
                            "arguments": json.dumps(
                                {"code": "open('/etc/shadow')"}
                            ),
                        },
                    }
                ],
            }
        else:
            # FATAL 错误后，Agent 给最后一轮机会解释
            return {
                "content": "Permission denied, I cannot continue.",
                "tool_calls": None,
            }


# ---------------------------------------------------------------------------
# Phase 4.5 错误恢复场景测试
# ---------------------------------------------------------------------------


class TestErrorRecoveryWorkflow:
    """Phase 4.5 错误恢复场景测试：验证 Agent 面对错误时的恢复能力。"""

    @pytest.mark.asyncio
    async def test_syntax_error_recovery(self) -> None:
        """SyntaxError 是可恢复的，LLM 应修正代码后成功交付。"""
        backend = ErrorInjectionBackend(
            execute_responses=[
                ExecutionResult(
                    exit_code=1,
                    stdout="",
                    stderr="SyntaxError: invalid syntax",
                    success=False,
                ),
                ExecutionResult(
                    exit_code=0,
                    stdout="hello",
                    stderr="",
                    success=True,
                ),
            ]
        )
        plan = TaskPlan(goal="运行代码")
        plan.add_step("execute", "执行代码并修正错误")
        plan.start_next()

        agent = Agent(
            llm_client=SyntaxErrorRecoveryClient(planner=plan),
            planner=plan,
            sandbox_backend=backend,
            max_turns=10,
        )

        response = await agent.run("Run this code")

        # 验证最终成功交付
        assert response == "Syntax fixed"
        # 验证 sandbox_exec 被调用了 2 次（一次失败、一次成功）
        assert backend.execute_count == 2
        # 验证步骤最终完成，且错误期间没有被错误推进或标记失败
        assert plan.steps[0].status == StepStatus.COMPLETED
        # 验证 LLM 在第二轮看到了完整的错误分类信息
        tool_results = [msg for msg in agent.messages if msg.role == "tool"]
        assert len(tool_results) >= 1
        first_error = tool_results[0].content
        assert "[工具执行失败]" in first_error
        assert "严重程度: RECOVERABLE" in first_error
        assert "建议恢复策略: REWRITE_CODE" in first_error
        assert "提示: 代码有 bug，修改后重试即可" in first_error

    @pytest.mark.asyncio
    async def test_name_error_with_context_check(self) -> None:
        """NameError 后 LLM 先检查环境，再修正执行。"""
        backend = ErrorInjectionBackend(
            execute_responses=[
                ExecutionResult(
                    exit_code=1,
                    stdout="",
                    stderr="NameError: name 'data' is not defined",
                    success=False,
                ),
                ExecutionResult(
                    exit_code=0,
                    stdout="loaded",
                    stderr="",
                    success=True,
                ),
            ],
            files={"/tmp/data.txt": b"sample data"},
        )
        plan = TaskPlan(goal="处理数据")
        plan.add_step("process", "处理数据并修正 NameError")
        plan.start_next()

        agent = Agent(
            llm_client=NameErrorRecoveryClient(planner=plan),
            planner=plan,
            sandbox_backend=backend,
            max_turns=10,
        )

        response = await agent.run("处理数据")

        # 验证最终成功，且结果来自环境探查得到的数据
        assert response == "Data: sample data"
        # 验证步骤最终完成，且错误期间没有被错误推进或标记失败
        assert plan.steps[0].status == StepStatus.COMPLETED
        # 验证 LLM 查看了环境文件
        assert "/tmp/data.txt" in backend.files
        # 验证第二次 sandbox_exec 的代码确实使用了探查到的文件
        assert any("/tmp/data.txt" in code for code in backend.execute_codes)
        # 验证 file_read 的结果确实被 LLM 看到
        tool_results = [msg for msg in agent.messages if msg.role == "tool"]
        file_read_result = next(
            msg for msg in tool_results if msg.name == "file_read"
        )
        assert "sample data" in file_read_result.content
        # 验证 NameError 被完整分类为 CHECK_CONTEXT
        name_error_result = next(
            msg for msg in tool_results if "NameError" in msg.content
        )
        assert "[工具执行失败]" in name_error_result.content
        assert "严重程度: RECOVERABLE" in name_error_result.content
        assert "建议恢复策略: CHECK_CONTEXT" in name_error_result.content
        assert "提示: 先检查环境中是否有需要的变量/模块" in name_error_result.content

    @pytest.mark.asyncio
    async def test_timeout_error_degrades_task(self) -> None:
        """TimeoutError 触发降级策略，LLM 简化任务后成功。"""
        backend = ErrorInjectionBackend(
            execute_responses=[
                ExecutionResult(
                    exit_code=1,
                    stdout="",
                    stderr="TimeoutError: execution exceeded 30s",
                    success=False,
                ),
                ExecutionResult(
                    exit_code=0,
                    stdout="4950",
                    stderr="",
                    success=True,
                ),
            ]
        )
        plan = TaskPlan(goal="计算大数据")
        plan.add_step("compute", "计算并降级处理")
        plan.start_next()

        agent = Agent(
            llm_client=TimeoutRecoveryClient(planner=plan),
            planner=plan,
            sandbox_backend=backend,
            max_turns=10,
        )

        response = await agent.run("计算大数据")

        # 验证最终成功
        assert response == "Task simplified"
        # 验证步骤最终完成，且错误期间没有被错误推进或标记失败
        assert plan.steps[0].status == StepStatus.COMPLETED
        # 验证 TimeoutError 被完整分类为 DEGRADE + SIMPLIFY_TASK
        tool_results = [msg for msg in agent.messages if msg.role == "tool"]
        timeout_result = next(
            msg for msg in tool_results if "TimeoutError" in msg.content
        )
        assert "[工具执行失败]" in timeout_result.content
        assert "严重程度: DEGRADE" in timeout_result.content
        assert "建议恢复策略: SIMPLIFY_TASK" in timeout_result.content
        assert "提示: 尝试用更简单、更省资源的方法" in timeout_result.content

    @pytest.mark.asyncio
    async def test_fatal_error_stops_agent(self) -> None:
        """PermissionError 是 FATAL，Agent 应停止并报告。"""
        backend = ErrorInjectionBackend(
            execute_responses=[
                ExecutionResult(
                    exit_code=1,
                    stdout="",
                    stderr=(
                        "PermissionError: [Errno 13] Permission denied: '/etc/shadow'"
                    ),
                    success=False,
                ),
            ]
        )
        plan = TaskPlan(goal="访问系统文件")
        plan.add_step("access", "访问敏感文件")
        plan.start_next()

        agent = Agent(
            llm_client=FatalErrorClient(),
            planner=plan,
            sandbox_backend=backend,
            max_turns=10,
        )

        response = await agent.run("读取系统文件")

        # 验证 Agent 返回了错误报告
        assert (
            "PermissionError" in response
            or "Permission denied" in response
            or "FATAL" in response
            or "无法继续" in response
        )
        # 验证工具结果中包含完整的 FATAL 分类信息
        tool_results = [msg for msg in agent.messages if msg.role == "tool"]
        assert len(tool_results) >= 1
        fatal_result = tool_results[0].content
        assert "[工具执行失败]" in fatal_result
        assert "严重程度: FATAL" in fatal_result
        assert "建议恢复策略: REPORT" in fatal_result
        assert "提示: 这个错误超出 Agent 能力范围，需要报告用户" in fatal_result
        # 验证当前步骤被标记为 FAILED
        assert plan.current_step is not None
        assert plan.current_step.status == StepStatus.FAILED


class DummyLLM(BaseLLMClient):
    """返回固定响应的 LLM 客户端。"""

    def __init__(self, response_text: str = "Hello from LLM") -> None:
        self.response_text = response_text

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        return {"content": self.response_text, "tool_calls": None}


class SingleToolThenTextClient(BaseLLMClient):
    """第一次调 tool，第二次给最终答案。"""

    def __init__(self) -> None:
        self.call_count = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        self.call_count += 1
        if self.call_count == 1:
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "add",
                            "arguments": '{"a": 2, "b": 3}',
                        },
                    }
                ],
            }
        else:
            return {"content": "The answer is 5.", "tool_calls": None}
