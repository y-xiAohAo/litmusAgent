"""Agent 交互模式 CLI 测试。"""

from __future__ import annotations

import pytest

from agent.cli.chat import run_chat_loop
from agent.core.engine import Agent
from agent.core.types import ToolSpec
from agent.llm import BaseLLMClient, EchoClient


def _has_ansi(text: str) -> bool:
    """检查文本是否包含 ANSI 转义序列。"""
    return "\x1b[" in text


class _ToolCallingMockClient(BaseLLMClient):
    """调用 mock_tool 然后给出最终答案的测试桩。"""

    def __init__(self) -> None:
        self._call_count = 0

    async def chat(
        self,
        messages: list[dict[str, object]],
        tools: list[dict[str, object]] | None = None,
        **kwargs: object,
    ) -> dict[str, object]:
        self._call_count += 1
        if self._call_count == 1:
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "mock_tool",
                            "arguments": "{}",
                        },
                    }
                ],
            }
        return {"content": "Done.", "tool_calls": None}


def test_chat_quit_immediately(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """输入 /quit 应立即退出交互模式。"""
    agent = Agent(llm_client=EchoClient())
    monkeypatch.setattr("agent.cli.chat.Prompt.ask", lambda prompt, default=None: "/quit")

    assert run_chat_loop(agent, plain=True) == 0
    captured = capsys.readouterr()
    assert "退出" in captured.out or "再见" in captured.out or captured.out == ""


def test_chat_one_turn_echo(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一轮 Echo 对话应正常返回结果。"""
    agent = Agent(llm_client=EchoClient())
    inputs = ["hello", "/quit"]
    monkeypatch.setattr("agent.cli.chat.Prompt.ask", lambda prompt, default=None: inputs.pop(0))

    assert run_chat_loop(agent, plain=True) == 0
    captured = capsys.readouterr()
    assert "You said: hello" in captured.out


def test_chat_help_command(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """/help 应显示帮助并继续循环。"""
    agent = Agent(llm_client=EchoClient())
    inputs = ["/help", "/quit"]
    monkeypatch.setattr("agent.cli.chat.Prompt.ask", lambda prompt, default=None: inputs.pop(0))

    assert run_chat_loop(agent, plain=True) == 0
    captured = capsys.readouterr()
    assert "/quit" in captured.out
    assert "/help" in captured.out


def test_chat_multi_turn_accumulates_history(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """多轮对话应累积 message history。"""
    agent = Agent(llm_client=EchoClient())
    inputs = ["first", "second", "/quit"]
    monkeypatch.setattr("agent.cli.chat.Prompt.ask", lambda prompt, default=None: inputs.pop(0))

    assert run_chat_loop(agent, plain=True) == 0
    captured = capsys.readouterr()
    assert "You said: first" in captured.out
    assert "You said: second" in captured.out
    assert len(agent.messages) >= 4  # user1, assistant1, user2, assistant2


def test_chat_tool_summary_plain(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """工具调用后应显示工具摘要（plain 模式）。"""
    agent = Agent(llm_client=_ToolCallingMockClient())
    agent.tools.register(
        ToolSpec(
            name="mock_tool",
            description="Mock tool for testing",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            handler=lambda: "mock result",
        )
    )
    inputs = ["call tool", "/quit"]
    monkeypatch.setattr("agent.cli.chat.Prompt.ask", lambda prompt, default=None: inputs.pop(0))

    assert run_chat_loop(agent, plain=True) == 0
    captured = capsys.readouterr()
    assert "mock_tool" in captured.out
    assert "Done." in captured.out
    assert not _has_ansi(captured.out)


def test_chat_plain_no_ansi(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """plain=True 时整个 chat 输出应无 ANSI 转义序列。"""
    agent = Agent(llm_client=EchoClient())
    inputs = ["hello", "/quit"]
    monkeypatch.setattr("agent.cli.chat.Prompt.ask", lambda prompt, default=None: inputs.pop(0))

    assert run_chat_loop(agent, plain=True) == 0
    captured = capsys.readouterr()
    assert not _has_ansi(captured.out)
    assert not _has_ansi(captured.err)


def test_chat_rich_output(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rich 模式下应输出带标题的面板。"""
    agent = Agent(llm_client=EchoClient())
    inputs = ["hello", "/quit"]
    monkeypatch.setattr("agent.cli.chat.Prompt.ask", lambda prompt, default=None: inputs.pop(0))

    assert run_chat_loop(agent, plain=False) == 0
    captured = capsys.readouterr()
    assert "Agent 结果" in captured.out
    assert "You said: hello" in captured.out


class TestChatLoopEventLoopReuse:
    """EVAL-013：对话循环复用同一事件循环（多轮不报 Event loop is closed）。"""

    def test_multi_turn_uses_same_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """连续两轮 run 应在同一个事件循环上执行。"""
        import asyncio

        from agent.cli import chat as chat_module
        from agent.core.engine import Agent
        from agent.llm.base import BaseLLMClient

        loops: list[int] = []

        class LoopRecordingClient(BaseLLMClient):
            async def chat(self, messages, tools=None, **kwargs):  # noqa: ANN001, ANN202
                loops.append(id(asyncio.get_running_loop()))
                return {"content": "ok", "tool_calls": None}

        inputs = iter(["第一轮", "第二轮"])
        monkeypatch.setattr(chat_module, "_read_user_input",
                            lambda plain=False: next(inputs, None))
        agent = Agent(llm_client=LoopRecordingClient())
        try:
            chat_module.run_chat_loop(agent, plain=True)
            assert len(loops) == 2
            assert loops[0] == loops[1]  # 两轮同一事件循环
        finally:
            agent._sandbox_backend.close()
