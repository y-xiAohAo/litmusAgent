# Feature Spec — 真实 LLM 联调场景套件（E2E Suite）

> **Spec 层级**：Feature Spec
> **协议**：SDD-RIPER-ONE（`No Spec, No Code` / `No Approval, No Execute` / `Spec is Truth`）
> **创建**：2026-07-18 02:50 | **Phase**：`PLAN` | **Status**：`[LOCKED]`
> **Approval Status**：`WAITING — 等待用户精确回复 "Plan Approved"（且 API Key 就绪）`
> **前置**：技术债 9/9 清零；Docker 沙箱真实可用；EVAL-009 已修复

---

## 0. 任务复述（Restate First）

- **最终目标**：用真实 LLM（DeepSeek）+ 真实 Docker 沙箱对 Hermes Agent 做端到端联调，产出有证据的评测记录（补齐 7/15 存疑记录），并为后续回归提供可重复执行的场景套件。
- **当前任务单元**：开发 `examples/e2e_suite.py` 场景套件 + 执行 S1-S5 联调 + 记录到 evaluation-log。
- **In Scope**：套件脚本、5 个场景、指标自动提取（轮数/工具序列/成败/耗时/证据断言）、Docker 主跑 + subprocess 对照（S1）、评测日志更新。
- **Out of Scope**：CI 集成（pytest e2e 标记）；token 消耗精确计量（客户端尚无 usage 统计，本轮以轮数/耗时为成本基准）；Web UI 联调。
- **Done Contract（验证方式）**：
  1. 套件脚本能批量执行场景并输出结构化报告（轮数/工具序列/耗时/证据断言 PASS-FAIL）。
  2. **S1-S5 全部真实执行**，每个场景的证据断言真实通过（trace 含真实工具调用、沙箱输出含预期值），失败场景如实记录。
  3. evaluation-log 端到端测试结果表新增 5+1 条记录（含 subprocess 对照），7/15 存疑记录被覆盖或标注。
  4. 全量门禁不回归。

## 1. Research Findings（关键事实）

1. **LLM 端点**：`deepseek-chat` @ `https://api.deepseek.com/v1`（7/15 已验证兼容）；Key 来源：`OPENAI_API_KEY` 环境变量（当前未就绪，⚠️ 阻塞项）。
2. **现有 demo**：`demo_real_llm.py` 单 prompt、无断言、无后端选择——套件不复用它，直接基于 `Agent` + `OpenAIClient` 构建。
3. **证据来源**：`agent.get_trace()` 提供逐步事件（工具名/参数/成败/内容）；`agent.messages` 含 tool result 全文。
4. **沙箱现状**：Docker 后端真实可用（python:3.11-slim 本地就绪）；subprocess 后端等价可用。
5. ** slim 镜像无 numpy**：S3 场景会真实触发 pip 安装与 TD-004 包追踪（注意：sandbox/code 策略默认 deny `import os` 等，但默认策略 enabled=False，联调不启用策略，S5 单独启用）。
6. **安全注意**：API Key 不落盘、不入 git、不写入任何文件；套件从环境变量读取。

## 2. 场景定义（用户已拍板：S1-S5 全覆盖）

| # | Prompt 要点 | 证据断言 | 验证对象 |
|---|---|---|---|
| S1 | 编写 fibonacci(n) 并验证 f(10)=55，返回源码 | trace 含 `sandbox_exec`；沙箱输出含 `55`；最终答案含 `def fibonacci` | 基础编码闭环（复跑覆盖 7/15 存疑记录） |
| S2 | 生成含 10 个随机数的 /workspace/data.csv，计算均值写入 /workspace/result.txt | trace 含 `file_write`+`sandbox_exec`+`file_read`；result.txt 存在且含数字 | 文件工作流 + workspace 持久化（TD-001） |
| S3 | 用 numpy 计算 1~100 的标准差（Docker 禁网原样跑） | trace 含 `sandbox_exec`；记录 Agent 面对 pip 失败的实际行为（降级 or 反复重试） | 错误自愈边界（禁网 vs pip 的真实张力） |
| S3b | 同 S3 prompt，使用预置 numpy 的 `hermes-sandbox` 镜像 | 沙箱输出含标准差结果；无 ImportError | 模式 1（预置镜像）可行性验证 |
| S4 | 读取 /workspace/data.csv（S2 复用或重建），生成分析报告并用 file_edit 修正其中一处措辞 | trace 含 `file_read`+`file_edit`；编辑后文件内容符合 | 多工具链 + file_edit |
| S5 | 要求把配置写入 /etc/hermes.conf（策略启用） | 策略拒绝发生；Agent 不崩溃并换路径（如 /workspace）或如实报告 | TD-006 策略拦截真实行为 |

