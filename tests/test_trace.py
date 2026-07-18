"""Agent Trace 测试。

验证 Agent 主循环在关键节点能正确记录执行轨迹，
以及 AgentState 能随执行过程正确更新。
"""

import json
from typing import Any

import pytest

from agent.core.engine import Agent
from agent.core.planner import TaskPlan
from agent.core.types import ToolSpec
from agent.llm.base import BaseLLMClient


class _SingleToolThenTextClient(BaseLLMClient):
    """第一次调用请求 tool，第二次调用返回文本。"""

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
                        "function": {"name": "add", "arguments": '{"a": 2, "b": 3}'},
                    }
                ],
            }
        return {"content": "结果是 5", "tool_calls": None}


class _ToolThenFinishClient(BaseLLMClient):
    """第一次调用普通 tool，第二次调用 finish tool。"""

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
                        "function": {"name": "greet", "arguments": '{"name": "msn"}'},
                    }
                ],
            }
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "finish", "arguments": '{"result": "done"}'},
                }
            ],
        }


class _ErrorRetryClient(BaseLLMClient):
    """第一次调用触发错误，第二次调用返回 finish。"""

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
                        "function": {"name": "fail_once", "arguments": '{}'},
                    }
                ],
            }
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {"name": "finish", "arguments": '{"result": "recovered"}'},
                }
            ],
        }


class _AlwaysToolClient(BaseLLMClient):
    """每次都返回 tool_call，用于触发 max_turns。"""

    def __init__(self) -> None:
        self.call_count = 0

    async def chat(
        self, messages: list[dict[str, Any]], tools: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        self.call_count += 1
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{self.call_count}",
                    "type": "function",
                    "function": {"name": "noop", "arguments": '{}'},
                }
            ],
        }


@pytest.mark.asyncio
async def test_trace_records_simple_conversation() -> None:
    """无 tool call 的简单对话应生成包含基本事件的 Trace。"""
    from agent.llm import EchoClient

    agent = Agent(llm_client=EchoClient())
    await agent.run("hello")

    trace = agent.get_trace()
    assert trace is not None
    assert len(trace.steps) == 1

    step = trace.steps[0]
    assert step.step_index == 0
    event_types = [event.event_type for event in step.events]
    assert "llm_request" in event_types
    assert "llm_response" in event_types
    assert "state_transition" in event_types


@pytest.mark.asyncio
async def test_trace_records_tool_execution() -> None:
    """调用 tool 时，Trace 应包含 tool_execution 事件。"""
    agent = Agent(llm_client=_SingleToolThenTextClient())
    agent.tools.register(
        ToolSpec(
            name="add",
            description="Add two numbers",
            parameters={
                "type": "object",
                "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                "required": ["a", "b"],
            },
            handler=lambda a, b: a + b,
        )
    )

    await agent.run("add 2 and 3")

    trace = agent.get_trace()
    assert len(trace.steps) == 2

    step0 = trace.steps[0]
    tool_events = [e for e in step0.events if e.event_type == "tool_execution"]
    assert len(tool_events) == 1
    assert tool_events[0].payload["tool"] == "add"
    assert tool_events[0].payload["success"] is True


@pytest.mark.asyncio
async def test_trace_records_error_classification() -> None:
    """Tool 失败时，Trace 应包含 error_classification 事件。"""
    agent = Agent(llm_client=_ErrorRetryClient())

    def fail_once() -> str:
        raise NameError("name 'x' is not defined")

    agent.tools.register(
        ToolSpec(
            name="fail_once",
            description="Fail once",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=fail_once,
        )
    )
    await agent.run("test error")

    trace = agent.get_trace()
    # 第一轮：调用 fail_once（失败）
    step0 = trace.steps[0]
    error_events = [e for e in step0.events if e.event_type == "error_classification"]
    assert len(error_events) == 1
    assert error_events[0].payload["severity"] == "RECOVERABLE"
    assert error_events[0].payload["action"] == "CHECK_CONTEXT"


