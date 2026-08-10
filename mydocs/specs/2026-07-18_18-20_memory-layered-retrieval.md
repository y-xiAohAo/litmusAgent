# Feature Spec — 记忆系统分层检索：L0 Recency 兜底 + L2 语义重排 + 内容快照

> **Spec 层级**：Feature Spec
> **协议**：SDD-RIPER-ONE（`No Spec, No Code` / `No Approval, No Execute` / `Spec is Truth`）
> **创建**：2026-07-18 18:20 | **Phase**：`PLAN` | **Status**：`[LOCKED]`
> **Approval Status**：`WAITING — 等待用户精确回复 "Plan Approved"`
> **触发**：S6 记忆叙事联调 FAIL → 三层设计审计（检索零命中根因定位）

---

## 0. 任务复述（Restate First）

- **最终目标**：修复记忆系统"存得住、取不出"的核心缺陷——中文自然语言查询下记忆召回率从 ~0 提升至可用水平，并形成可量化简历证据。
- **当前任务单元**：L0 recency 兜底 + L2 条件 LLM 语义重排 + artifact 内容快照（用户拍板全范围）。
- **In Scope**：`MemoryManager` 检索链改造、`StructuredMemoryStore.list_recent`、`RuleMemoryExtractor` 内容快照、配置扩展、测试、真实 LLM 复验（S6 场景）。
- **Out of Scope**：向量数据库/embedding；LLM 全量重排（不做，条件触发）；artifact 全量内容存储（只做截断快照）；记忆写入查重。
- **Done Contract（验证方式）**：
  1. L0：零重叠查询时注入最近 N 条记忆（`recency_fallback` 默认开；关闭时恢复零注入）。
  2. L2：`semantic_retrieval=true` 且 L1 未命中时，LLM 重排决定注入内容；LLM 失败降级 L0。
  3. 快照：`file_write` 产物的 artifact 记忆含 `content_preview`（截断）。
  4. **真实复验**：S6 原 prompt（含"项目代号"内容级提问）复跑通过。
  5. 全量门禁不回归。

## 1. Research Findings（审计结论）

1. **检索层**：`_overlap_score` 纯字面重叠（中文单字/英文单词计数）；零命中时 `inject()` 直接返回空——Agent 失忆（S6 实测）。
2. **召回层**：`memory_read` 需精确 URI，LLM 无 list 能力且会猜错 URI——注入一断全链断。
3. **存储层**：artifact 只存路径（`content: {path, type}`），不含内容——内容级问题无解。
4. **调用约束**：`inject()` 在 `run()` 的 async 上下文中被同步调用（engine.py:678）——可安全引入 `inject_async()` 而不影响其他同步调用方。
5. **基线证据**：`inject("我之前创建过什么文件？")` 对 artifact 条目返回空（实测）；`inject("notes.md")` 命中（字面重叠时工作）。

## 2. Innovate（用户已拍板）

| 决策点 | 结论 |
|---|---|
| L0 recency 兜底 | ✅ 默认开启（零成本纯收益，防零注入失忆） |
| L2 LLM 语义重排 | ✅ 条件触发（L1 未命中才调 LLM）+ 默认关闭（`memory.semantic_retrieval`） |
| 范围 | ✅ L0 + L2 + artifact 内容快照（全范围） |
| 排除 | 向量库/embedding（过重）；LLM 全量重排（成本）；写入查重（留后续） |

**降级链**：L1 命中 → 直接用；L1 未命中 + L2 开 → LLM 重排（失败 → L0）；L1 未命中 + L2 关 → L0。

## 3. Detailed Design & Implementation（Plan / The Contract）

### 3.1 File Changes

| 操作 | 路径 | 内容 |
|---|---|---|
| 修改 | `src/agent/core/memory.py` | `MemoryConfig` 增 2 字段；`StructuredMemoryStore.list_recent()`；`MemoryManager` 增 `llm_client` 参数 + `inject_async()` + L0/L2 内部方法；`RuleMemoryExtractor` artifact 内容快照 |
| 修改 | `src/agent/core/engine.py` | `run()` 改用 `await inject_async()` |
| 修改 | `src/agent/core/runtime.py` | `from_config` 透传 `llm_client` 给 MemoryManager |
| 修改 | `src/agent/config.py` | （MemoryConfig 字段实际在 memory.py 定义——核实后调整，保持一致性） |
| 新增 | `tests/test_memory_retrieval.py` | L0/L2/快照/降级测试 |
| 修改 | `docs/evaluation-log.md`、`docs/configuration.md`、`CODEMAP.md` 等 | 文档同步 |

