"""ReflectiveAdvisor 接入 Agent 主循环的集成测试。"""

from __future__ import annotations

from typing import Any

from agent.core.engine import Agent
from agent.core.reflective_advisor import ReflectiveAdvisor
from agent.core.types import ToolSpec
from agent.llm.base import BaseLLMClient


class _AlwaysToolCallClient(BaseLLMClient):
    """总是请求同一个工具的 Mock LLM 客户端。"""

    def __init__(self, tool_name: str = "mock_tool") -> None:
        self.tool_name = tool_name
        self.call_count = 0

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """返回固定的 tool_call 请求。"""
        self.call_count += 1
        return {
            "content": None,
            "tool_calls": [{
                "id": f"call_{self.call_count}",
                "type": "function",
                "function": {
                    "name": self.tool_name,
                    "arguments": "{}",
                },
            }],
        }


def _make_failing_tool(name: str = "mock_tool") -> ToolSpec:
    """创建一个总是抛出 NameError 的工具，用于模拟反复失败。"""

    def _handler() -> str:
        raise NameError("name 'pd' is not defined")

    return ToolSpec(
        name=name,
        description="一个总是以 NameError 失败的测试工具。",
        parameters={"type": "object", "properties": {}},
        handler=_handler,
    )


class TestReflectiveIntegration:
    """验证 ReflectiveAdvisor 在 Agent.run() 中的端到端行为。"""

    async def test_second_name_error_includes_reflection_hint(self) -> None:
        """同一 NameError 出现第 2 次时，错误消息应包含反思提示。"""
        agent = Agent(llm_client=_AlwaysToolCallClient(), max_turns=3)
        agent.tools.register(_make_failing_tool())

        await agent.run("run the tool")

        tool_messages = [msg for msg in agent.messages if msg.role == "tool"]
        assert len(tool_messages) >= 2
        # 第一次失败没有反思提示，第二次应该有
        assert "反思提示" not in tool_messages[0].content
        assert "反思提示" in tool_messages[1].content

    async def test_escalation_to_degrade_changes_message(self) -> None:
        """NameError 第 4 次出现时，严重程度应升级为 DEGRADE。"""
        agent = Agent(llm_client=_AlwaysToolCallClient(), max_turns=5)
        agent.tools.register(_make_failing_tool())

        await agent.run("run the tool")

        tool_messages = [msg for msg in agent.messages if msg.role == "tool"]
        # 第 4 次失败应该升级到 DEGRADE
        assert "严重程度: DEGRADE" in tool_messages[3].content
        assert "建议恢复策略: SIMPLIFY_TASK" in tool_messages[3].content

    async def test_escalation_to_fatal_stops_loop(self) -> None:
        """NameError 第 6 次出现时，应升级为 FATAL 并终止循环。"""
        agent = Agent(llm_client=_AlwaysToolCallClient(), max_turns=20)
        agent.tools.register(_make_failing_tool())

        response = await agent.run("run the tool")

        assert "致命" in response or "无法继续" in response or "无法恢复" in response
        # 验证 ledger 中 count 至少达到了 6
        pattern = agent.error_pattern_ledger.get_pattern("mock_tool", "NameError")
        assert pattern is not None
        assert pattern.count >= 6

    async def test_trace_contains_reflection_event(self) -> None:
        """Trace 中应包含 reflection 事件。"""
        agent = Agent(llm_client=_AlwaysToolCallClient(), max_turns=4)
        agent.tools.register(_make_failing_tool())

        await agent.run("run the tool")

        trace = agent.get_trace()
        reflection_events = [
            event
            for step in trace.steps
            for event in step.events
            if event.event_type == "reflection"
        ]
        assert len(reflection_events) >= 1

    async def test_reset_clears_ledger_by_default(self) -> None:
        """默认情况下，Agent.reset() 应清空错误模式账本。"""
        agent = Agent(llm_client=_AlwaysToolCallClient(), max_turns=2)
        agent.tools.register(_make_failing_tool())

        await agent.run("run the tool")
        agent.reset()

        pattern = agent.error_pattern_ledger.get_pattern("mock_tool", "NameError")
        assert pattern is None

    async def test_persist_error_patterns_keeps_ledger_after_reset(self) -> None:
        """persist_error_patterns=True 时，reset() 应保留错误模式账本。"""
        agent = Agent(
            llm_client=_AlwaysToolCallClient(), max_turns=2,
            persist_error_patterns=True,
        )
        agent.tools.register(_make_failing_tool())

        await agent.run("run the tool")
        agent.reset()

        pattern = agent.error_pattern_ledger.get_pattern("mock_tool", "NameError")
        assert pattern is not None
        assert pattern.count >= 1

    async def test_custom_reflective_advisor_threshold(self) -> None:
        """注入自定义 ReflectiveAdvisor 时，应使用自定义阈值。"""
        advisor = ReflectiveAdvisor(reflection_threshold=3)
        agent = Agent(
            llm_client=_AlwaysToolCallClient(), max_turns=4,
            reflective_advisor=advisor,
        )
        agent.tools.register(_make_failing_tool())

        await agent.run("run the tool")

        tool_messages = [msg for msg in agent.messages if msg.role == "tool"]
        # count=2 时不应触发反思提示，count=3 时才触发
        assert "反思提示" not in tool_messages[0].content
        assert "反思提示" not in tool_messages[1].content
        assert "反思提示" in tool_messages[2].content
