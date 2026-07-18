# 架构图（ASCII）规格说明 — Task 10.7「架构图（ASCII）」

> **适用范围**：`docs/architecture.md`、相关测试与文档。  
> **目标**：用 ASCII 图清晰展示 Hermes Agent 的系统架构与数据流，帮助用户和面试官快速理解设计。  
> **版本**：v1.0（Phase 10.7）

---

## 1. 背景与目标

Hermes Agent 经过多个 Phase 的迭代，已经包含 Agent 引擎、工具层、沙箱层、LLM 适配器、长期记忆、安全策略、CLI 等多个组件。对于新用户和面试官来说，仅凭源码很难快速理解：

1. 各组件之间如何协作。
2. 一次完整的 `Agent.run()` 经历了哪些步骤。
3. 遇到错误时系统如何自我纠错。

Phase 10.7 要重写 `docs/architecture.md`，用**三张 ASCII 图**把这些问题讲清楚。

---

## 2. 范围

### 2.1 必须做（Must Have）

1. 重写 `docs/architecture.md`：
   - 中文为主，关键术语保留英文。
   - 包含三张 ASCII 图：
     1. **组件架构图**：展示 Agent、LLM Client、ToolRegistry、Tools、DockerSandboxBackend、MemoryManager、PolicyEngine、CLI 之间的静态关系。
     2. **主循环数据流图**：展示 `Agent.run()` 的执行循环：用户输入 → LLM → 纯文本/tool_calls → 工具执行 → 结果反馈 → 返回。
     3. **序列图**：展示一次带有自我纠错的完整运行：用户请求 → LLM 生成代码 → 沙箱执行失败 → 错误分类 → LLM 修正 → 成功执行 → 返回结果。
   - 每张图附带简短文字说明。
2. 新增 `tests/test_architecture.py`：
   - 验证 `docs/architecture.md` 存在。
   - 验证包含三张 ASCII 图（通过统计包含 `` ``` `` 的代码块数量，或检测特定标题）。
   - 验证关键章节标题存在。
3. 更新文档：
   - `docs/progress-spec.md`：Task 10.7 状态改为 ✅ 完成。
   - `CODEMAP.md`：`docs/architecture.md` 说明更新。
   - `docs/session-context.md`：当前任务更新。
   - `docs/learning-journal.md`：新增 Phase 10.7 教学内容。
4. Commit：`docs: add ASCII architecture diagrams`。

### 2.2 严禁做（Must Not）

1. **不修改** `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager`。
2. **不引入** 新依赖。
3. **不做** 使用文档（10.8）/ Demo 录制（10.9）。
4. **不改动** `README.md`。

### 2.3 可选做（Nice to Have）

1. 增加一张「安全策略拦截流程」小图，展示 PolicyEngine 在工具执行前的检查位置。
2. 增加「记忆注入与记录流程」小图，展示 MemoryManager 如何与 Agent 主循环交互。

---

## 3. 三张 ASCII 图设计

### 3.1 组件架构图

展示各模块的层次与依赖关系：

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Layer                            │
│              agent run / agent chat / agent config           │
└───────────────────────────┬─────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                       Agent Core                             │
│  ┌─────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ Agent   │  │ ToolRegistry │  │ Planner / ErrorHandler │  │
│  │ .run()  │◄─┤  + Policy    ├──┤  + ReflectiveAdvisor   │  │
│  └────┬────┘  └───────┬──────┘  └────────────────────────┘  │
│       │               │                                      │
│       │        ┌──────┴──────┐                               │
│       │        │   Tools     │                               │
│       │        │ sandbox_exec│                               │
│       │        │ file_read   │                               │
│       │        │ finish      │                               │
│       │        └──────┬──────┘                               │
│       │               │                                      │
│  ┌────┴────┐     ┌────┴─────┐  ┌─────────────┐              │
│  │ LLM     │     │ Docker   │  │ MemoryStore │              │
│  │ Client  │     │ Sandbox  │  │ + Policy    │              │
│  └─────────┘     └──────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 主循环数据流图

展示 `Agent.run()` 的循环过程：

```
用户输入
    │
    ▼
Agent.run(prompt)
    │
    ▼
┌─────────────────┐
│  构造消息历史    │
│  system + user  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌──────────────┐
│  调用 LLM        │────►│  纯文本回复   │
│  client.chat()   │     │  直接返回     │
└────────┬────────┘     └──────────────┘
         │
         ▼
