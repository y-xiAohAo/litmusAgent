"""CLI 输出渲染模块。

封装 Rich 样式与纯文本输出，使 `agent_cli.py` 不直接依赖 Rich API，
便于后续更换主题或输出后端。
"""

from __future__ import annotations

import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from agent.config import AgentConfig


def _mask_api_key(api_key: str) -> str:
    """对 API key 做脱敏显示。"""
    if not api_key:
        return "未设置"
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:4]}...{api_key[-4:]}"


def render_config(config: AgentConfig, plain: bool = False) -> None:
    """渲染配置摘要。

    Args:
        config: 当前配置。
        plain: 是否禁用 Rich 样式，输出纯文本。
    """
    if plain:
        lines = [
            "当前配置摘要：",
            f"  provider: {config.llm.provider}",
            f"  model: {config.llm.model}",
            f"  base_url: {config.llm.base_url}",
            f"  temperature: {config.llm.temperature}",
            f"  max_tokens: {config.llm.max_tokens}",
            f"  max_turns: {config.agent.max_turns}",
            f"  backend: {config.sandbox.backend}",
            f"  api_key: {_mask_api_key(config.llm.api_key)}",
        ]
        print("\n".join(lines))
        return

    table = Table(title="当前配置摘要", show_header=False)
    table.add_column("配置项", style="cyan", no_wrap=True)
    table.add_column("值")
    table.add_row("provider", config.llm.provider)
    table.add_row("model", config.llm.model)
    table.add_row("base_url", config.llm.base_url)
    table.add_row("temperature", str(config.llm.temperature))
    table.add_row("max_tokens", str(config.llm.max_tokens))
    table.add_row("max_turns", str(config.agent.max_turns))
    table.add_row("backend", config.sandbox.backend)
    table.add_row("api_key", _mask_api_key(config.llm.api_key))

    console = Console()
    console.print(table)


def render_result(result: str, plain: bool = False) -> None:
    """渲染 Agent 最终结果。

    Args:
        result: Agent 返回的字符串结果。
        plain: 是否禁用 Rich 样式，输出纯文本。
    """
    if plain:
        print(result)
        return

    panel = Panel(Markdown(result), title="Agent 结果", border_style="green")
    console = Console()
    console.print(panel)


def render_error(message: str, plain: bool = False) -> None:
    """渲染错误信息。

    Args:
        message: 错误描述。
        plain: 是否禁用 Rich 样式，输出纯文本。
    """
    if plain:
        print(f"错误：{message}", file=sys.stderr)
        return

    panel = Panel(message, title="错误", border_style="red")
    console = Console(file=sys.stderr)
    console.print(panel)


def render_tool_summary(tool_names: list[str], plain: bool = False) -> None:
    """渲染本轮工具调用摘要。

    Args:
        tool_names: 工具名称列表。
        plain: 是否禁用 Rich 样式，输出纯文本。
    """
    if not tool_names:
        return

    if plain:
        joined = ", ".join(tool_names)
        print(f"本次运行调用了 {len(tool_names)} 个工具：{joined}")
        return

    panel = Panel(
        "\n".join(f"• {name}" for name in tool_names),
        title=f"工具调用（{len(tool_names)} 次）",
        border_style="blue",
    )
    console = Console()
    console.print(panel)
