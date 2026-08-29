"""Agent 主 CLI。

提供命令行入口，使用户无需编写 Python 脚本即可运行 Litmus Agent。
当前仅实现 argparse 骨架与核心子命令；Rich 美化、交互模式、Docker
一键启动等由后续 Task 负责。
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import os
import sys

import yaml

from agent import __version__
from agent.cli.chat import CliStreamRenderer, make_cli_approval_callback, run_chat_loop
from agent.cli.render import render_config, render_error, render_result
from agent.cli.workspace_guard import apply_bind_safeguards
from agent.config import AgentConfig, load_config
from agent.core.engine import Agent, ApprovalCallback
from agent.llm import BaseLLMClient, EchoClient, OpenAIClient, StreamEvents

logger = logging.getLogger(__name__)


def _make_non_interactive_deny_callback() -> ApprovalCallback:
    """构造非交互场景的审批回调：一律拒写（TD-015 单元 C）。

    拒绝结果由引擎包装为 ToolResult 回传 LLM，提示其改用其他方案。
    """

    def callback(tool_name: str, arguments: dict[str, object]) -> bool:
        """确认入口：非交互环境固定返回 False（拒绝执行）。"""
        return False

    return callback


def build_parser() -> argparse.ArgumentParser:
    """构造 Agent 主 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="agent",
        description="Litmus Agent —— 具备自我纠错能力的代码沙箱 Agent。",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"agent {__version__}",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="禁用 Rich 样式，输出纯文本（适合脚本管道）",
    )

    subparsers = parser.add_subparsers(dest="command")

    # run 子命令
    run_parser = subparsers.add_parser("run", help="运行 Agent 处理用户提示")
    run_parser.add_argument("prompt", help="要发送给 Agent 的提示文本")
    run_parser.add_argument(
        "--config",
        dest="config_path",
        help="YAML 配置文件路径",
    )
    run_parser.add_argument("--model", help="覆盖 LLM 模型名")
    run_parser.add_argument("--api-key", help="覆盖 API key")
    run_parser.add_argument("--base-url", help="覆盖 API base URL")
    run_parser.add_argument(
        "--temperature",
        type=float,
        help="覆盖生成温度（0-1）",
    )
    run_parser.add_argument(
        "--max-turns",
        type=int,
        help="覆盖最大对话轮数",
    )
    run_parser.add_argument(
        "--backend",
        choices=["docker", "subprocess"],
        help="覆盖沙箱后端",
    )
    run_parser.add_argument(
        "--echo",
        action="store_true",
        help="使用 EchoClient 替代真实 LLM，用于测试与演示",
    )
    run_parser.add_argument(
        "--approve",
        action="store_true",
        help="启用写操作人工确认（file_write/file_edit 执行前询问 y/n/a）",
    )
    run_parser.add_argument(
        "--plan",
        action="store_true",
        help="启用自动规划（run 前先由 LLM 分解任务步骤）",
    )
    run_parser.add_argument(
        "--stream",
        action="store_true",
        help="启用流式输出（逐字渲染回复与工具进度；等同配置 llm.stream: true）",
    )
    # config 子命令
    config_parser = subparsers.add_parser("config", help="显示当前生效配置摘要")
    config_parser.add_argument(
        "--config",
        dest="config_path",
        help="YAML 配置文件路径",
    )
    # chat 子命令
    chat_parser = subparsers.add_parser("chat", help="进入交互式对话模式")
    chat_parser.add_argument(
        "--config",
        dest="config_path",
        help="YAML 配置文件路径",
    )
    chat_parser.add_argument("--model", help="覆盖 LLM 模型名")
    chat_parser.add_argument("--api-key", help="覆盖 API key")
    chat_parser.add_argument("--base-url", help="覆盖 API base URL")
    chat_parser.add_argument(
        "--temperature",
        type=float,
        help="覆盖生成温度（0-1）",
    )
    chat_parser.add_argument(
        "--max-turns",
        type=int,
        help="覆盖最大对话轮数",
    )
    chat_parser.add_argument(
        "--backend",
        choices=["docker", "subprocess"],
        help="覆盖沙箱后端",
    )
    chat_parser.add_argument(
        "--echo",
        action="store_true",
        help="使用 EchoClient 替代真实 LLM，用于测试与演示",
    )
    chat_parser.add_argument(
        "--approve",
        action="store_true",
        help="启用写操作人工确认（file_write/file_edit 执行前询问 y/n/a）",
    )
    chat_parser.add_argument(
        "--plan",
        action="store_true",
        help="启用自动规划（run 前先由 LLM 分解任务步骤）",
    )
    chat_parser.add_argument(
        "--stream",
        action="store_true",
        help="启用流式输出（逐字渲染回复与工具进度；等同配置 llm.stream: true）",
    )
    return parser


