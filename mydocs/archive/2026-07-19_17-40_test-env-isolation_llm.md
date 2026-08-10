# 归档：测试环境隔离与依赖清单漂移修复（TD-011 / TD-012）— LLM 视角

> 用途：后续会话/任务快速接管相关上下文。只记约束、契约、触点与坑。

## 核心约束（未来任务必须遵守）

1. **`pytest tests/` 必须环境确定**：任何新测试不得依赖宿主机 `OPENAI_*` 环境变量的有无。需要环境变量时用 `monkeypatch.setenv` 显式设置（conftest 先清后设，顺序兼容）。
2. **真实 LLM 联调只走 `examples/e2e_suite.py`**（独立脚本，不经 conftest，从环境变量读 key）。不要在 `tests/` 下发起真实 API 调用。
3. **EVAL-012 优先级是特性不是 bug**：CLI 旗标 > 环境变量 > 配置文件 > 默认值（`src/agent/cli/agent_cli.py:136-179`）。测试"默认值"前必须确保 env 已清理（conftest 已做）。
4. **依赖双文件维护**：改 `pyproject.toml` 依赖必须同步 `requirements.txt`（Core 段）。

## 代码触点

| 触点 | 位置 | 说明 |
|---|---|---|
| 全局环境清理夹具 | `tests/conftest.py` | autouse + monkeypatch.delenv 三个 `OPENAI_*` 变量 |
| env 覆盖逻辑 | `src/agent/cli/agent_cli.py:157-162` | EVAL-012 实现处 |
| Web Agent 创建 | `src/agent/web/app.py:62-80` | 有 key→OpenAIClient.from_env()，无 key→EchoClient |
| 既有隔离范例 | `tests/test_cli.py:58-79`、`tests/test_web_ui.py:85-121` | delenv/setenv 标准写法 |

## 已验证事实

- 双环境（有/无 `OPENAI_*`）全量测试均 678 passed, 1 skipped；mypy strict + ruff 全绿。
- `tests/test_web_ui.py` L85-121 的 `TestAgentCreationEnvPriority` 仅构造 client 断言属性，不发真实请求，与 conftest 兼容。
- Windows ProactorEventLoop 下真实 httpx 调用在 TestClient 关闭阶段会抛 "Event loop is closed"（EVAL-013 同源症状）——conftest 清理后该路径不再触发。

## Anti-patterns（不要这么做）

- ❌ 在 `tests/` 里断言默认配置却不清理 env（TD-011 原罪）。
- ❌ 依赖"CI 上恰好没有 key"的隐式假设保证测试通过。
- ❌ 修 `pyproject.toml` 依赖后忘记 `requirements.txt`（TD-012 原罪）。

## 下一步钩子

- TD-010 候选：沙箱网络策略增强（两阶段网络 + `network_mode` 配置化），见总表。
- 若需 pytest 内真实 LLM 测试：新增 marker 机制（如 `@pytest.mark.real_llm` + conftest 按 marker 放行 env），单独立项。

## Trace to Sources

- Spec 全文：`mydocs/specs/2026-07-19_16-59_test-env-isolation.md`
- 技术债登记：`.kimi/vibe_specs/technical-debt-spec.md` TD-011/TD-012
- 验证日志：Spec §5 Execute Log（2026-07-19 双环境 pytest 输出）
