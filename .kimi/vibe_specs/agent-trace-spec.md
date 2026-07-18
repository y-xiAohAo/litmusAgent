# Agent Trace Spec — Task 5.1

> 本规格切片由 Phase 5.1 设计讨论产生，边界已经用户确认。

---

## 目标

实现 Agent Trace（执行轨迹记录），让 Agent 的每次运行都能生成可观测、可复盘的执行轨迹，并把 `AgentState` 接入 `Agent.run()` 主循环。

---

## 必须做

1. **新增 Trace 数据模型** (`src/agent/core/trace.py`)
   - 定义 `AgentTrace`、`TraceStep`、`TraceEvent` 三个 dataclass。
   - `AgentTrace` 包含 `steps: list[TraceStep]`、`start_time`、`end_time`、`final_state`。
   - `TraceStep` 包含 `step_index`（轮次索引）和 `events: list[TraceEvent]`。
   - `TraceEvent` 包含 `event_type: str`、`timestamp: datetime`、`payload: dict[str, Any]`。
   - 提供 `AgentTrace.to_dict()` / `AgentTrace.to_json()` 导出方法。

2. **把 AgentState 接入主循环** (`src/agent/core/engine.py`)
   - `Agent` 持有 `self.state: AgentState` 实例。
   - `run()` 开始时设置 `phase="running"`。
   - `finish` 成功时设置 `phase="finished"`。
   - FATAL 错误或达到 `max_turns` 时设置 `phase="failed"`。
   - 在 `AgentState` 变化时记录 `state_transition` Trace 事件。

3. **在关键节点记录 Trace 事件**
   - 每轮 LLM 调用前：记录 `llm_request`（messages 数量、tools 数量、system prompt 摘要）。
   - 每轮 LLM 返回后：记录 `llm_response`（content 摘要、tool_calls 列表）。
   - 每个 Tool 执行后：记录 `tool_execution`（tool 名称、参数、结果 success/content）。
   - 错误分类后：记录 `error_classification`（severity、action、hint）。
   - Planner 步骤变化后：记录 `planner_transition`（step 名称、旧状态、新状态）。

4. **暴露获取 Trace 的方法**
   - `Agent` 提供 `get_trace()` 方法，返回本次运行的 `AgentTrace`。

5. **测试覆盖** (`tests/test_trace.py`，共 11 个测试）
   - 基础测试：
     - `test_trace_records_simple_conversation`：无 tool call，验证 1 个 step 和基本事件。
     - `test_trace_records_tool_execution`：单轮调用 tool，验证 `tool_execution` 事件。
     - `test_trace_records_error_classification`：Tool 失败，验证 `error_classification` 事件。
     - `test_trace_records_multi_turn_conversation`：多轮调用，验证 step 数量递增。
     - `test_state_updates_during_run`：验证 phase 从 running → finished 的流转。
     - `test_trace_records_max_turns_failure`：验证达到 max_turns 时 phase 变为 failed。
   - 端到端测试：
     - `test_trace_end_to_end_with_planner`：带 Planner 的工作流，验证 `planner_transition` 和 State 同步。
     - `test_trace_end_to_end_error_recovery`：错误恢复工作流，验证 `error_classification` 事件。
     - `test_trace_end_to_end_multi_tool_workflow`：多 Tool 工作流，验证所有 tool 都被记录。
     - `test_trace_to_json_round_trip`：验证 Trace JSON 序列化往返。
     - `test_trace_state_artifacts_recorded`：验证 AgentState artifacts 被记录到 final_state。

---

## 严禁做

- 不实现上下文压缩、长期记忆、反思式错误恢复、安全策略引擎（Phase 6~9）。
- 不改变 `Agent.run()` 的核心语义（只插入记录点和 State 更新）。
- 不引入外部数据库或持久化层。
- 不修改现有 Tool 的实现。
- 不接入 `ExecutionContext`（已明确为独立技术债，待未来改造工具签名后处理）。

---

## 验收标准

- `python -m pytest tests/test_trace.py -v` 全部通过。
- `python -m pytest tests/ -q` 不新增失败，总通过数 ≥ 189。
- `python -m mypy src/` 零错误。
- `python -m ruff check src/ tests/` 零新增错误。
- 所有新增 public 函数/类有完整类型标注和中文 docstring。

---

## 涉及文件

- 新增：`src/agent/core/trace.py`
- 修改：`src/agent/core/engine.py`
- 新增：`tests/test_trace.py`

---

## 设计决策

1. **Trace 与 messages 分离**：messages 给 LLM 看，Trace 给 Agent/开发者看。
2. **Step + Event 结构**：按 Agent 主循环轮次组织，便于按轮次复盘。
3. **AgentState 接入**：Phase 5.1 只接入 AgentState，不接入 ExecutionContext。
4. **不记录完整 messages**：Trace 只记录 messages 元数据，避免 Trace 过大。
5. **Phase 用 `"running"`**：ReAct 范式下不区分 planning/executing。
6. **Planner 初始步骤同步到 State**：`run()` 开始时，如果 Planner 已有当前步骤，将其同步到 `AgentState.current_step`，保证 Trace 中的 state_transition 事件完整。
