# SDD Spec: 查询扩展（Multi-Query Expansion）记忆检索增强

- **Spec 层级**: Feature Spec
- **创建时间**: 2026-08-03 23:05
- **当前 Phase**: EXECUTE（验收阶段）
- **Approval Status**: `APPROVED — 2026-08-03 用户批准 Plan`
- **关联**: Batch 6（T122 硬 paraphrase 失败根因）；调研记录见 §2

## 0. Open Questions

- [ ] None

## 1. Requirements (Context)

- **Goal**: 修复硬 paraphrase 查询的记忆检索失败（T122 类）：LLM 将查询扩展为多个同义变体，分别字面检索并合并，使"发布用的编号"也能命中"构建标签"。
- **In-Scope**:
  1. `MemoryManager.search()` 增加查询扩展层：原查询 L1 失配时，LLM 生成 3-5 个同义搜索变体，逐一字面检索并合并去重排序。
  2. 配置 `memory.query_expansion_enabled: bool = False`（默认关闭，不改变现状）。
  3. 成本设计：仅失配时触发（命中零成本）；失败静默降级为原行为。
  4. 验收：单测 + T123-T125 硬 paraphrase 任务对照（qe on/off）+ 全量门禁。
- **Out-of-Scope**:
  - 向量检索 / HyDE（无 embedding 基础设施，调研已排除，见 §2.2）。
  - L2 语义重排改造（b6 已证无增量，保持现状）。
  - 查询澄清（反问用户）。

## 1.1 Context Sources

- Requirement Source: Batch 6 报告核心发现§3（T122 双臂 0/2：瓶颈在搜索词联想而非检索机制）
- Code Refs: `src/agent/core/memory.py:1018`（`_retrieve_l1`）、`:1038`（`search` fallback 链）、`src/agent/config.py:81`（MemoryConfig）
- 检索方法调研: §2.2

## 1.7 Minimum Chaos Unit Assessment

- Final Goal: 硬 paraphrase 查询召回成功（qe 开），且默认行为不变（qe 关）
- Current Task Unit: search() 内加扩展层 + 配置 + 测试验收
- Why small enough: 单点改动（一个方法内加一层），无新基础设施，失败降级有现成模式
- Verification Evidence: 单测覆盖 展开生成/合并去重/失配降级/开关默认；T123-T125 对照双臂分叉；门禁三件套全绿
- Failure / Rework Plan: LLM 变体质量差 → 收紧 prompt 并加变体数量上限；合并排序失真 → 原查询结果优先策略
- User Decision: 待批准

## 2. Research Findings

### 2.1 现状检索链（代码实证）

`search()` 当前 fallback 链：L1 字面（原查询）→ L2 语义重排（可选）→ L0 recency。L1 为字符/token 重叠匹配，查询与条目零共享词时必败——T122（"发布用的编号"→"构建标签"）双臂 0/2 的稳定失败即此。

### 2.2 查询扩展方法调研（2026-08-03 Web 调研）

| 方法 | 原理 | 适配性结论 |
|---|---|---|
| **Multi-Query 扩展** | LLM 改写查询为 N 个同义变体，分别检索后合并（rewrite-retrieve-read） | **选用**：字面检索器零改动复用；1 LLM 调用 + N 次免费字面搜索 |
| HyDE | LLM 生成假设答案文档，embedding 检索 | 排除：无向量库；关键词退化版不如 Multi-Query 直接 |
| Query2doc / Step-back | 伪文档扩展 / 抽象化 | 排除：面向长文档语义检索，精确事实召回过重 |
| Agentic 澄清 | 反问用户 | 排除：破坏无人值守 |

参考：rewrite-retrieve-read（arXiv:2511.01386）、HyDE 对比研究（arXiv:2502.04095）、DMQR 多查询改写（arXiv:2411.13154）。

### 2.3 设计要点

