"""交互模式（chat）实现。

提供 `agent chat` 的交互式多轮对话循环。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from agent.cli.render import render_error, render_result, render_tool_summary
from agent.cli.workspace_session import ConfirmCallback, WorkspaceSession
from agent.core.engine import Agent, ApprovalCallback
from agent.core.types import ToolCall
from agent.llm.base import StreamEvents

logger = logging.getLogger(__name__)


class CliStreamRenderer:
    """CLI 流式渲染器（TD-020）：把 StreamEvents 映射到终端输出。

    plain 模式：
      - on_token → ``print(text, end="", flush=True)`` 直出；
      - on_reasoning → 首片前打 ``[thinking]`` 前缀后同样直出；
      - on_tool_start / on_tool_end → ``→ name args`` 与 ``[OK]/[FAIL] name``
        进度行（plain 用 ASCII 标记，兼容 Windows GBK 终端）；

    rich 模式：
      - content 用 Rich ``Live`` 增量渲染 Markdown；
      - 思考链灰色弱化直出（终端滚动回显无法真正折叠，属 Spec §3.3
        "折叠"口径的已知简化）；
      - 工具进度行同上格式，着色区分成功/失败。

    ``finish()`` 在一轮 ``agent.run()`` 结束后调用：收尾 Live、补换行。
    调用方在流式模式下应跳过 ``render_result``（内容已逐字展示）。
    """

    def __init__(self, plain: bool = False) -> None:
        """初始化渲染器。

        参数：
          plain: True 时纯文本直出（适合脚本管道 / 测试断言）。
        """
        self._plain = plain
        self._console = None if plain else Console()
        self._buffer: list[str] = []
        self._live: Live | None = None
        self._reasoning_started = False
        self.events = StreamEvents(
            on_token=self._on_token,
            on_reasoning=self._on_reasoning,
            on_tool_start=self._on_tool_start,
            on_tool_end=self._on_tool_end,
        )

    def _stop_live(self) -> None:
        """停止当前 Live 渲染（内容分片继续时会自动重建）。"""
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _on_token(self, text: str) -> None:
        """content 分片回调：plain 直出，rich 走 Live 增量 Markdown。"""
        if self._plain or self._console is None:
            print(text, end="", flush=True)
            return
        self._buffer.append(text)
        if self._live is None:
            self._live = Live(
                Markdown("".join(self._buffer)),
                console=self._console,
                refresh_per_second=12,
            )
            self._live.start()
        else:
            self._live.update(Markdown("".join(self._buffer)))

    def _on_reasoning(self, text: str) -> None:
        """reasoning_content 分片回调：plain 带 [thinking] 前缀，rich 灰色。"""
        if self._plain or self._console is None:
            if not self._reasoning_started:
                print("\n[thinking] ", end="", flush=True)
                self._reasoning_started = True
            print(text, end="", flush=True)
            return
        self._stop_live()
        if not self._reasoning_started:
            self._console.print("[dim]── 思考链 ──[/dim]")
            self._reasoning_started = True
        self._console.print(f"[dim]{text}[/dim]", end="", highlight=False)

    def _on_tool_start(self, name: str, args_summary: str) -> None:
        """工具执行前回调：打印进度行。

        同时清空 content buffer（TD-020 评审 O1）：工具调用意味着新一轮
        LLM 输出即将开始，上一轮已渲染的 Markdown 不应再混入 Live 增量
        渲染，否则第二轮会把上一轮全文重复渲染一遍。
        """
        line = f"→ {name} {args_summary}"
        if self._plain or self._console is None:
            print(f"\n{line}", flush=True)
            return
        self._stop_live()
        self._buffer.clear()
        self._console.print(f"[cyan]{line}[/cyan]")

    def _on_tool_end(self, name: str, ok: bool) -> None:
        """工具执行后回调：[OK] 成功 / [FAIL] 失败（plain 用 ASCII，兼容
        Windows GBK 终端，TD-020 评审 Y4；rich 模式保留 ✓/✗ 着色）。"""
        if self._plain or self._console is None:
            mark = "[OK]" if ok else "[FAIL]"
            print(f"{mark} {name}", flush=True)
            return
        mark = "✓" if ok else "✗"
        style = "green" if ok else "red"
        self._console.print(f"[{style}]{mark} {name}[/{style}]")

    def finish(self) -> None:
        """一轮 run() 结束后的收尾：停 Live、补换行、重置分轮状态。"""
        self._stop_live()
        print(flush=True)
        self._buffer.clear()
        self._reasoning_started = False


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
    greeting = "进入 Litmus Agent 交互模式。输入 /help 查看命令，输入 /quit 退出。"
    _render_info(greeting, plain=plain)


def _render_farewell(plain: bool = False) -> None:
    """渲染退出交互模式时的告别信息。"""
    farewell = "再见。"
    _render_info(farewell, plain=plain)


def _render_help(plain: bool = False, bind_mode: bool = False) -> None:
    """渲染帮助信息。"""
    lines = [
        "可用命令：",
        "  /help    显示本帮助",
        "  /quit    退出交互模式",
        "  /exit    同 /quit",
        "  /clear   清屏",
        "  /diff    查看自最近任务快照以来的改动（仅 bind 工作区模式）",
        "  /undo    回滚到最近任务快照（仅 bind 工作区模式）",
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


def _make_confirm_callback(plain: bool = False) -> ConfirmCallback:
    """构造 /undo 的交互式 y/n 确认回调（plain 用 input，否则 Rich Prompt）。

    fail-closed（评审 O2）：EOFError / KeyboardInterrupt / 任何异常一律
    视为拒绝（返回 False），绝不向上抛——确认通道出问题时宁可不动。
    """

    def confirm(question: str) -> bool:
        """确认入口：返回 True 表示用户确认；异常/中断一律拒绝。"""
        try:
            if plain:
                return input(f"{question} [y/n] ").strip().lower() == "y"
            answer = Prompt.ask(
                f"[yellow]{question}[/yellow]", choices=["y", "n"], default="n"
            )
            return answer == "y"
        except (EOFError, KeyboardInterrupt):
            return False
        except Exception:  # noqa: BLE001
            logger.warning("/undo 确认交互异常，按拒绝处理", exc_info=True)
            return False

    return confirm


def _handle_command(
    command: str,
    plain: bool = False,
    workspace_session: WorkspaceSession | None = None,
    bind_mode: bool = False,
) -> bool:
    """处理特殊命令。

    Args:
        command: 用户输入的命令（以 / 开头）。
        plain: 是否禁用 Rich 样式。
        workspace_session: TD-021 bind 模式会话工作台；非 bind 为 None。
        bind_mode: 是否 bind 工作区模式（仅用于帮助/提示文案）。

    Returns:
        True 表示继续循环，False 表示退出。
    """
    cmd = command.strip().lower()
    if cmd in ("/quit", "/exit"):
        _render_farewell(plain=plain)
        return False
    if cmd == "/help":
        _render_help(plain=plain, bind_mode=bind_mode)
        return True
    if cmd == "/clear":
        _clear_screen()
        return True
    if cmd in ("/diff", "/undo"):
        if workspace_session is None:
            _render_info(
                f"{cmd} 仅 bind 工作区模式（sandbox.host_dir）可用。",
                plain=plain,
            )
            return True
        if cmd == "/diff":
            _render_info(workspace_session.diff_report(), plain=plain)
            return True
        result = workspace_session.undo(confirm=_make_confirm_callback(plain=plain))
        _render_info(result, plain=plain)
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


def run_chat_loop(
    agent: Agent,
    plain: bool = False,
    stream_renderer: CliStreamRenderer | None = None,
    workspace_session: WorkspaceSession | None = None,
) -> int:
    """运行交互式对话循环。

    Args:
        agent: 已构造好的 Agent 实例。
        plain: 是否禁用 Rich 样式。
        stream_renderer: TD-020 流式渲染器；传入时每轮回复已逐字展示，
            循环内跳过 render_result / render_tool_summary，仅做收尾。
        workspace_session: TD-021 bind 模式会话工作台；传入时注册
            /diff、/undo 命令，并在每次任务前补快照、任务后差集出
            Agent 新建文件清单。

    Returns:
        退出码：0 正常退出。
    """
    _render_greeting(plain=plain)
    if workspace_session is not None:
        _render_info("bind 工作区：可用 /diff 查看改动、/undo 回滚最近任务。", plain=plain)

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
                if not _handle_command(
                    user_input,
                    plain=plain,
                    workspace_session=workspace_session,
                    bind_mode=workspace_session is not None,
                ):
                    return 0
                continue

            # TD-021（裁决 Q3）：bind 模式每次任务前补快照。
            if workspace_session is not None:
                try:
                    workspace_session.begin_task()
                except ValueError as exc:
                    render_error(f"任务前快照失败：{exc}", plain=plain)
                    continue

            before_count = len(agent.messages)
            try:
                result = loop.run_until_complete(agent.run(user_input))
            except KeyboardInterrupt:
                if stream_renderer is not None:
                    stream_renderer.finish()
                _render_info("当前运行已中止。", plain=plain)
                continue
            except Exception as exc:  # noqa: BLE001
                if stream_renderer is not None:
                    stream_renderer.finish()
                render_error(f"Agent 运行出错：{exc}", plain=plain)
                continue
            finally:
                # TD-021：任务结束（含异常）差集出 Agent 新建文件清单。
                if workspace_session is not None:
                    try:
                        workspace_session.end_task()
                    except ValueError as exc:
                        logger.warning("任务后 untracked 差集失败：%s", exc)

            tool_names = _extract_tool_summary(agent, before_count)
            if stream_renderer is not None:
                # TD-020：回复与工具进度已逐字渲染，只做收尾，不重复输出。
                stream_renderer.finish()
                continue
            if tool_names:
                render_tool_summary(tool_names, plain=plain)
            render_result(result, plain=plain)
    finally:
        loop.close()
        # TD-021（评审 O3）：会话退出时清理 /diff 外迁的临时文件。
        if workspace_session is not None:
            workspace_session.cleanup()
        # TD-015：交互模式退出时收口沙箱 backend，避免孤儿卷泄漏。
        agent.close()

    return 0
