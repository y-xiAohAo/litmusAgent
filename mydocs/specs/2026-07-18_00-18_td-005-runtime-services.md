# Feature Spec — TD-005：RuntimeServices 统一装配，解耦 Agent.__init__

> **Spec 层级**：Feature Spec
> **协议**：SDD-RIPER-ONE（`No Spec, No Code` / `No Approval, No Execute` / `Spec is Truth`）
> **创建**：2026-07-18 00:18 | **Phase**：`PLAN` | **Status**：`[LOCKED]`
> **Approval Status**：`WAITING — 等待用户精确回复 "Plan Approved"`
> **上游依据**：`.kimi/vibe_specs/technical-debt-spec.md` TD-005 详规
> **前序**：TD-004 已交付并评审通过（`0ef5010`/`ead94b6`），`ExecutionContext` 注入机制可用

---

## 0. 任务复述（Restate First）

- **最终目标**：将内部工具的运行时依赖装配从 `Agent.__init__` 解耦——新增内部工具不再需要改动核心引擎。
- **当前任务单元**：TD-005 单项——引入 `RuntimeServices`（三槽位 + `from_config()` 工厂）与统一注册入口 `register_internal_tools()`，`Agent.__init__` 装配区收敛。
- **In Scope**：新增 `src/agent/core/runtime.py`；`tools/__init__.py` 新增统一注册函数；`engine.py` 装配区重构；测试与文档。
- **Out of Scope**：重型 DI 框架/插件系统；外部工具（`sandbox_exec`/`file_*`）注册方式变更；`register_context_tools`/`register_memory_tools` 签名变更（保持不变，向后兼容）；压缩/记忆子系统内部逻辑。
- **Done Contract（验证方式）**：
  1. `Agent.__init__` 中内部工具装配逻辑收敛为：工厂创建 + 一次 `register_internal_tools` 调用（`_create_default_memory_manager` / `_create_default_context_cache` / `_should_register_*` 从 Agent 移除）。
  2. 工厂行为：`config=None` → 空服务；启用压缩 → 有 cache；启用记忆 → 有 manager（含 policy 注入）；显式注入的 cache/manager 优先。
  3. 注册行为：cache 存在 → `context_read`；manager 存在 → `memory_read`；`register_*` 配置开关生效。
  4. 全量门禁：pytest（≥589+新增）/ mypy / ruff 全绿；既有记忆/压缩集成测试零回归。

## 1. Research Findings（关键事实）

1. **装配区现状**（engine.py `Agent.__init__` + 4 个私有方法，约 90 行）：policy → registry → backend → 工具注册 → context_cache 创建 + 条件注册 → compression setup → memory_manager 创建 + policy 二次注入 + 条件注册。
2. **依赖创建逻辑**：`_create_default_context_cache`（压缩启用才创建）、`_create_default_memory_manager`（记忆启用才创建，构造时接收 policy）、`_should_register_context_read` / `_should_register_memory_read`（config 开关，默认 True）。
3. **涟漪面已实测收窄**：`register_context_tools` / `register_memory_tools` 全仓约 10 处调用（含少数测试）——**本方案不改这两个函数签名**，涟漪面进一步压缩到仅 engine.py + tools/__init__.py。
4. **TD-004 已就绪**：`Agent.execution_context` 存在且注入 ToolRegistry；`RuntimeServices` 直接引用同一实例即可。
5. **Attribute 依赖**：`self.context_cache` / `self.memory_manager` 被 `run()`、`_setup_compression`、`_maybe_compress` 及多个测试引用——必须保留这两个属性（改为委托 services）。
6. **循环导入检查**：`core/runtime.py` → config/memory/context_cache/state/security，均不反向依赖 runtime；`tools/__init__.py` 仅 TYPE_CHECKING 引用。

## 2. Innovate

跳过正式方案对比——策略讨论（2026-07-17 23:40）已由用户拍板：**捆绑 + 工厂** 方案（RuntimeServices 三槽位 + `from_config()` 工厂，装配逻辑搬出 Agent）。"仅捆绑参数"方案已在讨论中排除（`__init__` 仍然臃肿，不解决根本问题）。

**关键设计决策**：
1. **注册函数签名不动**：`register_context_tools(registry, cache)` / `register_memory_tools(registry, manager)` 保持原样，`register_internal_tools` 在其上做条件编排——向后兼容最大化。
2. **属性委托**：`Agent.context_cache` / `Agent.memory_manager` 保留，指向 services 槽位，下游零改动。
3. **注入优先**：`from_config()` 接受可选的 cache/manager 覆盖（对应 Agent 构造参数），与既有注入语义一致。

## 3. Detailed Design & Implementation（Plan / The Contract）

### 3.1 File Changes