### 3.2 Signatures（契约级）

```python
# src/agent/core/memory.py
class MemoryConfig(BaseModel):
    recency_fallback: bool = True        # L0：零命中时注入最近 N 条
    semantic_retrieval: bool = False     # L2：L1 未命中时 LLM 语义重排

class StructuredMemoryStore:
    def list_recent(self, limit: int) -> list[MemoryEntry]:
        """按 updated_at 降序返回最近 limit 条记忆。"""

class MemoryManager:
    def __init__(self, ..., llm_client: Any | None = None) -> None: ...

    async def inject_async(self, user_input: str) -> str:
        """异步注入入口：L1 → (未命中) L2 语义重排 → (兜底) L0 recency。"""

    def _recency_fallback(self) -> list[MemoryEntry]:
        """L0：返回按时间排序的最近 top_k 条（经读策略过滤）。"""

    async def _semantic_rank(
        self, query: str, candidates: list[MemoryEntry]
    ) -> list[MemoryEntry]:
        """L2：LLM 对候选记忆按与 query 的相关性排序（JSON 输出，失败返回 []）。"""

# RuleMemoryExtractor._extract_artifacts：
# file_write 事件的 arguments.content 截断 ~200 字 → entry.content["content_preview"]
```

### 3.3 Implementation Checklist（原子步骤）

- [ ] 1. **RED**：L0 测试 3 例（零命中兜底注入最近 / 关闭时零注入 / 经读策略过滤）→ 确认失败
- [ ] 2. **GREEN**：`list_recent` + `_recency_fallback` + 配置字段 → 跑通
- [ ] 3. **RED**：L2 测试 3 例（LLM JSON 排序 / LLM 失败降级 L0 / 未启用不走 LLM）→ 确认失败
- [ ] 4. **GREEN**：`inject_async` + `_semantic_rank` + engine/runtime 接线 → 跑通
- [ ] 5. **RED**：快照测试 2 例（file_write 产物含 content_preview / 截断上限）→ 确认失败
- [ ] 6. **GREEN**：extractor 快照 → 跑通 + 全量门禁
- [ ] 7. **真实复验**：S6 原 prompt（"项目代号"内容级提问）×2，记录通过率（对照修复前 0/2）
- [ ] 8. 文档同步 + 双 commit

### 3.4 风险与回滚

| 风险 | 缓解 |
|---|---|
| `inject` 同步签名被其他调用方依赖 | 保留同步 `inject()`（L0+L1），engine 切 `inject_async`；测试锁定两路径 |
| L2 JSON 解析失败/格式漂移 | 宽容解析（找 id 子串）；失败降级 L0；测试覆盖 |
| 快照增大存储体积 | 截断 200 字 + 仅 file_write 产物 |
| recency 注入不相关记忆干扰 | 限 top_k + 仍过读策略 + 标注"最近记忆"区段 |
| 回滚 | `git checkout HEAD -- src/agent/core/memory.py src/agent/core/engine.py src/agent/core/runtime.py` |

---

## 4. Execute Log

| 步骤 | 内容 | 结果 |
|---|---|---|
| 1-2 | L0 测试 4 例 RED→GREEN（`list_recent` + `_recency_fallback` + 配置）；修正一处误插入 ABC 的编辑 | 全过 |
| 3-4 | L2 测试 4 例 RED→GREEN（`inject_async`/`_semantic_rank`/engine/runtime 接线）；发现并修复 L0 吞掉 L2 触发的逻辑缺陷 | 全过 |
| 5-6 | 快照测试 2 例 RED→GREEN（extractor content_preview） | 全过 |
| 7a | 真实复验第一轮：路径级 2/2，内容级 0/2——发现注入器只渲染 summary 不渲染快照 | 缺口定位 |
| 7b | MemoryInjector 渲染 content_preview + 1 测试；真实复验第二轮：**内容级 2/2 + 路径级 2/2** | ✅ 完全通过 |
| 8 | 全量门禁 664 passed / mypy / ruff 全绿；双 commit `434e2bf` + `a473a4c` | 工作区干净 |

## 5. Validation

| 验收项（Done Contract） | 证据 | 结论 |
|---|---|---|
| 1. L0 零命中注入最近 N 条；关闭时零注入 | `TestRecencyFallback` 4 例（含 L1 命中不触发兜底） | ✅ |
| 2. L2 条件触发 / LLM 失败降 L0 / 未启用不调 LLM / L1 命中不调 LLM | `TestSemanticRerank` 4 例 | ✅ |
| 3. file_write 产物含 content_preview（截断 200） | `TestArtifactContentPreview` 2 例 + `TestInjectorPreview` 1 例 | ✅ |
| 4. 真实复验：S6 内容级提问 | **2/2 通过**（修复前 0/2；Agent 准确回答 notes.md 与 hermes-2026） | ✅ |
| 5. 全量门禁 | 664 passed（653+11）；mypy 45 文件零错误；ruff 全绿 | ✅ |

