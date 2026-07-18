"""交互模式（chat）实现。

提供 `agent chat` 的交互式多轮对话循环。
"""

from __future__ import annotations

import asyncio
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from agent.cli.render import render_error, render_result, render_tool_summary
from agent.core.engine import Agent, ApprovalCallback
from agent.core.types import ToolCall


def make_cli_approval_callback(tools: set[str], plain: bool = False) -> ApprovalCallback:
    """构造 CLI 交互确认 callback（TD-008）。

    语义：
      - `y`：允许本次执行；
      - `n`：拒绝（工具返回失败，Agent 会看到“用户拒绝”提示）；
      - `a`：允许且本会话内该工具免确认（闭包记录，不泄露给其他工具）。

    参数：
        tools: 需要确认的工具名集合（用于展示与文档一致性）。
        plain: True 时使用内置 input()，False 时使用 Rich Prompt。
    """
    approved_always: set[str] = set()

    def callback(tool_name: str, arguments: dict[str, Any]) -> bool:
        """确认入口：返回 True 表示批准执行。"""
        if tool_name in approved_always:
            return True
        summary = ", ".join(f"{k}={str(v)[:60]}" for k, v in arguments.items())
        question = f"Agent 请求执行 {tool_name}（{summary}），是否允许？"
        if plain:
            answer = input(f"{question} [y/n/a] ").strip().lower()
        else:
            answer = Prompt.ask(
                f"[yellow]{question}[/yellow]",
                choices=["y", "n", "a"],
                default="n",
            )
        if answer == "a":
            approved_always.add(tool_name)
            return True
        return answer == "y"

    return callback


def _render_info(message: str, plain: bool = False) -> None:
    """渲染提示信息。

    Args:
        message: 提示文本。
        plain: 是否禁用 Rich 样式。
    """
    if plain:
        print(message)
        return
    console = Console()
    console.print(f"[dim]{message}[/dim]")


def _render_greeting(plain: bool = False) -> None:
    """渲染进入交互模式时的欢迎信息。"""
    greeting = "进入 Hermes Agent 交互模式。输入 /help 查看命令，输入 /quit 退出。"
    _render_info(greeting, plain=plain)


def _render_farewell(plain: bool = False) -> None:
    """渲染退出交互模式时的告别信息。"""
    farewell = "再见。"
    _render_info(farewell, plain=plain)


def _render_help(plain: bool = False) -> None:
    """渲染帮助信息。"""
    lines = [
        "可用命令：",
        "  /help    显示本帮助",
        "  /quit    退出交互模式",
        "  /exit    同 /quit",
        "  /clear   清屏",
    ]
    if plain:
        print("\n".join(lines))
        return
    panel = Panel("\n".join(lines), title="帮助", border_style="blue")
    console = Console()
    console.print(panel)


def _clear_screen() -> None:
    """清屏。"""
    print("\033[2J\033[H", end="")


def _extract_tool_summary(agent: Agent, before_count: int) -> list[str]:
    """从 agent.messages 中提取本轮新增的工具调用名称。

    Args:
        agent: 当前 Agent 实例。
        before_count: 本轮运行前的 messages 数量。

    Returns:
        去重后的工具调用名称列表。
    """
    names: list[str] = []
    for msg in agent.messages[before_count:]:
        if msg.role == "assistant" and msg.tool_calls:
            for call in msg.tool_calls:
                if isinstance(call, ToolCall) and call.name not in names:
                    names.append(call.name)
    return names


def _handle_command(command: str, plain: bool = False) -> bool:
    """处理特殊命令。

    Args:
        command: 用户输入的命令（以 / 开头）。
        plain: 是否禁用 Rich 样式。

    Returns:
        True 表示继续循环，False 表示退出。
    """
    cmd = command.strip().lower()
    if cmd in ("/quit", "/exit"):
        _render_farewell(plain=plain)
        return False
    if cmd == "/help":
        _render_help(plain=plain)
        return True
    if cmd == "/clear":
        _clear_screen()
        return True

    _render_info(f"未知命令：{command}，输入 /help 查看可用命令。", plain=plain)
    return True


def _read_user_input(plain: bool = False) -> str | None:
    """读取用户输入。

    Args:
        plain: 是否禁用 Rich 样式。

    Returns:
        用户输入字符串；用户请求退出（Ctrl+C / EOF）时返回 None。
    """
    try:
        return Prompt.ask("You")
    except (KeyboardInterrupt, EOFError):
        _render_farewell(plain=plain)
        return None


def run_chat_loop(agent: Agent, plain: bool = False) -> int:
    """运行交互式对话循环。

    Args:
        agent: 已构造好的 Agent 实例。
        plain: 是否禁用 Rich 样式。

    Returns:
        退出码：0 正常退出。
    """
    _render_greeting(plain=plain)

    # EVAL-013：整个对话循环复用同一个事件循环。
    # 若每轮 asyncio.run()，循环会被反复创建并关闭，
    # 绑定在首个循环上的资源（如 httpx.AsyncClient）在第二轮会报
    # "Event loop is closed"。
    loop = asyncio.new_event_loop()
    try:
        while True:
            user_input = _read_user_input(plain=plain)
            if user_input is None:
                return 0

            user_input = user_input.strip()
            if not user_input:
                continue

            if user_input.startswith("/"):
                if not _handle_command(user_input, plain=plain):
                    return 0
                continue

            before_count = len(agent.messages)
            try:
                result = loop.run_until_complete(agent.run(user_input))
            except KeyboardInterrupt:
                _render_info("当前运行已中止。", plain=plain)
                continue
            except Exception as exc:  # noqa: BLE001
                render_error(f"Agent 运行出错：{exc}", plain=plain)
                continue

            tool_names = _extract_tool_summary(agent, before_count)
            if tool_names:
                render_tool_summary(tool_names, plain=plain)
            render_result(result, plain=plain)
    finally:
        loop.close()

    return 0