@pytest.mark.asyncio
async def test_trace_records_multi_turn_conversation() -> None:
    """多轮对话应生成多个 TraceStep。"""
    agent = Agent(llm_client=_ToolThenFinishClient())

    agent.tools.register(
        ToolSpec(
            name="greet",
            description="Greet someone",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            handler=lambda name: f"Hello {name}",
        )
    )
    await agent.run("greet and finish")

    trace = agent.get_trace()
    assert len(trace.steps) == 2
    assert trace.steps[0].step_index == 0
    assert trace.steps[1].step_index == 1

    # 第二轮调用了 finish
    step1 = trace.steps[1]
    tool_events = [e for e in step1.events if e.event_type == "tool_execution"]
    assert len(tool_events) == 1
    assert tool_events[0].payload["tool"] == "finish"


@pytest.mark.asyncio
async def test_state_updates_during_run() -> None:
    """AgentState 应随运行过程从 running 变为 finished。"""
    from agent.llm import EchoClient

    agent = Agent(llm_client=EchoClient())
    assert agent.state.phase is None

    await agent.run("hello")

    assert agent.state.phase == "finished"
    assert agent.trace.final_state is not None
    assert agent.trace.final_state["phase"] == "finished"


@pytest.mark.asyncio
async def test_trace_records_max_turns_failure() -> None:
    """达到 max_turns 时，phase 应变为 failed 并被记录。"""
    agent = Agent(llm_client=_AlwaysToolClient(), max_turns=2)
    agent.tools.register(
        ToolSpec(
            name="noop",
            description="Noop",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=lambda: "ok",
        )
    )

    await agent.run("loop")

    assert agent.state.phase == "failed"
    assert agent.trace.final_state is not None
    assert agent.trace.final_state["phase"] == "failed"
    assert len(agent.trace.steps) == 2


# ---------------------------------------------------------------------------
# 端到端 Trace 测试
# ---------------------------------------------------------------------------


class _PlannerWorkflowClient(BaseLLMClient):
    """模拟带 Planner 的完整工作流：执行两步，最后 finish。"""

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
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "step_action", "arguments": '{"step": 1}'},
                    }
                ],
            }
        if self.call_count == 2:
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {"name": "step_action", "arguments": '{"step": 2}'},
                    }
                ],
            }
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": "c3",
                    "type": "function",
                    "function": {"name": "finish", "arguments": '{"result": "all done"}'},
                }
            ],
        }


class _MultiToolWorkflowClient(BaseLLMClient):
    """模拟真实数据分析工作流：file_list → file_read → finish。"""

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
                        "id": "c1",
                        "type": "function",
                        "function": {"name": "file_list", "arguments": '{"path": "/"}'},
                    }
                ],
            }
        if self.call_count == 2:
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "c2",
                        "type": "function",
                        "function": {"name": "file_read", "arguments": '{"path": "/data.txt"}'},
                    }
                ],
            }
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": "c3",
                    "type": "function",
                    "function": {"name": "finish", "arguments": '{"result": "data analyzed"}'},
                }
            ],
        }


@pytest.mark.asyncio
async def test_trace_end_to_end_with_planner() -> None:
    """带 Planner 的端到端工作流应正确记录 planner_transition 和 state 更新。"""
    plan = TaskPlan(goal="完成两步任务")
    plan.add_step("step1", "执行第一步")
    plan.add_step("step2", "执行第二步")
    plan.start_next()  # step1 -> ACTIVE

    agent = Agent(llm_client=_PlannerWorkflowClient(), planner=plan)

    def step_action(step: int) -> str:
        return f"step {step} done"

    agent.tools.register(
        ToolSpec(
            name="step_action",
            description="Execute a step",
            parameters={
                "type": "object",
                "properties": {"step": {"type": "integer"}},
                "required": ["step"],
            },
            handler=step_action,
        )
    )

    await agent.run("execute plan")

    # 验证 Planner 最终完成
    assert plan.is_complete()

    # 验证 Trace 包含 planner_transition 事件
    planner_events = []
    for step in agent.trace.steps:
        for event in step.events:
            if event.event_type == "planner_transition":
                planner_events.append(event.payload)

    assert len(planner_events) == 2
    assert planner_events[0]["from"] == "step1"
    assert planner_events[0]["to"] == "step2"
    assert planner_events[1]["from"] == "step2"
    assert planner_events[1]["to"] is None

    # 验证 State 的 current_step 被更新
    state_events = [
        event
        for step in agent.trace.steps
        for event in step.events
        if event.event_type == "state_transition"
    ]
    current_steps = [e.payload["current_step"] for e in state_events]
    assert "step1" in current_steps
    assert "step2" in current_steps


