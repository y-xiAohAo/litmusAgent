"""LLM 驱动的对话事实提取器（TD-013）。

规则提取器（RuleMemoryExtractor）只覆盖产物/环境/失败模式，用户在对话中
直接陈述的事实无法进入长期记忆（Batch 5 实证）。本提取器补上该缺口：
每 run 最多一次 LLM 调用，从对话中提取用户事实（PREFERENCES）与
任务摘要（TASK_SUMMARIES）。

成本护栏：预过滤（无实质用户输入则跳过）+ 每 run 最多 1 次调用 +
temperature 0 + max_tokens 有界。
失败降级：任何异常返回空列表（MemoryManager.record 已有 try/except 隔离，
绝不中断 Agent 主流程）。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from agent.core.memory import MemoryCategory, MemoryEntry
from agent.core.state import AgentState
from agent.core.trace import AgentTrace

_logger = logging.getLogger(__name__)

_DEFAULT_MAX_FACTS = 10
_MIN_USER_CHARS = 8  # user 消息总长低于此值视为纯触发语（继续/好的），跳过事实提取
_CONVERSATION_BUDGET = 4000  # 送入 LLM 的对话文本长度上限

_EXTRACTION_PROMPT = """你是记忆提取助手。从下面的对话中提取两类信息：

1. facts：用户在对话中直接陈述的、值得跨会话长期记住的事实（偏好、代号、
   参数、约定、人名、日期、数值等）。已存在的记忆不要重复输出；
   事实有更新时输出新值。
2. task_summary：本轮任务的一句话结果摘要（做了什么、结果如何）。

【已存在的同类记忆】
{existing}

【对话】
{conversation}

只输出 JSON：{{"facts": [{{"content": "...", "tags": ["..."]}}], "task_summary": "..."}}
无内容可提取时输出：{{"facts": [], "task_summary": null}}"""


class LLMMemoryExtractor:
    """LLM 驱动的对话事实提取器（PREFERENCES + TASK_SUMMARIES）。

    duck-typed 提取器：`async extract()` 返回 MemoryEntry 列表，
    由 MemoryManager.record 统一调度（isawaitable 兼容同步/异步）。
    """

    def __init__(self, llm_client: Any, *, max_facts: int = _DEFAULT_MAX_FACTS) -> None:
        """初始化。

        Args:
            llm_client: OpenAI 兼容 LLM 客户端（与主 Agent 共用）。
            max_facts: 单次最多提取的事实条数（防噪声膨胀）。
        """
        self._llm = llm_client
        self._max_facts = max_facts

    async def extract(
        self,
        trace: AgentTrace,
        state: AgentState,
        run_metadata: dict[str, Any],
    ) -> list[MemoryEntry]:
        """预过滤 → 组装 prompt（对话 + 现有 PREFERENCES 摘要）→ 解析 JSON → 构造条目。

        run_metadata 约定：
          - messages：本轮完整对话（Message 列表，engine 注入）；
          - existing_preferences：现有偏好记忆摘要文本（MemoryManager 注入）。
        """
        try:
            messages = run_metadata.get("messages") or []
            skip_facts, skip_summary = self._should_skip(messages, trace)
            if skip_facts and skip_summary:
                return []
            conversation = self._format_conversation(messages)
            if not conversation:
                return []
            existing = run_metadata.get("existing_preferences") or "（无）"
            prompt = _EXTRACTION_PROMPT.format(
                existing=existing,
                conversation=conversation,
            )
            response = await self._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=1024,
            )
            facts, summary = self._parse_output(str(response.get("content", "")))
        except Exception:
            _logger.exception("LLM 记忆提取失败，降级为空")
            return []

        entries: list[MemoryEntry] = []
        run_id = run_metadata.get("run_id")
        if not skip_facts:
            for fact in facts[: self._max_facts]:
                content = str(fact.get("content", "")).strip()
                if not content:
                    continue
                tags = [str(t) for t in fact.get("tags", [])][:5] or ["fact"]
                entries.append(
                    MemoryEntry(
                        entry_id=uuid.uuid4().hex,
                        category=MemoryCategory.PREFERENCES,
                        content={"fact": content},
                        summary=content,
                        tags=["llm-extract"] + tags,
                        source_run_id=run_id,
                    )
                )
        if not skip_summary and summary:
            entries.append(
                MemoryEntry(
                    entry_id=uuid.uuid4().hex,
                    category=MemoryCategory.TASK_SUMMARIES,
                    content={"summary": summary},
                    summary=summary,
                    tags=["llm-extract", "task-summary"],
                    source_run_id=run_id,
                )
            )
        return entries

    def _should_skip(
        self,
        messages: list[Any],
        trace: AgentTrace,
    ) -> tuple[bool, bool]:
        """返回 (skip_facts, skip_summary)。

        规则：
          - 无 user 消息 → 全跳过；
          - user 消息总长 < 8 字符（纯触发语）→ 跳过事实提取；
          - trace 无任何 tool_execution 事件 → 跳过任务摘要（无产出可总结）。
        """
        user_texts = [
            str(getattr(m, "content", "") or "")
            for m in messages
            if getattr(m, "role", "") == "user"
        ]
        if not user_texts:
            return True, True
        skip_facts = sum(len(t) for t in user_texts) < _MIN_USER_CHARS
        has_tool_events = any(
            event.event_type == "tool_execution"
            for step in trace.steps
            for event in step.events
        )
        skip_summary = not has_tool_events
        return skip_facts, skip_summary

    @staticmethod
    def _format_conversation(messages: list[Any]) -> str:
        """把 Message 列表格式化为对话文本（尾部截断到预算内）。"""
        lines: list[str] = []
        for m in messages:
            role = getattr(m, "role", "")
            content = str(getattr(m, "content", "") or "").strip()
            if role in ("user", "assistant") and content:
                lines.append(f"{role}: {content}")
        text = "\n".join(lines)
        if len(text) > _CONVERSATION_BUDGET:
            text = "……（前略）\n" + text[-_CONVERSATION_BUDGET:]
        return text

    @staticmethod
    def _parse_output(text: str) -> tuple[list[dict[str, Any]], str | None]:
        """容错解析 LLM JSON 输出。

        期望：{"facts": [...], "task_summary": "..."}；
        容忍 Markdown 代码块包裹与前后杂文本。
        """
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return [], None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return [], None
        facts_raw = data.get("facts") or []
        facts = [f for f in facts_raw if isinstance(f, dict)] if isinstance(facts_raw, list) else []
        summary_raw = data.get("task_summary")
        summary = str(summary_raw).strip() if summary_raw else None
        return facts, summary or None
