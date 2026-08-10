# SDD Spec: 批量 E2E 评测体系 Batch 6（大记忆库压力测试：检索层对照）

- **Spec 层级**: Feature Spec
- **创建时间**: 2026-07-21 23:10
- **当前 Phase**: EXECUTE（试点阶段）
- **Approval Status**: `APPROVED — 2026-07-21 用户批准 Plan`
- **关联**: Batch 5（小库注入通道已验证）；TD-013（提取通道已落地）；本批测检索层在大库下的表现

## 0. Open Questions

- [ ] None

## 1. Requirements (Context)

- **Goal**: 在 100 条背景记忆的压力下，测量三层检索链（L0 recency / L1 字面 / L2 语义重排）的检索质量与 `memory_search` 必要性，量化 L2 语义重排的增量价值。
- **In-Scope**:
  1. 任务集 b6（T103-T122，20 个）：大海捞针 8 + 相似干扰 6 + 深埋旧值 3 + 搜索必需 3。
  2. Runner 种子机制：程序化向 memory_root 预置 100 条记忆（目标 + 干扰 + 确定性噪声），零 API 成本；新臂 `mem-default` / `mem-semantic`。
  3. 试点 3 runs → 全批 80 runs（20 × 2 臂 × 2 采样）。
  4. 报告（L2 增量价值 + 失败分类 + 检索路径分析）+ evaluation-log + 成本。
- **Out-of-Scope**:
  - 更大规模（200+）；提取质量审计（LLM 提取噪声）；embedding/向量检索。
  - no-mem 臂（b5 已证 0%，边际信息为零）。

### 用户已决项（2026-07-21）

| 决策点 | 决定 |
|---|---|
| 背景记忆库规模 | **100 条**（注入预算覆盖 ~5%，检索必须选对） |
| 对照臂 | **L2 语义对照**：mem-default（L0+L1）vs mem-semantic（+L2） |
| 种子方式 | **程序化预置**（零 API 成本、可复现；仅 phase B 花 token） |

## 1.1 Context Sources

- Requirement Source: b5 spec Follow-ups（大库压力）；b5 报告（小库下注入通道足够，搜索非必经）
- Code Refs: `src/agent/core/memory.py`（inject 三层检索、inject_max_entries=5、inject_max_tokens=800、semantic_retrieval=False 默认）、`examples/batch_e2e.py`（臂机制、种子执行点）

## 1.7 Minimum Chaos Unit Assessment

- Final Goal: 100 条压力下的检索对照报告（80 runs），L2 增量价值量化
- Current Task Unit: 种子机制 + b6 任务集 + 双臂扩展 + 分阶段执行
- Why small enough: 复用全部基建；src 零改动；Runner 仅加种子分支与 2 个臂
- Verification Evidence: 门禁全绿；echo 冒烟；试点验证 种子落库正确 / 字面检索失败时语义臂表现分叉
- Failure / Rework Plan: L1 字面检索全部命中（搜索必需设计失效）→ 回任务集调整查询措辞（同义改写）
- User Decision: 待批准

## 2. Research Findings

- **注入预算**：`inject_max_entries=5` + `inject_max_tokens=800`——100 条库下注入覆盖率 ~5%；L0 recency 兜底注入最新 5 条，深埋旧目标必然出窗。
- **L1 字面检索按 query 与条目的字符/token 重叠排序**——查询与目标措辞同义改写（不出现共享词）时 L1 理论上失配；这正是 L2 语义重排的设计场景，也是 mem-semantic 臂的期望差异点（试点验证）。
- **种子机制**：直接 `StructuredMemoryStore.save()` 写入构造条目（content/summary/tags/updated_at 可控），无需 LLM——noise 条目确定性生成（svc-i/param-i），目标条目用 `target_age_days` 控制深度。
- **expected_tools 断言本批名正言顺**：大库下注入装不下，搜索是必经路径（与 b5 小库误杀有本质区别）；但 paraphrase 查询下 memory_search（同为字面检索）也可能失配——该现象本身即为 L2 价值证据，如实记录。
- **成本估算**：仅 phase B（无 phase A 教学），80 runs × 5-10k tokens ≈ **50-80 万 tokens**。
- **风险**：L1 比预期强（字面命中率高 → 双臂无差异）；noise 条目与目标撞词（生成时规避共享关键词）。

