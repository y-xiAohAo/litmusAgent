"""TD-016 测试用 fake MCP server（stdio 真实链路 / SSE 复用本模块定义）。

通过 `python tests/mcp_fake_server.py` 作为子进程启动；设置
FAKE_MCP_PID_FILE 环境变量时，启动后把自身 PID 写入该文件，
供测试在 close 后验证子进程退出。
"""

from __future__ import annotations

import asyncio
import os

from mcp.server.mcpserver import MCPServer

server = MCPServer("fake")


@server.tool()
def add(a: int, b: int) -> int:
    """两数相加。"""
    return a + b


@server.tool()
def echo(text: str) -> str:
    """原样回显文本。"""
    return f"echo:{text}"


@server.tool()
async def hang() -> str:
    """永不返回，用于 tool_timeout 僵死防护测试。"""
    await asyncio.sleep(3600)
    return "never"


@server.tool()
def fail() -> str:
    """总是抛错，用于 MCP isError → MCPError 前缀映射测试。"""
    raise RuntimeError("boom")


if __name__ == "__main__":
    pid_file = os.environ.get("FAKE_MCP_PID_FILE")
    if pid_file:
        with open(pid_file, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
    server.run("stdio")
