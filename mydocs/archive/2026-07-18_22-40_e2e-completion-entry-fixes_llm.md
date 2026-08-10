# 归档（LLM 视角）— 真实联调补全：S9-S12 + Web/CLI 入口修复

> 生成：2026-07-18 | 模式：thematic | 受众：llm（后续会话续接用）
> Source Index：`docs/evaluation-log.md`、`examples/e2e_suite.py`、三处入口修复 diff
> 冲突标记：无

---

## 1. 约束（Constraints，新增）

- **环境变量优先级全项目统一**：CLI 旗标 > `OPENAI_*` env > 配置文件 > 默认值。任何调用 `OpenAIClient.from_env()` 的地方禁止把 config 默认值显式传入 model/base_url（会屏蔽 env）。
- **跨轮复用 Agent 时必须复用事件循环**：禁止每轮 `asyncio.run()`（创建即关闭，httpx client 等循环绑定资源会崩）。模式：`loop = asyncio.new_event_loop()` + try/finally close。
- 套件新场景机制：`approval_answers`（脚本化 y/n/a）、`llm_summarizer`、`config_overrides`（点分路径）。
- 基线：**679 passed, 1 skipped**；mypy 46 文件零错误。

## 2. 实测行为事实（Facts）

1. 人工确认真实行为：批准后写执行、拒绝后 Agent 换方案且不重试（防重试文案有效）。
2. 沙箱代码扫描真实生效：`import os` 被"策略拒绝"拦截，Agent 改用安全方式完成。
3. context_read 真实链路：大输出外迁 → LLM 主动 context_read 读回 → 答出第 38 行内容。
4. LLMSummarizer 压缩质量：暗号类关键信息压缩后保留（S12）。
5. VPN 环境教训：vortex 类客户端 TLS 层按进程拦截（curl 放行、Python 拒绝），诊断法=HTTP 通/HTTPS 挂/raw TCP 通。

## 3. Bug 模式库（新增反模式）

1. ❌ `OpenAIClient.from_env(model=config.llm.model)` —— 显式传默认值屏蔽环境变量（EVAL-011/012 共同模式）。
2. ❌ 在长循环里每轮 `asyncio.run()` —— 事件循环反复销毁（EVAL-013）。
3. ❌ 把"评审通过"当"真实可用"——本会话第三次验证（TD-008）此原则。

## 4. 下一步钩子（Next-step Hooks）

1. e2e_suite `--strict` 退出码模式（CI 接入候选）。
2. Web UI trace 可视化（结构化 AgentTrace 已就绪）。
3. TD-010 两阶段网络。
4. 当前 git HEAD：`ce72200`。