## 3. Innovate (Optional: Options & Decision)

### Fork 1: 种子载体
- A. **BatchTask 结构化种子字段**（`seed_facts` / `seed_decoys` / `noise_count` / `target_age_days`）→ 选 A：声明式、可测试、可复现
- B. 任务自带 seed 脚本：灵活但不透明 → 否

### Fork 2: 搜索必需实现方式
- A. **同义改写查询**（literal miss → 只能 search/L2）→ 选 A：直接命中 L2 设计场景
- B. 只测 top-k 命中率（不限工具）：信息量少 → 否

### Fork 3: mem 臂是否带 llm_extraction
- A. **不带**（b6 测检索层，phase B 提取是噪声与额外成本）→ 选 A
- B. 带：偏离测量目标 → 否

## 4. Plan (Contract)

### 4.1 File Changes

- `examples/batch_tasks.py`（修改）：`BatchTask` 增加 `seed_facts` / `seed_decoys` / `noise_count` / `target_age_days` 字段
- `examples/batch_e2e.py`（修改）：种子机制（memory_root 构造 + 确定性噪声生成 + save 预置）；`mem-default` / `mem-semantic` 臂；b6 注册与 SET_ARMS
- `examples/batch_tasks_b6.py`（新增）：`BATCH6_TASKS`（T103-T122）
- `tests/test_batch_e2e.py`（修改）：b6 完整性 + 种子生成确定性测试 + 双臂构造测试
- `docs/batch-e2e-batch6-report.md`（新增）
- `docs/evaluation-log.md`（修改）

### 4.2 Signatures

```python
# BatchTask 新增字段
seed_facts: list[str] = field(default_factory=list)    # 目标事实（写为 PREFERENCES 条目）
seed_decoys: list[str] = field(default_factory=list)   # 相似干扰条目（同类别）
noise_count: int = 0                                   # 确定性背景噪声条数
target_age_days: float = 0.0                           # 目标条目年龄（深埋控制）

# Runner 种子机制
def seed_memory(root: Path, task: BatchTask) -> None:
    """程序化预置记忆库：目标 + 干扰 + 确定性噪声（svc-i/param-i），
    目标条目按 target_age_days 回填 updated_at（深埋），噪声条目年龄递增错开。"""

# 臂定义
# mem-default:  memory.enabled=True, semantic_retrieval=False, llm_extraction=False
# mem-semantic: memory.enabled=True, semantic_retrieval=True,  llm_extraction=False
```

### 4.3 Implementation Checklist

- [ ] 1. BatchTask 字段 + Runner 种子机制 + 双臂 + 测试 → 门禁全绿
- [ ] 2. `batch_tasks_b6.py` 20 任务落盘（noise 与目标无共享关键词，自审）
- [ ] 3. `--echo --set b6 --samples 2` 冒烟 80 合成
- [ ] 4. **试点**：`--only T103,T111,T120 --arms mem-default,mem-semantic`（6 runs）→ 验证种子落库 / L1 失配设计 / 双臂分叉
- [ ] 5. **全批**：80 runs 串行后台（预计 40-70 分钟）
- [ ] 6. 聚合报告（L2 增量价值 + 失败分类 + 检索路径分析）→ `docs/batch-e2e-batch6-report.md` + evaluation-log + 成本
- [ ] 7. 回写本 Spec §5/§6/§7

### 4.4 Route Alignment (Water Flow Check)

- Original assumption: 压力测试需要 agent 教学造库（贵）
- Current route: 程序化预置（零成本），只 phase B 花 token
- Scope impact: None

