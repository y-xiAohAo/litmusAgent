# 归档：测试环境隔离与依赖清单漂移修复（TD-011 / TD-012）— Human 视角

- **日期**：2026-07-19
- **Feature Spec**：`mydocs/specs/2026-07-19_16-59_test-env-isolation.md`
- **流程**：SDD-RIPER-ONE（Research → Innovate → Plan → `Plan Approved` → Execute → Review PASS）

## 目标与范围

消除默认测试套件对宿主机 `OPENAI_*` 环境变量的隐式依赖，恢复 `pytest tests/` 作为提交门禁的确定性；顺带修复 `requirements.txt` 与 `pyproject.toml` 的依赖漂移。

## 问题溯源

本机全量测试暴露 3 个失败（675 passed + 3 failed），初判疑似代码 bug，Research 后定性为环境污染：

1. 本机用户级 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` 指向 DeepSeek，经 EVAL-012 环境变量覆盖机制（故意特性）改变默认配置。
2. `test_cli_config_default_*` 未应用项目已有的 `monkeypatch.delenv` 隔离模式。
3. `test_web_ui.py` chat 测试在有真实 key 时**意外发起真实 API 调用**——烧配额且在 Windows 下崩溃，产不出有效证据。
4. `requirements.txt` 缺 web UI 三个运行依赖（fastapi / uvicorn / jinja2）。

## 关键决策

- **TD-011 界定（用户质疑后澄清）**：债 = 默认套件不确定性 + 隐性真实调用；真实 LLM 测试能力本身不是债，由显式通道 `examples/e2e_suite.py` 承载，修复不改变该通道任何行为。
- **方案选择**：全局 `tests/conftest.py` autouse 清理（Option A）优于逐测试补 delenv（Option B）——系统性免疫，未来新增测试不会踩坑。
- **TD-012 并入**（用户批准）：同属环境卫生主题，改动极小。

## 结果与证据

| 验证 | 结果 |
|---|---|
| 污染环境全量测试 | 678 passed, 1 skipped（修复前 675 + 3 failed） |
| 干净环境全量测试 | 678 passed, 1 skipped |
| mypy strict / ruff | 全绿 |
| Review 三轴评审 | PASS，回归风险 Low |

## 改动文件

- `tests/conftest.py`（新增）
- `requirements.txt`（+3 行）
- `.kimi/vibe_specs/technical-debt-spec.md`（TD-011/TD-012 登记）
- `docs/session-context.md`（基线 541→678）

## 遗留

- TD-010（沙箱网络策略增强）仍为总表唯一候选。
- "pytest 内显式 opt-in 真实 LLM" marker 机制：如需要请单独立项。

## Trace to Sources

- 失败现象与根因 → 本会话 pytest 输出；`src/agent/cli/agent_cli.py:157`；`src/agent/web/app.py:62-80`
- EVAL-012/013 特性记录 → `docs/evaluation-log.md:98-99`
- 决策过程与 checklist → `mydocs/specs/2026-07-19_16-59_test-env-isolation.md` §3/§4/§5
- 技术债登记 → `.kimi/vibe_specs/technical-debt-spec.md` TD-011/TD-012 条目
