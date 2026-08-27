"""MCP（Model Context Protocol）工具接入 —— MCPManager 与 ToolSpec 包装（TD-016）。

职责：
  1. 按配置连接 MCP server（stdio / SSE / Streamable HTTP 三种传输）；
  2. 发现 server 暴露的工具并包装为 ToolSpec 注册进 ToolRegistry，
     工具名强制前缀 ``mcp__<server>__<tool>``（避免跨 server 命名冲突）；
  3. 调用侧做僵死防护（``asyncio.wait_for`` 强制超时，SDK 已知 cancel
     通知不保证送达 server，见 python-sdk#2507）与错误映射（MCP isError
     → ``ToolResult(success=False)``，内容带 ``MCPError:`` 前缀，供
     ErrorClassifier 识别）。

安全模型（Spec §2.3-R1 / §3.3）：
  MCP server 是宿主进程或远程服务，其工具在宿主执行、不经沙箱——
  配置即信任声明。非 ``trust: true`` 的 server 工具由 Agent 层并入
  人工确认集合；策略层统一映射 resource=``mcp/server``、
  operation=``call``、subject=``mcp/<server>``。

生命周期任务模型：
  MCP SDK 的 stdio/SSE 传输基于 anyio cancel scope，要求进出在同一
  asyncio Task。因此每个 server 由专属的 ``_server_lifecycle`` 任务
  持有全部异步上下文（连接在任务内进入，收到 stop 事件后在同一任务
  内退出）；``close()`` 只 set 事件，天然支持同步入口 + 运行中循环。

降级口径（Spec §6-Q5）：单 server 连接失败只记 warning 并跳过，
全部失败也不阻塞 Agent。

调用降级（同行评审 Y3）：某 server 的调用超时/失败后记入降级表，
后续对该 server 的调用立即返回 ``MCPError: server 已降级`` 快速失败
（不做自动重连——重连是 Non-Goal）。
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any

from agent.core.types import ToolResult, ToolSpec

if TYPE_CHECKING:
    from agent.config import MCPConfig, MCPServerConfig
    from agent.core.engine import ToolRegistry

logger = logging.getLogger(__name__)

_MCP_MISSING_HINT = (
    "配置了 mcp.servers，但未安装 MCP SDK。请先执行 pip install agent[mcp]"
    "（或 pip install mcp）后再运行。"
)


def _mcp_http_client_factory(
    headers: dict[str, str] | None = None,
    timeout: Any = None,
    auth: Any = None,
) -> Any:
    """自建 httpx2.AsyncClient 工厂，替代 SDK 私有 ``mcp.shared._httpx_utils``（O2）。

    mcp 2.1.1 的 HTTP 栈基于 ``httpx2``（其 AsyncClient 带 ``.sse()``，
    是 mcp 的公开传递依赖）；签名对齐 ``sse_client`` 的
    ``httpx_client_factory`` 约定，行为对齐 SDK 默认：follow_redirects +
    保守超时（常规 30s / SSE 读 300s，调用级超时另由
    ``asyncio.wait_for(tool_timeout)`` 兜底）。httpx2 延迟导入——
    本模块要求未装 mcp 时可正常 import（由 connect() 报友好错误）。
    """
    import httpx2

    return httpx2.AsyncClient(
        headers=headers,
        timeout=timeout or httpx2.Timeout(30.0, read=300.0),
        auth=auth,
        follow_redirects=True,
    )


class _ServerHandle:
    """单个 server 生命周期任务的同步句柄（事件均为跨 Task 安全）。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.ready = asyncio.Event()     # 连接阶段结束（成功或失败）
        self.stop = asyncio.Event()      # 请求关闭
        self.closed = asyncio.Event()    # 生命周期任务已退出（资源已回收）
        self.error: BaseException | None = None
        self.task: asyncio.Task[None] | None = None


