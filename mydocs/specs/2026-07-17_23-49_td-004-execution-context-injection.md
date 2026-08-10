# Feature Spec — TD-004：ExecutionContext 接入工具签名

> **Spec 层级**：Feature Spec
> **协议**：SDD-RIPER-ONE（`No Spec, No Code` / `No Approval, No Execute` / `Spec is Truth`）
> **创建**：2026-07-17 23:49 | **Phase**：`PLAN` | **Status**：`[LOCKED]`
> **Approval Status**：`WAITING — 等待用户精确回复 "Plan Approved"`
> **上游依据**：`.kimi/vibe_specs/technical-debt-spec.md` TD-004 详规
> **关联**：TD-005（下一单元，共享"运行时上下文"设计）；归档 `mydocs/archive/2026-07-17_22-15_td-governance-round1_llm.md` §6

---

## 0. 任务复述（Restate First）

- **最终目标**：让工具 handler 能读写 `ExecutionContext`，Agent 可维护跨 tool call 的运行时状态（如"已安装包"）。
- **当前任务单元**：TD-004 单项——注入机制 + Agent 持有 ExecutionContext + 一个真实使用示例（sandbox_exec pip 包记录）。
- **In Scope**：`ToolRegistry` 签名探测与注入、`Agent` 持有与 `reset()` 清空、`sandbox_exec` 可选 ctx 参数、测试与文档。
- **Out of Scope**：所有工具改用 ctx（不强制）；ExecutionContext 暴露给 LLM；持久化；Trace 事件；TD-005 装配重构（下一单元）。
- **Done Contract（验证方式）**：
  1. 声明 `execution_context` 参数的 handler 能收到 Agent 的 ctx 实例；未声明的 handler 行为零变化。
  2. 状态可跨 tool call 保留（集成测试证明）；`reset()` 后清空。
  3. `sandbox_exec` 成功执行含 `pip install X` 的代码后，ctx 记录 X。
  4. 全量门禁：pytest（≥575+新增）/ mypy / ruff 全绿。

## 1. Research Findings（关键事实）

1. **注入点唯一**：`ToolRegistry.execute()` 的 `spec.handler(**call.arguments)`（engine.py:157）是所有工具调用的唯一入口——改动点收敛。
2. **partial 兼容性已实测**：`inspect.signature(partial(fn, backend=...))` 正确暴露剩余参数；keyword 绑定参数被重复传值时是覆盖而非 TypeError → 签名探测机制安全。
3. **探测时机**：`register()` 时探测并缓存到 registry 内部集合，`execute()` 热路径只做 O(1) 集合查找。
4. **生命周期（用户决策 2026-07-17）**：Session 级持有（Agent 实例属性，跨 `run()` 保留），`reset()` 时 `clear()`——与 `error_pattern_ledger` 语义对齐；Web/CLI 多轮场景下"已装包"状态有效。
5. **现状**：`ExecutionContext`（state.py）是纯内存键值 dataclass，从未被实例化；`reset()` 现有语义=清 messages/state/trace/ledger。
6. **预留参数冲突规则**：仅当 `call.arguments` 不含 `execution_context` 时注入（LLM 显式传入时不覆盖）。

## 2. Innovate

跳过正式方案对比——策略讨论（2026-07-17 23:40）已完成三项关键决策并经用户拍板：
① 生命周期 = Session 级 + reset() 清空；② 注入机制 = register 时签名探测 + arguments 未提供时注入；③ 示例 = sandbox_exec 真实 pip 包记录。
备选方案（execute 时实时探测 / run 时清空 / 测试桩示例）已在讨论中排除，理由见会话记录与本 Spec §1。

## 3. Detailed Design & Implementation（Plan / The Contract）

### 3.1 File Changes

| 操作 | 路径 | 内容 |
|---|---|---|
| 修改 | `src/agent/core/engine.py` | `ToolRegistry.__init__` 增加 `execution_context` 可选参数 + `_ctx_aware: set[str]`；`register()` 探测签名缓存；`execute()` 注入；`Agent.__init__` 实例化 `self.execution_context` 并传入 registry；`reset()` 清空 |
| 修改 | `src/agent/tools/sandbox_exec.py` | 增加可选参数 `execution_context: ExecutionContext \| None = None`；成功执行后记录 pip 安装包 |
| 新增 | `tests/test_execution_context.py` | 注入机制 + 生命周期 + pip 记录 + 集成测试 |
| 修改 | `CODEMAP.md`、`docs/progress-spec.md`、`docs/session-context.md`、`.kimi/vibe_specs/technical-debt-spec.md`、`docs/evaluation-log.md` | 状态与记录同步 |

### 3.2 Signatures（契约级，Execute 不得偏离）