def _load_config(args: argparse.Namespace) -> AgentConfig:
    """根据 CLI 参数与 YAML 配置文件构造最终 AgentConfig。

    覆盖优先级：CLI 参数 > 环境变量 > YAML 配置 > 代码默认值。

    环境变量（EVAL-012）：OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
    在 YAML 加载后、CLI 参数覆盖前应用，保证切换兼容端点（如 DeepSeek）
    时无需修改配置文件。

    Args:
        args: argparse 解析后的命名空间。

    Returns:
        合并后的 AgentConfig。
    """
    config = AgentConfig()

    if args.config_path:
        config = load_config(args.config_path)

    # EVAL-012：环境变量覆盖（优先级低于 CLI 参数、高于配置文件/默认值）。
    if os.environ.get("OPENAI_MODEL"):
        config.llm.model = os.environ["OPENAI_MODEL"]
    if os.environ.get("OPENAI_BASE_URL"):
        config.llm.base_url = os.environ["OPENAI_BASE_URL"]
    if os.environ.get("OPENAI_API_KEY"):
        config.llm.api_key = os.environ["OPENAI_API_KEY"]

    # CLI 参数覆盖。
    # 使用 getattr 是因为 config 子命令没有 run 子命令的全部参数。
    if getattr(args, "model", None) is not None:
        config.llm.model = args.model
    if getattr(args, "api_key", None) is not None:
        config.llm.api_key = args.api_key
    if getattr(args, "base_url", None) is not None:
        config.llm.base_url = args.base_url
    if getattr(args, "temperature", None) is not None:
        config.llm.temperature = args.temperature
    if getattr(args, "max_turns", None) is not None:
        config.agent.max_turns = args.max_turns
    if getattr(args, "backend", None) is not None:
        config.sandbox.backend = args.backend

    return config


def _effective_api_key(config: AgentConfig) -> str:
    """返回实际生效的 API key。

    优先级：配置中的 api_key > OPENAI_API_KEY 环境变量。

    Args:
        config: 当前配置。

    Returns:
        实际 API key，可能为空字符串。
    """
    if config.llm.api_key:
        return config.llm.api_key
    return os.environ.get("OPENAI_API_KEY", "")


def _build_llm_client(config: AgentConfig, echo: bool) -> BaseLLMClient:
    """根据配置构造 LLMClient。

    Args:
        config: 当前配置。
        echo: 是否使用 EchoClient。

    Returns:
        BaseLLMClient 实例。
    """
    if echo:
        return EchoClient()
    return OpenAIClient.from_env(
        api_key=config.llm.api_key or None,
        model=config.llm.model,
        base_url=config.llm.base_url or None,
        temperature=config.llm.temperature,
        max_tokens=config.llm.max_tokens,
        thinking=config.llm.thinking,
    )


def _prepare_bind_workspace(config: AgentConfig, plain: bool = False) -> None:
    """TD-015 单元 C：host_dir（bind）模式启动前的安全件装配。

    保险一/二/三（git 快照、审批与安全件默认推导）下沉为
    `workspace_guard.apply_bind_safeguards`，CLI 与 Web 共用避免漂移；
    本函数仅在其后追加保险四：打印启动横幅（挂载路径、快照 sha、
    写确认状态、回滚提示）。

    参数：
        config: 已合并的最终配置。
        plain: 是否使用纯文本输出。

    抛出：
        ValueError: git 校验或快照失败（由调用方走友好报错路径）。
    """
    host_dir = config.sandbox.host_dir
    assert host_dir is not None  # 调用方保证仅 bind 模式进入

    snapshot_sha = apply_bind_safeguards(config)
    # apply_bind_safeguards 已把三态 None 收敛为最终生效值。
    approval_on = bool(config.agent.human_approval.enabled)
    _render_bind_banner(host_dir, snapshot_sha, approval_on, plain=plain)


