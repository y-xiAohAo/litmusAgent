# Feature Spec — TD-006：文件写操作 workspace 边界限制

> **Spec 层级**：Feature Spec
> **协议**：SDD-RIPER-ONE（`No Spec, No Code` / `No Approval, No Execute` / `Spec is Truth`）
> **创建**：2026-07-17 21:45 | **Phase**：`PLAN` | **Status**：`[LOCKED]`
> **Approval Status**：`WAITING — 等待用户精确回复 "Plan Approved"`
> **上游依据**：`.kimi/vibe_specs/technical-debt-spec.md` TD-006 详规
> **前序**：TD-002+003 已交付（`811babb`/`e8b4c6e`），评测日志已同步（`a7c2c74`）

---

## 0. 任务复述（Restate First）

- **最终目标**：为 `file/path` write 操作建立默认 workspace 边界——只允许写入 `/workspace`（或可配置的 workspace）之下，其余路径默认拒绝，敏感路径保持原有高优先级拒绝。
- **当前任务单元**：TD-006 单项，纯策略层改动（YAML 规则 + 配置字段 + 测试 + 文档），不触碰工具实现与主循环。
- **In Scope**：`default_security_rules.yaml` 边界规则组；`SecurityConfig.workspace_path` 配置；`build_policy_engine()` 自定义 workspace 覆盖；安全测试与文档同步。
- **Out of Scope**：read 规则变更；文件系统 ACL；`ToolRegistry` 执行逻辑变更；TD-004/005/007/008。
- **Done Contract（验证方式）**：
  1. `file_write`/`file_edit` 写 `/workspace/...` → 允许；写 `/etc/passwd` → 拒绝（原有敏感规则）；写 `/tmp/...` → 默认拒绝（新增）；写 `/workspace/../etc/passwd` 等含 `..` 路径 → 拒绝（新增）。
  2. `security.workspace_path: "/app"` 时，`/app/x.py` 允许、`/workspace/x.py` 拒绝（边界随配置迁移）。
  3. 全量门禁：pytest（≥566+新增）/ mypy / ruff 全绿；`SecurityConfig.enabled=False` 默认行为零变化。

---

## 1. Research Findings（关键事实）