| 操作 | 路径 | 内容 |
|---|---|---|
| 新增 | `src/agent/core/runtime.py` | `RuntimeServices` dataclass + `from_config()` 工厂（含 cache/manager 创建与 policy 注入逻辑，从 engine 迁入） |
| 修改 | `src/agent/tools/__init__.py` | 新增 `register_internal_tools()`（编排两个现有注册函数 + 配置开关判断，从 engine 迁入） |
| 修改 | `src/agent/core/engine.py` | `Agent.__init__` 装配区收敛；删除 `_create_default_memory_manager` / `_create_default_context_cache` / `_should_register_memory_read` / `_should_register_context_read`；保留 `context_cache` / `memory_manager` 属性委托 |
| 新增 | `tests/test_runtime_services.py` | 工厂与统一注册测试 |
| 修改 | `CODEMAP.md`、`docs/progress-spec.md`、`docs/session-context.md`、`.kimi/vibe_specs/technical-debt-spec.md`、`docs/evaluation-log.md` | 状态与记录同步 |

### 3.2 Signatures（契约级，Execute 不得偏离）

```python
# src/agent/core/runtime.py
@dataclass
class RuntimeServices:
    """Agent 内部工具的运行时依赖集合（TD-005）。"""
    execution_context: ExecutionContext
    context_cache: ContextCache | None = None
    memory_manager: MemoryManager | None = None

    @classmethod
    def from_config(
        cls,
        config: AgentConfig | None,
        policy: PolicyEngine | None,
        execution_context: ExecutionContext,
        context_cache: ContextCache | None = None,
        memory_manager: MemoryManager | None = None,
    ) -> RuntimeServices: ...
    """按配置创建运行时服务；显式注入的 cache/manager 优先于配置创建。"""

# src/agent/tools/__init__.py
def register_internal_tools(
    registry: ToolRegistry,
    services: RuntimeServices,
    config: AgentConfig | None = None,
) -> None: ...
"""统一注册内部工具：context_cache 存在→context_read；memory_manager 存在→memory_read。
register_context_read / register_memory_read 配置开关（默认 True）在此生效。"""

# src/agent/core/engine.py —— Agent.__init__ 装配区收敛为：
#   self.runtime_services = RuntimeServices.from_config(
#       config, policy, self.execution_context,
#       context_cache=context_cache, memory_manager=memory_manager,
#   )
#   self.context_cache = self.runtime_services.context_cache
#   self.memory_manager = self.runtime_services.memory_manager
#   register_internal_tools(self.tools, self.runtime_services, config)
```

### 3.3 Implementation Checklist（原子步骤）

- [ ] 1. **RED**：`tests/test_runtime_services.py`——工厂 5 例（None config / 压缩启用 / 记忆启用+policy / 注入优先 / 记忆未启用无 manager）→ 确认失败
- [ ] 2. **GREEN**：新增 `core/runtime.py` → 跑通步骤 1
- [ ] 3. **RED**：注册编排 4 例（cache→context_read、manager→memory_read、开关关闭不注册、空服务不注册）→ 确认失败
- [ ] 4. **GREEN**：`tools/__init__.py` `register_internal_tools` → 跑通步骤 3
- [ ] 5. engine.py 装配区重构（删除 4 个私有方法，接入工厂与统一注册）→ 全量回归（重点：memory/compression 集成测试）
- [ ] 6. 全量门禁复核（pytest / mypy / ruff）
- [ ] 7. 文档与状态同步（CODEMAP / progress-spec / session-context / technical-debt-spec TD-005→✅ / evaluation-log 优化记录）
- [ ] 8. 双 commit：`feat: decouple internal tool wiring via RuntimeServices (TD-005)` + `docs: sync docs for runtime services (TD-005)`

### 3.4 风险与回滚

| 风险 | 缓解 |
|---|---|
| 装配顺序变化引入微妙行为差异（如 policy 注入 memory_manager 的时机） | 工厂内保持原有构造语义；memory/compression/security 集成测试全量回归 |
| 测试直接引用被删除的 Agent 私有方法 | 先 grep 确认无外部引用，再删除 |
| `Agent(context_cache=...)` 注入路径行为变化 | 工厂"注入优先"测试锁定语义 |
| 回滚 | `git checkout HEAD -- src/agent/core/engine.py src/agent/tools/__init__.py` + 删除新增文件 |

---

## 4. Execute Log

| 步骤 | 内容 | 结果 |
|---|---|---|
| 预检 | 被删私有方法外部引用核查（grep） | 零引用，安全 |
| 1 RED | `test_runtime_services.py` 工厂 5 例 | 收集错误，RED 成立 |
| 2 GREEN | 新增 `core/runtime.py`（三槽位 + from_config 工厂） | 5 passed |
| 3-4 RED→GREEN | 注册编排 4 例 + `register_internal_tools()` | 9 passed |
| 5 | engine.py 装配区收敛（删除 4 私有方法，接入工厂与统一注册；保留注入 manager 的 policy 补注入语义） | 全量 598 passed 零回归；修正一次 import 编辑失误与 4 个 ruff F401 |
| 6 | 全量门禁 | **598 passed, 1 skipped** / mypy 45 文件零错误 / ruff 全绿 |
| 7 | 文档同步（evaluation-log 改用表头锚定插入，未再踩表格问题） | 已落盘 |
| 8 | 双 commit：`f67f6df`（feat）、`e623797`（docs） | 工作区干净 |