## 5. Execute Log

- [x] Step 1: BatchTask 种子字段（seed_facts/seed_decoys/noise_count/target_age_days）+ Runner `seed_memory`（store.save + 时间戳回填深埋，噪声全部比目标新）+ `mem-default`/`mem-semantic` 双臂（只测检索层，不开 LLM 提取）；全量 **753 passed, 1 skipped**；ruff 全绿
- [x] Step 2: `batch_tasks_b6.py` 20 任务落盘（噪声与查询零共享关键词有测试锁定；搜索必需任务不带 expected_tools——语义臂 L2 注入即可回答时断言搜索是误杀，b5 T98 教训）
- [x] Step 3: `--echo --set b6 --samples 2` 冒烟 80 合成通过
- [x] Step 4: 试点 T103+T111+T120 双臂：种子/判分/双臂全通；T120 default 臂搜索词猜中成功、semantic 臂单样本失败（搜索词运气，待全批复核）
- [x] Step 5: 全批 80 runs（额度等待两周后于 2026-08-03 执行）：**双臂均 37/40（92%）**；17/20 任务族双臂 2/2 全过；唯一稳定失败 T122（硬 paraphrase，双臂 0/2）
- [x] Step 6: 报告落盘 `docs/batch-e2e-batch6-report.md`；evaluation-log 追加；基线 745→753；session-context 同步；总耗 **约 21.3 万 tokens**（六批最低，种子零成本生效）
- [x] Step 7: 本 Spec §6/§7 回写

## 6. Review Verdict

- Review Matrix (Mandatory):
| Axis | Key Checks | Verdict | Evidence |
|---|---|---|---|
| Spec Quality & Requirement Completion | 100 条压力检索质量已量化（字面 100% 稳健）；L2 增量价值已量化（**无可测增量**，如实阴性）；memory_search 必要性边界已定位（硬 paraphrase 瓶颈在搜索词联想） | PASS | `docs/batch-e2e-batch6-report.md` 核心发现§1-3 |
| Spec-Code Fidelity | 种子机制/双臂/任务集与 Plan 一致 | PASS | checklist 7/7；753 passed 全绿 |
| Code Intrinsic Quality | src 零改动；种子确定性有测试锁定；噪声-查询零共享词有测试锁定 | PASS | §5 Step 1-2 |
- Overall Verdict: **PASS**
- Blocking Issues: 无
- Regression risk: Low（src 零改动）
- Follow-ups:
  1. **查询扩展**（LLM 生成同义搜索词再检索）——直接针对 T122 类失败，可立项（产品改进）
  2. 简历口径补充：100 条压力检索稳健 + L2 默认关闭有数据支撑（诚实口径）
  3. 200+ 条 / 90 天深埋压力上限探测

## 7. Plan-Execution Diff

- 搜索必需任务未带 `expected_tools`（Plan 原拟携带）——执行前修正：语义臂 L2 注入即可回答时断言搜索是误杀（b5 T98 教训前置适用），改答案判分 + 工具序列记录分析。已在任务文件自审注释与 §2 记录
- 执行时间因额度等待从 07-21 延至 08-03（种子与任务集当日构建，机制无漂移）
- 其余无偏差。

## 8. Archive Record

- Archive Mode: `thematic`（并入 b1-b6 系列主题归档）
- Archive Outputs:
  - `mydocs/archive/2026-07-20_22-04_batch-e2e-benchmark-series_human.md`
  - `mydocs/archive/2026-07-20_22-04_batch-e2e-benchmark-series_llm.md`
- Key Distilled Knowledge: 程序化种子零成本测压法；L2 只重排注入候选（对 memory_search 字面本质鞭长莫及）；硬 paraphrase 的瓶颈在搜索词联想而非检索机制。

## 9. Project Sync Candidates

- 候选：「大库检索三层通道的压力表现与 L2 增量价值」→ 收口归档
- Sync decision: Not synced