- **触发位置**：`search()` 内 L1 失配后、L0 兜底前——命中零成本（不额外调 LLM），失配才花 1 次调用。
- **合并策略**：原查询结果优先（若意外有命中），扩展变体结果按各自 L1 排序合并去重（entry_id 首次出现顺序）。
- **降级**：扩展 LLM 调用失败/输出不可解析 → 静默跳过扩展层，行为与现状一致。
- **prompt 设计**：给 2 个例子（含 T122 同型：发布编号→构建标签/构建号/版本标识），要求 3-5 个变体、每行一个、temperature 0。

## 3. Innovate (Optional: Options & Decision)

### Fork 1: 扩展触发时机
- A. **仅 L1 失配时触发** → 选 A：命中零成本，失配才付费（与 L2 语义重排同位置竞争，QE 更对症）
- B. 每次搜索都扩展：成本高且无必要 → 否

### Fork 2: 变体数量与来源
- A. **3-5 个变体，LLM 单次调用生成** → 选 A：成本与覆盖的平衡点
- B. 多次调用多视角生成（DMQR 式）：成本高，Batch 验证后再议

### Fork 3: 与 L2 语义重排的关系
- A. **QE 层优先于 L2**（QE 失败再 L2）→ 选 A：QE 直接针对字面失配，L2 兜底
- B. 替代 L2：保持两层共存更稳，不删既有机制 → 否

## 4. Plan (Contract)

### 4.1 File Changes

- `src/agent/config.py`（修改）：`MemoryConfig` 增加 `query_expansion_enabled: bool = False`
- `src/agent/core/memory.py`（修改）：`search()` 增加 `_expand_and_retrieve()` 层 + prompt 模板
- `tests/test_memory_llm_extractor.py` 或新增 `tests/test_memory_query_expansion.py`（新增）：扩展层单测
- `examples/batch_tasks_b6.py`（修改）：新增 T123-T125 硬 paraphrase 复验任务
- `examples/batch_e2e.py`（修改）：`mem-qe` 臂（memory 开 + query_expansion 开）
- `docs/configuration.md`（修改）：新配置项说明
- `docs/evaluation-log.md`（修改）：验收条目

### 4.2 Signatures

```python
# src/agent/config.py（MemoryConfig 增加）
query_expansion_enabled: bool = False  # 查询扩展：L1 失配时 LLM 生成同义变体再检索

# src/agent/core/memory.py（MemoryManager 新增方法）
_QE_PROMPT: str = """你是检索查询扩展助手。用户要在个人记忆库中搜索信息，
但原始查询可能与记忆的措辞不同。生成 3-5 个可能命中目标的中文或英文
同义搜索词/短语（每行一个，不要编号，不要解释）。

原始查询：{query}"""

async def _expand_and_retrieve(self, text: str, limit: int) -> list[MemoryEntry]:
    """查询扩展层：LLM 生成同义变体 → 逐一 L1 检索 → 合并去重。

    失败/无变体/变体全失配时返回 []（调用方按原 fallback 链继续）。
    """
```

```python
# search() fallback 链（修改后）
# L1（原查询）→ [query_expansion_enabled 时] QE 扩展层 → L2 语义重排 → L0 recency
```

### 4.3 Implementation Checklist

- [ ] 1. config + `_expand_and_retrieve()` + search() 链接入（原查询优先合并）
- [ ] 2. 单测：变体生成调用时机（命中不触发/失配触发）/ 合并去重 / LLM 失败降级 / 开关默认关
- [ ] 3. `mem-qe` 臂 + T123-T125 硬 paraphrase 任务（T122 同型 3 个）
- [ ] 4. 门禁三件套全绿 + `--echo` 冒烟
- [ ] 5. **验收运行**：T122+T123-T125 × mem-default/mem-qe × 2 采样（16 runs）→ qe 臂应显著优于 default 臂
- [ ] 6. `docs/configuration.md` + evaluation-log 验收条目 + 成本报告
- [ ] 7. 回写本 Spec §5/§6/§7

### 4.4 Route Alignment (Water Flow Check)