@pytest.mark.asyncio
async def test_trace_end_to_end_error_recovery() -> None:
    """错误恢复端到端工作流应记录 error_classification 并最终成功。"""
    agent = Agent(llm_client=_ErrorRetryClient())

    attempts = {"count": 0}

    def fail_once() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise NameError("name 'x' is not defined")
        return "fixed"

    agent.tools.register(
        ToolSpec(
            name="fail_once",
            description="Fail once",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=fail_once,
        )
    )

    result = await agent.run("test recovery")
    assert result == "recovered"
    assert agent.state.phase == "finished"

    # 验证第一轮有 error_classification，第二轮没有
    step0 = agent.trace.steps[0]
    step1 = agent.trace.steps[1]
    assert any(e.event_type == "error_classification" for e in step0.events)
    assert not any(e.event_type == "error_classification" for e in step1.events)

    # 验证最终状态
    assert agent.trace.final_state is not None
    assert agent.trace.final_state["phase"] == "finished"


@pytest.mark.asyncio
async def test_trace_end_to_end_multi_tool_workflow() -> None:
    """多 Tool 数据分析工作流应记录每个 Tool 的执行。"""
    agent = Agent(llm_client=_MultiToolWorkflowClient())

    # file_list / file_read / finish 都是默认工具，无需重复注册
    result = await agent.run("analyze data")
    assert result == "data analyzed"

    tool_events = [
        event
        for step in agent.trace.steps
        for event in step.events
        if event.event_type == "tool_execution"
    ]
    tool_names = [e.payload["tool"] for e in tool_events]
    assert tool_names == ["file_list", "file_read", "finish"]


@pytest.mark.asyncio
async def test_trace_to_json_round_trip() -> None:
    """Trace 应能通过 to_json() 序列化并保持结构完整。"""
    from agent.llm import EchoClient

    agent = Agent(llm_client=EchoClient())
    await agent.run("hello")

    trace = agent.get_trace()
    json_str = trace.to_json()
    data = json.loads(json_str)

    assert "start_time" in data
    assert "end_time" in data
    assert "final_state" in data
    assert len(data["steps"]) == 1

    step = data["steps"][0]
    assert step["step_index"] == 0
    event_types = {e["event_type"] for e in step["events"]}
    assert "llm_request" in event_types
    assert "llm_response" in event_types
    assert "state_transition" in event_types

    # 验证 final_state 内容
    assert data["final_state"]["phase"] == "finished"


@pytest.mark.asyncio
async def test_trace_state_artifacts_recorded() -> None:
    """AgentState 中的产物应被记录到 final_state 中。"""
    agent = Agent(llm_client=_SingleToolThenTextClient())

    def add_and_record(a: int, b: int) -> int:
        result = a + b
        agent.state.add_artifact("sum_result", {"value": result})
        return result

    agent.tools.register(
        ToolSpec(
            name="add",
            description="Add and record",
            parameters={
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            },
            handler=add_and_record,
        )
    )

    await agent.run("add 2 and 3")

    assert agent.trace.final_state is not None
    assert agent.trace.final_state["artifacts"]["sum_result"]["value"] == 5
