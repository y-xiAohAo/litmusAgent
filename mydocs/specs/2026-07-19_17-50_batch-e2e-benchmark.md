# SDD Spec: 批量 E2E 评测体系 Batch 1（Batch E2E Benchmark）

- **Spec 层级**: Feature Spec
- **创建时间**: 2026-07-19 17:50
- **当前 Phase**: EXECUTE（全批运行中）
- **Approval Status**: `APPROVED — 2026-07-19 用户批准 Plan（含三项待决项：先 20 再扩 50 / 断言+judge 混合 / 不设硬顶分批报告）`
- **关联**: seed `2026-07-19_batch-e2e-benchmark-seed.md`；数据红线继承自 `2026-07-19_01-50_project-star-finalization.md`

## 0. Open Questions

- [ ] Q1: Batch 2 扩展项（planner-off 臂、50 任务、重复采样）在本批报告评审后再立项，是否认可？

## 1. Requirements (Context)

- **Goal**: 建立可重复运行的批量评测体系，用 20 任务 × 2 机制臂的真实 LLM 运行产出统计强度足够的聚合指标（成功率/轮数/无效调用率/失败分类/token 成本），为简历数字升级提供证据。
- **In-Scope**:
  1. `OpenAIClient` 增加 token 用量累计（`usage_totals`）。
  2. 20 个批量任务（16 断言 + 4 LLM-judge），覆盖 算法5 / 文件处理5 / 数据分析3 / 多步链路3 / 开放报告4，难度 L1-L3。
  3. 批量 Runner：串行执行、2 机制臂（full / no-reflect）、沙箱内判分、失败分类、token 成本聚合。
  4. echo 冒烟 + 2 任务真实试点 + 全批 40 次运行。
  5. 聚合报告（公开 `docs/`）+ evaluation-log 条目 + 实际成本报告。
- **Out-of-Scope**:
  - 简历措辞修改（报告评审后单独打磨，走 R3 流程）。
  - planner-off 臂、50 任务扩容、重复采样（Batch 2 候选）。
  - 改编公开 benchmark。
  - 并发执行（串行为主，规避 Docker 与 API 限流风险）。

### 用户已决项（2026-07-19）

| 待决项 | 决定 |
|---|---|
| 任务集规模与来源 | 分批：先 20 再扩 50（自建） |
| 判分自动化 | 断言 + LLM-as-judge 混合 |
| Token 预算 | 不设硬顶，分批报告实际消耗 |

## 1.1 Context Sources

- Requirement Source: seed spec 动机（小样本数字守得住但不硬；JD 要求 benchmark 构建能力）
- Existing Infra: `examples/e2e_suite.py`（Scenario/evidence/report 模式）、TD-001 workspace 持久性、`docs/evaluation-log.md` 报告格式
- Code Refs: `src/agent/llm/client.py:126-201`（usage 解析点）、`src/agent/core/engine.py:315,387`（reflective_advisor 注入点）、`src/agent/core/reflective_advisor.py:171-189`（threshold 构造）

## 1.5 Codemap Used

- Codemap File: `mydocs/codemap/2026-07-17_20-38_hermes-agent-project.md`（复用）

## 1.6 Context Bundle Snapshot

- 未生成（Research 已在对话内完成直接证据采集）

## 1.7 Minimum Chaos Unit Assessment

- Final Goal: Batch 1 聚合报告 + 真实成本数据，供简历升级评审
- Current Task Unit: usage_totals 小改动 + 任务集 + Runner + 三阶段执行（冒烟/试点/全批）
- Why small enough: 唯一 src 改动是 3 行累加；其余均为 examples/tests 新增；执行分三阶段，每阶段有独立 GO/NO-GO 证据
- Verification Evidence: 门禁三件套全绿；echo 冒烟通过；试点 2 run 判分链路完整；全批报告生成且成本可报
- Failure / Rework Plan: 试点暴露判分链路问题 → 回 Plan 修正；全批中单 run 失败重试 1 次仍败 → 记为失败样本（不中止批次）
- User Decision: 待批准

