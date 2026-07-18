# Phase 4.4 端到端集成测试规格切片

> 来源：`docs/progress-spec.md` 第 4 节 Phase 4.4
> 状态：已批准，进入实现
> 批准人：用户（回复 "放行"）

---

## 目标

编写覆盖完整 Agent 工作流（**计划 → 执行 → 观察 → 交付**）的集成测试，验证 Phase 4 工具链在真实多轮交互中的协同行为。

具体工作流：在一个 `Agent.run()` 中，LLM 依次调用 `sandbox_exec` 执行代码、`file_list`/`file_read` 观察产物、最后调用 `finish` 交付最终结果。

---

## 必须做

1. **扩展 `tests/test_integration.py`**
   - 新增端到端测试类 `TestEndToEndWorkflow`。
   - 至少覆盖 2 个完整工作流场景：
     - **场景 A：无 Planner 的完整工作流**
       1. `sandbox_exec` 写文件（如 `/tmp/result.txt`）。
       2. `file_list` 观察 `/tmp` 目录。
       3. `file_read` 读取文件内容。
       4. `finish` 交付最终结果。
       5. 断言 `Agent.run()` 返回 `finish` 的 `result`，且工具调用顺序正确。
     - **场景 B：带 Planner 的完整工作流**
       1. `TaskPlan` 包含 3 个步骤：`write_file` → `inspect` → `deliver`。
       2. LLM 按步骤依次调用工具，Planner 自动推进。
       3. 最后调用 `finish` 结束。
       4. 断言所有步骤为 `COMPLETED`，且返回最终结果。

2. **增强 Mock 沙箱后端**
   - 扩展现有 `MockSandboxBackend`，支持 `get_file` 与动态 `execute_code` 响应。
   - `execute_code` 根据代码内容返回结果（识别写文件、列表目录等操作）。
   - 全部在内存模拟，不连接真实 Docker。

3. **中文 docstring 与注释**
   - 新增 Mock 类、测试类、辅助函数必须有中文 docstring。
   - 测试断言意图用中文注释说明。

---

## 严禁做

1. 不修改四个 Tool 的实现（`sandbox_exec.py`、`file_read.py`、`file_list.py`、`finish.py`）。
2. 不修改 `Agent.run()` 核心逻辑，除非测试暴露必要缺陷且修改是最小必要改动。
3. 不写依赖真实 Docker daemon 的测试。
4. 不超出 Phase 4.4 范围（不做 Phase 4.5 错误恢复、不做 Phase 4.6 配置驱动）。
5. 不使用文件备份替代版本控制。

---

## 验收标准

1. `python -m pytest tests/test_integration.py -v` 新增测试全部通过。
2. `python -m pytest tests/ -q` 不新增失败，总通过数 ≥ 167。
3. `python -m mypy src/` 零错误。
4. `python -m ruff check src/ tests/` 零新增错误。
5. 所有新增代码有完整类型标注和中文注释。

---

## 涉及文件

- **主要修改**：`tests/test_integration.py`
- **可能涉及**（仅在必要时）：`src/agent/core/engine.py`