1. **引擎语义**：`PolicyEngine.evaluate()` 按 priority 降序取第一条命中规则；无命中走 `default_action`（默认 ALLOW）。→ 边界可用纯规则表达，**无需改引擎代码**（除配置装配）。
2. **归一化**：`file/path` subject 经 `_normalize_file_path_subject` 统一小写、`\`→`/`，规则 pattern 用小写 POSIX 风格即可。
3. **现状缺口**：默认规则集中 `file/path` write 只有敏感路径 deny（priority 90-100），无 catch-all → 其余路径全部默认 ALLOW（TD-006 根因）。
4. **逃逸面**：`..` 未被任何规则覆盖；`/workspace/../etc/passwd` 能被敏感规则兜住（子串匹配），但 `/workspace/../tmp/x` 会逃逸 → 需要独立的 `..` 拒绝规则。
5. **回归面**：现有安全测试（`test_tool_security.py` / `test_security_integration.py`）在策略启用下只写 `/workspace/result.txt`（允许侧）和 `/etc/passwd`（拒绝侧），**无 /tmp 写入** → deny catch-all 不破坏既有测试。
6. **配置装配**：`SecurityConfig.build_policy_engine()` 两条路径——`rules` 为空走默认 YAML；非空则自定义规则完全接管（边界不注入，语义保持"自定义全权"）。
7. **默认关闭**：`SecurityConfig.enabled=False` 时 `build_policy_engine()` 返回 None，本任务一切改动对默认行为零影响。

## 2. Innovate（方案对比与决策）

| 方案 | 描述 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| A. YAML 静态边界 + 配置覆盖追加 | 默认 YAML 加 `/workspace` 边界三件套；`workspace_path != "/workspace"` 时 `build_policy_engine` 追加高优先级覆盖规则 | 默认集自包含可读；配置可迁移边界 | 覆盖逻辑需精确处理优先级 | ✅ **选定** |
| B. 纯代码动态生成 | 边界规则全由 `build_policy_engine` 按 `workspace_path` 生成，YAML 不放 | 无静态/动态重复 | 违背 TD-006 详规 Must Have 1（要求写进 YAML）；默认集不再自包含 | ❌ |
| C. 引擎增加"默认 deny 资源"概念 | 扩展 PolicyEngine 语义 | 表达力强 | 改引擎核心语义，风险与范围超标 | ❌ |

**边界三件套设计（默认 YAML，`file/path` + `write`）**：

| priority | action | pattern | 作用 |
|---|---|---|---|
| 95 | deny | `\.\.` | 拒绝一切含 `..` 的逃逸路径（高于 allow，低于敏感路径 100） |
| 50 | allow | `^/workspace(/|$)` | workspace 边界内允许 |
| 1 | deny | `.*` | catch-all：workspace 以外默认拒绝 |

- 既有敏感路径 deny（priority 90-100）不受影响，仍最先命中。
- `workspace_path` 自定义时追加：allow `^{custom}(/|$)` priority 60 + deny `^/workspace(/|$)` priority 55（撤销默认边界）。

## 3. Detailed Design & Implementation（Plan / The Contract）

### 3.1 File Changes

| 操作 | 路径 | 内容 |
|---|---|---|
| 修改 | `src/agent/core/default_security_rules.yaml` | 新增边界三件套规则（见上表） |
| 修改 | `src/agent/config.py` | `SecurityConfig` 新增 `workspace_path: str = "/workspace"`；`build_policy_engine()` 在走默认规则集且 `workspace_path != "/workspace"` 时追加覆盖规则（allow-60 / deny-55，`re.escape` 前缀、去尾部 `/`、转小写） |
| 修改 | `tests/test_tool_security.py` | 新增：写 `/workspace/x` 允许、写 `/tmp/x` 拒绝、写 `/workspace/../etc/passwd` 拒绝、`file_edit` 同样边界 |
| 修改 | `tests/test_config.py` | 新增：`workspace_path` 默认值、自定义 `/app` 时 `/app/x` 允许且 `/workspace/x` 拒绝、自定义规则集不注入边界 |
| 修改 | `docs/configuration.md` | `security.workspace_path` 配置说明与默认边界行为 |
| 修改 | `.kimi/vibe_specs/technical-debt-spec.md` | TD-006 → ✅ 已完成 |
| 修改 | `docs/evaluation-log.md` | EVAL-008 → ✅ 已修复（显式边界，补完"部分修复"） |
| 修改 | `docs/progress-spec.md`、`docs/session-context.md`、`CODEMAP.md` | 状态与变更日志同步 |

### 3.2 Signatures（契约级）

```python
# src/agent/config.py —— SecurityConfig 新增字段（其余不变）
class SecurityConfig(BaseModel):
    workspace_path: str = "/workspace"   # file/path write 的允许根（POSIX 风格）

    def build_policy_engine(self) -> PolicyEngine | None: ...
    # 行为增补：仅当使用默认规则集（rules 为空）且 workspace_path != "/workspace" 时，
    # 在引擎上追加两条覆盖规则；自定义规则集不注入。