## 2. Research Findings

- `OpenAIClient._do_chat_request`（client.py:161-167）解析响应时**丢弃 `usage` 字段**——token 成本目前无法统计，需加 3 行累加（additive，不改 `chat()` 契约，EchoClient 与全部既有调用方不受影响）。
- 反思机制**无配置开关**：engine 默认构造 `ReflectiveAdvisor`（engine.py:387），规则式不耗 token。no-reflect 臂可通过注入 `ReflectiveAdvisor(reflection_threshold=10**9, escalate_threshold=10**9)` 确定性关闭，**无需改 src**。
- 判分可复用 TD-001 成果：Agent run 结束后其 `_sandbox_backend` 仍存活，runner 可在同 workspace 内执行判分脚本（文件持久性已验证）。
- e2e_suite 的 evidence 机制（工具调用 + 输出包含）不足以做通过率统计——批量需要"任务级二元判分"（断言退出码 / judge 分数）。
- 成本估算：40 runs × 均 ~6 轮 × ~8k input tokens/轮 ≈ 2M tokens 量级（DeepSeek 单价下约数元）；试点后报告真实数字。
- 风险：单样本方差（batch 1 每 task-arm 1 次，记为局限）；judge 一致性（temperature 0 + rubric + 原文留痕）；长跑稳定性（每 run 独立 backend，失败重试 1 次）。

## 2.1 Next Actions

- 等待 `Plan Approved` 后按 §4.3 执行。

## 3. Innovate (Optional: Options & Decision)

### Fork 1: Runner 形态
- A. 扩展 `e2e_suite.py`：场景联调工具与批量评测耦合，文件膨胀 → 否
- B. **新建 `examples/batch_e2e.py` + 数据/运行分离（`batch_tasks.py`）** → 选 B：e2e_suite 保持场景抽查定位，批量体系独立演进

### Fork 2: Judge 模型
- A. **同模型（deepseek-chat）temperature 0** → 选 A：成本可控；局限（自评偏差）记入报告
- B. 更强模型做 judge：本批无可用第二 provider，Batch 2 再议

### Fork 3: 机制臂数量
- A. **Batch 1 两臂（full / no-reflect）40 runs** → 选 A：对照简历现有反思 A/B 声称
- B. 2×2 全因子 80 runs：留 Batch 2

## 4. Plan (Contract)

### 4.1 File Changes

- `src/agent/llm/client.py`（修改）：`OpenAIClient.__init__` 新增 `usage_totals`；`_do_chat_request` 累加 usage（3 行）
- `tests/test_llm_client.py`（修改）：新增 usage 累加单测（mock httpx 响应含 usage 字段）
- `examples/batch_tasks.py`（新增）：`BatchTask` dataclass + `BATCH_TASKS`（20 任务定义 + 判分脚本/rubric）
- `examples/batch_e2e.py`（新增）：批量 Runner（CLI：`--echo` / `--only` / `--arms` / `--limit`）
- `tests/test_batch_e2e.py`（新增）：Runner 结构测试（echo 冒烟、分类器单测、judge 解析单测、任务集完整性）
- `docs/batch-e2e-batch1-report.md`（新增，公开）：全批详细报告（执行后生成）
- `docs/evaluation-log.md`（修改）：Batch 1 聚合条目（执行后追加）

### 4.2 Signatures

```python
# src/agent/llm/client.py（新增片段，__init__ 内）
self.usage_totals: dict[str, int] = {
    "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
}
# _do_chat_request 内，data = resp.json() 之后：
usage = data.get("usage") or {}
for key in self.usage_totals:
    self.usage_totals[key] += int(usage.get(key, 0) or 0)
```

