"""Agent 执行状态 —— 追踪执行阶段、当前步骤和产物。

这个模块提供两个层级的状态管理：

AgentState（Agent 级别）
  - 追踪"现在在做什么阶段"（规划中 / 执行中 / 已完成）
  - 追踪"当前正在做哪一个步骤"
  - 记录执行过程中产生的产物（图片、文件等）
  - 生命周期：整个对话期间

ExecutionContext（沙箱/环境级别）
  - 追踪"沙箱里已经装了什么包"
  - 追踪"已经加载了什么数据"
  - 通用的键值存储，执行过程中随时查询
  - 生命周期：单次任务执行期间

设计原则：
  - 使用 dataclass 而非 dict —— 类型安全，IDE 有自动补全
  - 轻量级 —— 不用数据库，纯内存操作
  - 不依赖外部库 —— 只用 Python 标准库
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    """Agent 的高层执行状态。

    追踪 Agent 在执行哪个阶段、当前步骤是什么、
    以及产生了哪些产物。

    典型用法：
        state = AgentState()
        state.set_phase("executing", step="load_data")
        # ... 执行 load_data ...
        state.add_artifact("chart.png", {"type": "image"})
        state.set_phase("executing", step="analyze")
    """

    # 当前阶段：planning（规划）、executing（执行）、finished（完成）
    phase: str | None = None
    # 当前正在执行的步骤名称
    current_step: str | None = None
    # 产物字典：名称 → 元数据（类型、路径、大小等）
    artifacts: dict[str, dict[str, Any]] = field(default_factory=dict)

    def set_phase(self, phase: str, step: str | None = None) -> None:
        """切换到新的执行阶段，可选地设置当前步骤。

        Args:
            phase: 阶段名称，如 "planning"、"executing"、"finished"
            step:  当前步骤名称（仅在 phase="executing" 时通常有值）
        """
        self.phase = phase
        self.current_step = step

    def add_artifact(self, name: str, metadata: dict[str, Any]) -> None:
        """记录一个执行过程中产生的产物。

        例如图表、数据文件、报告等。元数据可以包含
        类型（type）、路径（path）、大小（size）等任意字段。

        Args:
            name:     产物名称（人类可读）
            metadata: 元数据字典（如 {"type": "image", "path": "/tmp/out.png"}）
        """
        self.artifacts[name] = metadata


@dataclass
class ExecutionContext:
    """沙箱/运行时的可变键值存储。

    用于在一次 Agent 执行过程中，跨 tool call 共享状态。
    典型场景：
      - "pandas 已经装过了，下次不用再装"
      - "data.csv 已经读到 df 变量里了"
      - "当前工作目录是 /tmp/workspace"

    注意：这是 Agent 级别的上下文，不是 LLM 的对话历史。
    LLM 通过 message history 感知对话，Agent 通过 ExecutionContext
    感知环境状态。两者互补。

    Usage:
        ctx = ExecutionContext()
        ctx.set("packages_installed", ["pandas", "numpy"])
        # ... 几次 tool call 后 ...
        if "pandas" in ctx.get("packages_installed", []):
            print("pandas 已安装，跳过")
    """

    # 内部存储：dict 比 dataclass 字段更灵活，支持任意 key
    _data: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        """存储一个键值对。

        Args:
            key:   键名（如 "packages_installed"）
            value: 值（可以是任意 Python 对象）
        """
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """根据键获取值，如果不存在则返回默认值。

        与 dict.get() 行为一致：不会因为 key 不存在而抛异常。

        Args:
            key:     键名
            default: 键不存在时返回的默认值
        """
        return self._data.get(key, default)

    def clear(self) -> None:
        """清空所有存储的键值对。

        通常在开始新任务时调用，确保上一轮的状态不会污染下一轮。
        """
        self._data.clear()