def _render_bind_banner(
    host_dir: str,
    snapshot_sha: str | None,
    approval_on: bool,
    plain: bool = False,
) -> None:
    """打印 bind 模式启动横幅（保险四）。

    非 TTY（无终端/管道）场景下审批回调固定拒写，文案如实标注
    "非交互：写操作默认拒绝"，不展示 y/n/a 交互提示。
    """
    if approval_on:
        try:
            interactive = sys.stdin.isatty()
        except (AttributeError, ValueError):
            # stdin 缺失或已关闭时按非交互处理（更安全口径）。
            interactive = False
        approval_text = "已启用（y/n/a）" if interactive else "已启用（非交互：写操作默认拒绝）"
    else:
        approval_text = "已关闭（显式配置，风险自担）"
    lines = [
        "[bind 工作区模式] Agent 将直接操作宿主机目录",
        f"  挂载路径：{host_dir} → 容器内 /workspace",
        f"  git 快照：{snapshot_sha if snapshot_sha else '工作区干净，无需快照'}",
        f"  写确认：{approval_text}",
    ]
    if snapshot_sha:
        lines.append(f"  回滚：git -C {host_dir} reset --hard {snapshot_sha}")
    lines.append(f"  审计：git -C {host_dir} status / git -C {host_dir} diff")
    message = "\n".join(lines)
    if plain:
        print(message)
        return
    from rich.console import Console
    from rich.panel import Panel

    Console().print(Panel(message, title="bind 工作区", border_style="yellow"))


def _build_agent(
    config: AgentConfig,
    llm_client: BaseLLMClient,
    approve: bool = False,
    plain: bool = False,
    plan: bool = False,
    stream_events: StreamEvents | None = None,
) -> Agent:
    """根据配置与 LLMClient 构造 Agent。

    Args:
        config: 当前配置。
        llm_client: 已构造的 LLM 客户端。
        approve: 是否强制启用写操作人工确认（覆盖配置文件）。
        plain: 是否使用纯文本交互（无 Rich）。
        plan: 是否强制启用自动规划（覆盖配置文件）。
        stream_events: TD-020 流式渲染回调；仅在 config.llm.stream
            开启时由引擎真正使用。

    Returns:
        初始化后的 Agent 实例。
    """
    approval_callback = None
    if approve or config.agent.human_approval.enabled:
        if not sys.stdin.isatty():
            # TD-015 单元 C：非交互场景（无 TTY / 管道）无法询问用户，
            # 审批回调默认拒写；拒绝原因由引擎作为 ToolResult 回传 LLM，
            # LLM 可改走其他路径（如仅在沙箱内执行）。
            logger.warning("非交互环境（无 TTY）：写操作审批默认拒绝")
            approval_callback = _make_non_interactive_deny_callback()
        else:
            approval_callback = make_cli_approval_callback(
                set(config.agent.human_approval.tools), plain=plain
            )
        config.agent.human_approval.enabled = True
    if plan:
        config.agent.planner.enabled = True
    return Agent(
        llm_client=llm_client,
        system_prompt=config.agent.system_prompt,
        max_turns=config.agent.max_turns,
        config=config,
        approval_callback=approval_callback,
        stream_events=stream_events,
    )


def _make_stream_renderer(
    args: argparse.Namespace, config: AgentConfig
) -> CliStreamRenderer | None:
    """TD-020：--stream 或配置 llm.stream 开启时构造 CLI 流式渲染器。

    开启时同步把 config.llm.stream 置 True，使引擎主循环改走
    chat_stream（SSE），渲染回调经 StreamEvents 注入 Agent。
    """
    if getattr(args, "stream", False) or config.llm.stream:
        config.llm.stream = True
        return CliStreamRenderer(plain=args.plain)
    return None


def cmd_chat(args: argparse.Namespace) -> int:
    """执行 chat 子命令。

    Args:
        args: argparse 解析后的命名空间。

    Returns:
        退出码：0 正常退出，1 业务错误。
    """
    try:
        config = _load_config(args)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        render_error(f"配置加载失败：{exc}", plain=args.plain)
        return 1

    if config.sandbox.is_bind_mode():
        try:
            _prepare_bind_workspace(config, plain=args.plain)
        except ValueError as exc:
            render_error(f"bind 工作区校验失败：{exc}", plain=args.plain)
            return 1

    if not args.echo:
        api_key = _effective_api_key(config)
        if not api_key:
            render_error(
                "未提供 OPENAI_API_KEY。请设置环境变量 OPENAI_API_KEY，"
                "或在配置文件/YAML/命令行中提供 --api-key，也可以使用 --echo 模式测试。",
                plain=args.plain,
            )
            return 1

    llm_client = _build_llm_client(config, echo=args.echo)
    stream_renderer = _make_stream_renderer(args, config)
    try:
        agent = _build_agent(
            config, llm_client, approve=args.approve, plain=args.plain, plan=args.plan,
            stream_events=stream_renderer.events if stream_renderer else None,
        )
    except ValueError as exc:
        # 沙箱配置非法（如 subprocess + volume_name）时工厂会 raise ValueError，
        # 走友好输出而不是裸 traceback。
        render_error(f"沙箱配置错误：{exc}", plain=args.plain)
        return 1
    return run_chat_loop(agent, plain=args.plain, stream_renderer=stream_renderer)


