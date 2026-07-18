"""Agent 引擎 —— 编排 LLM 调用和工具执行的循环。

这是整个项目的核心。Agent 引擎实现了一个"上下文驱动的决策循环"：

  用户输入 → Agent.run()
    ↓
  [循环] 调 LLM → 看回复
    ├─ 纯文本 → 返回给用户
    └─ tool_call → 执行工具 → 结果发回 LLM → 继续循环

为什么需要循环？
  LLM 本身是"金鱼记忆"——它不记得自己刚才做了什么。
  这个循环让 LLM 在每一步都能看到"上一步做了什么、结果是什么"，
  然后决定下一步。这就是 Agent 和普通"调 API 脚本"的本质区别。

Phase 2.7 集成的组件：
  - Planner（TaskPlan）：追踪任务进度，将进度信息注入 system prompt
  - ErrorHandler（ErrorClassifier）：工具执行失败时，分类错误并附加恢复建议
  - 严重级别为 FATAL 的错误会导致 Agent 立即停止（不继续循环）

关键设计决策：
  1. ToolRegistry 是独立的，不耦合在 Agent 中
  2. LLM client 通过依赖注入传入（不是硬编码）
  3. max_turns 安全限制
  4. Planner 和 ErrorClassifier 都是可选的依赖注入
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from agent.core.compressor import ContextCompressor, HybridCompressor
from agent.core.context_cache import ContextCache
from agent.core.error_pattern import ErrorPatternLedger
from agent.core.memory import MemoryManager
from agent.core.reflective_advisor import ReflectiveAdvisor
from agent.core.runtime import RuntimeServices
from agent.core.security import PolicyAction, PolicyDecision, PolicyEngine
from agent.core.state import AgentState, ExecutionContext
from agent.core.summarizer import LLMSummarizer, StaticSummarizer, Summarizer
from agent.core.token_estimator import CharTokenEstimator, TokenEstimator
from agent.core.tool_result_externalizer import ToolResultExternalizer
from agent.core.trace import AgentTrace
from agent.core.types import Message, ToolCall, ToolResult, ToolSpec
from agent.sandbox import create_sandbox_backend
from agent.sandbox.base import SandboxBackend
from agent.tools import (
    register_default_tools,
    register_internal_tools,
    register_tools_from_config,
)

if TYPE_CHECKING:
    from agent.config import AgentConfig
    from agent.core.error_handler import ErrorClassifier
    from agent.core.planner import TaskPlan
    from agent.core.trace import TraceStep

logger = logging.getLogger(__name__)

# TD-008：人工确认 callback 签名——(工具名, 调用参数) -> 是否批准
ApprovalCallback = Callable[[str, dict[str, Any]], bool]


class ToolRegistry:
    """工具注册中心 —— Agent 可以调用的所有工具都在这里。"""

    # 需要做参数级策略检查的工具映射：tool_name -> (resource, operation, arg_name)
    _PARAMETRIC_CHECKS: dict[str, tuple[str, str, str]] = {
        "sandbox_exec": ("sandbox/code", "execute", "code"),
        "file_read": ("file/path", "read", "path"),
        "file_list": ("file/path", "read", "path"),
        "file_write": ("file/path", "write", "path"),
        "file_edit": ("file/path", "write", "path"),
    }

    def __init__(
        self,
        policy: PolicyEngine | None = None,
        execution_context: ExecutionContext | None = None,
        approval_callback: ApprovalCallback | None = None,
        approval_tools: set[str] | None = None,
    ) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._policy = policy
        # TD-004：可选的 ExecutionContext，注入给声明了该参数的工具 handler。
        self._execution_context = execution_context
        # register 时探测并缓存签名结果，execute 热路径只做 O(1) 集合查找。
        self._ctx_aware: set[str] = set()
        # TD-008：可选的人工确认钩子；仅 callback 与 tools 同时存在时生效。
        self._approval_callback = approval_callback
        self._approval_tools = approval_tools

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"工具已注册：{spec.name}")
        self._tools[spec.name] = spec
        # TD-004：探测 handler 是否声明 execution_context 参数并缓存。
        # 取不到签名的 callable（如部分内置函数）按不注入处理。
        try:
            if "execution_context" in inspect.signature(spec.handler).parameters:
                self._ctx_aware.add(spec.name)
        except (TypeError, ValueError):
            pass

    def register_func(
        self, name: str, description: str, parameters: dict[str, Any],
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.register(
                ToolSpec(
                    name=name, description=description, parameters=parameters, handler=fn,
                )
            )
            return fn
        return decorator

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list_schemas(self) -> list[dict[str, Any]]:
        return [t.to_openai_format() for t in self._tools.values()]

    async def execute(self, call: ToolCall) -> ToolResult:
        """执行工具调用，失败时保留异常类名以便 ErrorClassifier 识别。

        支持两类 handler：
          1. 同步 handler，返回任意可字符串化的结果。
          2. 异步 handler，返回 coroutine；执行前会被 await。

        如果 handler 直接返回 ToolResult，则复用其 content 与 success，
        仅把 tool_call_id 补全为当前调用的 id。

        Phase 9：如果注入了 PolicyEngine，则在执行前进行策略检查；
        策略拒绝时返回 ToolResult(success=False)，不抛异常。
        """
        # Phase 9：工具级策略检查
        if self._policy is not None:
            decision = self._policy.evaluate(
                resource="tool",
                operation="execute",
                subject=call.name,
                context={"arguments": call.arguments},
            )
            if decision.action == PolicyAction.DENY:
                logger.warning(
                    "策略拒绝调用工具：%s，原因：%s", call.name, decision.reason
                )
                return ToolResult(
                    tool_call_id=call.id,
                    content=f"策略拒绝：{decision.reason}",
                    success=False,
                )

            # 参数级策略检查
            parametric_decision = self._evaluate_parametric_policy(call)
            if parametric_decision is not None and parametric_decision.action == PolicyAction.DENY:
                logger.warning(
                    "策略拒绝工具参数：%s，原因：%s", call.name, parametric_decision.reason
                )
                return ToolResult(
                    tool_call_id=call.id,
                    content=f"策略拒绝：{parametric_decision.reason}",
                    success=False,
                )

        spec = self._tools.get(call.name)
        if spec is None:
            return ToolResult(tool_call_id=call.id, content=f"未知工具：{call.name}", success=False)

        # TD-008：人工确认钩子（策略检查之后、handler 执行之前）。
        if (
            self._approval_callback is not None
            and self._approval_tools is not None
            and call.name in self._approval_tools
            and not self._approval_callback(call.name, call.arguments)
        ):
            logger.info("用户拒绝工具调用：%s", call.name)
            return ToolResult(
                tool_call_id=call.id,
                content=(
                    f"用户拒绝了 {call.name} 操作。这不是系统错误，"
                    "请与用户确认意图，或改用其他方案，不要盲目重试。"
                ),
                success=False,
            )

        try:
            # TD-004：ctx 感知工具且调用方未显式传入时，注入 ExecutionContext。
            arguments = call.arguments
            if (
                call.name in self._ctx_aware
                and "execution_context" not in arguments
            ):
                arguments = {
                    **arguments,
                    "execution_context": self._execution_context,
                }
            result = spec.handler(**arguments)

            # 支持异步 handler：await coroutine 拿到实际结果
            if asyncio.iscoroutine(result):
                result = await result

            # 如果 handler 已经返回 ToolResult，直接复用并补全 tool_call_id
            if isinstance(result, ToolResult):
                return ToolResult(
                    tool_call_id=call.id, content=result.content, success=result.success,
                )

            content = str(result) if result is not None else ""
            return ToolResult(tool_call_id=call.id, content=content)
        except Exception as e:
            logger.exception("工具执行失败：%s", call.name)
            exc_name = type(e).__name__
            return ToolResult(tool_call_id=call.id, content=f"{exc_name}: {e}", success=False)

    def _evaluate_parametric_policy(
        self, call: ToolCall
    ) -> PolicyDecision | None:
        """对需要参数级检查的工具进行评估。

        Args:
            call: 工具调用请求。

        Returns:
            策略决策；不需要参数级检查时返回 None。
        """
        assert self._policy is not None

        if call.name in self._PARAMETRIC_CHECKS:
            resource, operation, arg_name = self._PARAMETRIC_CHECKS[call.name]
            subject = call.arguments.get(arg_name, "")
            if resource == "file/path":
                subject = self._normalize_file_path_subject(subject)
            return self._policy.evaluate(
                resource=resource,
                operation=operation,
                subject=subject,
                context={"arguments": call.arguments},
            )

        if call.name == "memory_read":
            category = self._extract_memory_category(call.arguments.get("uri", ""))
            if category is not None:
                return self._policy.evaluate(
                    resource="memory/category",
                    operation="read",
                    subject=category,
                    context={"arguments": call.arguments},
                )

        return None

    @staticmethod
    def _normalize_file_path_subject(subject: Any) -> str:
        """对 file/path 类型的 subject 做路径归一化。

        归一化规则：
          1. 先转字符串，防御 LLM 传入非字符串参数。
          2. 反斜杠替换为正斜杠，兼容 Windows 路径。
          3. 统一转小写，避免大小写绕过。

        Args:
            subject: 原始路径参数，可能为任意类型。

        Returns:
            归一化后的路径字符串。
        """
        path = str(subject)
        return path.replace("\\", "/").lower()

    @staticmethod
    def _extract_memory_category(uri: Any) -> str | None:
        """从 hermes://memory/<category>/<entry_id>.jsonl 解析 category。

        Args:
            uri: 记忆 URI，可能为非字符串类型（LLM 参数异常）。

        Returns:
            category 字符串；无法解析时返回 None。
        """
        if not isinstance(uri, str):
            return None
        prefix = "hermes://memory/"
        if not uri.startswith(prefix):
            return None
        rest = uri[len(prefix):]
        parts = rest.split("/")
        if len(parts) != 2 or not parts[1].endswith(".jsonl"):
            return None
        return parts[0]


class Agent:
    """Agent 主类 —— 编排对话和工具执行的完整循环。"""

    def __init__(
        self,
        llm_client: Any,
        system_prompt: str = "你是一个有用的 AI 助手。",
        max_turns: int = 20,
        planner: TaskPlan | None = None,
        error_classifier: type[ErrorClassifier] | None = None,
        sandbox_backend: SandboxBackend | None = None,
        config: AgentConfig | None = None,
        reflective_advisor: ReflectiveAdvisor | None = None,
        persist_error_patterns: bool = False,
        context_cache: ContextCache | None = None,
        token_estimator: TokenEstimator | None = None,
        context_compressor: ContextCompressor | None = None,
        summarizer: Summarizer | None = None,
        summarizer_llm_client: Any | None = None,
        memory_manager: MemoryManager | None = None,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        self.llm = llm_client
        policy = (
            config.security.build_policy_engine() if config is not None else None
        )
        # TD-004：session 级 ExecutionContext，跨 run() 保留，reset() 时清空。
        self.execution_context = ExecutionContext()
        # TD-008：人工确认工具集（config 启用时生效）；callback 由前端注入。
        approval_tools = (
            set(config.agent.human_approval.tools)
            if config is not None and config.agent.human_approval.enabled
            else None
        )
        self.tools = ToolRegistry(
            policy=policy,
            execution_context=self.execution_context,
            approval_callback=approval_callback,
            approval_tools=approval_tools,
        )
        self.system_prompt = system_prompt
        self.max_turns = max_turns
        self.planner = planner
        # Auto-Planner：自动规划开关与步数上限（config.agent.planner）。
        self._planner_enabled = (
            config.agent.planner.enabled if config is not None else False
        )
        self._planner_max_steps = (
            config.agent.planner.max_steps if config is not None else 6
        )
        self.persist_error_patterns = persist_error_patterns

        # 未传入时按 config.sandbox.backend 经工厂创建默认后端（TD-003）；
        # 后端构造失败会优雅降级，不会阻塞 Agent 创建。
        self._sandbox_backend = sandbox_backend or create_sandbox_backend(
            config.sandbox if config is not None else None
        )

        # Phase 4.6：支持通过配置决定加载哪些工具。
        # 传入 config 时按配置注册；未传入时保持向后兼容，注册所有默认工具。
        if config is not None:
            register_tools_from_config(self.tools, self._sandbox_backend, config)
        else:
            register_default_tools(self.tools, self._sandbox_backend)

        if error_classifier is None:
            from agent.core.error_handler import ErrorClassifier
            self.error_classifier: type[ErrorClassifier] = ErrorClassifier
        else:
            self.error_classifier = error_classifier

        self.messages: list[Message] = []

        # Phase 8：历史记忆注入片段，每次 run() 前刷新。
        self._memory_context = ""

        # Phase 5.1：AgentState 接入主循环，用于 Trace 记录执行状态。
        # ExecutionContext 暂不接入，待未来改造工具签名后再使用。
        self.state = AgentState()
        self.trace = AgentTrace()

        # Phase 6.1/6.3：错误模式账本 + 反思策略生成器。
        # 默认 ledger 随 reset() 清空；reflective_advisor 可注入自定义实例。
        self.error_pattern_ledger = ErrorPatternLedger()
        self.reflective_advisor = reflective_advisor or ReflectiveAdvisor()

        # Phase 7.4 / 7.5：上下文缓存 + 压缩子系统。
        self._cleanup_cache_on_exit = (
            config.agent.compression.cleanup_on_exit
            if config is not None
            else True
        )

        # TD-005：内部工具的运行时依赖统一由 RuntimeServices 装配，
        # 新增内部工具不再需要修改本构造函数。
        self.runtime_services = RuntimeServices.from_config(
            config,
            policy,
            self.execution_context,
            context_cache=context_cache,
            memory_manager=memory_manager,
            llm_client=llm_client,
        )
        self.context_cache = self.runtime_services.context_cache
        self.memory_manager = self.runtime_services.memory_manager
        register_internal_tools(self.tools, self.runtime_services, config)

        # 注入的 MemoryManager 未带策略时，补注入同一策略引擎（保持原有语义）。
        if (
            self.memory_manager is not None
            and policy is not None
            and getattr(self.memory_manager, "_policy", None) is None
        ):
            self.memory_manager._policy = policy

        self._setup_compression(
            config,
            token_estimator,
            context_compressor,
            summarizer,
            summarizer_llm_client,
        )

    def _setup_compression(
        self,
        config: AgentConfig | None,
        token_estimator: TokenEstimator | None,
        context_compressor: ContextCompressor | None,
        summarizer: Summarizer | None,
        summarizer_llm_client: Any | None,
    ) -> None:
        """根据配置初始化压缩相关组件。

        只有显式启用压缩且存在 ContextCache 时才创建默认组件；
        未启用时所有压缩组件为 None，避免影响现有行为。
        """
        if config is None or self.context_cache is None:
            self._token_estimator: TokenEstimator | None = None
            self._tool_result_externalizer: ToolResultExternalizer | None = None
            self._summarizer: Summarizer | None = None
            self._context_compressor: ContextCompressor | None = None
            self._compression_budget = 0
            return

        if not config.agent.compression.enabled:
            self._token_estimator = None
            self._tool_result_externalizer = None
            self._summarizer = None
            self._context_compressor = None
            self._compression_budget = 0
            return

        compression = config.agent.compression
        self._compression_budget = max(0, compression.context_window - compression.reserve_tokens)
        self._token_estimator = token_estimator or CharTokenEstimator()
        self._tool_result_externalizer = ToolResultExternalizer(
            cache=self.context_cache,
            threshold=compression.externalize_threshold,
            file_read_preview=compression.file_read_preview_chars,
            exec_success_preview=compression.exec_success_preview_chars,
            exec_error_preview=compression.exec_error_preview_chars,
        )
        if summarizer is not None:
            self._summarizer = summarizer
        elif summarizer_llm_client is not None:
            self._summarizer = LLMSummarizer(
                llm_client=summarizer_llm_client,
                model=compression.summary_model,
                max_tokens=compression.summary_max_tokens,
            )
        else:
            self._summarizer = StaticSummarizer()
        self._context_compressor = context_compressor or HybridCompressor(
            summarizer=self._summarizer,
            protect_first_n=compression.protect_first_n,
            protect_last_n_turns=compression.protect_last_n_turns,
        )

    async def _maybe_compress(self, run_id: str, trace_step: TraceStep | None = None) -> None:
        """如果当前消息历史超过 token 预算，则调用压缩器。"""
        if self._context_compressor is None or self._token_estimator is None:
            return

        original_tokens = self._token_estimator.estimate(self.messages)
        if original_tokens <= self._compression_budget:
            return

        result = await self._context_compressor.compress(
            self.messages, self._compression_budget, self._token_estimator
        )
        self.messages = result.messages

        if trace_step is not None:
            trace_step.add_event(
                "context_compression",
                {
                    "run_id": run_id,
                    "strategy": result.strategy,
                    "original_message_count": result.original_message_count,
                    "compressed_message_count": result.compressed_message_count,
                    "original_token_count": result.original_token_count,
                    "compressed_token_count": result.compressed_token_count,
                    "removed_ranges": result.removed_ranges,
                    "summary": result.summary,
                    "cache_entries": [e.entry_id for e in result.cache_entries],
                },
            )

    def close(self) -> None:
        """关闭 Agent，释放资源。

        当前主要清理 ContextCache（如果配置开启 cleanup_on_exit）。
        """
        if self.context_cache is not None and self._cleanup_cache_on_exit:
            self.context_cache.cleanup()

    def reset(self) -> None:
        """重置 Agent 的运行状态。

        清空对话历史、State、Trace；根据 `persist_error_patterns` 决定是否保留
        错误模式账本（默认清空）。
        """
        self.messages = []
        self.state = AgentState()
        self.trace = AgentTrace()
        # TD-004：session 级 ExecutionContext 随 reset() 清空。
        self.execution_context.clear()
        if not self.persist_error_patterns:
            self.error_pattern_ledger.clear()

    def get_trace(self) -> AgentTrace:
        """获取本次 Agent 运行的执行轨迹。"""
        return self.trace

    def _finalize_run(self, phase: str) -> None:
        """结束本次运行，更新 State、Trace 时间戳，并记录最终状态转换。

        Args:
            phase: 结束时的 phase，如 "finished" 或 "failed"。
        """
        self.state.set_phase(phase)
        self.trace.end_time = datetime.now(timezone.utc)
        self.trace.final_state = {
            "phase": self.state.phase,
            "current_step": self.state.current_step,
            "artifacts": self.state.artifacts,
        }
        current_step = self.trace.current_step()
        if current_step is not None:
            current_step.add_event(
                "state_transition",
                {"phase": self.state.phase, "current_step": self.state.current_step},
            )

    def _build_openai_messages(self) -> list[dict[str, Any]]:
        system_content = self.system_prompt
        if self.planner and len(self.planner.steps) > 0:
            system_content += "\n\n" + self.planner.to_progress_prompt()
        if self._memory_context:
            system_content += "\n\n" + self._memory_context

        result: list[dict[str, Any]] = [{"role": "system", "content": system_content}]

        for msg in self.messages:
            entry: dict[str, Any] = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            if msg.name:
                entry["name"] = msg.name
            result.append(entry)

        return result

    def _classify_tool_error(self, error_content: str) -> tuple[Any, Any, str] | None:
        """从工具错误内容中解析异常并分类，返回 (severity, action, hint) 或 None。"""
        match = re.search(r"(\w+Error|\w+Exception)", error_content)
        if match:
            exc_name = match.group(1)
            try:
                builtins_mod = __builtins__
                if isinstance(builtins_mod, dict):
                    exc_type = builtins_mod.get(exc_name)
                else:
                    exc_type = getattr(builtins_mod, exc_name, None)
                if exc_type and issubclass(exc_type, BaseException):
                    severity, action = self.error_classifier.classify(exc_type(""))
                    hints = {
                        1: "代码有 bug，修改后重试即可",
                        2: "先检查环境中是否有需要的变量/模块",
                        3: "尝试用更简单、更省资源的方法",
                        4: "这个错误超出 Agent 能力范围，需要报告用户",
                    }
                    return (severity, action, hints.get(action.value, ""))
            except Exception:
                pass
        return None

    @staticmethod
    def _parse_plan_steps(text: str, max_steps: int) -> list[str]:
        """从 LLM 输出解析编号步骤描述。

        兼容 `1.` / `1)` / `1、` / `-` / `*` 等列表前缀，跳过前言后语，
        最多返回 max_steps 条；完全无法解析时返回空列表（调用方降级直跑）。
        """
        pattern = re.compile(r"^\s*(?:\d+\s*[.)、]|[-•*])\s*(.+?)\s*$")
        steps: list[str] = []
        for line in text.splitlines():
            match = pattern.match(line)
            if match:
                steps.append(match.group(1))
                if len(steps) >= max_steps:
                    break
        return steps

    async def _maybe_create_plan(self, user_input: str) -> None:
        """启用自动规划且当前无 planner 时，调用 LLM 把任务分解为 TaskPlan。

        降级链（均不阻塞任务直跑）：LLM 调用异常 → 返回；解析 0 步 → 返回。
        外部注入的 planner 优先，不会被覆盖。
        """
        if not self._planner_enabled or self.planner is not None:
            return
        from agent.core.planner import TaskPlan

        planning_prompt = (
            f"把以下任务分解为不超过 {self._planner_max_steps} 个有序执行步骤。"
            "只输出编号步骤列表（每行一步），不要解释、不要前言后语。\n\n"
            f"任务：{user_input}"
        )
        try:
            response = await self.llm.chat(
                [{"role": "user", "content": planning_prompt}], tools=None
            )
        except Exception as exc:  # noqa: BLE001 —— 规划失败不阻塞主任务
            logger.warning("自动规划调用失败，直接执行任务：%s", exc)
            return
        text = response.get("content", "") if isinstance(response, dict) else str(response)
        descriptions = self._parse_plan_steps(text, self._planner_max_steps)
        if not descriptions:
            logger.info("自动规划未解析出步骤，直接执行任务")
            return
        plan = TaskPlan(goal=user_input[:50])
        for idx, desc in enumerate(descriptions, 1):
            plan.add_step(f"step{idx}", desc)
        plan.start_next()
        self.planner = plan
        logger.info("自动规划生成 %d 个步骤", len(descriptions))

    async def run(self, user_input: str) -> str:
        run_id = uuid.uuid4().hex
        self.trace.start_time = datetime.now(timezone.utc)
        self.messages.append(Message(role="user", content=user_input))

        # Auto-Planner：主循环前按需自动生成计划
        await self._maybe_create_plan(user_input)

        # 初始阶段：running
        # 如果外部已经启动了 Planner，把当前步骤同步到 State
        if self.planner and self.planner.current_step:
            initial_step = self.planner.current_step.name
        else:
            initial_step = None
        self.state.set_phase("running", initial_step)

        # Phase 8：启动时注入历史记忆
        self._memory_context = ""
        if self.memory_manager is not None:
            self._memory_context = await self.memory_manager.inject_async(user_input)

        trace_step: TraceStep | None = None
        try:
            for turn in range(self.max_turns):
                # 每个轮次对应 Trace 中的一个 step
                trace_step = self.trace.add_step(turn)
                if turn == 0:
                    # 记录初始状态转换
                    trace_step.add_event(
                        "state_transition",
                        {"phase": self.state.phase, "current_step": self.state.current_step},
                    )

                # Phase 7.5：若超过 token 预算，先压缩历史
                await self._maybe_compress(run_id, trace_step)

                # 构建 OpenAI 消息，同时提取 system prompt 摘要
                openai_messages = self._build_openai_messages()
                system_prompt_summary = ""
                if openai_messages and openai_messages[0].get("role") == "system":
                    system_prompt_summary = openai_messages[0].get("content", "")[:200]

                # 记录 LLM 请求（不保存完整 messages，只记录元数据）
                trace_step.add_event(
                    "llm_request",
                    {
                        "messages_count": len(self.messages),
                        "tools_count": len(self.tools.list_schemas()),
                        "system_prompt_summary": system_prompt_summary,
                    },
                )

                response = await self.llm.chat(
                    messages=openai_messages,
                    tools=self.tools.list_schemas() or None,
                )

                # 记录 LLM 响应（content 做摘要，避免 Trace 过大）
                response_content = response.get("content", "") or ""
                trace_step.add_event(
                    "llm_response",
                    {
                        "content_summary": response_content[:200],
                        "tool_calls": [
                            {"name": tc["function"]["name"], "id": tc["id"]}
                            for tc in (response.get("tool_calls") or [])
                        ],
                    },
                )

                tool_calls_data = response.get("tool_calls")
                assistant_msg = Message(
                    role="assistant",
                    content=response.get("content", "") or "",
                    tool_calls=(
                        [
                            ToolCall(id=tc["id"], name=tc["function"]["name"],
                                     arguments=json.loads(tc["function"]["arguments"]))
                            for tc in tool_calls_data
                        ]
                        if tool_calls_data else None
                    ),
                )
                self.messages.append(assistant_msg)

                if not assistant_msg.tool_calls:
                    # 纯文本回复，任务自然结束
                    self._finalize_run("finished")
                    return assistant_msg.content

                # 执行工具，带错误分类
                fatal_occurred = False
                any_failure = False
                for tc in assistant_msg.tool_calls:
                    result = await self.tools.execute(tc)
                    raw_content = result.content
                    result_content = raw_content

                    # 记录工具执行事件（始终保留原始内容）
                    trace_step.add_event(
                        "tool_execution",
                        {
                            "tool": tc.name,
                            "arguments": tc.arguments,
                            "success": result.success,
                            "content": raw_content,
                        },
                    )

                    # Phase 7.5：过长工具结果外迁（错误分类仍使用原始 raw_content）
                    if self._tool_result_externalizer is not None:
                        externalizer = self._tool_result_externalizer
                        result_content, entry = externalizer.externalize_if_needed(
                            run_id=run_id,
                            tool_name=tc.name,
                            content=raw_content,
                            success=result.success,
                        )
                        if entry is not None:
                            trace_step.add_event(
                                "tool_result_externalized",
                                {
                                    "tool": tc.name,
                                    "entry_id": entry.entry_id,
                                    "uri": entry.uri,
                                    "original_length": entry.content_length,
                                    "summary": entry.summary,
                                },
                            )

                    if not result.success:
                        any_failure = True
                        classified = self._classify_tool_error(raw_content)
                        if classified:
                            severity, action, hint = classified
                            # 记录错误分类事件（保留原始分类结果）
                            trace_step.add_event(
                                "error_classification",
                                {
                                    "severity": severity.name,
                                    "action": action.name,
                                    "hint": hint,
                                },
                            )

                            # Phase 6.1/6.2：记录错误模式并生成反思建议
                            pattern = self.error_pattern_ledger.record(tc.name, raw_content)
                            advice = self.reflective_advisor.advise(pattern, severity, action)

                            effective_severity = advice.severity
                            effective_action = advice.action

                            result_content = (
                                f"[工具执行失败]\n错误: {result_content}\n"
                                f"严重程度: {effective_severity.name}\n"
                                f"建议恢复策略: {effective_action.name}\n"
                                f"提示: {hint}"
                            )
                            if advice.hint:
                                result_content += f"\n反思提示: {advice.hint}"

                            # 当生成了反思提示或发生升级时，记录 reflection 事件
                            if advice.hint or advice.is_escalated:
                                trace_step.add_event("reflection", advice.reflection_payload)

                            if effective_severity.value >= 3:  # FATAL
                                fatal_occurred = True

                    self.messages.append(Message(
                        role="tool", content=result_content,
                        tool_call_id=result.tool_call_id, name=tc.name,
                    ))

                    # finish 工具：任务完成，终止主循环并返回最终结果
                    if tc.name == "finish":
                        if self.planner and self.planner.current_step:
                            self.planner.complete_current()
                        self._finalize_run("finished")
                        return result_content

                # FATAL 错误：给 LLM 最后一轮机会解释，然后退出
                if fatal_occurred:
                    self._finalize_run("failed")
                    # 记录这次额外的 LLM 调用，保证 Trace 完整
                    await self._maybe_compress(run_id, trace_step)
                    fatal_messages = self._build_openai_messages()
                    fatal_system_summary = ""
                    if fatal_messages and fatal_messages[0].get("role") == "system":
                        fatal_system_summary = fatal_messages[0].get("content", "")[:200]
                    trace_step.add_event(
                        "llm_request",
                        {
                            "messages_count": len(self.messages),
                            "tools_count": 0,
                            "system_prompt_summary": fatal_system_summary,
                        },
                    )
                    try:
                        response = await self.llm.chat(
                            messages=fatal_messages, tools=None,
                        )
                        final_content = response.get("content", "") or ""
                        trace_step.add_event(
                            "llm_response",
                            {
                                "content_summary": final_content[:200],
                                "tool_calls": [],
                            },
                        )
                    except Exception:
                        final_content = ""
                        trace_step.add_event(
                            "llm_response",
                            {"content_summary": "", "tool_calls": []},
                        )
                    if not final_content:
                        final_content = "发生致命错误，无法继续。"
                    self.messages.append(Message(role="assistant", content=final_content))
                    if self.planner and self.planner.current_step:
                        self.planner.current_step.mark_failed("FATAL 错误，任务中止")
                    return final_content

                # 只有当本轮所有工具都成功时，才推进计划步骤
                if not any_failure and self.planner and self.planner.current_step:
                    old_step = self.planner.current_step.name
                    self.planner.complete_current()
                    self.planner.start_next()
                    new_step = self.planner.current_step.name if self.planner.current_step else None
                    # 更新 State 当前步骤（此时 phase 仍然是 running）
                    self.state.set_phase("running", new_step)
                    trace_step.add_event(
                        "state_transition",
                        {"phase": self.state.phase, "current_step": self.state.current_step},
                    )
                    trace_step.add_event(
                        "planner_transition",
                        {"from": old_step, "to": new_step},
                    )

            # 达到最大对话轮数限制
            self._finalize_run("failed")
            return "Agent 已达到最大对话轮数限制。"
        finally:
            # Phase 8：运行结束时提取并持久化记忆
            if self.memory_manager is not None and trace_step is not None:
                saved_entries = self.memory_manager.record(
                    self.trace, self.state, {"run_id": run_id}
                )
                if saved_entries:
                    trace_step.add_event(
                        "memory_recorded",
                        {
                            "entries_count": len(saved_entries),
                            "categories": sorted(
                                {e.category.value for e in saved_entries}
                            ),
                            "entry_ids": [e.entry_id for e in saved_entries],
                        },
                    )
