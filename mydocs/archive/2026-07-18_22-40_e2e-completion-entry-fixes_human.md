# 归档（Human 视角）— 真实联调补全：S9-S12 + Web/CLI 入口修复

> 生成：2026-07-18 | 模式：thematic | 受众：human
> Source Index：
> - `docs/evaluation-log.md`（S9-S12、Web/CLI E2E 记录；EVAL-011/012/013）
> - `examples/e2e_suite.py`、`src/agent/web/app.py`、`src/agent/cli/agent_cli.py`、`src/agent/cli/chat.py`
> - 关联：联调套件归档 `2026-07-18_14-10_real-llm-e2e-suite_*`

---

## 1. 目标与范围

补齐真实 LLM 覆盖矩阵的最后缺口：人工确认（S9）、沙箱代码扫描（S10）、context_read 外迁读回（S11）、LLM 摘要器（S12）、Web UI 与 CLI chat 两个入口。过程中发现并修复三个入口级 bug。

## 2. 关键决策

1. **套件化扩展**：所有新场景进入 `e2e_suite.py`（含 `approval_answers` 脚本化确认、`llm_summarizer` 开关、`config_overrides` 点分配置），可重复回归。
2. **环境诚实记录**：VPN TLS 拦截导致的失败如实诊断（HTTP 通/HTTPS 挂），不掩饰不重报。
3. **真实验证驱动修复**：三个 bug（EVAL-011/012/013）全部由真实联调暴露——mock 全绿无法覆盖（EchoClient 不需网络、不绑定事件循环）。

## 3. 结果与证据

| 场景 | 结果 | 验证点 |
|---|---|---|
| S9 人工确认（批准） | ✅ 2 轮 | y → file_write 真实执行 |
| S9b 人工确认（拒绝） | ✅ 2 轮 | n → 拦截 + Agent 换方案不重试 |
| S10 沙箱代码扫描 | ✅ 3 轮 | import os 被策略拒绝，Agent 换安全方式 |
| S11 context_read | ✅ 3 轮 | 大输出外迁后 LLM 真实使用 context_read 读回 |
| S12 LLM 摘要器 | ✅ 4 轮 | LLMSummarizer 压缩后关键信息保留 |
| Web UI 端点 | ✅ 2 轮 | 修复 EVAL-011 后工具事件 + 多轮上下文正确 |
| CLI chat 多轮 | ✅ 2 轮 | 修复 EVAL-012/013 后多轮上下文保持 |

## 4. 修复的 Bug

| ID | 问题 | 根因 | 修复 |
|---|---|---|---|
| EVAL-011 | Web UI 忽略 OPENAI_* 环境变量 | config 默认值显式传给 from_env 屏蔽 env（EVAL-001 同类） | env 优先 |
| EVAL-012 | CLI run/chat 同样忽略 env | `_load_config` 无环境变量层 | CLI 旗标 > env > 配置 > 默认 |
| EVAL-013 | CLI chat 第二轮 "Event loop is closed" | 每轮 `asyncio.run()` 创建并关闭新循环 | 对话循环复用单一事件循环 |

## 5. 汇报口径（可直接引用）

> 完成 Agent 框架 14 项功能的全量真实 LLM 验证：通过场景化联调套件（13 个场景 + 双对照）系统性验证核心链路，过程中发现并修复 6 个 mock 不可见的真实缺陷（含 docker-py 兼容性、沙箱权限不对称、记忆检索零命中、双入口环境变量屏蔽、事件循环复用），全部留有量化前后对照证据。

## 6. 下一步钩子

- 可选：CI 中接入 `--strict` 退出码模式
- 可选：Web UI trace 可视化增强
- TD-010 网络策略增强
