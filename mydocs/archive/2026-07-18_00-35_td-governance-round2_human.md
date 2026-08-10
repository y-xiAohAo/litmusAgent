# 归档（Human 视角）— 技术债治理第二轮：TD-004 / TD-005 架构主线

> 生成：2026-07-18 | 模式：thematic | 受众：human
> Source Index：
> - `mydocs/specs/2026-07-17_23-49_td-004-execution-context-injection.md`
> - `mydocs/specs/2026-07-18_00-18_td-005-runtime-services.md`
> - `.kimi/vibe_specs/technical-debt-spec.md`（上游详规）
> - `docs/evaluation-log.md`（指标与 STAR 记录）

---

## 1. 目标与范围

第二轮聚焦"架构扩展性"主线，完成 2 项相互关联的债务：

| 债务 | 目标 | 范围 |
|---|---|---|
| TD-004 | 工具 handler 可读写 ExecutionContext，支持跨 tool call 运行时状态 | 注入机制 + session 级生命周期 + sandbox_exec pip 记录示例 |
| TD-005 | 解耦内部工具装配，`Agent.__init__` 不再是依赖装配中心 | RuntimeServices 三槽位 + 工厂 + 统一注册 |

明确未做：ExecutionContext 暴露给 LLM、持久化、Trace 接入；DI 框架/插件系统；外部工具注册方式变更。

## 2. 关键决策

1. **register 时签名探测 + 条件注入**：工具 handler 声明 `execution_context` 参数才注入（LLM arguments 未提供时），探测结果注册时缓存，热路径 O(1)——向后兼容与性能兼得。〔Trace: TD-004 Spec §2〕
2. **Session 级生命周期**：ExecutionContext 跨 `run()` 保留、`reset()` 清空——与沙箱内已装包的真实持久性语义一致（用户拍板）。〔Trace: TD-004 Spec §1.4〕
3. **捆绑 + 工厂**：RuntimeServices 统一持有 execution_context / context_cache / memory_manager，`from_config()` 迁入创建逻辑——Agent 装配区 ~40 行收敛到 4 行（用户拍板）。〔Trace: TD-005 Spec §2〕
4. **零涟漪兼容策略**：`register_context_tools`/`register_memory_tools` 签名不动、Agent 属性委托保留——20+ 既有测试零改动。〔Trace: TD-005 Spec §2〕

## 3. 结果与证据

| 指标 | 治理前 | 治理后 |
|---|---|---|
| 测试 | 575 passed | **598 passed**（+23） |
| mypy | 44 文件 | 45 文件零错误 |
| 工具上下文 | 无法跨调用共享状态 | 签名声明即注入，主循环集成验证 |
| Agent.__init__ | ~90 行装配 + 4 私有方法 | 4 行装配，私有方法清零 |

- 三轴评审（两个单元）：全部 PASS，无阻塞项；含真实 subprocess 后端行为抽查。
- 提交：`0ef5010`/`ead94b6`（TD-004）、`f67f6df`/`e623797`（TD-005）。

## 4. 风险与遗留

1. pip 记录启发式仅覆盖行级 `pip install` 形态，真实 subprocess 风格调用不覆盖（评审观察项，已列为 FAST 收尾任务）。
2. 新增内部工具需同步两处：RuntimeServices 槽位 + register_internal_tools 分支（TD-008 接入时验证该扩展路径）。
3. `evaluation-log.md` 表格列数不一致历史遗留（本次会话 3 次踩中，均已修复；校验测试待做）。

## 5. 汇报口径（可直接引用）

> 本轮完成 Hermes Agent 架构主线治理：通过注册时签名探测机制让工具按需注入 ExecutionContext，实现跨调用运行时状态共享；并以 RuntimeServices 统一装配内部工具依赖，将 Agent 构造函数从依赖装配中心解放出来。新增 23 个测试，全量 598 passed、mypy 45 文件零错误，两项三轴评审均无阻塞通过。后续有状态工具（如人工确认钩子）接入成本归零。

## 6. 下一步钩子

- 候选：TD-008（人工确认，注入点已就绪）、TD-007（镜像源，按需）、TD-009（核实关闭）
- FAST 收尾：pip 提取增强（subprocess 风格）、evaluation-log 表格校验测试
