#!/usr/bin/env python
"""单次任务示例：模拟 CLI 的 `agent run` 行为。

本示例展示如何：
  1. 用 EchoClient 构造一个 Agent。
  2. 给 Agent 一个提示并获取回复。
  3. 在注释中说明如何在 CLI 中做同样的事。

对应 CLI 用法（无 API key 时可用 --echo 测试）：
  agent run "帮我写一个快速排序算法" --echo

接入真实 LLM 时：
  agent run "帮我写一个快速排序算法" --config examples/config.yaml
"""

from __future__ import annotations

import asyncio

from agent import Agent
from agent.llm import EchoClient


async def main() -> None:
    """运行一次单次任务示例。"""
    client = EchoClient()
    agent = Agent(
        llm_client=client,
        system_prompt="你是一名编程助手，擅长用 Python 写清晰、可运行的代码。",
    )

    prompt = "帮我写一个快速排序算法。"
    response = await agent.run(prompt)
    print(f"用户：{prompt}")
    print(f"Agent：{response}")


if __name__ == "__main__":
    asyncio.run(main())
