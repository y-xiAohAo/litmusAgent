# Task 6.3 Spec：接入 Agent 主循环与 Trace

> 本 spec 属于 Phase 6「反思式错误恢复」的第三个 Task。
> 把 Task 6.1 的错误模式账本和 Task 6.2 的反思策略生成器接入 `Agent.run()` 主循环，
> 让重复错误真正影响 Agent 行为，并把反思事件写入 Trace。

---

## 目标

修改 `src/agent/core/engine.py` 的 `Agent` 类，实现：

1. **持有错误模式账本**：`Agent` 实例化时创建 `ErrorPatternLedger`。
2. **可注入反思策略生成器**：通过 `reflective_advisor` 参数注入 `ReflectiveAdvisor`，未注入时使用默认实例。
3. **工具失败时记录并反思**：在 `run()` 的错误处理路径中，工具失败后：
   - 用 `ErrorClassifier` 分类，得到原始 `(severity, action, hint)`；
   - 用 `ErrorPatternLedger.record()` 记录错误；
   - 用 `ReflectiveAdvisor.advise()` 生成 `ReflectionAdvice`；
   - 使用 Advisor 返回的 `severity/action` 作为 effective 策略；
   - 把原始 `hint` 和 Advisor 的 `hint` 同时放入返回 LLM 的错误消息；
   - 如果 effective severity 为 FATAL，触发现有 FATAL 退出逻辑。
4. **Trace 记录**：
   - `error_classification` 事件记录 **原始** 分类结果；
   - 当生成了反思提示或发生升级时，追加 `reflection` 事件，payload 使用 `ReflectionAdvice.reflection_payload`。
5. **生命周期控制**：`Agent.reset()` 默认清空 ledger；可通过 `persist_error_patterns=True` 保留。

---

## 必须做

1. **修改 `src/agent/core/engine.py`**
   - 导入 `ErrorPatternLedger`、`ReflectiveAdvisor`。
   - 扩展 `Agent.__init__` 参数：
     - `reflective_advisor: ReflectiveAdvisor | None = None`
     - `persist_error_patterns: bool = False`
   - 在 `Agent` 中持有：
     - `self.error_pattern_ledger: ErrorPatternLedger`
     - `self.reflective_advisor: ReflectiveAdvisor`
   - 修改 `Agent.reset()`：
     - 如果 `persist_error_patterns` 为 False，调用 `self.error_pattern_ledger.clear()`。
   - 修改 `Agent.run()` 中工具失败的逻辑：
     - 保持原有 `_classify_tool_error()` 调用，得到原始 `(severity, action, hint)`。
     - 调用 `self.error_pattern_ledger.record(tc.name, result.content)`。
     - 调用 `self.reflective_advisor.advise(pattern, severity, action)`。
     - 使用 advice 的 `severity` / `action` 作为 effective 策略更新返回 LLM 的消息。
     - 如果 `advice.hint` 非空，在错误消息末尾追加 `
反思提示: {advice.hint}`。
     - 如果 effective severity 为 FATAL，设置 `fatal_occurred = True`。
     - 在原有 `error_classification` TraceEvent 之后，当 `advice.hint != ""` 或 `advice.is_escalated` 时，追加 `reflection` TraceEvent。

2. **新增 `tests/test_reflective_integration.py`**
   - 覆盖以下场景：
     - 同一 `NameError` 出现 2 次，第二次返回给 LLM 的错误消息包含「反思提示」。
     - `NameError` 出现 4 次，severity 升级为 DEGRADE，返回消息包含升级后的策略。
     - `NameError` 出现 6 次，severity 升级为 FATAL，Agent 停止循环。
     - Trace 中包含 `reflection` 事件。
     - `Agent.reset()` 默认清空 ledger；`persist_error_patterns=True` 时保留。
     - 注入自定义 `ReflectiveAdvisor`（如 threshold=3）后，行为按自定义阈值生效。

3. **所有新增/修改的 public 函数/类必须有中文 docstring，函数签名完整类型标注。**

---

## 严禁做

- 不修改 `src/agent/core/error_handler.py` 的分类规则。
- 不修改 `src/agent/core/error_pattern.py` 的数据层逻辑。
- 不修改 `src/agent/core/reflective_advisor.py` 的策略层逻辑。
- 不接入 `ExecutionContext`。
- 不修改任何 Tool 签名或 Tool 实现。
- 不调用 LLM 做总结。
- 不改变 `Agent.run()` 的整体控制流（只在错误处理路径中插入逻辑）。
- 不引入外部持久化层。

---

## 涉及文件

- 修改：`src/agent/core/engine.py`
- 新增：`tests/test_reflective_integration.py`
- 只读依赖：`src/agent/core/error_pattern.py`、`src/agent/core/reflective_advisor.py`、`src/agent/core/error_handler.py`

---

## 验收标准

1. `python -m pytest tests/test_reflective_integration.py -v` 全部通过。
2. `python -m pytest tests/ -q` 不新增失败，总通过数 ≥ 当前基线（219）。
3. `python -m mypy src/` 零新增错误。
4. `python -m ruff check src/ tests/` 零新增错误。
5. 所有新增/修改 public 类/函数有中文 docstring 和完整类型标注。
6. 不改动除 `engine.py` 和新增测试文件以外的源码文件。

---

## 设计决策记录

- **原始分类保留在 error_classification 事件中**：`ErrorClassifier` 的职责是分类，反思层是在其基础上做二次决策，两者不要混淆。
- **effective 策略用于 LLM 消息和 FATAL 判断**：LLM 看到的是 Agent 当前认为最合适的恢复策略。
- **反射提示独立成段**：同时保留原有提示和反思提示，信息最完整，对现有测试的 substring 断言影响最小。
- **reflective_advisor 采用依赖注入**：与 `planner`、`error_classifier` 保持一致风格，便于测试和自定义。
- **ledger 生命周期默认单次运行**：通过 `persist_error_patterns` 参数控制，与之前决策一致。