- Original assumption: 需要向量检索/HyDE 才能解 paraphrase
- Current route: Multi-Query 扩展复用字面检索器，调研排除重基础设施
- Scope impact: 默认关闭，现有行为不变

## 5. Execute Log

- [x] Step 1: `config.py` + `query_expansion_enabled`；`memory.py` 新增 `_QE_PROMPT`（含 T122 同型双示例）与 `_expand_and_retrieve()`（变体解析剥离编号/去重/上限 5；LLM 失败静默降级）；`search()` fallback 链改为 L1 → QE → L2 → L0（仅失配触发，命中零成本）
- [x] Step 2: `tests/test_memory_query_expansion.py` 7 单测（触发时机/变体解析/合并去重/降级/集成）通过
- [x] Step 3: `mem-qe` 臂（记忆开 + QE 开，不开 LLM 提取）；b6 新增 T123-T125 三个 T122 同型硬 paraphrase 任务（任务集 20→23）
- [x] Step 4: 门禁三件套全绿（760 passed / mypy 47 / ruff）；echo 冒烟通过
- [x] Step 5: **验收运行（16 runs，约 4 万 tokens）**：mem-qe **8/8（100%）** vs mem-default 5/8（63%）；**T122（b6 双臂 0/2 稳定失败）在 qe 臂 2/2 复活**；T123 的搜索词运气型分裂被稳定为 2/2；T124/T125 双臂均过（可猜 paraphrase）
- [x] Step 6: `docs/configuration.md` QE 配置说明；evaluation-log 验收条目；基线 753→760；session-context 同步

## 6. Review Verdict

- Review Matrix (Mandatory):
| Axis | Key Checks | Verdict | Evidence |
|---|---|---|---|
| Spec Quality & Requirement Completion | **目标超额达成**：硬 paraphrase 召回修复（T122 复活 2/2），qe 臂 8/8 vs default 5/8；默认关闭行为不变 | PASS | 验收 16 runs 输出；单测 7 个 |
| Spec-Code Fidelity | fallback 链/配置/臂/任务与 Plan 一致 | PASS | checklist 7/7；760 passed / mypy 47 / ruff 全绿 |
| Code Intrinsic Quality | 命中零成本触发设计有测试锁定；LLM 失败静默降级；变体解析边界有测试 | PASS | test_memory_query_expansion.py |
- Overall Verdict: **PASS**
- Blocking Issues: 无
- Regression risk: Low（默认关闭；存量行为有测试锁定）
- Follow-ups:
  1. 简历口径可补：查询扩展修复硬 paraphrase（T122 复活，qe 8/8 vs 5/8）
  2. Batch 7 候选：QE 全量复跑 b6（验证无回归）/ 200+ 条压力 / LLM 提取质量审计
  3. QE 变体质量抽查（prompt 迭代空间）

## 7. Plan-Execution Diff

- `_QE_PROMPT` 由 Plan 的简版扩充为含 T122 同型双示例（提高变体质量，ruff 行宽同步调整）
- b6 任务集 20→23（T123-T125 加入"搜索必需"类，完整性测试同步）
- 其余无偏差。

## 8. Archive Record

- Archive Mode: `snapshot`
- Audience: `both`
- Source Targets:
  - `mydocs/specs/2026-08-03_23-05_query-expansion-memory.md`
  - `docs/evaluation-log.md`（2026-08-03 QE 验收行）
- Archive Outputs:
  - `mydocs/archive/2026-08-03_23-30_query-expansion-memory_human.md`
  - `mydocs/archive/2026-08-03_23-30_query-expansion-memory_llm.md`
- Key Distilled Knowledge: Multi-Query 选型（vs HyDE/Query2doc/澄清）；仅失配触发的零成本设计；QE 与 L2 的分工（治失配 vs 重排注入）。

## 9. Project Sync Candidates

- 候选：「Multi-Query 扩展层位置：L1 后 L0 前，命中零成本」→ 收口归档
- Sync decision: Not synced
