"""Agent 主 CLI。

提供命令行入口，使用户无需编写 Python 脚本即可运行 Litmus Agent。
当前仅实现 argparse 骨架与核心子命令；Rich 美化、交互模式、Docker
一键启动等由后续 Task 负责。
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys

import yaml

from agent import __version__
from agent.cli.chat import make_cli_approval_callback, run_chat_loop
from agent.cli.render import render_config, render_error, render_result
from agent.config import AgentConfig, load_config
from agent.core.engine import Agent
from agent.llm import BaseLLMClient, EchoClient, OpenAIClient


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
    )


def _build_agent(
    config: AgentConfig,
    llm_client: BaseLLMClient,
    approve: bool = False,
    plain: bool = False,
    plan: bool = False,
) -> Agent:
    """根据配置与 LLMClient 构造 Agent。

    Args:
        config: 当前配置。
        llm_client: 已构造的 LLM 客户端。
        approve: 是否强制启用写操作人工确认（覆盖配置文件）。
        plain: 是否使用纯文本交互（无 Rich）。
        plan: 是否强制启用自动规划（覆盖配置文件）。

    Returns:
        初始化后的 Agent 实例。
    """
    approval_callback = None
    if approve or config.agent.human_approval.enabled:
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
    )


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
    agent = _build_agent(config, llm_client, approve=args.approve, plain=args.plain, plan=args.plan)
    return run_chat_loop(agent, plain=args.plain)


def cmd_run(args: argparse.Namespace) -> int:
    """执行 run 子命令。

    Args:
        args: argparse 解析后的命名空间。

    Returns:
        退出码：0 成功，1 业务错误。
    """
    config = _load_config(args)

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
    agent = _build_agent(config, llm_client, approve=args.approve, plain=args.plain, plan=args.plan)

    try:
        result = asyncio.run(agent.run(args.prompt))
    except Exception as exc:  # noqa: BLE001
        render_error(f"Agent 运行出错：{exc}", plain=args.plain)
        return 1

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