## 6. Review Verdict

**评审时间**：2026-07-18 19:10 | **评审方式**：三轴评审（Spec 原文 + 变更代码回读 + 两轮真实复验 + 真实 LLM 抽查）

### Review Matrix

| 轴 | 关键检查 | 结论 | 证据 |
|---|---|---|---|
| Axis-1 Spec 质量与需求达成 | Goal/In/Out/Acceptance 清晰可验证 | **PASS** | §0 Done Contract 5 条均有实测证据（见 §5 Validation） |
| Axis-1 需求达成 | L0/L2/快照三层修复 | **PASS** | 11 例单测全过；真实复验 S6 内容级 2/2 + 路径级 2/2（修复前 0/2） |
| Axis-1 需求达成 | 真实 LLM 下检索相关性 | **PASS** | 抽查：语义相关问题注入“川菜”且不含无关“numpy”；L0 兑底与同步 inject 兼容路径均正常 |
| Axis-2 Spec-代码一致性 | Signatures 与 Plan §3.2 对照 | **PASS（含 2 项增补）** | 契约签名全部一致；`list_recent` 落位于 StructuredMemoryStore（非 ABC）；`MemoryInjector` 快照渲染为复验中发现的必要增补 |
| Axis-2 行为一致性 | 默认行为兼容 | **PASS** | 同步 `inject()` 保留（L0+L1）；`semantic_retrieval` 默认关；既有记忆测试 105 例零回归 |
| Axis-3 代码质量 | 降级健壮性 | **PASS** | L2 调用失败/JSON 解析失败均降 L0；client None 防御；异常不阻塞主循环 |
| Axis-3 代码质量 | 过程质量 | **PASS（附观察项 2）** | 执行中出现 1 次 ABC 误插入与 1 次重复定义，均即时修正并门禁确认 |
| Axis-3 风险 | 行为变化面 | **PASS** | L0 默认开改变零命中时的行为（空→注入最近 N 条）——这是本任务的目标行为，已文档化 |

### Overall Verdict：**PASS（可关闭）**

### Blocking Issues：无

### 观察项（非阻塞）
1. **memory_read URI 可发现性**：LLM 会从文件名猜 URI（`artifacts/notes.md.jsonl`）而非真实 entry_id——召回链的已知弱点，候选改进：注入文本附带条目 URI 或提供 memory_list 工具。
2. 执行过程编辑失误 2 次（ABC 误插入/inject 重复定义）——教训：大块替换后先跑 mypy 再继续。
3. L2 的 LLM 排序对长记忆库的 token 消耗随 top_k 线性增长——未来可加候选预筛。

## 7. Plan-Execution Diff

| 项 | Plan | 实际 | 性质 |
|---|---|---|---|
| `list_recent` 位置 | Plan 未明确 | StructuredMemoryStore（非 ABC），`_recency_fallback` 带 hasattr 兑底 | 实现选择，更稳健 |
| 注入器快照渲染 | Plan 未包含 | MemoryInjector 增加 content_preview 渲染（复验发现的必要增补） | ✅ 执行期发现，先验证后修复，合规 |
| 新增测试数 | 未定量 | 11 例 | 与 Plan 一致 |
| 其余 File Changes / Checklist | — | 全部一致 | — |

## 8. Change Log

| 时间 | 变更 |
|---|---|
| 2026-07-18 18:20 | sdd_bootstrap 记忆分层检索单元：审计完成（三层缺陷定位）；用户拍板三项决策（L0 默认开 / L2 条件触发默认关 / 含内容快照全范围）；Plan 落盘，等待 `Plan Approved` |
| 2026-07-18 18:50 | `Plan Approved` 收到，进入 EXECUTE。8 步 checklist 完成（含两轮真实复验：第一轮发现注入器不渲染快照的残留缺口并修复）；S6 复验 0/2→2/2；双 commit `434e2bf` + `a473a4c`；待 `REVIEW EXECUTE` |
| 2026-07-18 19:10 | REVIEW EXECUTE 完成：三轴全 PASS（含真实 LLM 抽查：语义相关注入正确、L0 兑底与兼容路径正常），Overall Verdict = PASS（可关闭），Blocking Issues = 无 |