```python
# src/agent/core/engine.py
class ToolRegistry:
    def __init__(
        self,
        policy: PolicyEngine | None = None,
        execution_context: ExecutionContext | None = None,
    ) -> None: ...
    def register(self, spec: ToolSpec) -> None:
        """注册工具；探测 handler 签名是否声明 execution_context 并缓存。"""
    async def execute(self, call: ToolCall) -> ToolResult:
        """执行调用；若工具已声明且 arguments 未提供 execution_context，则注入。"""

class Agent:
    execution_context: ExecutionContext   # session 级；reset() 时 clear()

# src/agent/tools/sandbox_exec.py
async def sandbox_exec(
    code: str,
    backend: SandboxBackend,
    execution_context: ExecutionContext | None = None,
) -> ToolResult: ...

# pip 检测（模块级私有函数）
def _extract_pip_packages(code: str) -> list[str]:
    """从代码中提取 `pip install` 的包名列表（忽略 - 开头的选项与注释行）。"""
# 记录键名约定：execution_context key = "packages_installed"（list[str]，去重追加）
```

### 3.3 Implementation Checklist（原子步骤）

- [ ] 1. **RED**：`tests/test_execution_context.py`——ctx 感知 handler 收到同一实例 / 普通 handler 零变化 / arguments 已提供时不覆盖 / 跨两次调用状态保留 / `reset()` 清空 → 确认失败
- [ ] 2. **GREEN**：engine.py 注入机制 + Agent 持有 + reset 清空 → 跑通步骤 1 + 全量回归
- [ ] 3. **RED**：sandbox_exec pip 记录测试（mock backend：成功执行 `"pip install requests numpy"` 后 ctx 含两包；执行失败不记录；无 pip 代码不记录）→ 确认失败
- [ ] 4. **GREEN**：sandbox_exec 可选 ctx 参数 + `_extract_pip_packages` → 跑通步骤 3
- [ ] 5. 集成测试：Agent 端到端，自定义 ctx 工具第一次 set、第二次 get 读到
- [ ] 6. 全量门禁复核（pytest / mypy / ruff）
- [ ] 7. 文档与状态同步（CODEMAP / progress-spec / session-context / technical-debt-spec TD-004→✅ / evaluation-log 优化记录）
- [ ] 8. 双 commit：`feat: inject ExecutionContext into tool handlers (TD-004)` + `docs: sync docs for execution context injection (TD-004)`

### 3.4 风险与回滚

| 风险 | 缓解 |
|---|---|
| 注入逻辑影响所有工具调用（热路径） | register 时缓存探测结果；现有 500+ 测试覆盖各种 handler 形态；集合查找 O(1) |
| partial/lambda/async handler 兼容 | 已实测 partial；测试覆盖 lambda/async/ToolResult 返回形态 |
| pip 检测误报（注释里的 pip install） | 逐行匹配、跳过 `#` 开头行；定位为"示例级"启发式并在 docstring 声明 |
| reset() 清空语义变化 | 新增行为（此前无 ctx），无回归面；测试断言 |
| 回滚 | `git checkout HEAD -- src/agent/core/engine.py src/agent/tools/sandbox_exec.py` + 删除新增测试 |

---

## 4. Execute Log

| 步骤 | 内容 | 结果 |
|---|---|---|
| 1 RED | `test_execution_context.py` 注入/生命周期 8 例 | 7 失败 1 通过，RED 成立 |
| 2 GREEN | engine.py：register 探测缓存 + execute 条件注入 + Agent 持有 + reset 清空 | 8 例全过；全量 583 passed 零回归 |
| 3 RED | pip 记录 5 例（含修正 1 处测试编写错误：pip 语句误写注释行） | 4 失败，RED 成立 |
| 4 GREEN | sandbox_exec ctx 参数 + `_extract_pip_packages`（跳注释/选项/.txt） | 13 passed |
| 5 | 集成：脚本化 LLM 客户端驱动 writer→reader 跨调用共享 | 一次通过，14 passed |
| 6 | 全量门禁 | **589 passed, 1 skipped** / mypy 44 文件零错误 / ruff 全绿 |
| 7 | 文档同步（含 evaluation-log 表格误插入修复，第 3 次踩中同一遗留问题） | 已落盘 |
| 8 | 双 commit：`0ef5010`（feat）、`ead94b6`（docs） | 工作区干净 |

## 5. Validation

| 验收项（Done Contract） | 证据 | 结论 |
|---|---|---|
| 1. ctx 感知 handler 收到同一实例；普通 handler 零变化 | `TestContextInjection` 6 例（含 arguments 不覆盖、异步 handler、无 ctx 配置传 None） | ✅ |
| 2. 跨 tool call 状态保留 + reset() 清空 | `test_state_persists_across_calls` + `test_reset_clears_execution_context` + 主循环集成 1 例 | ✅ |
| 3. sandbox_exec 成功执行后记录 pip 包 | `TestSandboxExecPipTracking` 5 例（成功记录/失败不记/无 pip 不记/选项与注释免疫/向后兼容） | ✅ |
| 4. 全量门禁 | 589 passed（575+14）；mypy/ruff 全绿 | ✅ |

