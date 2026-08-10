# 归档（Human 视角）— 技术债治理第一轮：TD-002 / TD-003 / TD-006

> 生成：2026-07-17 | 模式：thematic | 受众：human
> Source Index：
> - `mydocs/specs/2026-07-17_20-55_td-002-003-subprocess-backend.md`
> - `mydocs/specs/2026-07-17_21-45_td-006-workspace-write-boundary.md`
> - `.kimi/vibe_specs/technical-debt-spec.md`（上游详规）
> - `docs/evaluation-log.md`（指标与 STAR 记录）

---

## 1. 目标与范围

第一轮技术债治理聚焦"可用性 + 安全边界"两条线，完成 3 项债务：

| 债务 | 目标 | 范围 |
|---|---|---|
| TD-002 | 无 Docker 环境下恢复代码执行闭环 | 新增本地子进程沙箱后端 |
| TD-003 | `config.sandbox.backend` 配置真正生效 | 后端工厂 + Agent 接线 |
| TD-006 | 文件写操作默认限制在 workspace 内 | 策略规则 + 可配置边界 |

明确未做（Non-Goals）：cgroup/seccomp 等 Docker 级隔离（subprocess 后端为轻量 fallback）、read 规则变更、引擎核心语义变更。

## 2. 关键决策

1. **Protocol 结构化抽象**（TD-002）：新增 `SandboxBackend` Protocol 而非 ABC 继承或 Union 类型——Docker 后端零侵入，未来新后端零成本接入。〔Trace: TD-002/003 Spec §2〕
2. **POSIX 路径映射**：subprocess 后端将 `/workspace/...`、`/tmp/...` 统一映射到实例临时目录，天然隔离且与 Docker 语义一致。〔Trace: TD-002/003 Spec §2〕
3. **纯规则表达边界**（TD-006）：利用 PolicyEngine "优先级降序首命中"语义，以 deny(`..`)@95 / allow(workspace)@50 / deny(catch-all)@1 三件套表达默认边界，零引擎改动。〔Trace: TD-006 Spec §2〕
4. **执行期合规修订**：`file_list` 经 `execute_code` 绝对路径绕过映射 → 新增后端可选能力 `list_dir`，先改 Spec 后改码。〔Trace: TD-002/003 Spec Change Log 21:20〕

## 3. 结果与证据

| 指标 | 治理前 | 治理后 |
|---|---|---|
| 测试 | 541 passed | **575 passed**（+34） |
| mypy | 42 文件零错误 | 44 文件零错误 |
| 沙箱后端 | 仅 Docker | Docker + Subprocess 双后端，配置驱动 |
| 写操作边界 | 仅拦敏感路径 | 默认限 workspace，可配置迁移，防 `..` 逃逸 |

- 三轴评审（两个单元）：全部 PASS，无阻塞项。〔Trace: 两 Spec §6 Review Verdict〕
- 提交：`811babb`/`e8b4c6e`（TD-002/003）、`5fb0122`/`00e9479`（TD-006）。

## 4. 风险与遗留

1. subprocess 后端无 OS 级隔离，仅适合可信代码与演示场景（文档已声明）。
2. LLM 代码硬编码绝对 POSIX 路径时在 Windows 宿主机的 subprocess 后端不可见（已知限制）。
3. 策略启用后写 `/tmp` 的存量用法会被拒绝（TD-006 的目标行为，路由提示已引导 `/workspace`）。
4. `evaluation-log.md` 表格分隔行存在列数不一致（历史遗留），建议补表格一致性校验测试。

## 5. 汇报口径（可直接引用）

> 本轮完成 Hermes Agent 第一轮技术债治理：通过 Protocol 抽象引入双沙箱后端架构，使 Agent 在无 Docker 环境下恢复完整编码闭环；并以纯策略规则实现可配置的文件写边界。新增 34 个测试，全量 575 passed、mypy/ruff 全绿，两项三轴评审均无阻塞通过。

## 6. 下一步钩子

- 推荐：TD-004+TD-005（ExecutionContext 注入 + 解耦 `Agent.__init__`，架构主线）
- 候选：TD-008（人工确认，受益于 TD-004）、TD-007（镜像源，按需）、TD-009（核实关闭）
- 小任务：evaluation-log 表格一致性校验测试