def cmd_run(args: argparse.Namespace) -> int:
    """执行 run 子命令。

    Args:
        args: argparse 解析后的命名空间。

    Returns:
        退出码：0 成功，1 业务错误。
    """
    try:
        config = _load_config(args)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        render_error(f"配置加载失败：{exc}", plain=args.plain)
        return 1

    if config.sandbox.is_bind_mode():
        try:
            _prepare_bind_workspace(config, plain=args.plain)
        except ValueError as exc:
            render_error(f"bind 工作区校验失败：{exc}", plain=args.plain)
            return 1

    if not args.echo:
        api_key = _effective_api_key(config)
        if not api_key:
            render_error(
                "未提供 OPENAI_API_KEY。请设置环境变量 OPENAI_API_KEY，"
                "或在配置文件/YAML/命令行中提供 --api-key，也可以使用 --echo 模式测试。",
                plain=args.plain,
            )
            return 1

    llm_client = _build_llm_client(config, echo=args.echo)
    stream_renderer = _make_stream_renderer(args, config)
    try:
        agent = _build_agent(
            config, llm_client, approve=args.approve, plain=args.plain, plan=args.plan,
            stream_events=stream_renderer.events if stream_renderer else None,
        )
    except ValueError as exc:
        # 沙箱配置非法（如 subprocess + volume_name）时工厂会 raise ValueError，
        # 走友好输出而不是裸 traceback。
        render_error(f"沙箱配置错误：{exc}", plain=args.plain)
        return 1

    try:
        result = asyncio.run(agent.run(args.prompt))
    except Exception as exc:  # noqa: BLE001
        if stream_renderer is not None:
            stream_renderer.finish()
        render_error(f"Agent 运行出错：{exc}", plain=args.plain)
        return 1
    finally:
        # TD-015：谁创建谁关闭——收口沙箱 backend，避免孤儿卷泄漏。
        agent.close()

    if stream_renderer is not None:
        # TD-020：回复已逐字流式渲染，只做收尾，不重复输出全文。
        stream_renderer.finish()
    else:
        render_result(result, plain=args.plain)
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """执行 config 子命令。

    Args:
        args: argparse 解析后的命名空间。

    Returns:
        退出码：0 成功，1 配置加载失败。
    """
    try:
        config = _load_config(args)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        render_error(f"配置加载失败：{exc}", plain=args.plain)
        return 1

    render_config(config, plain=args.plain)
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。

    Args:
        argv: 命令行参数列表；None 时使用 sys.argv。

    Returns:
        退出码：0 成功，1 业务错误，2 参数错误（argparse 自动处理）。
    """
    # Windows 终端默认编码可能为 GBK，强制使用 UTF-8 输出中文帮助与结果。
    try:
        if isinstance(sys.stdout, io.TextIOWrapper) and isinstance(sys.stderr, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    # --plain 是全局参数，但 argparse 子命令要求它出现在子命令前或后。
    # 这里预处理：无论 --plain 出现在哪里都识别，并过滤掉避免子解析器冲突。
    plain = False
    if argv is not None:
        filtered: list[str] = []
        for arg in argv:
            if arg == "--plain":
                plain = True
            else:
                filtered.append(arg)
        argv = filtered
    else:
        filtered = []
        for arg in sys.argv[1:]:
            if arg == "--plain":
                plain = True
            else:
                filtered.append(arg)
        argv = filtered

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse 在处理 --version/--help 时会调用 parser.exit()，
        # 这里把退出码透传，避免在测试或被调用时抛出 SystemExit。
        return exc.code if isinstance(exc.code, int) else 0

    args.plain = plain or getattr(args, "plain", False)

    if args.command == "run":
        return cmd_run(args)
    if args.command == "config":
        return cmd_config(args)
    if args.command == "chat":
        return cmd_chat(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
