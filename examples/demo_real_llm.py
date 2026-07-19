"""Phase 10.9：真实 LLM 端到端演示脚本。

本脚本用于展示 Litmus Agent 在真实 LLM 驱动下的完整工作流：
  1. 接收一个编程/数据分析任务。
  2. 调用 LLM 决策。
  3. 在 Docker 沙箱中执行代码（可选）。
  4. 返回最终结果。

运行方式：
  # 真实 LLM（需配置 OPENAI_API_KEY）
  python examples/demo_real_llm.py

  # 仅演示 Agent 循环结构，无需 API Key
  python examples/demo_real_llm.py --echo

  # 加载自定义配置
  python examples/demo_real_llm.py --config examples/config.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys

from agent import Agent
from agent.config import AgentConfig, load_config
from agent.llm import EchoClient, OpenAIClient

DEFAULT_PROMPT = (
    "请编写一个 Python 函数 fibonacci(n)，"
    "在沙箱中验证它对于 n=10 返回 55，"
    "然后返回该函数的源码。"
)


def _ensure_utf8_stdout() -> None:
    """Windows 终端默认可能为 GBK，强制 UTF-8 以便中文正常显示。"""
    try:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8")
        if isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass


def build_parser() -> argparse.ArgumentParser:
    """构造 Demo 参数解析器。"""
    parser = argparse.ArgumentParser(
        prog="demo_real_llm",
        description="Litmus Agent 真实 LLM 端到端演示。",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="要发送给 Agent 的任务描述（默认是一个编程验证任务）",
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        help="YAML 配置文件路径",
    )
    parser.add_argument(
        "--model",
        help="覆盖 LLM 模型名",
    )
    parser.add_argument(
        "--base-url",
        dest="base_url",
        help="覆盖 API Base URL，例如 https://api.deepseek.com/v1",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        help="覆盖 API Key",
    )
    parser.add_argument(
        "--echo",
        action="store_true",
        help="使用 EchoClient 替代真实 LLM，用于无 Key 环境测试",
    )
    return parser


def _load_config(args: argparse.Namespace) -> AgentConfig:
    """根据命令行参数加载配置。"""
    if args.config_path:
        return load_config(args.config_path)
    return AgentConfig()


def _effective_api_key(config: AgentConfig) -> str:
    """返回实际生效的 API key。"""
    if config.llm.api_key:
        return config.llm.api_key
    return os.environ.get("OPENAI_API_KEY", "")


def _print_header(title: str) -> None:
    """打印带分隔符的标题。"""
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main(argv: list[str] | None = None) -> int:
    """Demo 入口。

    返回：
      0 正常结束（包括无 Key 时打印提示后退出）。
      1 配置加载失败。
    """
    _ensure_utf8_stdout()

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = _load_config(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"配置加载失败：{exc}", file=sys.stderr)
        return 1

    # 优先级：CLI 参数 > 环境变量 > 配置文件 > 默认值
    effective_model = args.model or os.environ.get("OPENAI_MODEL") or config.llm.model
    effective_base_url = (
        args.base_url or os.environ.get("OPENAI_BASE_URL") or config.llm.base_url
    )
    effective_api_key = args.api_key or _effective_api_key(config)

    if args.echo:
        llm_client = EchoClient()
        mode = "EchoClient（无真实 LLM 调用）"
    else:
        if not effective_api_key:
            _print_header("未检测到 API Key")
            print("本 Demo 需要真实 LLM 才能展示完整能力。")
            print("请通过以下任一方式提供 Key：")
            print("  1. 设置环境变量：export OPENAI_API_KEY=sk-...")
            print("  2. 在 YAML 配置中填写 llm.api_key")
            print("  3. 使用 --api-key 参数")
            print("  4. 先使用 --echo 模式体验循环结构：")
            print("     python examples/demo_real_llm.py --echo")
            return 0
        llm_client = OpenAIClient.from_env(
            api_key=effective_api_key,
            model=effective_model,
            base_url=effective_base_url,
            temperature=config.llm.temperature,
            max_tokens=config.llm.max_tokens,
        )
        mode = f"真实 LLM：{effective_model} @ {effective_base_url}"

    _print_header("Litmus Agent 端到端演示")
    print(f"运行模式：{mode}")
    print(f"任务：{args.prompt}")

    agent = Agent(
        llm_client=llm_client,
        system_prompt=config.agent.system_prompt,
        max_turns=config.agent.max_turns,
        config=config,
    )

    _print_header("Agent 运行结果")
    result = asyncio.run(agent.run(args.prompt))
    print(result)

    trace = agent.get_trace()
    _print_header("执行轨迹摘要")
    print(f"总轮数：{len(trace.steps)}")
    print(f"开始时间：{trace.start_time}")
    print(f"结束时间：{trace.end_time}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
