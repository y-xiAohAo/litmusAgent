"""Tool definitions and default tool registration."""

from __future__ import annotations

import logging
from functools import partial
from typing import TYPE_CHECKING

from agent.core.types import ToolResult, ToolSpec
from agent.tools.context_read import context_read
from agent.tools.file_edit import file_edit
from agent.tools.file_list import file_list
from agent.tools.file_read import file_read
from agent.tools.file_write import file_write
from agent.tools.finish import finish
from agent.tools.glob import glob
from agent.tools.grep import grep
from agent.tools.memory_read import memory_read
from agent.tools.memory_search import memory_search
from agent.tools.sandbox_exec import sandbox_exec

if TYPE_CHECKING:
    from agent.config import AgentConfig
    from agent.core.context_cache import ContextCache
    from agent.core.engine import ToolRegistry
    from agent.core.memory import MemoryManager
    from agent.core.runtime import RuntimeServices
    from agent.sandbox.base import SandboxBackend

logger = logging.getLogger(__name__)

__all__ = [
    "ToolSpec",
    "ToolResult",
    "sandbox_exec",
    "file_read",
    "file_write",
    "file_list",
    "file_edit",
    "grep",
    "glob",
    "finish",
    "context_read",
    "memory_read",
    "memory_search",
    "register_default_tools",
    "register_internal_tools",
    "register_memory_tools",
    "register_tools_from_config",
    "register_context_tools",
]


def _build_tool_specs(backend: SandboxBackend) -> dict[str, ToolSpec]:
    """构建所有默认工具的 ToolSpec 字典。

    把工具构建逻辑抽出来，方便 `register_default_tools` 和
    `register_tools_from_config` 复用。
    """
    return {
        "sandbox_exec": ToolSpec(
            name="sandbox_exec",
            description="在隔离的 Docker 沙箱中执行 Python 代码并返回结果。",
            parameters={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "要执行的 Python 源代码。",
                    },
                },
                "required": ["code"],
                "additionalProperties": False,
            },
            handler=partial(sandbox_exec, backend=backend),
        ),
        "file_read": ToolSpec(
            name="file_read",
            description="读取沙箱内指定路径的文件内容。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "沙箱内的文件路径，例如 /tmp/result.txt。",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=partial(file_read, backend=backend),
        ),
        "file_list": ToolSpec(
            name="file_list",
            description="列出沙箱内指定目录下的文件和子目录。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "沙箱内的目录路径，例如 /tmp。",
                    },
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=partial(file_list, backend=backend),
        ),
        "file_write": ToolSpec(
            name="file_write",
            description="在沙箱内创建或覆盖指定文件。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "沙箱内的目标文件路径，例如 /workspace/main.py。",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入的完整 UTF-8 文本内容。",
                    },
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            handler=partial(file_write, backend=backend),
        ),
        "file_edit": ToolSpec(
            name="file_edit",
            description="精确编辑沙箱内已有文件的局部内容。",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "沙箱内的目标文件路径，例如 /workspace/main.py。",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "要被替换的原始字符串片段，必须在文件中唯一出现。",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "用于替换的新字符串片段。",
                    },
                },
                "required": ["path", "old_string", "new_string"],
                "additionalProperties": False,
            },
            handler=partial(file_edit, backend=backend),
        ),
        "grep": ToolSpec(
            name="grep",
            description="在沙箱内按正则搜索文件内容，返回 相对路径:行号:匹配行 列表。",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "正则表达式，例如 def\\s+\\w+。",
                    },
                    "path": {
                        "type": "string",
                        "description": "沙箱内的目录或文件路径，例如 /workspace。",
                    },
                    "include": {
                        "type": "string",
                        "description": "可选的文件名过滤模式（fnmatch），例如 *.py。",
                    },
                    "ignore_case": {
                        "type": "boolean",
                        "description": "是否忽略大小写，默认 false。",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回条数，默认 200，上限 1000。",
                    },
                },
                "required": ["pattern", "path"],
                "additionalProperties": False,
            },
            handler=partial(grep, backend=backend),
        ),
        "glob": ToolSpec(
            name="glob",
            description="在沙箱内按文件名模式匹配文件，返回每行一个相对路径（支持 ** 递归）。",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "glob 模式，例如 **/*.py。",
                    },
                    "path": {
                        "type": "string",
                        "description": "沙箱内的搜索根目录，默认 /workspace。",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回条数，默认 200，上限 1000。",
                    },
                },
                "required": ["pattern"],
                "additionalProperties": False,
            },
            handler=partial(glob, backend=backend),
        ),
        "finish": ToolSpec(
            name="finish",
            description="标记任务完成并返回最终结果。",
            parameters={
                "type": "object",
                "properties": {
                    "result": {
                        "type": "string",
                        "description": "任务的最终答案或交付物描述。",
                    },
                },
                "required": ["result"],
                "additionalProperties": False,
            },
            handler=finish,
        ),
    }


