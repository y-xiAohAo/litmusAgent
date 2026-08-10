# 归档（LLM 视角）— 真实 LLM 联调单元（E2E Suite）

> 生成：2026-07-18 | 模式：snapshot | 受众：llm（后续会话续接用）
> Source Index：
> - `mydocs/specs/2026-07-18_02-50_real-llm-e2e-suite.md`（含 Review Matrix）
> - `docs/evaluation-log.md` 端到端测试结果表
> 冲突标记：无

---

## 1. 约束（Constraints，新增）

- 联调场景的证据断言**不得对 LLM 行为做脆性假设**（如"必须用某工具"）；行为偏差如实记录，转为优化项而非阻塞项。
- API Key 仅从环境变量读取；报告不得含 key；明文 key 当前位于 `~/.bashrc`（用户要求，建议轮换）。
- 联调基线：DeepSeek `deepseek-chat`（= v4-flash 别名）@ `https://api.deepseek.com/v1`；成本基准：7 场景 ≈ 30 轮调用 ≈ 80s 总耗时。
- 预置镜像 `hermes-sandbox:latest`（numpy/pandas）已存在于本机 Docker；重建见 `examples/docker/Dockerfile.sandbox`。

## 2. 接口与契约（Interfaces / Contracts）

```python
# examples/e2e_suite.py
@dataclass Scenario: id/name/prompt/backend/enable_security/image/
                     expected_tools/expected_in_output/max_turns=15
@dataclass ScenarioResult: scenario_id/success/turns/tools_used/duration_s/evidence/error
async def run_scenario(sc, client) -> ScenarioResult   # try/finally 关后端，异常转 error
def evaluate_evidence(sc, tool_events, final_answer) -> list[tuple[str, bool]]
def render_report(results) -> str                      # Markdown，可粘贴 evaluation-log
# CLI：--only S1,S3,S1-sub,S3b / --echo / --list
```

## 3. 实测行为事实（Facts from Real Runs）

| 事实 | 数据 |
|---|---|
| DeepSeek 偏好 sandbox_exec 通吃 | S2 两轮均 1 轮完成且跳过 file_write/file_read；S4 稳定跳过 file_edit |
| 禁网自愈路径存在 | S3（禁网）5 轮成功，Agent 未死循环 |
| TD-006 策略拦截真实生效 | S5 写 /etc 被拒，Agent 换方案并解释 |
| 预置镜像收益量化 | S3b 3 轮 8.5s vs S3 5 轮 23.1s（-63%） |
| subprocess 后端等价 | S1-sub PASS，工具使用反而更丰富（file_list/file_read 出现） |

## 4. 已接受模式（Accepted Patterns，新增）

1. **联调即资产**：场景定义 + 证据断言 + 自动报告 = 可回归的评测资产，优于手动单次验证。
2. **失败重跑定性**：联调 FAIL 先重跑一次区分"模型抖动"与"稳定行为"，再决定定性。
3. **对照场景设计**：关键变量（后端/镜像）用对照场景隔离（S1-sub、S3b）。

## 5. 反模式（Anti-patterns，新增）

1. ❌ 对 LLM 行为写脆性断言（"必须调用某工具"）——用工具序列记录 + 结果断言替代。
2. ❌ 联调失败只记录 PASS/FAIL 不记录行为细节——工具序列与证据比是诊断入口。
3. ❌ 在报告/日志中落 API Key。

## 6. 下一步钩子（Next-step Hooks）

1. **S2/S4 消息级诊断**：dump agent.messages 看 LLM 决策原文，定位是 system prompt 工具引导不足还是工具 description 不够吸引（当前 system_prompt 无工具使用引导；`tool_router.py` 有指导文案但未确认注入时机）。
2. **工具偏好优化**：基于诊断结论，候选——system_prompt 加工具使用约束 / 工具 description 强化场景感 / tool_router 注入 system prompt。
3. **TD-010**：两阶段网络（联调实测依据已具备）。
4. 当前 git HEAD：`32e2eb0`（本地 master，无远程）。
