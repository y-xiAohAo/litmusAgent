# SDD Spec: 测试环境隔离与依赖清单漂移修复（TD-011 / TD-012）

- **Spec 层级**: Feature Spec
- **创建时间**: 2026-07-19 16:59
- **当前 Phase**: Plan 完成，等待 `Plan Approved`
- **Approval Status**: 未批准

## 0. Open Questions

- [x] Q1: TD-012 并入本 Spec 一并修复？→ **已决（2026-07-19 用户）：同意并入**。
- [x] Q3: TD-011 是否真实技术债？→ **已决（2026-07-19 用户质疑后澄清）**：债 = 默认门禁套件环境不确定性 + 隐性真实调用；真实 LLM 测试能力本身不是债，走既有显式通道（见 §2.1）。
- [ ] Q2: 技术债总表位于 `.kimi/vibe_specs/`（AGENTS.md 标注"旧体系，只读参考"，但落点表仍将"技术债总表"指向该文件）——本次按落点表继续更新总表，执行时请确认。

## 1. Requirements (Context)

- **Goal**: 消除默认测试套件对宿主机 `OPENAI_*` 环境变量的隐式依赖，恢复 `pytest tests/` 作为提交门禁的确定性；修复 requirements.txt 依赖漂移。
- **In-Scope**:
  1. 新增 `tests/conftest.py`，autouse 清理 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`。
  2. 验证既有显式 `setenv`/`delenv` 测试与 conftest 兼容。
  3. `requirements.txt` 补齐 `fastapi` / `uvicorn[standard]` / `jinja2`。
  4. 双环境全量验证 + mypy + ruff。
  5. 登记 TD-011 / TD-012 至技术债总表并按维护规则同步文档。
- **Out-of-Scope**:
  - 不修改 EVAL-012 环境变量覆盖机制本身（已确认为故意特性）。
  - **不触碰真实 LLM 测试通道**：`examples/e2e_suite.py`（独立脚本，不经 conftest）行为完全不变，照旧从环境变量读 key 做真实联调。
  - 不新增"pytest 内显式 opt-in 真实 LLM"的 marker 机制（如未来需要，单独立项）。
  - 不重构 web app 的 `_create_agent()` 回退逻辑（EchoClient 回退已存在且正确）。
  - 不处理 Windows ProactorEventLoop 的 httpx 关闭告警（隐性真实调用消失后该症状自然消失）。
  - 不改动其他 46 个测试文件。

## 1.1 Context Sources

- Requirement Source: 本会话全量测试暴露的 3 个失败（`test_cli.py` × 2、`test_web_ui.py` × 1）
- Design Refs: `docs/evaluation-log.md`（EVAL-011/012/013 记录）、`.kimi/vibe_specs/technical-debt-spec.md`（TD-001~010）、`examples/e2e_suite.py`（真实 LLM 联调显式通道）
- Code Refs: `src/agent/cli/agent_cli.py:136-179`（`_load_config` env 覆盖）、`src/agent/web/app.py:62-80`（`_create_agent` key 检测回退）、`tests/test_cli.py:58-79`（既有 delenv 模式）、`tests/test_web_ui.py:89-112`（显式 setenv 用例）

## 1.5 Codemap Used (Feature/Project Index)

- Codemap Mode: `project`（复用既有，未重新生成）
- Codemap File: `mydocs/codemap/2026-07-17_20-38_hermes-agent-project.md`
- Key Index: CLI 入口 `src/agent/cli/agent_cli.py`；Web 入口 `src/agent/web/app.py`；LLM 客户端 `src/agent/llm/client.py`

## 1.6 Context Bundle Snapshot

- Bundle Level: 未生成（问题域已完全定位，按需产物省略）

## 1.7 Minimum Chaos Unit Assessment

- Final Goal: 默认测试套件环境确定性（污染/干净环境均全绿），真实 LLM 通道不受影响
- Current Task Unit: 一个 conftest.py + requirements.txt 补三行 + 验证登记
- Why this unit is small enough: 改动集中在 2 个文件，不触碰 src/ 业务代码，验证方式明确
- Verification Evidence: 污染环境（当前机器）与干净环境（`env -u`）两轮 `pytest tests/ -q` 均 678 全绿；mypy/ruff 全绿
- Failure / Rework Plan: 若 conftest 导致既有测试回归，回退到逐测试 delenv 方案（Option B）
- User Decision: 待批准

## 2. Research Findings

### 2.1 问题分类：既有记录 vs 新技术债

**A. 既有 spec/日志已记录，非新债：**

| 现象 | 已有记录 | 结论 |
|---|---|---|
| `OPENAI_*` 环境变量覆盖默认配置导致测试断言 `gpt-4o` 失败 | EVAL-012（`docs/evaluation-log.md:98`）：CLI 旗标 > 环境变量 > 配置文件 > 默认值，是**故意特性** | 特性本身无债；债在测试未隔离 |
| "Event loop is closed" 症状 | EVAL-013（`evaluation-log.md:99`）：CLI chat 侧已修复（复用单事件循环） | 同源症状出现在 web 测试侧，属新表现 |
| 测试内 `monkeypatch.delenv` 隔离模式 | `tests/test_cli.py:58-79` 已有两个测试类使用 | 项目已有实践，但覆盖不全 |
| 真实 LLM 测试需求 | `examples/e2e_suite.py`：显式手动运行的真实联调套件，输出 evaluation-log 格式报告；evaluation-log 中 S11/S12/Web UI 真实联调均由此产出 | **正当需求且已有专门通道，非债** |

**B. 新发现技术债（总表 TD-001~010 无记录）：**

| 编号 | 名称 | 严重程度 | 证据 |
|---|---|---|---|
| **TD-011** | 默认门禁套件环境不确定性：`test_cli_config_default_plain/rich` 未应用既有 delenv 模式；`test_web_ui.py` chat 测试依赖"环境里恰好没有 key"的隐式假设 | 🟠 中 | 污染环境 3 失败；干净环境 678 全绿；同一 commit CI 绿/本地红 |
| **TD-011 加重情节** | 有真实 key 时 web 接口层测试**意外发起真实 DeepSeek 调用**——烧配额且在 Windows 下崩溃，产不出 evaluation-log 级有效证据（该层 docstring 自述"不依赖真实 LLM"） | 🔴 高（隐性成本） | `test_web_ui.py` docstring；`web/app.py:62-80` 有 key 即建真实 client |
| **TD-012** | `requirements.txt` 与 `pyproject.toml` 依赖漂移：缺 `fastapi>=0.110.0`、`uvicorn[standard]>=0.27.0`、`jinja2>=3.1.0`（web UI 运行依赖） | 🟡 低 | 两文件逐行比对；按 requirements.txt 安装将得到残缺环境 |

**TD-011 界定说明（用户质疑后澄清）**：债 = 默认套件不确定性 + 隐性真实调用；真实 LLM 测试能力本身不是债，由 `examples/e2e_suite.py` 显式通道承载，本修复不改变该通道任何行为。

### 2.2 风险与不确定项

- conftest autouse 清理可能影响"恰好依赖污染环境"的其他测试（当前仅 3 个失败，概率低，双环境验证兜底）。
- `tests/test_web_ui.py:89-112` 的显式 `setenv` 用例在 conftest 清理后再自行 setenv，顺序兼容（autouse fixture 先于测试体执行），但需逐个人工确认其不发起真实请求。

## 2.1 Next Actions

- 进入 Plan（本文件 §4），等待 `Plan Approved`。

## 3. Innovate (Optional: Options & Decision)

### Option A: 全局 conftest autouse 清理（推荐）

- 做法：新增 `tests/conftest.py`，function 级 autouse fixture 用 monkeypatch 删除三个 `OPENAI_*` 变量。
- Pros: 一处修复全覆盖，未来新增测试自动免疫；与既有显式 `setenv`/`delenv` 用例天然兼容（先清后设/再删无害）；web 测试自动走设计好的 EchoClient 回退路径，TD-011 加重情节（隐性真实调用）根除；不影响 e2e_suite 真实联调通道（独立脚本，不经 conftest）。
- Cons: 全局行为变更，理论上有影响"依赖污染环境"测试的风险（用双环境验证对冲）。

### Option B: 逐测试补 delenv（复用文件内既有模式）

- 做法：只给 `test_cli_config_default_*` 和 web chat 测试分别加 monkeypatch 清理。
- Pros: 改动局部，无全局影响；与文件内现有写法一致。
- Cons: 治标——下一个新测试仍会踩同样的坑；web 测试的真实调用风险依赖每个作者自觉。

### Decision

- Selected: **Option A**（TD-011）+ requirements.txt 补三行（TD-012）
- Why: 系统性消除整类问题而非个案；conftest 是 pytest 标准机制；Option B 作为回退方案已记录。

## 4. Plan (Contract)

### 4.1 File Changes

- `tests/conftest.py`（**新增**）：autouse 环境清理 fixture
- `requirements.txt`（修改）：补 `fastapi>=0.110.0`、`uvicorn[standard]>=0.27.0`、`jinja2>=3.1.0`
- `.kimi/vibe_specs/technical-debt-spec.md`（修改）：登记 TD-011（✅ 已完成）/ TD-012（✅ 已完成）行
- `docs/progress-spec.md` / `docs/session-context.md` / `docs/evaluation-log.md`（按总表维护规则同步，执行时确认必要性）

### 4.2 Signatures

```python
# tests/conftest.py
"""pytest 全局夹具：保证测试套件对宿主机 OPENAI_* 环境变量免疫。"""

