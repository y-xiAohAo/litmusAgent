# 归档（LLM 视角）— Auto-Planner：自动 LLM 任务分解

> 生成：2026-07-18 | 模式：snapshot | 受众：llm（后续会话续接用）
> Source Index：`mydocs/specs/2026-07-18_15-30_auto-planner.md`（含 Review Matrix）、`docs/evaluation-log.md`
> 冲突标记：无

---

## 1. 约束（Constraints，新增）

- 自动规划**默认关闭**（`agent.planner.enabled`）；外部注入的 planner 永远优先，不覆盖。
- 规划失败必须静默降级直跑（三层：LLM 异常 / 解析空 / 每 run 一次）——不得阻塞主任务。
- `Agent` 不持有 config 对象：规划开关存于 `self._planner_enabled` / `_planner_max_steps`。
- 基线：**649 passed, 1 skipped**；mypy 45 文件零错误。

## 2. 接口与契约（Interfaces / Contracts）

```python
# src/agent/config.py
class PlannerConfig(BaseModel):
    enabled: bool = False
    max_steps: int = 6
# 挂载点：AgentRuntimeConfig.planner

# src/agent/core/engine.py
class Agent:
    async def _maybe_create_plan(self, user_input: str) -> None
    # run() 主循环前调用；enabled 且 planner is None 时：
    #   LLM 分解 → _parse_plan_steps → TaskPlan → start_next() → self.planner
    @staticmethod
    def _parse_plan_steps(text: str, max_steps: int) -> list[str]
    # 兼容 1. / 1) / 1、/ - / * 前缀；跳过前言后语；上限截断；空→降级

# src/agent/cli/agent_cli.py
# run/chat --plan 旗标 → _build_agent(..., plan=True) → config.agent.planner.enabled = True
```

## 3. 实测行为事实（Facts）

1. DeepSeek v4-flash 的规划分解质量高：S4 任务自动生成 5-6 步计划，准确包含"用 file_edit 改标题"关键步骤。
2. 自动规划真实验证：file_edit 2/2、标题 2/2（= 手工计划 3/3 水平，>> 裸跑 0/8）。
3. 规划 prompt 用 user-only 消息（无 system）即可稳定输出编号列表。

## 4. 已接受模式（Accepted Patterns，新增）

1. **能力默认关闭 + 旗标强制开启**：`--plan` / `--approve` 同模式（flag 覆盖 config，文档化优先级）。
2. **增强型调用降级链**：任何附加 LLM 调用（规划/摘要）失败都必须静默降级，不阻塞主链路。
3. **证据驱动的功能立项**：先有对照实验（S4p 0/8→3/3）证明价值，再实现自动化——避免为想象的需求写代码。

## 5. 反模式（Anti-patterns，新增）

1. ❌ 让附加能力的失败阻塞主任务（规划失败 → 任务必须能直跑）。
2. ❌ 把 config 对象挂在 Agent 上（拆字段存储，避免配置对象生命周期耦合）。
3. ❌ 对 LLM 输出做严格格式假设（解析器必须宽容 + 上限截断 + 空降级）。

## 6. 下一步钩子（Next-step Hooks）

1. **覆盖率提升单元**（91% → 95%+）：token_estimator 73% / context_cache 75% / CLI 75-87% / subprocess_backend 89% / web 88%。
2. 候选：chat 会话级计划复用、独立轻量规划模型（PlannerConfig.model）。
3. **TD-010**（两阶段网络）/ Web UI 确认单元。
4. 当前 git HEAD：`d42be4d`（本地 master，无远程）。