def register_default_tools(
    registry: ToolRegistry,
    backend: SandboxBackend,
) -> None:
    """把默认工具注册到 ToolRegistry 中。

    当前默认工具：
      - sandbox_exec：在隔离的 Docker 沙箱中执行 Python 代码。
      - file_read：读取沙箱内的文件内容。
      - file_list：列出沙箱内指定目录的文件。
      - file_write：在沙箱内创建或覆盖文件。
      - file_edit：精确编辑沙箱内已有文件的局部内容。
      - finish：标记任务完成并返回最终结果。

    参数：
        registry: 工具注册中心。
        backend: 用于执行代码/文件操作的 Docker 沙箱后端。
    """
    for spec in _build_tool_specs(backend).values():
        registry.register(spec)


def register_context_tools(
    registry: ToolRegistry,
    cache: ContextCache,
) -> None:
    """向 ToolRegistry 注册 context_read 工具。

    该工具是 Phase 7 上下文压缩的内部配套工具，不通过 config.tools.enabled
    控制；只要启用了压缩，Agent 就会调用此函数完成注册。

    Args:
        registry: 工具注册中心。
        cache: 当前 Agent 的 ContextCache 实例，通过闭包注入工具 handler。
    """
    async def _handler(uri: str) -> ToolResult:
        return await context_read(uri, cache)

    registry.register(
        ToolSpec(
            name="context_read",
            description=(
                "读取 hermes://context/... 格式的缓存文件内容。"
                "当工具结果（如 file_read、sandbox_exec 输出）被外迁到缓存时，"
                "使用该工具获取完整内容。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "uri": {
                        "type": "string",
                        "description": "缓存 URI，例如 hermes://context/<session_id>/<run_id>/<entry_id>.md",
                    },
                },
                "required": ["uri"],
                "additionalProperties": False,
            },
            handler=_handler,
        )
    )


def register_memory_tools(
    registry: ToolRegistry,
    manager: MemoryManager,
) -> None:
    """向 ToolRegistry 注册 memory_read 工具。

    该工具是 Phase 8 长期记忆的内部配套工具，不通过 config.tools.enabled
    控制；只要启用了长期记忆，Agent 就会调用此函数完成注册。

    Args:
        registry: 工具注册中心。
        manager: 当前 Agent 的 MemoryManager 实例，通过闭包注入工具 handler。
    """
    async def _handler(uri: str) -> ToolResult:
        return await memory_read(uri, manager)

    registry.register(
        ToolSpec(
            name="memory_read",
            description=(
                "读取 hermes://memory/... 格式的长期记忆内容。"
                "当 system prompt 中的历史记忆摘要不够详细时，"
                "使用该工具获取完整内容。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "uri": {
                        "type": "string",
                        "description": "记忆 URI，例如 hermes://memory/<category>/<entry_id>.jsonl",
                    },
                },
                "required": ["uri"],
                "additionalProperties": False,
            },
            handler=_handler,
        )
    )

    async def _search_handler(query: str, limit: int = 5) -> ToolResult:
        return await memory_search(query, manager, limit)

    registry.register(
        ToolSpec(
            name="memory_search",
            description=(
                "用自然语言搜索长期记忆。当需要回忆之前创建的文件、"
                "安装过的包、用户偏好或历史错误模式时使用。"
                "返回候选列表（含 uri），可用 memory_read 精读详情。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "自然语言查询，如“项目代号”“之前创建的文件”。",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "最大返回条数，默认 5。",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=_search_handler,
        )
    )


def register_internal_tools(
    registry: ToolRegistry,
    services: RuntimeServices,
    config: AgentConfig | None = None,
) -> None:
    """统一注册内部工具（TD-005）。

    编排规则：
      - `services.context_cache` 存在且 `register_context_read` 开关开启
        （默认 True）→ 注册 `context_read`；
      - `services.memory_manager` 存在且 `register_memory_read` 开关开启
        （默认 True）→ 注册 `memory_read`。

    新增内部工具时，只需在 `RuntimeServices` 加槽位并在此处追加注册，
    无需改动 `Agent.__init__`。

    参数：
        registry: 工具注册中心。
        services: 运行时依赖集合。
        config: Agent 顶层配置；None 时两个开关按默认 True 处理。
    """
    if services.context_cache is not None:
        enabled = (
            config is None or config.agent.compression.register_context_read
        )
        if enabled:
            register_context_tools(registry, services.context_cache)
    if services.memory_manager is not None:
        enabled = config is None or config.agent.memory.register_memory_read
        if enabled:
            register_memory_tools(registry, services.memory_manager)


def register_tools_from_config(
    registry: ToolRegistry,
    backend: SandboxBackend,
    config: AgentConfig,
) -> None:
    """根据 AgentConfig 中的 tools.enabled 配置注册工具。

    如果 config.tools.enabled 为 None，注册所有默认工具（与
    register_default_tools 行为一致）。
    如果为列表，只注册列表中存在的工具名，未知工具名会被忽略并记录警告。

    参数：
        registry: 工具注册中心。
        backend: 用于执行代码/文件操作的 Docker 沙箱后端。
        config: Agent 顶层配置，包含 tools.enabled。
    """
    all_specs = _build_tool_specs(backend)
    enabled = config.tools.enabled

    if enabled is None:
        for spec in all_specs.values():
            registry.register(spec)
        return

    for name in enabled:
        if name in all_specs:
            registry.register(all_specs[name])
        else:
            logger.warning("配置中启用了未知工具：%s，已忽略", name)

