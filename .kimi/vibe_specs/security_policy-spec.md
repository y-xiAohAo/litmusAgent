# 安全策略引擎 — Phase 9.5~9.7 规格切片

> 本文件由 vibe-coding harness 管理，描述 Phase 9 会话 3 的边界、验收标准与严禁事项。
> 涉及模块：`src/agent/core/engine.py`、`src/agent/core/memory.py`、
> `src/agent/core/default_security_rules.yaml`、测试与文档。

---

## 1. 目标

在已完成 Phase 9.1~9.4 的基线上，继续完成：

- **9.5 文件操作路径策略**：对 `file_read` / `file_list` 的 `path` 参数做归一化后策略检查，
  兼容 Windows 路径与大小写绕过。
- **9.6 记忆读写策略**：在 `MemoryManager` 的 `record` / `inject` / `read` 路径接入
  `memory/category` 读写策略检查。
- **9.7 文档同步**：更新 `docs/progress-spec.md`、`docs/session-context.md`、`CODEMAP.md`，
  必要时补充 `docs/learning-journal.md`。

---

## 2. 必须做

### 9.5 文件路径策略

1. 在 `ToolRegistry._evaluate_parametric_policy()` 中，对 `resource == "file/path"` 的
   `subject` 做路径归一化：
   - 反斜杠 `\\` 替换为正斜杠 `/`。
   - 统一转小写。
   - 保留空字符串/非字符串防御（已有 `str(subject)`）。
2. 在 `default_security_rules.yaml` 中补充 Windows 敏感路径规则，例如：
   - `windows/system32/config/sam`
   - `windows/system32/config/system`
   - `windows/system32/config/security`
   - `windows/repair/sam`
   - 已有 Linux 规则（`/etc/passwd`、`.ssh`）保持生效。
   - 自定义 `file/path` 规则中的 pattern 应使用小写，因为 subject 已归一化为小写。
3. 测试覆盖：
   - `C:\\Windows\\System32\\config\\SAM` 被拒绝。
   - `/ETC/PASSWD` 经归一化后被拒绝。
   - 普通工作区路径（如 `/workspace/result.txt`）仍被允许。

### 9.6 记忆读写策略

1. 修改 `MemoryManager.__init__()`，增加可选 `policy: PolicyEngine | None = None` 参数。
2. `record()`：
   - 对每条提取到的 `MemoryEntry`，调用
     `policy.evaluate(resource="memory/category", operation="write", subject=entry.category.value)`。
   - 被拒绝的条目跳过保存，记录警告日志，不抛异常，不阻塞主循环。
   - 返回列表中只包含成功保存的条目。
3. `inject()`：
   - 对 `store.query` 召回的候选条目，按 `memory/category` 的 `read` 策略过滤。
   - 被拒绝的条目不进入排序与注入片段。
4. `read(uri)`：
   - 解析出 category 后，先评估 `memory/category` 的 `read` 策略。
   - 被拒绝时返回 `None`，记录警告日志。
5. `Agent.__init__()`：
   - 先构建 `policy`（`config.security.build_policy_engine()`）。
   - 将该 `policy` 同时注入 `ToolRegistry` 与默认 `MemoryManager`。
   - 外部传入的 `memory_manager` 若未设置 policy，则注入 Agent 的 policy；
     若已设置，则尊重其自有 policy，不强制覆盖。
6. `MemoryManager.check_read_policy(uri)`：
   - 提供显式的 `memory/category` 读策略检查接口，返回 `PolicyDecision`。
   - `memory_read` 工具在调用 `manager.read(uri)` 前先检查策略，
     被拒绝时返回 `ToolResult(success=False, content="策略拒绝：...")`。
7. 新增 `tests/test_memory_security.py`，覆盖：
   - 写入时被拒绝 category 不保存。
   - 无 policy 时行为不变。
   - `inject` 过滤只读/禁止 category。
   - `read` 拒绝返回 `None`。
   - `memory_read` 工具返回策略拒绝原因。

### 9.7 文档同步

1. `docs/progress-spec.md`：
   - 将 9.5、9.6 状态改为 ✅ 完成，9.7 改为 ✅ 完成。
   - 更新质量状态（测试数、source files 数）。
   - 更新变更日志。
2. `docs/session-context.md`：
   - 更新“当前任务状态”为 Phase 9 全部完成。
   - 更新“剩余任务”表。
   - 更新“接力重点”。
3. `CODEMAP.md`：
   - 更新进度表 Phase 9 状态为 ✅ 完成。
   - 在模块职责中补充 MemoryManager 策略注入说明。
4. `docs/learning-journal.md`：
   - 按 progress-spec 教程更新记录表，视情况补充 Phase 9 教学内容。

### 9.8 主循环集成测试（补充）

1. 新增/扩展 `tests/test_security_integration.py`，覆盖 `Agent.run()` 层面的安全策略行为：
   - 危险 `file_read` 被拦截且后端未被调用。
   - 危险 `sandbox_exec` 被拦截且后端未被调用。
   - 危险 `memory_read` 返回明确策略原因。
   - 未启用安全策略时行为不变。
   - 策略拒绝后 LLM 改用安全路径可恢复执行。
2. 文档同步：在 `progress-spec.md`、`session-context.md`、`CODEMAP.md`、
   `learning-journal.md` 中记录集成测试文件与测试数更新。

---

## 3. 严禁做

- 不修改任何 tool handler 函数签名。
- 不让策略拒绝抛异常阻塞主循环；拒绝必须优雅降级（跳过/返回 `None`/返回
  `ToolResult(success=False)`）。
- 不替换现有 `ToolRegistry` / `MemoryManager` / `Agent` 的核心语义。
- 不引入外部策略引擎或 DSL。
- 不破坏 Phase 1~8 的现有行为；`SecurityConfig.enabled` 默认保持 `False`。
- 不使用文件备份替代 git 回滚。

---

## 4. 验收标准

- `python -m pytest tests/ -q`：全部通过，基线外新增失败为 0。
- `python -m mypy src/`：零错误。
- `python -m ruff check src/ tests/`：全绿。
- 新增测试文件 `tests/test_memory_security.py` 至少覆盖 4 个场景。
- `tests/test_tool_security.py` 扩展 Windows 路径与大小写绕过用例。
- 新增/扩展 `tests/test_security_integration.py`，覆盖 Agent 主循环中的策略拦截与恢复。
- 文档与代码实现一致。

---

## 5. 涉及文件

| 类型 | 文件 |
|------|------|
| 规格 | `.kimi/vibe_specs/security_policy-spec.md`（本文件） |
| 实现 | `src/agent/core/engine.py` |
| 实现 | `src/agent/core/memory.py` |
| 配置 | `src/agent/core/default_security_rules.yaml` |
| 测试 | `tests/test_tool_security.py` |
| 测试 | `tests/test_memory_security.py`（新增） |
| 测试 | `tests/test_security_integration.py`（新增） |
| 文档 | `docs/progress-spec.md` |
| 文档 | `docs/session-context.md` |
| 文档 | `CODEMAP.md` |
| 文档 | `docs/learning-journal.md`（视情况） |