## 5. Validation

| 验收项（Done Contract） | 证据 | 结论 |
|---|---|---|
| 1. Agent.__init__ 装配收敛，4 私有方法移除 | engine.py diff：装配区 4 行（from_config + 属性委托 + register_internal_tools）；`_create_default_*` / `_should_register_*` 已删除且无外部引用 | ✅ |
| 2. 工厂行为（None 配置/压缩/记忆+policy/注入优先/未启用） | `TestRuntimeServicesFromConfig` 5 例 | ✅ |
| 3. 注册行为（cache→context_read、manager→memory_read、开关、空服务） | `TestRegisterInternalTools` 4 例 | ✅ |
| 4. 全量门禁 + 零回归 | 598 passed（589+9）；记忆/压缩/安全集成测试全绿；mypy 45 文件零错误 | ✅ |

## 6. Review Verdict

**评审时间**：2026-07-18 00:50 | **评审方式**：三轴评审（Spec 原文 + 变更代码回读 + 行为级抽查脚本实测）

### Review Matrix

| 轴 | 关键检查 | 结论 | 证据 |
|---|---|---|---|
| Axis-1 Spec 质量与需求达成 | Goal/In/Out/Acceptance 清晰可验证 | **PASS** | §0 Done Contract 4 条均有实测证据（见 §5 Validation） |
| Axis-1 需求达成 | TD-005 详规验收（装配简化/新增工具不改引擎/既有测试通过） | **PASS** | 装配区收敛为 4 行 + 4 私有方法移除（行为抽查 4 结构性验证）；598 passed 零回归 |
| Axis-1 需求达成 | 工厂/注册行为 | **PASS** | 行为抽查 1-3：压缩+记忆全开时装配正确、属性委托一致、内部工具注册、注入优先；默认配置零内部工具 |
| Axis-2 Spec-代码一致性 | Signatures 与 Plan §3.2 对照 | **PASS** | `RuntimeServices.from_config` / `register_internal_tools` 与契约一致；装配区形态与 Plan §3.2 注释一致 |
| Axis-2 行为一致性 | 与原装配语义等价 | **PASS** | 记忆/压缩/安全集成测试全绿；注入 manager 的 policy 补注入语义保留（engine.py 显式保留块） |
| Axis-3 代码质量 | 设计质量 | **PASS** | 注册函数签名未动（涟漪面最小化）；属性委托保持下游零改动；工厂职责单一 |
| Axis-3 代码质量 | 过程质量 | **PASS（附观察项 1）** | 执行中出现一次 import 编辑失误与 4 个 F401，均已即时修正并由门禁确认 |
| Axis-3 风险 | 循环导入 | **PASS** | runtime.py 与 tools/__init__.py 均为单向依赖（TYPE_CHECKING）；mypy strict 通过 |

### Overall Verdict：**PASS（可关闭）**

### Blocking Issues：无

### 观察项（非阻塞）
1. 执行中出现一次 import 编辑失误（PLACEHOLDER 误写），同一轮内修正——过程教训：多锚点编辑应逐个验证。
2. `register_internal_tools` 的开关判断与工厂创建逻辑分离（工厂不管开关）——职责清晰，但新增内部工具时需记得两处都要加（槽位 + 注册分支），可在 TD-008 接入时验证该扩展路径。

## 7. Plan-Execution Diff

| 项 | Plan | 实际 | 性质 |
|---|---|---|---|
| 注入 manager 的 policy 补注入 | Plan 未显式提及 | engine.py 保留该块（原语义） | 行为保真，非偏差 |
| 新增测试数 | 未定量 | 9 例（5 工厂 + 4 注册） | 与 Plan 一致 |
| 其余 File Changes / Checklist | — | 全部一致 | — |

## 8. Change Log

| 时间 | 变更 |
|---|---|
| 2026-07-18 00:18 | sdd_bootstrap TD-005：Research 完成（装配区结构/依赖创建逻辑/涟漪面/循环导入核实）；用户已拍板"捆绑+工厂"方案；Plan 落盘，等待 `Plan Approved`；pip 提取增强留作后续 FAST 收尾 |
| 2026-07-18 00:40 | `Plan Approved` 收到，进入 EXECUTE。8 步 checklist 全部完成：598 passed / mypy / ruff 全绿；双 commit `f67f6df`（feat）+ `e623797`（docs）；Validation 4 项验收全部达成，待 `REVIEW EXECUTE` |
| 2026-07-18 00:50 | REVIEW EXECUTE 完成：三轴全 PASS（含 4 项行为级抽查：装配/委托/注册/注入优先/结构验证），Overall Verdict = PASS（可关闭），Blocking Issues = 无 |

## 9. Archive Record

| 时间 | 归档产物 | 模式 |
|---|---|---|
| 2026-07-18 00:35 | `mydocs/archive/2026-07-18_00-35_td-governance-round2_human.md` + `..._llm.md` | thematic（与 TD-004 合并主题"架构主线"） |

- 归档为知识衍生品，不影响本 Spec 的真相源地位；原始文件未删除/未移动。
