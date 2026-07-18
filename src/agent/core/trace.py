"""Agent Trace —— 执行轨迹记录。

Agent Trace 把 Agent 的运行过程记录成结构化事件流，
用于复盘、调试和为后续机制（反思、记忆、压缩）提供数据。

设计要点：
  - Trace 与 messages 分离：messages 给 LLM 看，Trace 给 Agent/开发者看。
  - 按 Agent 主循环轮次组织为 TraceStep，每个 step 包含多个 TraceEvent。
  - 事件类型使用字符串，payload 使用 dict，保持轻量和可扩展。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TraceEvent:
    """Trace 中的单个事件。

    Attributes:
        event_type: 事件类型，如 "llm_request" / "llm_response" /
            "tool_execution" / "state_transition" / "error_classification" /
            "planner_transition"。
        timestamp: 事件发生时间（UTC）。
        payload: 事件负载，按事件类型不同存放不同字段。
    """

    event_type: str
    timestamp: datetime
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceStep:
    """Agent 主循环一轮迭代对应的 Trace 步骤。

    Attributes:
        step_index: 轮次索引，从 0 开始。
        events: 本轮产生的事件列表。
    """

    step_index: int
    events: list[TraceEvent] = field(default_factory=list)

    def add_event(self, event_type: str, payload: dict[str, Any] | None = None) -> TraceEvent:
        """向本轮添加一个事件，并返回该事件。

        Args:
            event_type: 事件类型。
            payload: 事件负载，可选。

        Returns:
            新创建的 TraceEvent。
        """
        event = TraceEvent(
            event_type=event_type,
            timestamp=datetime.now(timezone.utc),
            payload=payload or {},
        )
        self.events.append(event)
        return event


@dataclass
class AgentTrace:
    """一次 Agent 运行的完整执行轨迹。

    Attributes:
        steps: 按轮次组织的 Trace 步骤列表。
        start_time: 运行开始时间（UTC）。
        end_time: 运行结束时间（UTC）。
        final_state: 运行结束时的 AgentState 快照。
    """

    steps: list[TraceStep] = field(default_factory=list)
    start_time: datetime | None = None
    end_time: datetime | None = None
    final_state: dict[str, Any] | None = None

    def add_step(self, step_index: int) -> TraceStep:
        """添加并返回一个新的 TraceStep。

        Args:
            step_index: 轮次索引。

        Returns:
            新创建的 TraceStep。
        """
        step = TraceStep(step_index=step_index)
        self.steps.append(step)
        return step

    def current_step(self) -> TraceStep | None:
        """返回当前正在记录的步骤，如果没有则返回 None。"""
        return self.steps[-1] if self.steps else None

    def to_dict(self) -> dict[str, Any]:
        """将 Trace 导出为可序列化的字典。"""

        def _serialize(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, list):
                return [_serialize(item) for item in obj]
            if isinstance(obj, dict):
                return {key: _serialize(value) for key, value in obj.items()}
            if isinstance(obj, str | int | float | bool | None):
                return obj
            # 对不可序列化的自定义对象做兜底处理，避免 json.dumps 崩溃
            try:
                return str(obj)
            except Exception:
                return f"<unserializable: {type(obj).__name__}>"

        return {
            "start_time": _serialize(self.start_time),
            "end_time": _serialize(self.end_time),
            "final_state": _serialize(self.final_state),
            "steps": [
                {
                    "step_index": step.step_index,
                    "events": [
                        {
                            "event_type": event.event_type,
                            "timestamp": _serialize(event.timestamp),
                            "payload": _serialize(event.payload),
                        }
                        for event in step.events
                    ],
                }
                for step in self.steps
            ],
        }

    def to_json(self) -> str:
        """将 Trace 导出为 JSON 字符串。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
