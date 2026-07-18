# Task 6.1 Spec：错误模式账本（Error Pattern Ledger）

> 本 spec 属于 Phase 6「反思式错误恢复」的第一个 Task。
> 在 Agent 主循环接入反思层之前，先实现一个能记录、识别、提取错误模式的轻量账本。

---

## 目标

实现 `src/agent/core/error_pattern.py`，提供两类能力：

1. **错误模式记录**：在单次 `Agent.run()` 运行中，按 `(工具名, 异常类型)` 聚类记录工具失败事件。
2. **错误模式识别**：从工具返回的错误内容中提取异常类型名，并在重复次数达到阈值后，进一步提取错误消息中的关键标识（如 NameError 中的变量名、KeyError 中的键名）。

这个模块是后续反思提示生成器（Task 6.2）和主循环接入（Task 6.3）的数据基础。

---

## 必须做

1. **新增 `src/agent/core/error_pattern.py`**
   - 定义 `ErrorPattern` dataclass：
     - `tool_name: str`：发生错误的工具名。
     - `exc_type: str`：异常类型名（如 `"NameError"`）。
     - `count: int`：出现次数。
     - `messages: list[str]`：最近 N 条原始错误消息（去重或保留最近若干条）。
     - `last_seen_at: datetime`：最近一次出现时间（UTC）。
   - 定义 `ErrorPatternLedger` 类：
     - `record(tool_name, error_content)`：记录一次错误，返回对应的 `ErrorPattern`。
     - `match(tool_name, error_content) -> ErrorPattern | None`：查询是否已有匹配模式。
     - `get_pattern(tool_name, exc_type) -> ErrorPattern | None`：按主键查询。
     - `clear()`：清空账本。
   - 实现 `_extract_exception_type(error_content: str) -> str | None`：从错误内容中匹配 `XxxError` 或 `XxxException`。
   - 实现 `_extract_message_signature(exc_type: str, error_content: str) -> str | None`：
     - 对 `NameError` 提取引号内的变量名；
     - 对 `KeyError` / `AttributeError` 提取引号内的键/属性名；
     - 其他类型返回 `None`（表示不做次级匹配）。

2. **新增 `tests/test_error_pattern.py`**
   - 覆盖以下场景：
     - 首次记录错误后生成新的 `ErrorPattern`，`count == 1`。
     - 同一工具、同一异常类型连续记录，`count` 递增。
     - 不同工具或不同异常类型分开计数。
     - 从错误内容中正确提取 `NameError`、`KeyError`、`TimeoutError` 等类型名。
     - `NameError` 消息中提取变量名作为消息签名。
     - `clear()` 后账本为空。

3. **所有 public 类/函数必须有中文 docstring，函数签名完整类型标注。**

---

## 严禁做

- 不修改 `src/agent/core/error_handler.py` 的分类规则。
- 不修改 `src/agent/core/engine.py` 的主循环。
- 不接入 `ExecutionContext`。
- 不修改任何 Tool 签名或 Tool 实现。
- 不实现反思提示生成逻辑（留给 Task 6.2）。
- 不实现 action/severity 升级逻辑（留给 Task 6.2）。
- 不引入外部持久化层（数据库、文件）。

---

## 涉及文件

- 新增：`src/agent/core/error_pattern.py`
- 新增：`tests/test_error_pattern.py`

---

## 验收标准

1. `python -m pytest tests/test_error_pattern.py -v` 全部通过。
2. `python -m pytest tests/ -q` 不新增失败，总通过数 ≥ 189。
3. `python -m mypy src/` 零新增错误。
4. `python -m ruff check src/ tests/` 零新增错误。
5. 所有新增 public 函数/类有中文 docstring。
6. 不改动除上述两个文件以外的任何源码文件。

---

## 设计决策记录

- **主键 = (tool_name, exc_type)**：同类错误首先按工具和异常类型聚类，符合 Agent 的运行方式。
- **次级匹配延迟到阈值后**：Task 6.1 只提供签名提取能力，具体「达到阈值后再看相似度」的策略在 Task 6.2 中实现。
- **账本生命周期默认单次运行**：`ErrorPatternLedger` 本身不决定生命周期，后续由 `Agent` 在 `reset()` 中控制是否清空。
- **异常类型提取复用与 engine.py 一致的规则**：匹配 `\w+Error|\w+Exception`，与 `_classify_tool_error` 的正则保持一致。
