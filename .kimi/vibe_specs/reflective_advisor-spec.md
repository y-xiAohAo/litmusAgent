# Task 6.2 Spec：反思策略生成器（ReflectiveAdvisor）

> 本 spec 属于 Phase 6「反思式错误恢复」的第二个 Task。
> 在 Task 6.1 的错误模式账本基础上，实现一个基于硬编码规则的反思策略生成器。

---

## 目标

实现 `src/agent/core/reflective_advisor.py`，让 Agent 能够根据错误模式的出现次数和异常类型，主动生成结构化反思建议，并在必要时升级恢复策略。

核心能力：

1. **反思提示生成**：当同类错误重复出现时，生成递进式提示文本。
2. **策略升级**：当重复次数达到更高阈值时，按异常类型升级 `ErrorSeverity` / `RecoveryAction`。
3. **签名收敛分析**：在重复次数达到阈值后，对最近错误消息做签名频率统计，生成更具体的提示。

---

## 必须做

1. **新增 `src/agent/core/reflective_advisor.py`**
   - 定义 `ReflectionAdvice` dataclass：
     - `hint: str`：追加给 LLM 的反思提示文本。
     - `severity: ErrorSeverity`：原始或升级后的严重程度。
     - `action: RecoveryAction`：原始或升级后的恢复策略。
     - `is_escalated: bool`：是否发生了升级。
     - `reflection_payload: dict[str, Any]`：供 Trace 记录的结构化数据。
   - 定义 `ReflectiveAdvisor` 类：
     - 构造参数：
       - `reflection_threshold: int = 2`：开始生成反思提示的重复次数。
       - `escalate_threshold: int = 4`：开始升级 action/severity 的重复次数。
     - 方法：
       - `advise(pattern: ErrorPattern, severity: ErrorSeverity, action: RecoveryAction) -> ReflectionAdvice`：根据模式、严重程度和恢复策略生成反思建议。
   - 实现按异常类型定制的升级路径：
     - `NameError` / `KeyError` / `AttributeError` / `ImportError` / `ModuleNotFoundError` / `FileNotFoundError`：路径为 `RECOVERABLE + CHECK_CONTEXT` → `DEGRADE + SIMPLIFY_TASK` → `FATAL + REPORT`。
     - `SyntaxError` / `IndentationError` / `TypeError` / `ValueError` / `ZeroDivisionError` / `IndexError`：路径为 `RECOVERABLE + REWRITE_CODE` → `DEGRADE + SIMPLIFY_TASK` → `FATAL + REPORT`。
     - `MemoryError` / `TimeoutError` / `RecursionError`：路径为 `DEGRADE + SIMPLIFY_TASK` → `FATAL + REPORT`。
     - `PermissionError` / `UnknownError`：路径为 `FATAL + REPORT`。
     - **关键约束**：以 `ErrorClassifier` 输出的 `(severity, action)` 作为当前阶段，只向上推进，绝不降级或覆盖。
   - 实现签名收敛判断：
     - 当 `pattern.count >= reflection_threshold` 且输入 severity 不是 `FATAL` 时，对 `pattern.messages` 中的消息调用 `_extract_message_signature()` 提取签名；
     - 统计各签名出现频率；
     - 如果某个签名占比超过一半，生成包含该签名的具体提示；
     - 否则生成泛化提示。

2. **新增 `tests/test_reflective_advisor.py`**
   - 覆盖以下场景：
     - 首次出现错误（count < threshold）不生成反思提示，is_escalated 为 False。
     - 重复达到 threshold 后生成提示，但尚未升级 action。
     - 不同异常类型的升级路径不同。
     - `NameError` 重复且签名收敛时，提示包含具体变量名。
     - `TimeoutError` 作为初始 DEGRADE，达到 escalate_threshold 后升级为 FATAL + REPORT。
     - `PermissionError` 不升级。
     - 自定义 threshold / escalate_threshold 生效。

3. **所有 public 类/函数必须有中文 docstring，函数签名完整类型标注。**

---

## 严禁做

- 不修改 `src/agent/core/error_handler.py` 的分类规则。
- 不修改 `src/agent/core/engine.py` 的主循环。
- 不接入 `ExecutionContext`。
- 不修改任何 Tool 签名或 Tool 实现。
- 不调用 LLM 做总结或根因分析。
- 不引入外部持久化层。
- 不把反思逻辑直接写入 `error_pattern.py`（保持数据层与策略层分离）。

---

## 涉及文件

- 新增：`src/agent/core/reflective_advisor.py`
- 新增：`tests/test_reflective_advisor.py`
- 只读依赖：`src/agent/core/error_pattern.py`（复用 `_extract_message_signature`）
- 只读依赖：`src/agent/core/error_handler.py`（使用 `ErrorSeverity` / `RecoveryAction`）

---

## 验收标准

1. `python -m pytest tests/test_reflective_advisor.py -v` 全部通过。
2. `python -m pytest tests/ -q` 不新增失败，总通过数 ≥ 当前基线。
3. `python -m mypy src/` 零新增错误。
4. `python -m ruff check src/ tests/` 零新增错误。
5. 所有新增 public 类/函数有中文 docstring 和完整类型标注。
6. 不改动除上述新增文件以外的任何源码文件。

---

## 设计决策记录

- **硬编码规则 + 计数阈值**：不调用 LLM，保证确定性、低成本、可测试。
- **按异常类型定制升级路径**：不同异常类型的恢复语义不同，但起点必须是 `ErrorClassifier` 的输出，Advisor 只做升级不做覆盖。
- **签名收敛判断属于轻量分析**：复用 6.1 的 `_extract_message_signature()`，6.2 只负责统计和使用。
- **输出结构化 dict**：方便 6.3 接入主循环时直接用于拼接错误消息和写入 Trace。
