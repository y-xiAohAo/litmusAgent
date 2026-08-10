# Feature Spec — memory_search 工具：记忆召回的 search-then-read 重构

> **Spec 层级**：Feature Spec
> **协议**：SDD-RIPER-ONE（`No Spec, No Code` / `No Approval, No Execute` / `Spec is Truth`）
> **创建**：2026-07-18 19:40 | **Phase**：`PLAN` | **Status**：`[LOCKED]`
> **Approval Status**：`WAITING — 等待用户精确回复 "Plan Approved"`
> **上游**：记忆分层检索单元评审观察项 1（memory_read URI 可发现性）；用户拍板"系统化方案，不打补丁"

---

## 0. 任务复述（Restate First）

- **最终目标**：让 LLM 能用自然语言搜索记忆（而非猜 URI），打通"发现 → 读取"的完整召回闭环。
- **当前任务单元**：新增 `memory_search` 内部工具（复用分层检索）+ `memory_read` 保持按 id 精读。
- **In Scope**：`MemoryManager.search()`、新工具 `memory_search`、`register_memory_tools` 注册、测试、真实复验。
- **Out of Scope**：注入文本附带 URI（补丁方案，已排除）；URI 模糊解析（安全弱化，已排除）；memory_list 全量浏览（search 覆盖）。
- **Done Contract（验证方式）**：
  1. `memory_search("项目代号")` 返回含 entry_id/category/summary/content_preview/uri 的候选列表（JSON）。
  2. 空库/无命中返回空列表而非错误；结果数受 limit 约束；只读策略生效。
  3. **真实复验**：LLM 在 S6 式场景中能通过 memory_search 找到记忆（不再猜 URI 报错）。
  4. 全量门禁不回归。

## 1. Research Findings

1. **交互反模式已实证**：LLM 两次猜 URI 失败（`hermes://memory/` 根路径 / 按文件名拼 `notes.md.jsonl`），烧轮次且被错误文案误导。
2. **检索能力已就绪**：本单元刚交付的 `_retrieve_l1` / `_recency_fallback` / `_semantic_rank` 可直接复用为搜索后端——**一次投资，注入与工具两个出口**。
3. **同构先例**：`memory_read` 为 async handler + manager 注入模式（tools/memory_read.py），`register_memory_tools` 统一注册内部工具。
4. **安全边界**：`manager.check_read_policy(uri)` 已有读策略检查；search 结果逐条过 `_filter_readable_entries`。

## 2. Innovate

已由用户拍板：系统化 search-then-read 方案，排除补丁（注入附 URI / URI 模糊解析）。无遗留分叉。

## 3. Detailed Design & Implementation（Plan / The Contract）

### 3.1 File Changes

| 操作 | 路径 | 内容 |
|---|---|---|
| 修改 | `src/agent/core/memory.py` | `MemoryManager` 新增 `search()` 方法 |
| 新增 | `src/agent/tools/memory_search.py` | `memory_search` 工具 handler |
| 修改 | `src/agent/tools/__init__.py` | `register_memory_tools` 同时注册 memory_search |
| 新增 | `tests/test_memory_search.py` | 工具与 search 方法测试 |
| 修改 | `docs/configuration.md`、`CODEMAP.md` 等 | 文档同步 |

### 3.2 Signatures（契约级）

```python
# src/agent/core/memory.py
class MemoryManager:
    async def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """按自然语言搜索记忆（search-then-read 的发现层）。

        复用分层检索：L1 命中直接用；未命中按配置走 L2/L0。
        返回结构化候选：[{entry_id, category, summary, content_preview, uri}, ...]，
        按相关性排序，最多 limit 条；空库/无命中返回 []。"""

# src/agent/tools/memory_search.py
async def memory_search(query: str, manager: MemoryManager, limit: int = 5) -> ToolResult:
    """搜索长期记忆并返回候选（含可传给 memory_read 的 uri）。"""
```

### 3.3 Implementation Checklist（原子步骤）

- [ ] 1. **RED**：`search()` 测试 4 例（命中含完整字段 / 空库返回 [] / limit 截断 / L1 未命中走 L0 兜底）→ 确认失败
- [ ] 2. **GREEN**：`MemoryManager.search()` → 跑通
- [ ] 3. **RED**：`memory_search` 工具测试 3 例（ToolResult 内容含 JSON 候选 / 注册后可经 registry 调用 / 无命中返回空列表提示）→ 确认失败
- [ ] 4. **GREEN**：工具 + 注册 → 跑通 + 全量门禁
- [ ] 5. **真实复验**：新 Agent（带记忆库）被问记忆相关问题，观察是否使用 memory_search（记录行为）
- [ ] 6. 文档同步 + 双 commit

### 3.4 风险与回滚

| 风险 | 缓解 |
|---|---|
| LLM 不使用新工具（习惯不改） | 工具描述写明"想查找历史记忆时使用"；真实复验观察，必要时调 system prompt |
| search 结果过大 | limit 默认 5 + preview 截断 |
| 读策略绕过 | 结果逐条过 `_filter_readable_entries`；测试覆盖 |
| 回滚 | 删除新文件 + revert 注册行 |