class MCPManager:
    """MCP server 连接与工具注册管理器（TD-016）。

    生命周期：由 ``Agent._ensure_mcp_connected()`` 在首次 ``run()`` 前
    惰性创建并 ``connect()``；由 ``Agent.close()`` 经 ``close()`` 收口
    （各 server 生命周期任务退出其异步上下文，stdio 子进程随之回收）。

    属性（主要供 Agent 装配与测试断言）：
        tool_servers: 工具全名 → server 名映射。
        untrusted_tools: 需要人工确认的 MCP 工具全名（trust=False 的）。
        connected_servers / failed_servers: 连接成功 / 失败的 server 名。
    """

    def __init__(self, config: MCPConfig) -> None:
        self._config = config
        self._loop: asyncio.AbstractEventLoop | None = None
        self._handles: list[_ServerHandle] = []
        self.tool_servers: dict[str, str] = {}
        self.untrusted_tools: set[str] = set()
        self.connected_servers: list[str] = []
        self.failed_servers: list[str] = []
        # Y3 调用降级表：server 名 → 降级原因（超时/调用失败后快速失败）。
        self._degraded: dict[str, str] = {}

    async def connect(
        self,
        registry: ToolRegistry,
        enabled: list[str] | None = None,
    ) -> None:
        """连接全部已配置 server 并把发现的工具注册进 registry。

        参数：
            registry: 工具注册中心，MCP 工具注册进默认层，
                策略/审批/Trace/外迁自动生效。
            enabled: ``tools.enabled`` 白名单；None 表示全部注册，
                否则只注册全名在白名单内的 MCP 工具（全名匹配）。

        抛出：
            ImportError: 配置了 mcp 段但未安装 mcp 包（转中文友好提示）。
        """
        try:
            import mcp  # noqa: F401 —— 仅探测包是否安装
        except ImportError as exc:
            raise ImportError(_MCP_MISSING_HINT) from exc

        self._loop = asyncio.get_running_loop()
        # 连接（含子进程启动 + initialize）与单次调用分开计时：
        # Windows 上冷启动较慢，下限 15s，避免小的 tool_timeout 误杀连接。
        connect_timeout = max(self._config.tool_timeout, 15)
        for server in self._config.servers:
            handle = _ServerHandle(server.name)
            self._handles.append(handle)
            handle.task = asyncio.create_task(
                self._server_lifecycle(server, handle, registry, enabled)
            )
            try:
                await asyncio.wait_for(
                    handle.ready.wait(), timeout=connect_timeout
                )
            except (TimeoutError, asyncio.TimeoutError):
                handle.error = TimeoutError("连接初始化超时")
                handle.stop.set()
            if handle.error is not None:
                logger.warning(
                    "MCP server %s 连接失败，已跳过：%s", server.name, handle.error
                )
                self.failed_servers.append(server.name)
            else:
                self.connected_servers.append(server.name)
                logger.info("MCP server %s 已连接", server.name)
        if not self.connected_servers:
            logger.warning(
                "所有 MCP server 均连接失败（%s），Agent 将在无 MCP 工具下继续运行",
                "、".join(self.failed_servers),
            )

    async def _server_lifecycle(
        self,
        server: MCPServerConfig,
        handle: _ServerHandle,
        registry: ToolRegistry,
        enabled: list[str] | None,
    ) -> None:
        """单个 server 的生命周期任务：连接 → 等待 stop → 同任务内清理。

        cancel scope 的进入与退出都在本任务内完成，满足 anyio 的任务绑定
        约束；关闭由 ``stop`` 事件驱动，因此 ``close()`` 可从任意同步
        上下文触发。
        """
        try:
            async with AsyncExitStack() as stack:
                try:
                    await self._connect_server(server, stack, registry, enabled)
                except Exception as exc:  # noqa: BLE001 —— 单 server 失败跳过降级
                    handle.error = exc
                    handle.ready.set()
                    return
                handle.ready.set()
                await handle.stop.wait()
        except Exception as exc:  # noqa: BLE001 —— 关闭失败不向上传播
            logger.warning("MCP server %s 关闭异常：%s", server.name, exc)
        finally:
            handle.closed.set()

    async def _connect_server(
        self,
        server: MCPServerConfig,
        stack: AsyncExitStack,
        registry: ToolRegistry,
        enabled: list[str] | None,
    ) -> None:
        """连接单个 server：建立 session、发现并注册工具。"""
        from mcp import ClientSession, StdioServerParameters

        # Y2 传输判别：显式 transport 优先；None 时退回启发式
        # （有 command → stdio；url 以 /sse 结尾 → SSE；否则 → HTTP）。
        transport = server.transport
        if transport is None:
            if server.command is not None:
                transport = "stdio"
            elif server.url is not None and server.url.rstrip("/").endswith("/sse"):
                transport = "sse"
            else:
                transport = "http"

        if transport == "stdio":
            assert server.command is not None
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=server.command, args=server.args, env=server.env
            )
            read, write = await stack.enter_async_context(stdio_client(params))
        elif transport == "sse":
            assert server.url is not None
            from mcp.client.sse import sse_client

            read, write = await stack.enter_async_context(
                sse_client(
                    url=server.url,
                    headers=server.headers,
                    httpx_client_factory=_mcp_http_client_factory,
                )
            )
        else:
            assert server.url is not None
            from mcp.client.streamable_http import streamable_http_client

            # 自建 httpx client（O2），随 AsyncExitStack 一起关闭。
            http_client = await stack.enter_async_context(
                _mcp_http_client_factory(headers=server.headers)
            )
            read, write = await stack.enter_async_context(
                streamable_http_client(server.url, http_client=http_client)
            )

        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        tools = await session.list_tools()
        for tool in tools.tools:
            full_name = f"mcp__{server.name}__{tool.name}"
            if enabled is not None and full_name not in enabled:
                continue
            self.tool_servers[full_name] = server.name
            if not server.trust:
                self.untrusted_tools.add(full_name)
            registry.register(self._wrap_tool(server, session, tool))
        logger.info(
            "MCP server %s 注册 %d 个工具", server.name, len(tools.tools)
        )

    def _wrap_tool(
        self,
        server: MCPServerConfig,
        session: Any,
        tool: Any,
    ) -> ToolSpec:
        """把 MCP 工具包装为 ToolSpec（超时兜底 + 错误前缀映射）。

        handler 行为：
          - ``session.call_tool`` 外层套 ``asyncio.wait_for(tool_timeout)``，
            server 僵死时强制超时，返回失败结果而不阻塞 Agent；
          - 调用超时/异常后该 server 记入降级表（Y3），后续调用立即
            返回 ``MCPError: server 已降级`` 快速失败，不做自动重连；
          - MCP 结果 ``is_error=True`` → ``ToolResult(success=False)``，
            内容带 ``MCPError:`` 前缀（ErrorClassifier 可识别）；
          - 成功时拼接全部 text 内容块；无 text 但有 structured_content
            时退回 JSON 序列化。
        """
        timeout = self._config.tool_timeout
        tool_name: str = tool.name
        full_name = f"mcp__{server.name}__{tool.name}"

        async def _handler(**kwargs: Any) -> ToolResult:
            # Y3：server 已降级（上次调用超时/失败）→ 快速失败，不重连。
            degrade_reason = self._degraded.get(server.name)
            if degrade_reason is not None:
                return ToolResult(
                    tool_call_id="",
                    content=(
                        f"MCPError: server 已降级（{degrade_reason}），"
                        f"快速失败：{full_name}"
                    ),
                    success=False,
                )
            try:
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, kwargs), timeout=timeout
                )
            except (TimeoutError, asyncio.TimeoutError):
                logger.warning("MCP 工具调用超时（%ds）：%s", timeout, full_name)
                self._degraded[server.name] = "上次调用超时"
                return ToolResult(
                    tool_call_id="",
                    content=(
                        f"MCPError: 调用超时（>{timeout}s），server 可能已僵死："
                        f"{full_name}"
                    ),
                    success=False,
                )
            except Exception as exc:  # noqa: BLE001 —— 统一映射为失败结果
                self._degraded[server.name] = (
                    f"上次调用失败：{type(exc).__name__}"
                )
                return ToolResult(
                    tool_call_id="",
                    content=(
                        f"MCPError: {type(exc).__name__}: {exc}（{full_name}）"
                    ),
                    success=False,
                )

            texts = [
                block.text
                for block in (result.content or [])
                if getattr(block, "type", None) == "text"
            ]
            content = "\n".join(texts)
            if not content and getattr(result, "structured_content", None):
                content = json.dumps(
                    result.structured_content, ensure_ascii=False, default=str
                )
            if getattr(result, "is_error", False):
                return ToolResult(
                    tool_call_id="",
                    content=f"MCPError: {content or '工具返回错误'}（{full_name}）",
                    success=False,
                )
            return ToolResult(tool_call_id="", content=content, success=True)

        description = getattr(tool, "description", None) or ""
        return ToolSpec(
            name=full_name,
            description=f"[MCP:{server.name}] {description}".strip(),
            parameters=tool.input_schema
            or {"type": "object", "properties": {}},
            handler=_handler,
        )

    async def aclose(self) -> None:
        """异步关闭全部连接并等待回收完成（幂等）。"""
        for handle in self._handles:
            handle.stop.set()
        if self._handles:
            await asyncio.gather(
                *(h.closed.wait() for h in self._handles),
                return_exceptions=True,
            )
        self._handles = []

    def close(self) -> None:
        """同步关闭入口（供 ``Agent.close()`` 调用，幂等）。

        只向各生命周期任务发 stop 事件——实际清理由任务自己在同一
        asyncio Task 内完成（满足 anyio cancel scope 任务绑定）：
          - 事件循环仍在运行（web 异步 shutdown / 测试内）：任务随循环
            推进自行完成回收，调用方让出循环后子进程即退出；
          - 循环存在但未运行（CLI run 之后）：``run_until_complete``
            同步等待回收完成；
          - 循环已关闭（CLI chat 的 loop.close() 之后）：任务已随循环
            消亡，stdio 子进程在主进程退出时由系统回收兜底。
        """
        if not self._handles:
            return
        for handle in self._handles:
            handle.stop.set()
        loop = self._loop
        if loop is not None and not loop.is_closed() and not loop.is_running():
            try:
                loop.run_until_complete(
                    asyncio.gather(
                        *(h.closed.wait() for h in self._handles),
                        return_exceptions=True,
                    )
                )
            except Exception as exc:  # noqa: BLE001 —— 关闭失败不向上传播
                logger.warning("MCP 连接关闭等待异常：%s", exc)
        self._handles = []