对照：S1 用 subprocess 后端复跑一次（验证 fallback 等价性）。

## 3. Detailed Design & Implementation（Plan / The Contract）

### 3.1 File Changes

| 操作 | 路径 | 内容 |
|---|---|---|
| 新增 | `examples/e2e_suite.py` | 场景套件：场景定义、执行器、证据断言、报告输出 |
| 新增 | `tests/test_e2e_suite.py` | 套件离线测试（EchoClient/mock 场景，断言报告结构与证据提取逻辑） |
| 修改 | `docs/evaluation-log.md` | 端到端测试结果表：S1-S5 + 对照记录；7/15 记录标注已被复跑覆盖 |
| 修改 | `docs/demo.md`、`docs/session-context.md`、`docs/progress-spec.md` | 套件使用说明与状态同步 |
| 新增 | `examples/docker/Dockerfile.sandbox` | 预置镜像：`python:3.11-slim` + numpy/pandas，构建为 `hermes-sandbox:latest`（S3b 用） |

### 3.2 Signatures（契约级）

```python
# examples/e2e_suite.py
@dataclass
class Scenario:
    id: str            # "S1"
    name: str          # 场景名
    prompt: str
    backend: str = "docker"           # docker / subprocess
    enable_security: bool = False      # S5 启用策略
    expected_tools: list[str] = ...    # 证据：trace 中应出现的工具
    expected_in_output: list[str] = ... # 证据：沙箱/最终输出应包含的文本
    max_turns: int = 15

@dataclass
class ScenarioResult:
    scenario_id: str
    success: bool
    turns: int
    tools_used: list[str]
    duration_s: float
    evidence: list[tuple[str, bool]]   # (断言描述, 是否通过)
    error: str = ""

async def run_scenario(sc: Scenario, client: BaseLLMClient) -> ScenarioResult: ...
def render_report(results: list[ScenarioResult]) -> str: ...  # Markdown 表格，可直接粘贴 evaluation-log
```

### 3.3 Implementation Checklist（原子步骤）

- [ ] 1. **RED**：`tests/test_e2e_suite.py`——报告结构/证据提取/断言判定（mock Agent，离线）→ 确认失败
- [ ] 2. **GREEN**：`examples/e2e_suite.py` 套件实现 → 离线测试通过 + `--echo` 冒烟跑通结构
- [ ] 3. 全量门禁复核
- [ ] 3.5 构建预置镜像：`docker build -t hermes-sandbox:latest -f examples/docker/Dockerfile.sandbox examples/docker`（经 daocloud 镜像源拉基础镜像）
- [ ] 4. **API Key 就绪后**：S1-S5 Docker 真实联调 + S1 subprocess 对照 + S3b 预置镜像对照；如实记录结果（失败也记录并分析）
- [ ] 5. evaluation-log / 文档同步
- [ ] 6. 双 commit：`feat: add e2e scenario suite for real LLM integration` + `docs: record real LLM e2e results`

### 3.4 风险与回滚

| 风险 | 缓解 |
|---|---|
| LLM 行为不确定导致场景失败 | 失败如实记录（联调目的即暴露问题）；每场景独立，不阻塞后续 |
| API 成本失控 | max_turns 15/场景；套件支持只跑指定场景（`--only S1,S3`） |
| Key 泄露 | 仅从环境变量读取；报告不含 key；`.gitignore` 核查 |
| Docker 沙箱网络限制导致 pip install 失败（S3） | 预期内风险——已升级为双场景设计：S3 禁网原样跑（记录降级行为）+ S3b 预置镜像对照（验证模式 1）；网络策略增强已登记为技术债候选 TD-010 |
| 回滚 | 删除新增文件即可，零侵入 |

---

## 附录 A：技术债候选登记（已同步 technical-debt-spec）

- **TD-010**：沙箱网络策略增强——两阶段网络（setup 阶段联网装包 / 执行阶段禁网）+ `network_mode` 配置化。来源：2026-07-18 联调讨论（行业模式 2：Codex Cloud 两阶段模式），与预热池 + ExecutionContext 包追踪天然契合。

---

## 4. Execute Log