```python
# examples/batch_tasks.py
@dataclass
class BatchTask:
    """批量评测任务定义。"""
    id: str                     # T01..T20
    name: str
    category: str               # 算法 / 文件处理 / 数据分析 / 多步链路 / 开放报告
    difficulty: str             # L1 / L2 / L3
    prompt: str
    verify_script: str | None = None   # 断言类：沙箱内执行，退出码 0 = 通过
    judge_rubric: str | None = None    # 开放类：LLM-judge 评分标准（1-5，≥4 通过）
    max_turns: int = 12

BATCH_TASKS: list[BatchTask] = [...]  # 20 项，verify_script 与 judge_rubric 恰居其一
```

```python
# examples/batch_e2e.py
@dataclass
class BatchRunResult:
    """单次 task×arm 运行结果。"""
    task_id: str
    arm: str                    # full / no-reflect
    success: bool
    judge: str                  # assert / llm-judge / error
    turns: int
    tokens: int
    duration_s: float
    failure_class: str          # "" / 语法 / 逻辑 / 环境 / 工具偏好 / 超时
    detail: str

def classify_failure(evidence: str, timed_out: bool) -> str: ...
async def run_one(task: BatchTask, arm: str, client: OpenAIClient) -> BatchRunResult: ...
def render_report(results: list[BatchRunResult]) -> str: ...  # 聚合：分臂成功率/均轮/均token/失败分布
```

### 4.3 Implementation Checklist

- [ ] 1. `client.py` usage_totals + `test_llm_client.py` 单测 → `pytest tests/ -q` + mypy + ruff 全绿
- [ ] 2. `examples/batch_tasks.py`：20 任务落盘（每条断言脚本人工自审）
- [ ] 3. `examples/batch_e2e.py` + `tests/test_batch_e2e.py` → 门禁三件套全绿
- [ ] 4. `python examples/batch_e2e.py --echo` 冒烟（0 成本）：20 任务 × 2 臂结构走通
- [ ] 5. **试点**：`--only T01,T11 --arms full`（2 次真实运行）→ 验证 判分脚本入沙箱 / usage 捕获 / judge 链路；报告实际 token 数
- [ ] 6. **全批**：20 × 2 臂串行后台执行（预计 40-80 分钟），原始结果落 `mydocs/reports/batch1_raw.jsonl`，单 run 失败重试 1 次
- [ ] 7. 聚合报告 → `docs/batch-e2e-batch1-report.md` + `docs/evaluation-log.md` 条目 + 实际总成本向用户报告
- [ ] 8. 回写本 Spec §5/§6/§7；简历升级另起 R3 打磨（用户评审报告后）

### 4.4 Spec Review Notes

- 未执行 `review_spec`；如需预审请指示。

### 4.5 Route Alignment (Water Flow Check)

- Original assumption: 批量评测需要新建判分基础设施
- Current route: 复用 e2e_suite 模式 + TD-001 workspace 持久性 + advisor threshold 注入，src 仅 3 行 additive 改动
- Scope impact: None

## 5. Execute Log

- [x] Step 1: `client.py` 新增 `usage_totals`（EVAL-015，additive 3 行累加）+ `test_llm_client.py` 2 个单测 → 19 passed；mypy 46 文件零问题；ruff 全绿
- [x] Step 2: `examples/batch_tasks.py` 20 任务落盘；断言自审修正 2 处判分基准错误（T13 std 12.30→12.32 宽容差校验；T19 空列表实为返回 None 而非 ZeroDivisionError，rubric 已按事实改写）
- [x] Step 3: `examples/batch_e2e.py` + `tests/test_batch_e2e.py`（16 测试）→ 全量 696 passed, 1 skipped；门禁全绿。执行中修复 1 处：Windows GBK 控制台无法编码 ✅/❌ → 补 `_ensure_utf8_stdout()`（复用 e2e_suite 模式）
- [x] Step 4: `--echo` 冒烟通过：20 任务 × 2 臂 = 40 合成运行 + 报告渲染 + JSONL 落盘链路全部走通（0 成本）
- [x] Step 5: 真实试点 **GO**（任务选择由 T01,T11 调整为 T01,T17，以同时覆盖 assert 与 llm-judge 两条判分链）：
  - T01 assert：4 轮，4,859 tokens，14.1s，PASS
  - T17 llm-judge：6 轮，16,438 tokens，31.8s，PASS
  - 合计 21,297 tokens；全批 40 runs 估算 ≈ 35-50 万 tokens（DeepSeek 单价约 ¥1-2）