---

## 4. Execute Log

| 步骤 | 内容 | 结果 |
|---|---|---|
| 1 RED | `test_memory_search.py` 8 例 | 8 失败（方法/工具/注册均不存在），RED 成立 |
| 2-4 GREEN | `MemoryManager.search()` + `memory_search` 工具 + `register_memory_tools` 注册 | 8 passed；全量 672 passed / mypy 46 文件零错误 / ruff 全绿 |
| 5 真实复验 | S6 式跨实例记忆场景，观察 LLM 工具行为 | **LLM 自然形成 `memory_search` → `memory_read` → 答出代号链路，零 URI 猜测错误** |
| 6 | 文档同步 + 双 commit：`149c535`（feat）、`8478ae2`（docs） | 工作区干净 |

## 5. Validation

| 验收项（Done Contract） | 证据 | 结论 |
|---|---|---|
| 1. search 返回含 entry_id/category/summary/content_preview/uri 的候选 | `test_hit_returns_full_fields` | ✅ |
| 2. 空库/无命中返回空列表；limit 截断；读策略生效 | `test_empty_store` / `test_limit_truncates` / 结果经 `_filter_readable_entries` | ✅ |
| 3. 真实复验：LLM 通过 memory_search 找到记忆（不猜 URI） | 工具序列 `memory_search → memory_read → file_read`；搜索 query 为自然语言；回答含 hermes-2026 | ✅ |
| 4. 全量门禁 | 672 passed（664+8）；mypy 46 文件零错误；ruff 全绿 | ✅ |

## 6. Review Verdict

**评审时间**：2026-07-18 20:10 | **评审方式**：三轴评审（Spec 原文 + 变更代码回读 + 真实 LLM 行为复验 + 读策略抽查）

### Review Matrix

| 轴 | 关键检查 | 结论 | 证据 |
|---|---|---|---|
| Axis-1 Spec 质量与需求达成 | Goal/In/Out/Acceptance 清晰可验证 | **PASS** | §0 Done Contract 4 条均有实测证据（见 §5 Validation） |
| Axis-1 需求达成 | search-then-read 闭环 | **PASS** | 真实复验：LLM 自然形成 `memory_search → memory_read → 答出代号`链路，零 URI 猜测错误 |
| Axis-2 Spec-代码一致性 | Signatures 与 Plan §3.2 对照 | **PASS** | `search()` / `memory_search` 签名与契约一致；注册并入 `register_memory_tools` 如 Plan |
| Axis-2 行为一致性 | 安全边界保持 | **PASS** | 抽查：读策略在 search 路径实际生效（environment 条目被过滤，artifacts 正常）；未触碰 URI 校验 |
| Axis-3 代码质量 | 检索复用与降级 | **PASS** | search() 复用 L1/L2/L0 分层检索（零重复代码）；空库/无命中/未启用均返回空列表非错误 |
| Axis-3 代码质量 | 工具设计质量 | **PASS** | JSON 结构化输出含 uri（可衔接 memory_read）；描述引导 LLM 正确使用（实测被自然采纳） |
| Axis-3 风险 | 行为变化面 | **PASS** | 纯增量（新工具 + 新方法），既有路径零改动，672 passed 全绿 |

### Overall Verdict：**PASS（可关闭）**

### Blocking Issues：无

### 观察项（非阻塞）
1. `memory_search` 的 tool description 当前有效引导了 DeepSeek，其他模型可能需要实测微调。
2. 记忆库规模增长后，search 的 L0 兑底（最近 N 条）可能与查询无关——未来可加时间衰减权重或最小相关性阈值。

## 7. Plan-Execution Diff

| 项 | Plan | 实际 | 性质 |
|---|---|---|---|
| File Changes / Signatures / Checklist | — | 全部一致 | 零偏差 |
| 新增测试数 | 未定量 | 8 例 | 与 Plan 一致 |

## 8. Archive Record

（待归档后填写）

| 时间 | 变更 |
|---|---|
| 2026-07-18 19:40 | sdd_bootstrap memory_search 单元：Research 完成（交互反模式实证/检索能力可复用确认）；用户拍板系统化方案；Plan 落盘，等待 `Plan Approved` |
| 2026-07-18 20:00 | `Plan Approved` 收到，进入 EXECUTE。6 步 checklist 完成：672 passed 全绿；真实复验 search-then-read 链路自然形成；双 commit `149c535` + `8478ae2`；待 `REVIEW EXECUTE` |

## 9. Change Log

| 时间 | 变更 |
|---|---|
| 2026-07-18 19:40 | sdd_bootstrap memory_search 单元：Research 完成；用户拍板系统化方案；Plan 落盘，等待 `Plan Approved` |
| 2026-07-18 20:00 | `Plan Approved` 收到，进入 EXECUTE。6 步 checklist 完成：672 passed 全绿；真实复验 search-then-read 链路自然形成；双 commit `149c535` + `8478ae2` |
| 2026-07-18 20:10 | REVIEW EXECUTE 完成：三轴全 PASS（含读策略抽查），Overall Verdict = PASS（可关闭），Blocking Issues = 无 |