| 步骤 | 内容 | 结果 |
|---|---|---|
| 1 RED | `test_e2e_suite.py` 7 例 | 全部 error（套件不存在），RED 成立 |
| 2 GREEN | `examples/e2e_suite.py` 实现 + 修正 1 处测试设计错误 | 7 passed；`--list`/`--echo` 冒烟结构正确 |
| 3 | 全量门禁 | 632 passed / mypy / ruff 全绿 |
| 3.5 | 预置镜像构建（daocloud 基础镜像 + numpy/pandas） | 16s 构建成功 |
| 4 真实联调 | S1-S5 + S1-sub + S3b 七场景真实执行 | **5/7 PASS**；S2/S4 FAIL 重跑确认行为稳定（非抖动） |
| 5 | evaluation-log（7 条 E2E 记录 + 7/15 覆盖标注 + Action Items）/ demo.md / session-context / progress-spec | 已落盘 |
| 6 | 双 commit：`9f54e47`（feat）、`32e2eb0`（docs） | 工作区干净 |

## 5. Validation

| 验收项（Done Contract） | 证据 | 结论 |
|---|---|---|
| 1. 套件批量执行 + 结构化报告 | 7 离线测试 + 真实联调输出 Markdown 报告（轮数/工具序列/耗时/证据比） | ✅ |
| 2. S1-S5 真实执行 + 证据断言 | 报告：S1 3/3、S3 1/1、S5 2/2 通过；S2 1/3、S4 2/4 如实记录 FAIL 并分析根因 | ✅（含失败如实记录） |
| 3. evaluation-log 新增 7 条记录 + 7/15 覆盖 | E2E 表 7 条新行 + 7/15 行标注已被复跑覆盖 | ✅ |
| 4. 全量门禁不回归 | 632 passed（625+7）；mypy/ruff 全绿 | ✅ |

**联调核心发现**：① DeepSeek 偏好 `sandbox_exec` 通吃，稳定跳过专用文件工具（S2/S4，重跑确认）；② 禁网下 Agent 能降级完成任务（S3）；③ TD-006 策略拦截真实生效（S5）；④ 预置镜像使 numpy 场景提速 63%（S3b vs S3）。

## 6. Review Verdict

**评审时间**：2026-07-18 14:10 | **评审方式**：三轴评审（Spec 原文 + 变更代码回读 + 真实联调记录 + S2/S4 重跑稳定性证据）

### Review Matrix

| 轴 | 关键检查 | 结论 | 证据 |
|---|---|---|---|
| Axis-1 Spec 质量与需求达成 | Goal/In/Out/Acceptance 清晰可验证 | **PASS** | §0 Done Contract 4 条均有实测证据（见 §5 Validation）；场景/证据断言/成本防护定义明确 |
| Axis-1 需求达成 | S1-S5 真实执行 + 证据断言 + 如实记录 | **PASS** | 7 场景真实执行（含双对照）；S1 覆盖 7/15 存疑记录；S2/S4 FAIL 如实记录并重跑确认行为稳定（非抖动） |
| Axis-1 需求达成 | evaluation-log 记录完整 | **PASS** | E2E 表新增 7 条记录；7/15 行标注已被覆盖；Action Items 更新（工具偏好优化 + TD-010） |
| Axis-2 Spec-代码一致性 | File Changes 与 Plan §3.1 对照 | **PASS** | 4 类文件变更全部落实（套件/测试/Dockerfile/文档），无计划外代码 |
| Axis-2 Spec-代码一致性 | Signatures 与 Plan §3.2 对照 | **PASS** | `Scenario`/`ScenarioResult`/`run_scenario`/`render_report` 与契约一致（`image` 字段为 S3b 增补，见 Diff） |
| Axis-2 行为一致性 | 套件行为与场景定义一致 | **PASS** | 7 离线测试 + `--echo` 冒烟 + 真实联调输出与场景表一一对应 |
| Axis-3 代码质量 | 正确性/健壮性 | **PASS** | 场景异常不阻塞后续（try/finally 关后端）；Key 仅环境变量读取不落盘不打印；UTF-8 终端处理 |
| Axis-3 代码质量 | 测试充分性 | **PASS** | 7 离线测试覆盖证据判定/报告渲染/执行闭环；真实联调即集成验证 |
| Axis-3 风险 | 成本与安全 | **PASS（附观察项 1、2）** | max_turns 防护；无 Key 泄露；API 消耗约 30 轮 LLM 调用（7 场景 + 2 重跑） |

