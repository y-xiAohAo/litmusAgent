# Phase 4.5 错误恢复场景测试规格切片

> 来源：`docs/progress-spec.md` 第 4 节 Phase 4.5 + 项目上下文补全
> 状态：已批准，进入实现
> 批准人：用户（回复 "放行"）

---

## 目标

编写覆盖 Agent **错误恢复路径**的集成测试，验证 Agent 在完整工作流中遇到各类错误时，能否根据 `ErrorClassifier` 的提示进行自我修正、降级处理或正确终止。

---

## 必须做

1. **扩展 `tests/test_integration.py`**
   - 新增错误恢复测试类 `TestErrorRecoveryWorkflow`。
   - 至少覆盖 4 个场景：
     - **代码错误自我修复**：`sandbox_exec` 抛 `SyntaxError` → LLM 看到恢复建议 → 修正代码 → 成功。
     - **环境探查后修复**：`sandbox_exec` 抛 `NameError` → LLM 用 `file_list`/`file_read` 检查环境 → 再次执行 → 成功。
     - **资源耗尽降级**：`sandbox_exec` 超时或内存不足 → LLM 收到 `DEGRADE` 建议 → 简化任务 → 成功。
     - **FATAL 错误终止**：`sandbox_exec` 抛 `PermissionError` → Agent 停止并报告错误。

2. **验证错误分类信息正确传递到 LLM**
   - 断言 tool result 内容包含 `[工具执行失败]`、严重级别名、恢复策略名、提示。

3. **验证 Planner 在错误场景下的状态**
   - `RECOVERABLE`/`DEGRADE` 错误：当前步骤保持 `ACTIVE`，不被错误推进。
   - `FATAL` 错误：当前步骤被标记为 `FAILED`。

4. **使用 Mock，不依赖真实 Docker**
   - 复用/扩展 `StatefulMockBackend`，让 `execute_code` 能根据代码内容或调用顺序返回错误/成功。

---

## 严禁做

1. 不修改 `ErrorClassifier` 的现有规则映射（除非测试暴露规则确实缺失）。
2. 不修改 `Agent.run()` 的核心错误处理逻辑，除非测试暴露必要缺陷且修改是最小必要改动。
3. 不写依赖真实 Docker daemon 的测试。
4. 不超出 Phase 4.5 范围（不做 Phase 4.6 配置驱动，不做 Phase 5 核心机制扩展）。
5. 不使用文件备份替代版本控制。

---

## 验收标准

1. `python -m pytest tests/test_integration.py::TestErrorRecoveryWorkflow -v` 全部通过。
2. `python -m pytest tests/ -q` 不新增失败，总通过数 > 167。
3. `python -m mypy src/` 零错误。
4. `python -m ruff check src/ tests/` 零新增错误。
5. 所有新增代码有完整类型标注和中文注释。

---

## 涉及文件

- **主要修改**：`tests/test_integration.py`
- **可能涉及**（仅在必要时）：`src/agent/core/engine.py`、`src/agent/core/error_handler.py`
