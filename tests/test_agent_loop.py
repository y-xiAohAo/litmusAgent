"""Tests for the Agent core engine — main conversation loop."""



import pytest

from agent.core.engine import Agent
from agent.core.types import ToolSpec
from agent.llm.base import BaseLLMClient

# ---------------------------------------------------------------------------

# Mock LLM clients for testing the agent loop

# ---------------------------------------------------------------------------





class DummyLLM(BaseLLMClient):

    """Returns a canned response every time."""



    def __init__(self, response_text: str = "Hello from LLM"):

        self.response_text = response_text



    async def chat(self, messages, tools=None, **kwargs):

        return {"content": self.response_text, "tool_calls": None}





class SingleToolThenTextClient(BaseLLMClient):

    """First call returns a tool_call, second call returns final text."""



    def __init__(self):

        self.call_count = 0



    async def chat(self, messages, tools=None, **kwargs):

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

        else:

            return {"content": "The answer is 5.", "tool_calls": None}





class AlwaysToolClient(BaseLLMClient):

    """Returns a tool_call on every invocation — triggers max_turns limit."""



    async def chat(self, messages, tools=None, **kwargs):

        return {

            "content": None,

            "tool_calls": [

                {

                    "id": "call_loop",

                    "type": "function",

                    "function": {"name": "loop", "arguments": "{}"},

                }

            ],

        }





# ---------------------------------------------------------------------------

# Tests

# ---------------------------------------------------------------------------





class TestAgentBasicLoop:

    """Tests for the fundamental agent conversation loop."""



    @pytest.mark.asyncio

    async def test_single_turn_no_tools(self):

        """Agent should return LLM response when no tools are invoked."""

        agent = Agent(

            llm_client=DummyLLM("Hello from LLM"),

            system_prompt="You are helpful.",

        )

        response = await agent.run("hello")

        assert response == "Hello from LLM"



    @pytest.mark.asyncio

    async def test_builds_message_history(self):

        """Each call to agent.run() should append to conversation history."""

        agent = Agent(llm_client=DummyLLM("ok"))

        await agent.run("msg1")

        assert len(agent.messages) == 2  # user + assistant

        await agent.run("msg2")

        assert len(agent.messages) == 4  # accumulated (user + assistant) × 2



    @pytest.mark.asyncio

    async def test_history_contains_user_and_assistant(self):

        """Messages should alternate user / assistant correctly."""

        agent = Agent(llm_client=DummyLLM("response"))

        await agent.run("hello")

        roles = [m.role for m in agent.messages]

        assert roles == ["user", "assistant"]



    @pytest.mark.asyncio

    async def test_multiple_runs_accumulate(self):

        """Three runs should produce 6 messages (3 user + 3 assistant)."""

        agent = Agent(llm_client=DummyLLM("ok"))

        await agent.run("a")

        await agent.run("b")

        await agent.run("c")

        assert len(agent.messages) == 6

        roles = [m.role for m in agent.messages]

        assert roles == ["user", "assistant", "user", "assistant", "user", "assistant"]



    @pytest.mark.asyncio

    async def test_reset_clears_history(self):

        """reset() should clear all conversation history."""

        agent = Agent(llm_client=DummyLLM("ok"))

        await agent.run("hello")

        assert len(agent.messages) > 0

        agent.reset()

        assert len(agent.messages) == 0



    @pytest.mark.asyncio

    async def test_system_prompt_included(self):

        """The system prompt should be the first message sent to the LLM."""



        class CapturingClient(DummyLLM):

            async def chat(self, messages, tools=None, **kwargs):

                self.captured_messages = messages

                return await super().chat(messages, tools, **kwargs)



        client = CapturingClient("ok")

        agent = Agent(llm_client=client, system_prompt="You are a pirate.")

        await agent.run("hello")

        assert client.captured_messages[0]["role"] == "system"

        assert client.captured_messages[0]["content"] == "You are a pirate."





class TestAgentToolLoop:

    """Tests for the agent loop with tool calls."""



    @pytest.mark.asyncio

    async def test_executes_tool_and_returns_final_answer(self):

        """Agent should execute a tool call and feed result back to LLM."""

        agent = Agent(llm_client=SingleToolThenTextClient())

        agent.tools.register(

            ToolSpec(

                name="add",

                description="Add two numbers",

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

        response = await agent.run("add 2 and 3")

        assert response == "The answer is 5."

        assert len(agent.messages) == 4  # user, assistant+toolcall, tool, assistant



    @pytest.mark.asyncio

    async def test_max_turns_limits_loop(self):

        """Agent should stop with an error message when max_turns is exceeded."""

        agent = Agent(llm_client=AlwaysToolClient(), max_turns=2)

        agent.tools.register(

            ToolSpec(

                name="loop",

                description="loops forever",

                parameters={"type": "object", "properties": {}},

                handler=lambda: "looped",

            )

        )

        response = await agent.run("start")

        assert "已达" in response.lower()



    @pytest.mark.asyncio

    async def test_unknown_tool_returns_error(self):

        """If LLM requests a tool that doesn't exist, agent should report error."""

        agent = Agent(llm_client=SingleToolThenTextClient(), max_turns=1)
        # Don't register any tools — LLM's tool_call will fail
        _ = await agent.run("add 2 and 3")
        # Should still get a response (the error is fed back to LLM as tool result)
        assert len(agent.messages) >= 2  # at least user + assistant