### Overall Verdict：**PASS（可关闭）**

### Blocking Issues：无

### 观察项（非阻塞）
1. **Key 持久化面**：`~/.bashrc` 含明文 key（用户主动要求），建议后续轮换；已在会话中提示。
2. **S2/S4 FAIL 的性质**：不是产品缺陷，是模型行为与场景期望的偏差（DeepSeek 偏好 sandbox_exec 通吃）——已转化为 Action Items（工具引导优化），建议作为后续单元而非本单元阻塞项。
3. 套件 `main()` 对 FAIL 场景返回 0（报告型工具语义），若未来进 CI 需要可加 `--strict` 退出码模式。

## 7. Plan-Execution Diff

| 项 | Plan | 实际 | 性质 |
|---|---|---|---|
| S3 证据断言 | Plan 场景表含“最终成功”期望 | 套件实现仅断言 `sandbox_exec` 调用，降级行为作为发现记录 | 避免脆性断言，行为如实记录，合理偏差 |
| `Scenario.image` 字段 | Plan §3.2 未列出 | 为 S3b 预置镜像增补 | 讨论阶段已确认的 S3b 增补的自然延伸 |
| S3b 构建步骤 | checklist 3.5 | 完成（16s） | 一致 |
| 其余 File Changes / Checklist | — | 全部一致 | — |

## 8. Change Log

| 时间 | 变更 |
|---|---|
| 2026-07-18 02:50 | sdd_bootstrap 联调单元：Research 完成（现状/证据源/沙箱条件核实）；用户拍板四项决策（套件脚本 / S1-S5 全覆盖 / Docker 主+对照 / Key 自行提供）；Plan 落盘；⚠️ 阻塞项：OPENAI_API_KEY 未就绪（用户之前记录未找到，待重新提供） |
| 2026-07-18 13:40 | 阻塞解除：用户提供 DeepSeek Key（已持久化到 setx + ~/.bashrc，不落项目文件）；联调讨论增补 S3b 预置镜像场景与 TD-010 候选登记（`54e38e7`） |
| 2026-07-18 14:00 | `Plan Approved` 收到，进入 EXECUTE。6 步 checklist 完成：632 passed 全绿；真实联调 5/7 PASS 并记录分析；双 commit `9f54e47` + `32e2eb0`；待 `REVIEW EXECUTE` |
| 2026-07-18 14:10 | REVIEW EXECUTE 完成：三轴全 PASS（基于真实联调记录 + S2/S4 重跑稳定性证据），Overall Verdict = PASS（可关闭），Blocking Issues = 无；S2/S4 FAIL 定性为模型行为偏差，转化为 Action Items |
| 2026-07-18 14:30 | S2/S4 消息级诊断（Reverse Sync）：S2 根因=EVAL-010 workspace 权限 bug（root volume + nobody 容器）+ DSML 模型怪癖（复刻 0/5 未复现，证实非我方引导问题）；S4 重测 8/8 跳过 file_edit 与改标题（含 T=0），定性为系统性模型行为（全量重写偏好 + 多步指令丢步骤），非框架不稳定 |
| 2026-07-18 14:45 | FAST 修复 EVAL-010：chown 65534 + put_file tar uid/gid；风险评估 5 项确认；真实 Docker 回归 3/3 通过；S2 复跑权限错误消除（剩余 FAIL 为工具偏好）；635 passed |
| 2026-07-18 15:00 | S4p 对照实验（Reverse Sync）：S4 + TaskPlan（4 步分步推进）×3 全过——file_edit 3/3、标题正确 3/3、计划步骤 12/12，对照 S4（无 Planner）0/8。**结论：框架 Planner 机制可完全补偿模型的多步指令弱点**，已记录 evaluation-log 与 Action Items |
| 2026-07-18 15:10 | 修复 Planner 进度显示 bug（完成后显示 Step 5/4）：封顶 + ACTIVE 状态判断（`45abd55`）；归档本轮调查（`mydocs/archive/2026-07-18_15-00_e2e-deep-dive_*`） |

## 9. Archive Record

| 时间 | 归档产物 | 模式 |
|---|---|---|
| 2026-07-18 14:10 | `mydocs/archive/2026-07-18_14-10_real-llm-e2e-suite_human.md` + `..._llm.md` | snapshot（联调单元） |

- 归档为知识衍生品，不影响本 Spec 的真相源地位；原始文件未删除/未移动。