- [x] Step 6: 全批 20 × 2 臂串行完成（用时约 11 分钟）：full 20/20（均轮 4.1，118,384 tokens）、no-reflect 20/20（均轮 4.5，128,629 tokens）；零失败样本，无需重试
- [x] Step 7: 报告落盘 `docs/batch-e2e-batch1-report.md`（含"观察与局限"如实记录）；`docs/evaluation-log.md` 追加 Batch 1 条目 + 基线 679→696；`docs/session-context.md` 同步；总消耗 **247,013 tokens**
- [x] Step 8: 本 Spec §6/§7 回写

## 6. Review Verdict

- Review Matrix (Mandatory):
| Axis | Key Checks | Verdict | Evidence |
|---|---|---|---|
| Spec Quality & Requirement Completion | 批量体系建成 + 聚合指标 + 真实成本，目标达成 | PASS | `docs/batch-e2e-batch1-report.md`；247,013 tokens 实测 |
| Spec-Code Fidelity | 文件/签名/checklist 与 Plan §4 一致（1 处计划内调整 + 1 处增补字段，见 §7） | PASS | checklist 8/8；门禁三件套全绿（696 passed） |
| Code Intrinsic Quality | src 仅 3 行 additive；Runner 16 个离线测试；判分基准人工自审修正 2 处 | PASS | §5 Step 2/3；T13/T19 修正记录 |
- Overall Verdict: **PASS**
- Blocking Issues: 无
- Regression risk: Low（src 改动 additive；全量测试 678→696 全绿）
- Follow-ups:
  1. **Batch 2 立项候选**：提高任务难度（当前任务集对 deepseek-chat 偏易，双臂 100% 无判别力）、planner-off 臂、50 任务扩容、重复采样
  2. 简历数字升级（R3 打磨）：Batch 1 可用口径为"20 任务批量评测双臂 100% 通过、平均 4.1 轮、自动判分（断言+LLM-judge）、单次评测成本 247k tokens"；**判别性数字（机制对照差异）需等 Batch 2**
  3. 弱信号仅记录不声称：no-reflect 臂轮数 +0.4 / token +8.7%

## 7. Plan-Execution Diff

- 试点任务选择：T01,T11 → **T01,T17**（理由：同时覆盖 assert 与 llm-judge 两条判分链；Plan 原选择只覆盖 assert）
- `BatchTask` 增补 `artifact_path: str = ""` 字段（judge 任务需显式产物路径，Plan §4.2 签名未含；实现必需）
- 执行中修复 1 处：Windows GBK 控制台无法编码 ✅/❌ → Runner 补 `_ensure_utf8_stdout()`（复用 e2e_suite 既有模式）
- 其余无偏差。

## 8. Archive Record

- Archive Mode: `thematic`（b1-b4 合并主题归档）
- Archive Outputs:
  - `mydocs/archive/2026-07-20_22-04_batch-e2e-benchmark-series_human.md`
  - `mydocs/archive/2026-07-20_22-04_batch-e2e-benchmark-series_llm.md`
- Key Distilled Knowledge: 难度阶梯设计法（显式分步→陷阱→开放→L5）；判分规格自包含；工具路径断言。

## 9. Project Sync Candidates

- 稳定事实候选：「批量评测体系 = 项目可展示组件」→ 报告生成后同步 `README.md` / `docs/` 索引（执行时确认）
- Sync decision: Not synced