┌─────────────────┐
│  返回 tool_calls │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ ToolRegistry    │────►│ 执行失败        │
│ .execute(call)  │     │ ErrorClassifier │
└────────┬────────┘     │ 返回恢复建议     │
         │              └────────┬────────┘
         ▼                       │
┌─────────────────┐              │
│  执行成功        │◄─────────────┘
│  结果追加到历史  │
└────────┬────────┘
         │
         ▼
   继续调用 LLM
         │
         ▼
   直到没有 tool_calls
```

### 3.3 序列图

展示一次完整的自我纠错执行：

```
User    Agent    LLMClient  ToolRegistry  Sandbox  ErrorClassifier
 │         │          │            │          │          │
 │────────►│          │            │          │          │  run("写排序算法")
 │         │─────────►│            │          │          │  chat()
 │         │◄─────────│            │          │          │  返回代码
 │         │─────────►│            │          │          │  返回 tool_call
 │         │          │            │          │          │  (sandbox_exec)
 │         │─────────────────────►│          │          │  execute()
 │         │          │            │─────────►│          │  execute_code()
 │         │          │            │◄─────────│          │  SyntaxError
 │         │          │            │          │─────────►│  classify()
 │         │          │            │◄─────────│          │  RECOVERABLE
 │         │◄─────────────────────│          │          │  ToolResult(错误)
 │         │─────────►│            │          │          │  再次 chat()
 │         │◄─────────│            │          │          │  返回修正代码
 │         │─────────────────────►│          │          │  execute()
 │         │          │            │─────────►│          │  execute_code()
 │         │          │            │◄─────────│          │  成功
 │         │◄─────────────────────│          │          │  ToolResult(结果)
 │         │─────────►│            │          │          │  最终 chat()
 │         │◄─────────│            │          │          │  返回最终答案
 │◄────────│          │            │          │          │  print(结果)
```

---

## 4. 测试策略

1. 先写 `tests/test_architecture.py`，预期失败（文件内容不满足三张图要求）。
2. 重写 `docs/architecture.md`。
3. 跑测试，修复直至全绿。
4. 跑完整质量门禁。

测试要点：

- 读取 `docs/architecture.md`。
- 检查关键章节标题：「组件架构」、「数据流」、「执行序列」。
- 检查至少包含 3 个 ASCII 图代码块（通过 `` ``` `` 统计或检测特定标记）。
- 不验证图的内容艺术性，只验证存在性与结构。

---

## 5. 验收标准

| 检查项 | 通过标准 |
|--------|---------|
| 文件存在 | `docs/architecture.md` 存在且非空 |
| 章节完整 | 包含「组件架构」、「数据流」、「执行序列」三个章节 |
| ASCII 图数量 | 至少包含 3 个 ASCII 图代码块 |
| 单元测试 | `pytest tests/test_architecture.py -v` 全部通过 |
| 全部测试 | `pytest tests/ -q` 保持 491 passed, 1 skipped 以上 |
| 类型检查 | `mypy src/` 无新增错误 |
| Lint | `ruff check src/ tests/` 全绿 |
| 文档同步 | `docs/progress-spec.md`、`CODEMAP.md`、`docs/session-context.md`、`docs/learning-journal.md` 已更新 |
| 核心 untouched | `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager` 无修改 |

---

## 6. 风险与回滚

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| ASCII 图在不同终端宽度下显示错位 | 中 | 低 | 使用较窄的图（不超过 80 字符），并在文字中说明 |
| 图的内容与代码实现不同步 | 中 | 中 | 保持图的抽象层次，不画具体函数签名；后续代码大改时同步更新 |

**回滚策略**：若出现不可快速修复的问题，执行 `git checkout HEAD -- docs/architecture.md tests/test_architecture.py` 回退改动。

---

## 7. 相关文件

- `docs/architecture.md`（修改）
- `tests/test_architecture.py`（新建）
- `docs/progress-spec.md`、`CODEMAP.md`、`docs/session-context.md`、`docs/learning-journal.md`（修改）

---

## 8. 文档更新清单

Task 10.7 完成后需同步：

- [ ] `docs/progress-spec.md`：Task 10.7 状态改为 ✅ 完成
- [ ] `CODEMAP.md`：`docs/architecture.md` 说明更新
- [ ] `docs/session-context.md`：当前任务更新
- [ ] `docs/learning-journal.md`：新增 Phase 10.7 教学内容

---

*Generated: 2026-07-12 | Spec version: 1.0*
