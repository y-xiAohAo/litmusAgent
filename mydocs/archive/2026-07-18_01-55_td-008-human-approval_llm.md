# 归档（LLM 视角）— TD-008：写操作人工确认钩子（CLI）

> 生成：2026-07-18 | 模式：snapshot | 受众：llm（后续会话续接用）
> Source Index：
> - `mydocs/specs/2026-07-18_01-15_td-008-human-approval.md`（Research/Plan/Execute/Validation/Review）
> - `mydocs/archive/2026-07-18_00-35_td-governance-round2_llm.md`（注入机制前序）
> 冲突标记：无

---

## 1. 约束（Constraints，新增）

- `ApprovalCallback` 为**同步**签名（CLI 单用户阻塞可接受）；Web 接入异步确认前不得改签名，需新设计。
- 人工确认**永不默认开启**；未启用 config 或未注入 callback 时行为必须零变化。
- 策略拒绝（PolicyEngine）**优先于**人工确认——确认钩子必须位于策略检查之后。
- 拒绝 content 必须显式含"用户拒绝"及防重试引导语。
- 当前基线：**615 passed, 1 skipped**；mypy 45 文件零错误。

## 2. 接口与契约（Interfaces / Contracts）

```python
# src/agent/core/engine.py
ApprovalCallback = Callable[[str, dict[str, Any]], bool]   # (工具名, 参数) -> 批准?

class ToolRegistry:
    def __init__(self, policy=None, execution_context=None,
                 approval_callback: ApprovalCallback | None = None,
                 approval_tools: set[str] | None = None)
    # execute() 顺序：工具级策略 → 参数级策略 → 未知工具检查 → 人工确认 → handler
    # 仅 callback 与 approval_tools 同时存在且 call.name ∈ approval_tools 时触发

class Agent:
    def __init__(self, ..., approval_callback: ApprovalCallback | None = None)
    # approval_tools 来自 config.agent.human_approval（enabled=True 才装配）

# src/agent/config.py
class HumanApprovalConfig(BaseModel):
    enabled: bool = False
    tools: list[str] = ["file_write", "file_edit"]
# 挂载点：AgentRuntimeConfig.human_approval

# src/agent/cli/chat.py
def make_cli_approval_callback(tools: set[str], plain: bool = False) -> ApprovalCallback
    # y=批准 / n=拒绝 / a=闭包 approved_always 记录该工具名，会话内免确认（按工具名隔离）

# src/agent/cli/agent_cli.py
# run/chat 子命令 --approve 旗标：_build_agent(..., approve=...) 强制启用并注入 CLI callback
```

## 3. 代码触点（Code Touchpoints）

| 主题 | 位置 |
|---|---|
| 确认钩子 | `engine.py` `ToolRegistry.execute()`（策略块之后、handler 之前） |
| Agent 装配 | `engine.py` `Agent.__init__`（`approval_tools` 由 config 派生） |
| CLI 交互 | `cli/chat.py` `make_cli_approval_callback`（`approved_always` 闭包） |
| 旗标接线 | `cli/agent_cli.py` `_build_agent(approve=..., plain=...)`，旗标 > 配置文件 |

## 4. 已接受模式（Accepted Patterns，新增）

1. **钩子注入模式**：横切关注点（策略/确认）都挂 `ToolRegistry.execute()` 统一前置链，顺序 = 工具策略 → 参数策略 → 人工确认 → 执行。
2. **失败文案面向 LLM 设计**：工具失败信息要防误分类（显式"用户拒绝，不是系统错误"）。
3. **会话级豁免闭包**：交互式免确认用闭包集合实现，按工具名隔离粒度。

## 5. 反模式（Anti-patterns，新增）

1. ❌ 在请求-响应式 Web 端点里做 per-call 阻塞确认（架构冲突，Non-Goal 排除）。
2. ❌ 让人工确认先于策略检查（被禁止的操作不应触发用户询问）。
3. ❌ 免确认状态做成全局共享（必须按工具名隔离）。
4. ❌ 拒绝文案写成通用错误样式（LLM 会误重试）。

## 6. 下一步钩子（Next-step Hooks）

1. **Web UI 确认单元**：需 asyncio.Event 挂起/恢复 + 前端确认面板；可复用 `ApprovalCallback` 概念但需异步变体。
2. **TD-009**：核实 Phase 8.4 交付状态后关闭。
3. **TD-007**：按需。
4. **FAST**：`tests/test_evaluation_log.py` 表格列数校验。
5. 当前 git HEAD：`dea9e75`（本地 master，无远程）。