from __future__ import annotations

import pytest

_OPENAI_ENV_VARS: tuple[str, ...] = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL")


@pytest.fixture(autouse=True)
def _clean_openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清理宿主机 OPENAI_* 环境变量，使测试默认走 EchoClient / 默认配置路径。

    需要真实环境变量的用例可在测试体内自行 monkeypatch.setenv（先清后设，顺序兼容）。
    真实 LLM 联调请使用独立通道 examples/e2e_suite.py（不经本夹具）。
    """
    for var in _OPENAI_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
```

### 4.3 Implementation Checklist

- [ ] 1. 通读 `tests/test_web_ui.py` 全部显式 setenv 用例（L80-120），确认与 conftest 兼容且不依赖真实请求
- [ ] 2. 新增 `tests/conftest.py`（按 §4.2）
- [ ] 3. **污染环境**（当前机器，OPENAI_* 已设）跑 `pytest tests/ -q`，目标 678 全绿
- [ ] 4. **干净环境**（`env -u OPENAI_MODEL -u OPENAI_BASE_URL -u OPENAI_API_KEY`）跑 `pytest tests/ -q`，目标全绿
- [ ] 5. `requirements.txt` 补三个依赖（位置：Core 段 docker 之后）
- [ ] 6. `mypy src/` + `ruff check src/ tests/` 全绿
- [ ] 7. 登记 TD-011 / TD-012 至技术债总表，按维护规则同步文档
- [ ] 8. 更新本 Spec §5 Execute Log 与 §6 Review Verdict

### 4.4 Spec Review Notes (Optional Advisory, Pre-Execute)

- 未执行 `review_spec`（改动面小，双环境验证即充分证据）；如需预审请指示。

### 4.5 Route Alignment (Water Flow Check)

- Original assumption: 3 个测试失败是代码 bug
- Current implementation route: 失败为环境污染所致，修复落在测试基础设施而非业务代码
- Why it fits code terrain: 项目已有 delenv 实践与 EchoClient 回退设计，conftest 只是把已有实践全局化
- Scope impact: None

## 5. Execute Log

- [x] Step 1: 通读 `tests/test_web_ui.py` 显式 setenv 用例（L85-121 `TestAgentCreationEnvPriority`）——仅构造 client 断言属性，不发真实请求，与 conftest 顺序兼容（先清后设）
- [x] Step 2: 新增 `tests/conftest.py`（autouse 清理 `OPENAI_API_KEY`/`OPENAI_BASE_URL`/`OPENAI_MODEL`）
- [x] Step 3: 污染环境 `pytest tests/ -q` → **678 passed, 1 skipped**（26.70s），修复前为 675 passed + 3 failed
- [x] Step 4: 干净环境 `pytest tests/ -q` → **678 passed, 1 skipped**（26.51s）
- [x] Step 5: `requirements.txt` Core 段补 `fastapi>=0.110.0` / `uvicorn[standard]>=0.27.0` / `jinja2>=3.1.0`
- [x] Step 6: `mypy src/` 46 files 零问题；`ruff check src/ tests/` 全绿
- [x] Step 7: 总表登记 TD-011/TD-012（含详细条目与修复记录），"最后更新"改为 2026-07-19；`docs/session-context.md` 测试基线 541→678、当前任务/规格同步
- [x] Step 8: 回写本 Spec §5/§6/§7

## 6. Review Verdict

- Review Matrix (Mandatory):
| Axis | Key Checks | Verdict | Evidence |
|---|---|---|---|
| Spec Quality & Requirement Completion | 双环境全绿 + 真实联调通道不受影响 | PASS | §5 Step 3/4 日志；e2e_suite.py 未改动 |
| Spec-Code Fidelity | 文件/签名/checklist 与 Plan §4 一致 | PASS | `tests/conftest.py` 与 §4.2 逐字一致；checklist 8/8 完成 |
| Code Intrinsic Quality | 无业务代码改动；conftest 符合项目既有 delenv 实践 | PASS | ruff/mypy 全绿；既有 setenv 用例（L85-121）全部通过 |
- Overall Verdict: **PASS**
- Blocking Issues: 无
- Regression risk: Low（仅测试基础设施与依赖清单，未触碰 src/）
- Follow-ups: TD-010 仍为候选；"pytest 内显式 opt-in 真实 LLM" marker 机制如需要请单独立项

## 7. Plan-Execution Diff

- 无偏差。checklist 8 步全部按 Plan 执行；docs 同步范围按总表维护规则最小化（仅 session-context.md 当前态；progress-spec.md/evaluation-log.md 历史记录不改写）。

## 8. Archive Record

- Archive Mode: `snapshot`
- Audience: `both`
- Source Targets:
  - `mydocs/specs/2026-07-19_16-59_test-env-isolation.md`
  - `.kimi/vibe_specs/technical-debt-spec.md`（TD-011/TD-012 条目）
- Archive Outputs:
  - `mydocs/archive/2026-07-19_17-40_test-env-isolation_human.md`
  - `mydocs/archive/2026-07-19_17-40_test-env-isolation_llm.md`
- Key Distilled Knowledge: 测试必须环境确定；真实 LLM 联调只走 e2e_suite；EVAL-012 是特性；依赖双文件需同步维护。

## 9. Project Sync Candidates

- 已同步（本次任务内）：
  - 技术债总表：TD-011/TD-012 登记 ✅
  - `docs/session-context.md`：测试基线与当前任务 ✅
- 稳定事实候选（未同步，留待用户确认）：「本机用户级 `OPENAI_*` 指向 DeepSeek；真实 LLM 联调走 `examples/e2e_suite.py`」→ 建议落点 `docs/session-context.md`
- Sync decision: 部分 Synced（上述两项）；候选事实 Not synced