# default_security_rules.yaml 新增（结构示意，非完整 YAML）：
# - resource: file/path, operation: write, pattern: "\\.\\.", action: deny, priority: 95
# - resource: file/path, operation: write, pattern: "^/workspace(/|$)", action: allow, priority: 50
# - resource: file/path, operation: write, pattern: ".*", action: deny, priority: 1
```

### 3.3 Implementation Checklist（原子步骤）

- [ ] 1. **RED**：`tests/test_tool_security.py` 新增边界用例（allow /workspace、deny /tmp、deny `..`、file_edit 同边界）→ 确认失败
- [ ] 2. **GREEN**：YAML 边界三件套 → 跑通步骤 1 + 既有安全测试不回归
- [ ] 3. **RED**：`tests/test_config.py` 新增 `workspace_path` 三例 → 确认失败
- [ ] 4. **GREEN**：`SecurityConfig.workspace_path` + `build_policy_engine()` 覆盖逻辑 → 跑通步骤 3
- [ ] 5. 全量门禁复核（pytest / mypy / ruff）
- [ ] 6. 文档与状态同步（configuration / technical-debt-spec / evaluation-log / progress-spec / session-context / CODEMAP）
- [ ] 7. 双 commit：`feat: enforce workspace boundary for file write operations (TD-006)` + `docs: sync docs for workspace write boundary (TD-006)`

### 3.4 风险与回滚

| 风险 | 缓解 |
|---|---|
| deny catch-all 误伤既有策略启用场景 | 已核查：现有安全测试无 /tmp 写入；全量 pytest 兜底 |
| 自定义覆盖规则优先级错配 | 测试断言 `/app` 允许且 `/workspace` 拒绝双方向 |
| LLM 习惯写 /tmp 导致任务失败率上升 | 路由提示已引导 `/workspace`（EVAL-008 部分修复）；拒绝信息中说明边界 |
| 回滚 | `git checkout HEAD -- src/agent/core/default_security_rules.yaml src/agent/config.py` |

---

## 4. Execute Log

| 步骤 | 内容 | 结果 |
|---|---|---|
| 1 RED | `TestWorkspaceWriteBoundary` 5 例（test_tool_security.py） | 3 个 deny 侧失败，RED 成立 |
| 2 GREEN | YAML 边界三件套（deny `..` @95 / allow `/workspace` @50 / deny `.*` @1） | 边界 5 例通过；安全 5 测试文件 73 passed 零回归 |
| 3 RED | `TestSecurityConfigWorkspacePath` 4 例（test_config.py） | 字段缺失/覆盖逻辑缺失，2 失败，RED 成立 |
| 4 GREEN | `SecurityConfig.workspace_path` + `_apply_workspace_override()`（allow-60/deny-55） | 23 passed |
| 5 | 全量门禁 | 575 passed / mypy 44 文件零错误 / ruff 全绿 |
| 6 | 文档同步（configuration / technical-debt-spec / evaluation-log / progress-spec / session-context / CODEMAP） | 已落盘（evaluation-log 表格插入位置失误两次，均已修复并复核） |
| 7 | 双 commit：`5fb0122`（feat）、`00e9479`（docs） | 工作区干净 |

## 5. Validation

| 验收项（Done Contract） | 证据 | 结论 |
|---|---|---|
| 1. /workspace 允许、/etc/passwd 拒绝、/tmp 拒绝、`..` 逃逸拒绝 | `TestWorkspaceWriteBoundary` 5 例（含 file_edit 共享边界、敏感路径优先级不受影响） | ✅ |
| 2. `workspace_path: /app` 时 /app 允许、/workspace 拒绝 | `TestSecurityConfigWorkspacePath` 4 例（含自定义规则集不注入边界） | ✅ |
| 3. 全量门禁 + 默认行为零变化 | **575 passed, 1 skipped**（566+9）；mypy/ruff 全绿；`enabled=False` 时 `build_policy_engine()` 仍返回 None | ✅ |

## 6. Review Verdict

**评审时间**：2026-07-17 22:10 | **评审方式**：三轴评审（Spec 原文 + 变更代码回读 + 行为级抽查脚本实测）

### Review Matrix

| 轴 | 关键检查 | 结论 | 证据 |
|---|---|---|---|
| Axis-1 Spec 质量与需求达成 | Goal/In/Out/Acceptance 清晰可验证 | **PASS** | Spec §0 Done Contract 3 条均有实测证据（见 §5 Validation）；Out of Scope 明确（read 规则/ACL/引擎语义不变） |
| Axis-1 需求达成 | TD-006 验收三条（/workspace 允许、/etc/passwd 拒绝、/tmp 拒绝） | **PASS** | `TestWorkspaceWriteBoundary` 5 例 + 行为抽查 3：`/workspace`→allow、`/tmp`→deny、`..`→deny、大小写/反斜杠归一化正确 |
| Axis-1 需求达成 | `workspace_path` 配置迁移边界 | **PASS** | `TestSecurityConfigWorkspacePath` 4 例 + 行为抽查 3c：`/app` 允许且 `/workspace` 拒绝；自定义规则集不注入 |
| Axis-2 Spec-代码一致性 | File Changes 与 Plan §3.1 对照 | **PASS** | 8 项文件变更全部落实，无计划外代码文件 |
| Axis-2 Spec-代码一致性 | Signatures 与 Plan §3.2 对照 | **PASS** | `workspace_path` 字段与 `build_policy_engine()` 行为增补一致；覆盖实现抽出为 `_apply_workspace_override()`（实现组织差异，行为等价） |
| Axis-2 优先级正确性 | 三件套与既有敏感规则的优先级关系 | **PASS** | 行为抽查：`/etc/passwd` 仍命中 100 优先 deny；allow-50 不越权；覆盖规则 60/55 顺序正确 |
| Axis-3 代码质量 | 正确性/健壮性 | **PASS** | 前缀 `re.escape`、去尾 `/`、统一小写；`/workspace2` 类前缀不误判（`(/|$)` 锚定） |
| Axis-3 代码质量 | 回归风险 | **PASS** | 安全 5 测试文件 73 passed 零回归；`enabled=False` 返回 None 不变；全量 575 passed |
| Axis-3 风险 | 默认行为变化面 | **PASS（附观察项）** | 策略启用且写 /tmp 的存量用法会被拒绝——属本任务目标行为本身；路由提示已引导 /workspace |

### Overall Verdict：**PASS（可关闭）**

### Blocking Issues：无

### 观察项（非阻塞）
1. `_apply_workspace_override()` 内使用函数级 `import re` 与 PolicyRule 导入——为避免扩大模块顶部 import 面，可接受；后续若配置项增多可上提。
2. 评审过程中发现 `docs/evaluation-log.md` 两处表格分隔行列数与表头不一致（历史遗留），插入新行时两次误定位，均已修复——建议后续为该文档补充表格一致性校验测试（候选小任务）。

## 7. Plan-Execution Diff

| 项 | Plan | 实际 | 性质 |
|---|---|---|---|
| 覆盖逻辑组织 | `build_policy_engine()` 内追加 | 抽为 `_apply_workspace_override()` 私有方法 | 等价重构，签名契约不变 |
| 新增测试数 | 未定量 | 9 例（5 边界 + 4 配置） | 超出 Plan 下限，向上偏差 |
| 其余 File Changes / Checklist | — | 全部一致 | — |

## 8. Change Log

| 时间 | 变更 |
|---|---|
| 2026-07-17 21:45 | sdd_bootstrap TD-006：Research 完成（引擎语义/归一化/回归面/配置装配核实），Innovate 选定方案 A（YAML 静态边界 + 配置覆盖追加），Plan 落盘，等待 `Plan Approved` |
| 2026-07-17 22:00 | `Plan Approved` 收到，进入 EXECUTE。7 步 checklist 全部完成：575 passed / mypy / ruff 全绿；双 commit `5fb0122`（feat）+ `00e9479`（docs）；Validation 3 项验收全部达成，待 `REVIEW EXECUTE` |
| 2026-07-17 22:10 | REVIEW EXECUTE 完成：三轴全 PASS（含行为级抽查脚本实测），Overall Verdict = PASS（可关闭），Blocking Issues = 无，Plan-Execution Diff 仅 2 项非偏差项 |

## 9. Archive Record

| 时间 | 归档产物 | 模式 |
|---|---|---|
| 2026-07-17 22:15 | `mydocs/archive/2026-07-17_22-15_td-governance-round1_human.md` + `..._llm.md` | thematic（与 TD-002/003 合并主题"技术债治理第一轮"） |

- 归档为知识衍生品，不影响本 Spec 的真相源地位；原始文件未删除/未移动。
