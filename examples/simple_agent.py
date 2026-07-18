#!/usr/bin/env python
"""最小 Agent 示例：使用 EchoClient 运行一次简单对话。

本示例展示如何：
  1. 导入 Agent 与 EchoClient。
  2. 为 Agent 注册一个自定义 tool。
  3. 调用 agent.run() 获取回复。

注意：
  - EchoClient 是测试桩，会原样返回用户输入，不需要 API key。
  - 若希望接入真实 LLM，只需把 EchoClient 替换为 OpenAIClient.from_env()，
    并确保环境变量 OPENAI_API_KEY 已设置。
"""

from __future__ import annotations

import asyncio

from agent import Agent
from agent.core.types import ToolSpec
from agent.llm import EchoClient


async def main() -> None:
    """运行最小 Agent 示例。"""
    client = EchoClient()
    agent = Agent(llm_client=client)

    def greet(name: str) -> str:
        """按名字向用户打招呼。"""
        return f"你好，{name}！欢迎使用 Hermes Agent 框架。"

    agent.tools.register(
        ToolSpec(
            name="greet",
            description="按名字向用户打招呼",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "用户名字"}},
                "required": ["name"],
            },
            handler=greet,
        )
    )

    response = await agent.run("能向我打个招呼吗？我叫 Alice。")
    print("Agent:", response)


if __name__ == "__main__":
    asyncio.run(main())
