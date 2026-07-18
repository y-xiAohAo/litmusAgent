"""RuntimeServices —— Agent 内部工具的运行时依赖集合（TD-005）。

设计动机：
  此前 `context_read` / `memory_read` 等内部工具的依赖（ContextCache、
  MemoryManager）在 `Agent.__init__` 中逐个创建并通过闭包注入，每新增
  一个内部工具都要修改核心引擎。本模块把依赖的创建与持有收敛到一个
  轻量数据对象中：

    - `RuntimeServices`：三槽位 dataclass（execution_context /
      context_cache / memory_manager）。
    - `from_config()`：按配置创建默认依赖的工厂，显式注入优先。

  注册编排见 `agent.tools.register_internal_tools()`。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agent.core.context_cache import ContextCache
from agent.core.memory import MemoryManager, RuleMemoryExtractor, StructuredMemoryStore
from agent.core.state import ExecutionContext

if TYPE_CHECKING:
    from agent.config import AgentConfig
    from agent.core.security import PolicyEngine


@dataclass
class RuntimeServices:
    """Agent 内部工具的运行时依赖集合。

    属性：
        execution_context: session 级执行上下文（TD-004，必有）。
        context_cache: 上下文压缩缓存（启用压缩时存在）。
        memory_manager: 长期记忆管理器（启用记忆时存在）。
    """

    execution_context: ExecutionContext
    context_cache: ContextCache | None = None
    memory_manager: MemoryManager | None = None

    @classmethod
    def from_config(
        cls,
        config: AgentConfig | None,
        policy: PolicyEngine | None,
        execution_context: ExecutionContext,
        context_cache: ContextCache | None = None,
        memory_manager: MemoryManager | None = None,
        llm_client: Any | None = None,
    ) -> RuntimeServices:
        """按配置创建运行时服务。

        创建规则（与 TD-005 之前 `Agent.__init__` 的语义一致）：
          - 显式注入的 `context_cache` / `memory_manager` 优先，不再创建；
          - `config.agent.compression.enabled` 时创建默认 ContextCache；
          - `config.agent.memory.enabled` 时创建默认 MemoryManager，
            并注入同一个 PolicyEngine（记忆读写权限控制）。

        参数：
            config: Agent 顶层配置；None 时不创建任何可选服务。
            policy: 安全策略引擎（注入 MemoryManager）；None 表示不启用策略。
            execution_context: Agent 持有的 session 级执行上下文。
            context_cache: 显式注入的缓存（优先于配置创建）。
            memory_manager: 显式注入的记忆管理器（优先于配置创建）。

        返回：
            装配完成的 RuntimeServices。
        """
        if context_cache is None and config is not None and config.agent.compression.enabled:
            compression = config.agent.compression
            context_cache = ContextCache(
                root_dir=Path(compression.cache_root),
                session_id=uuid.uuid4().hex,
            )

        if memory_manager is None and config is not None and config.agent.memory.enabled:
            memory_config = config.agent.memory
            memory_manager = MemoryManager(
                store=StructuredMemoryStore(root_dir=Path(memory_config.memory_root)),
                extractor=RuleMemoryExtractor(),
                config=memory_config,
                policy=policy,
                llm_client=llm_client,
            )

        return cls(
            execution_context=execution_context,
            context_cache=context_cache,
            memory_manager=memory_manager,
        )