## 6. Review Verdict

**评审时间**：2026-07-18 00:20 | **评审方式**：三轴评审（Spec 原文 + 变更代码回读 + 行为级抽查脚本实测，含真实 subprocess 后端）

### Review Matrix

| 轴 | 关键检查 | 结论 | 证据 |
|---|---|---|---|
| Axis-1 Spec 质量与需求达成 | Goal/In/Out/Acceptance 清晰可验证 | **PASS** | §0 Done Contract 4 条均有实测证据（见 §5 Validation） |
| Axis-1 需求达成 | TD-004 详规验收（可选接收/向后兼容/跨调用保留 + 至少一个示例） | **PASS** | `TestContextInjection` 6 例 + 生命周期 2 例 + pip 记录 5 例 + 主循环集成 1 例 |
| Axis-2 Spec-代码一致性 | Signatures 与 Plan §3.2 对照 | **PASS** | `ToolRegistry.__init__` / `register` / `execute` / `sandbox_exec` 签名与契约一致；探测缓存于 `_ctx_aware` 集合（实现组织差异，行为等价） |
| Axis-2 行为一致性 | 默认工具（partial 包装）在真实后端的注入行为 | **PASS** | 行为抽查 A：default-registered ctx 工具经 `execute()` 正确注入同一实例 |
| Axis-3 代码质量 | 正确性/健壮性 | **PASS** | arguments 不被原地修改（新建 dict）；签名探测 try/except 兼容内置 callable；无 ctx 配置时注入 None 而非报错 |
| Axis-3 代码质量 | 性能 | **PASS** | 探测在 register 时完成，execute 热路径仅 O(1) 集合查找 |
| Axis-3 风险 | 示例的实用价值 | **PASS（附观察项 1）** | 行为抽查 B：真实 pip 安装走 `subprocess.run([sys.executable, '-m', 'pip', ...])`（合法 Python），当前行级启发式不覆盖——机制本身无缺陷，示例覆盖面有限 |

### Overall Verdict：**PASS（可关闭）**

### Blocking Issues：无

### 观察项（非阻塞）
1. **pip 记录覆盖面**：真实 Coding Agent 场景中 pip 安装几乎总是 `subprocess` 调用形式（`pip install X` 裸行不是合法 Python，会被沙箱拒绝），建议后续增强 `_extract_pip_packages` 支持 `subprocess` 风格匹配（候选 FAST 小任务）。
2. `ToolRegistry._ctx_aware` 与工具同生命周期，无 unregister 路径——当前无该需求，未来加卸载能力时需同步清理。

## 7. Plan-Execution Diff

| 项 | Plan | 实际 | 性质 |
|---|---|---|---|
| 探测缓存位置 | 未指定载体 | `ToolRegistry._ctx_aware: set[str]` | 实现选择，行为等价 |
| 测试编写错误修正 | — | pip 语句误写注释行，已修正 | 过程记录，非偏差 |
| 其余 File Changes / Checklist | — | 全部一致 | — |

## 8. Change Log

| 时间 | 变更 |
|---|---|
| 2026-07-17 23:49 | sdd_bootstrap TD-004：Research 完成（partial 兼容性/涟漪面/reset 语义已实测核实）；策略讨论三项决策经用户拍板（Session 级生命周期 / register 时探测注入 / sandbox_exec pip 示例）；Plan 落盘，等待 `Plan Approved` |
| 2026-07-18 00:10 | `Plan Approved` 收到，进入 EXECUTE。8 步 checklist 全部完成：589 passed / mypy / ruff 全绿；双 commit `0ef5010`（feat）+ `ead94b6`（docs）；Validation 4 项验收全部达成，待 `REVIEW EXECUTE` |
| 2026-07-18 00:20 | REVIEW EXECUTE 完成：三轴全 PASS（含真实 subprocess 后端行为抽查），Overall Verdict = PASS（可关闭），Blocking Issues = 无；观察项：pip 记录启发式对 subprocess 风格调用覆盖不足（候选 FAST 增强） |
| 2026-07-18 01:00 | FAST 收尾（观察项 1 关闭）：`_extract_pip_packages` 增强支持三种形态（行级 / subprocess 列表 / os.system 字符串），新增 `_normalize_package`（去版本钉/extras、过滤选项）；修复 `[^\]]` 误配 extras 中 `]` 的 bug；新增 6 个测试，全量 604 passed / mypy / ruff 全绿 |

## 9. Archive Record

| 时间 | 归档产物 | 模式 |
|---|---|---|
| 2026-07-18 00:35 | `mydocs/archive/2026-07-18_00-35_td-governance-round2_human.md` + `..._llm.md` | thematic（与 TD-005 合并主题"架构主线"） |

- 归档为知识衍生品，不影响本 Spec 的真相源地位；原始文件未删除/未移动。
