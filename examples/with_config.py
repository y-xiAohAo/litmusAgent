#!/usr/bin/env python
"""配置驱动示例：从 YAML 加载配置并运行 Agent。

本示例展示如何：
  1. 使用 load_config() 从 YAML 文件加载 AgentConfig。
  2. 将配置传入 Agent。
  3. 使用 EchoClient 让示例在无 API key 环境下也能运行。

切换到真实 LLM 的方法：
  1. 在 examples/config.yaml 的 llm.api_key 填入你的 API key，
     或设置环境变量 OPENAI_API_KEY。
  2. 将下面代码中的 `client = EchoClient()` 和 `llm_client=client`
     替换为 `llm_client=OpenAIClient.from_env(...)`。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from agent import Agent
from agent.config import load_config
from agent.llm import EchoClient


async def main() -> None:
    """加载配置并运行 Agent 示例。"""
    config_path = Path(__file__).parent / "config.yaml"
    config = load_config(config_path)

    # 示例阶段使用 EchoClient，无需真实 API key。
    # 接入真实 LLM 时，请替换为 OpenAIClient.from_env()。
    client = EchoClient()
    agent = Agent(llm_client=client, config=config)

    prompt = "展示如何从配置中读取 system prompt。"
    response = await agent.run(prompt)
    print(f"用户：{prompt}")
    print(f"Agent：{response}")
    print(f"system_prompt：{agent.system_prompt}")


if __name__ == "__main__":
    asyncio.run(main())
