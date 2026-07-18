"""Tests for the agent core engine and types."""

import pytest

from agent.core.engine import Agent, ToolRegistry
from agent.core.types import Message, ToolCall, ToolSpec
from agent.llm import EchoClient


class TestTypes:
    def test_message_creation(self):
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"

    def test_tool_spec_openai_format(self):
        def dummy_fn():
            pass

        spec = ToolSpec(
            name="test",
            description="A test tool",
            parameters={"type": "object", "properties": {}},
            handler=dummy_fn,
        )
        fmt = spec.to_openai_format()
        assert fmt["function"]["name"] == "test"
        assert fmt["type"] == "function"


class TestToolRegistry:
    def test_register_and_list(self):
        reg = ToolRegistry()

        @reg.register_func(
            name="echo",
            description="Echo input",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
        def echo(text: str) -> str:
            return text

        assert reg.get("echo") is not None
        schemas = reg.list_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "echo"

    def test_duplicate_raises(self):
        reg = ToolRegistry()
        reg.register(
            ToolSpec(name="dup", description="", parameters={}, handler=lambda: None)
        )
        with pytest.raises(ValueError, match="已注册"):
            reg.register(
                ToolSpec(name="dup", description="", parameters={}, handler=lambda: None)
            )

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        reg = ToolRegistry()
        result = await reg.execute(ToolCall(id="1", name="nope", arguments={}))
        assert not result.success

    @pytest.mark.asyncio
    async def test_execute_success(self):
        reg = ToolRegistry()
        reg.register(
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
        result = await reg.execute(
            ToolCall(id="1", name="add", arguments={"a": 2, "b": 3})
        )
        assert result.success
        assert result.content == "5"


class TestAgent:
    @pytest.mark.asyncio
    async def test_echo_agent(self):
        client = EchoClient()
        agent = Agent(llm_client=client, system_prompt="You are a test assistant.")
        response = await agent.run("hello")
        assert "You said: hello" in response

    @pytest.mark.asyncio
    async def test_max_turns(self):
        """Agent should stop when max_turns is reached."""
        from agent.llm import BaseLLMClient

        class LoopingClient(BaseLLMClient):
            """Returns a tool_call every time, causing infinite loop."""
            async def chat(self, messages, tools=None, **kwargs):
                return {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "loop", "arguments": "{}"},
                    }],
                }

        agent = Agent(llm_client=LoopingClient(), max_turns=1)

        @agent.tools.register_func(
            name="loop",
            description="keeps looping",
            parameters={"type": "object", "properties": {}},
        )
        def loop():
            return "done"

        response = await agent.run("start")
        assert "已达" in response
