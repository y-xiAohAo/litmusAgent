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

调用降级（同行评审 Y3 + TD-019）：某 server 的调用超时/失败后记入
降级表，后续对该 server 的调用立即返回 ``MCPError: server 已降级``
快速失败。降级带 TTL（``MCPConfig.degrade_ttl``，默认 60 秒）：TTL
过期后的下一次调用先惰性重连该 server（新建 ClientSession，走与初次
连接相同的传输路径，并在新的专属生命周期任务内建立——旧任务先 stop
回收再重建，满足 anyio cancel scope 的任务绑定），成功则清除降级标记
并正常执行本次调用，失败则刷新降级时间戳继续快速失败。纯惰性：
无后台线程/定时任务，重连仅由 TTL 过期后的第一次调用触发。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
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


def _monotonic() -> float:
    """单调时钟秒数（模块级封装，便于测试 monkeypatch 控制降级 TTL 计时）。"""
    return time.monotonic()


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
        # TD-019：server 名 → 当前 ClientSession（handler 调用时动态解析，
        # 重连后自动指向新 session）；server 名 → 配置（供惰性重连查找）。
        self._sessions: dict[str, Any] = {}
        self._server_configs: dict[str, MCPServerConfig] = {}
        # 串行化惰性重连：并发调用只重建一次（锁内双重检查）。
        self._reconnect_lock = asyncio.Lock()
        # close()/aclose() 后置 True：禁止再触发惰性重连。
        self._closed = False
        self.tool_servers: dict[str, str] = {}
        self.untrusted_tools: set[str] = set()
        self.connected_servers: list[str] = []
        self.failed_servers: list[str] = []
        # Y3 调用降级表（TD-019 起带 TTL）：server 名 → (降级原因, 降级时刻)。
        self._degraded: dict[str, tuple[str, float]] = {}

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
            self._server_configs[server.name] = server
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
        上下文触发。任务退出时摘除 ``_sessions`` 里本任务建立的 session。
        """
        session: Any = None
        try:
            async with AsyncExitStack() as stack:
                try:
                    session = await self._connect_server(
                        server, stack, registry, enabled
                    )
                except Exception as exc:  # noqa: BLE001 —— 单 server 失败跳过降级
                    handle.error = exc
                    handle.ready.set()
                    return
                handle.ready.set()
                await handle.stop.wait()
        except Exception as exc:  # noqa: BLE001 —— 关闭失败不向上传播
            logger.warning("MCP server %s 关闭异常：%s", server.name, exc)
        finally:
            self._drop_session(server.name, session)
            handle.closed.set()

    async def _reconnect_lifecycle(
        self,
        server: MCPServerConfig,
        handle: _ServerHandle,
    ) -> None:
        """重连生命周期任务：建立新 session → 等待 stop → 同任务内清理（TD-019）。

        与 ``_server_lifecycle`` 同模型（cancel scope 进出都在本任务内），
        但不重新发现/注册工具——工具 schema 沿用首次发现结果，handler 经
        ``_sessions`` 动态解析当前 session，重连后自动指向新 session。
        """
        session: Any = None
        try:
            async with AsyncExitStack() as stack:
                try:
                    session = await self._open_session(server, stack)
                except Exception as exc:  # noqa: BLE001 —— 重连失败回传 error
                    handle.error = exc
                    handle.ready.set()
                    return
                self._sessions[server.name] = session
                handle.ready.set()
                await handle.stop.wait()
        except Exception as exc:  # noqa: BLE001 —— 关闭失败不向上传播
            logger.warning("MCP server %s 重连任务关闭异常：%s", server.name, exc)
        finally:
            self._drop_session(server.name, session)
            handle.closed.set()

    def _drop_session(self, server_name: str, session: Any) -> None:
        """摘除 ``_sessions`` 中的 session（仅当仍指向传入的这个对象）。

        身份比较防止误删重连后由新生命周期任务建立的同名 session。
        """
        if session is not None and self._sessions.get(server_name) is session:
            del self._sessions[server_name]

    async def _connect_server(
        self,
        server: MCPServerConfig,
        stack: AsyncExitStack,
        registry: ToolRegistry,
        enabled: list[str] | None,
    ) -> Any:
        """连接单个 server：建立 session、发现并注册工具，返回就绪 session。"""
        session = await self._open_session(server, stack)
        tools = await session.list_tools()
        for tool in tools.tools:
            full_name = f"mcp__{server.name}__{tool.name}"
            if enabled is not None and full_name not in enabled:
                continue
            self.tool_servers[full_name] = server.name
            if not server.trust:
                self.untrusted_tools.add(full_name)
            registry.register(self._wrap_tool(server, tool))
        self._sessions[server.name] = session
        logger.info(
            "MCP server %s 注册 %d 个工具", server.name, len(tools.tools)
        )
        return session

    async def _open_session(
        self,
        server: MCPServerConfig,
        stack: AsyncExitStack,
    ) -> Any:
        """建立传输 + ClientSession + initialize，返回就绪 session（TD-019 拆出）。

        只负责连接建立，不发现/注册工具——初次连接（``_connect_server``）
        与降级重连（``_reconnect_lifecycle``）共用同一路径。异步上下文挂
        在调用方传入的 stack 上，须由专属生命周期任务持有（anyio 约束）。
        """
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
        return session

    def _wrap_tool(
        self,
        server: MCPServerConfig,
        tool: Any,
    ) -> ToolSpec:
        """把 MCP 工具包装为 ToolSpec（超时兜底 + 错误前缀映射 + 降级门控）。

        handler 行为：
          - session 在调用时经 ``_sessions`` 动态解析（TD-019）：重连后
            自动指向新 session，无需重新注册工具；
          - 降级门控（Y3 + TD-019）：server 在降级 TTL 内 → 立即返回
            ``MCPError: server 已降级`` 快速失败；TTL 过期 → 先惰性重连，
            成功则清除降级并继续本次调用，失败则刷新时间戳继续快速失败；
          - ``session.call_tool`` 外层套 ``asyncio.wait_for(tool_timeout)``，
            server 僵死时强制超时，返回失败结果而不阻塞 Agent；
          - 调用超时/异常后该 server 记入降级表（带单调时钟时间戳）；
          - MCP 结果 ``is_error=True`` → ``ToolResult(success=False)``，
            内容带 ``MCPError:`` 前缀（ErrorClassifier 可识别）；
          - 成功时拼接全部 text 内容块；无 text 但有 structured_content
            时退回 JSON 序列化。
        """
        timeout = self._config.tool_timeout
        tool_name: str = tool.name
        full_name = f"mcp__{server.name}__{tool.name}"

        async def _handler(**kwargs: Any) -> ToolResult:
            # Y3 + TD-019：降级门控（TTL 内快速失败；过期先惰性重连）。
            degrade_reason = await self._degrade_gate(server.name)
            if degrade_reason is not None:
                return ToolResult(
                    tool_call_id="",
                    content=(
                        f"MCPError: server 已降级（{degrade_reason}），"
                        f"快速失败：{full_name}"
                    ),
                    success=False,
                )
            session = self._sessions.get(server.name)
            if session is None:
                return ToolResult(
                    tool_call_id="",
                    content=f"MCPError: server 未连接或已关闭：{full_name}",
                    success=False,
                )
            try:
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, kwargs), timeout=timeout
                )
            except (TimeoutError, asyncio.TimeoutError):
                logger.warning("MCP 工具调用超时（%ds）：%s", timeout, full_name)
                self._degraded[server.name] = ("上次调用超时", _monotonic())
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
                    f"上次调用失败：{type(exc).__name__}",
                    _monotonic(),
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

    async def _degrade_gate(self, server_name: str) -> str | None:
        """降级门控（TD-019）：返回 None 放行，否则返回快速失败的降级原因。

        TTL（``degrade_ttl``）内直接返回原因；TTL 过期后在锁内惰性重连：
        成功则清除降级标记放行（本次调用继续执行），失败则刷新降级时间戳
        继续快速失败。无后台线程——重连仅由 TTL 过期后的第一次调用触发；
        ``_reconnect_lock`` 保证并发调用只重建一次（锁内双重检查）。
        close() 后不再重连，降级永久快速失败。
        """
        entry = self._degraded.get(server_name)
        if entry is None:
            return None
        reason, since = entry
        if self._closed or _monotonic() - since < self._config.degrade_ttl:
            return reason
        async with self._reconnect_lock:
            # 双重检查：等锁期间并发调用可能已重连成功或刚刷新过时间戳。
            entry = self._degraded.get(server_name)
            if entry is None:
                return None
            reason, since = entry
            if _monotonic() - since < self._config.degrade_ttl:
                return reason
            if await self._reconnect_server(server_name):
                del self._degraded[server_name]
                return None
            base_reason = reason.split("；", 1)[0]
            new_reason = f"{base_reason}；重连失败"
            self._degraded[server_name] = (new_reason, _monotonic())
            return new_reason

    async def _reconnect_server(self, server_name: str) -> bool:
        """惰性重连单个 server（TD-019），调用方须已持 ``_reconnect_lock``。

        旧生命周期任务先 stop 并等待退出（旧 session / stdio 子进程随其
        异步上下文回收），再在同一事件循环内创建新的专属任务建立新
        session（anyio cancel scope 绑创建任务，不能跨任务复用旧上下文）。
        成功返回 True（``_sessions`` 已指向新 session），失败返回 False。
        """
        if self._closed:
            return False
        server = self._server_configs.get(server_name)
        if server is None:
            return False
        connect_timeout = max(self._config.tool_timeout, 15)
        old = next((h for h in self._handles if h.name == server_name), None)
        if old is not None:
            old.stop.set()
            try:
                await asyncio.wait_for(old.closed.wait(), timeout=connect_timeout)
            except (TimeoutError, asyncio.TimeoutError):
                logger.warning("MCP server %s 旧连接关闭超时，继续重建", server_name)
            if old in self._handles:
                self._handles.remove(old)
        handle = _ServerHandle(server_name)
        self._handles.append(handle)
        handle.task = asyncio.create_task(self._reconnect_lifecycle(server, handle))
        try:
            await asyncio.wait_for(handle.ready.wait(), timeout=connect_timeout)
        except (TimeoutError, asyncio.TimeoutError):
            handle.error = TimeoutError("重连初始化超时")
            handle.stop.set()
        if handle.error is not None:
            logger.warning("MCP server %s 重连失败：%s", server_name, handle.error)
            return False
        logger.info("MCP server %s 重连成功，降级解除", server_name)
        return True

    async def aclose(self) -> None:
        """异步关闭全部连接并等待回收完成（幂等）。"""
        self._closed = True
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
        self._closed = True
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
