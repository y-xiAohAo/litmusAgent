# 归档（LLM 视角）— 技术债治理第二轮：TD-004 / TD-005 架构主线

> 生成：2026-07-18 | 模式：thematic | 受众：llm（后续会话续接用）
> Source Index：
> - `mydocs/specs/2026-07-17_23-49_td-004-execution-context-injection.md`
> - `mydocs/specs/2026-07-18_00-18_td-005-runtime-services.md`
> - `mydocs/archive/2026-07-17_22-15_td-governance-round1_llm.md`（round1 约束与模式）
> 冲突标记：无

---

## 1. 约束（Constraints，新增/更新）

- 工具 handler 的 `execution_context` 是**保留参数名**：声明即被注入（arguments 未提供时），不要用它做 LLM 可见参数。
- `ExecutionContext` 生命周期：session 级（Agent 实例属性），`reset()` 清空；不持久化、不暴露给 LLM。
- 新增内部工具 = `RuntimeServices` 加槽位 + `register_internal_tools()` 加分支；**禁止**把装配逻辑写回 `Agent.__init__`。
- 当前基线：**598 passed, 1 skipped**；mypy 45 文件零错误；ruff 全绿。

## 2. 接口与契约（Interfaces / Contracts）

```python
# src/agent/core/engine.py
class ToolRegistry:
    def __init__(self, policy=None, execution_context: ExecutionContext | None = None)
    def register(self, spec: ToolSpec) -> None
    # register 时 inspect.signature 探测 "execution_context" 并缓存到 _ctx_aware: set[str]
    # execute 时：call.name in _ctx_aware 且 arguments 未提供 → 注入（新建 dict，不改原 arguments）

class Agent:
    execution_context: ExecutionContext   # session 级；reset() clear()
    runtime_services: RuntimeServices
    context_cache / memory_manager        # 属性委托 runtime_services 槽位

# src/agent/core/runtime.py
@dataclass
class RuntimeServices:
    execution_context: ExecutionContext
    context_cache: ContextCache | None = None
    memory_manager: MemoryManager | None = None
    @classmethod
    def from_config(cls, config, policy, execution_context,
                    context_cache=None, memory_manager=None) -> RuntimeServices
    # 注入优先；压缩启用→cache；记忆启用→manager（构造时注入 policy）

# src/agent/tools/__init__.py
def register_internal_tools(registry, services, config=None) -> None
    # cache 存在且开关开 → context_read；manager 存在且开关开 → memory_read

# src/agent/tools/sandbox_exec.py
async def sandbox_exec(code, backend, execution_context=None) -> ToolResult
def _extract_pip_packages(code: str) -> list[str]   # 行级启发式；ctx key = "packages_installed"
```

## 3. 代码触点（Code Touchpoints）

| 主题 | 位置 |
|---|---|
| 注入机制 | `engine.py` `ToolRegistry.register/execute`，`_ctx_aware` 集合 |
| 装配区 | `engine.py` `Agent.__init__`：`RuntimeServices.from_config(...)` + 属性委托 + `register_internal_tools` + 注入 manager 的 policy 补注入块 |
| 工厂 | `core/runtime.py`（cache/manager 创建逻辑原属 engine 私有方法，已删除） |
| 注册编排 | `tools/__init__.py` `register_internal_tools`（开关判断原属 engine，已迁入） |

## 4. 已接受模式（Accepted Patterns，新增）

1. **签名声明即注入**：有状态能力通过可选参数声明获取，registry 统一注入——优于闭包（TD-005 已取代闭包方案为官方路径）。
2. **探测结果 register 时缓存**，execute 热路径不做 introspection。
3. **属性委托保兼容**：重构装配时保留原属性名指向新结构，下游与测试零改动。
4. **注入优先于配置创建**：所有工厂路径必须接受显式注入覆盖。

## 5. 反模式（Anti-patterns，新增）

1. ❌ 在 `execute()` 热路径做 `inspect.signature`（已踩性能设计坑，注册时缓存）。
2. ❌ 把新内部工具的创建/注册写回 `Agent.__init__`（TD-005 治理对象，禁止回潮）。
3. ❌ 修改 `register_context_tools`/`register_memory_tools` 签名（保持向后兼容的决定）。
4. ❌ 假设 `pip install X` 裸行是合法 Python——沙箱中真实 pip 安装走 `subprocess.run([sys.executable, '-m', 'pip', ...])`（评审实证）。

## 6. 下一步钩子（Next-step Hooks）

1. **TD-008**（人工确认钩子）：注入点已就绪——approval callback 可设计为经 ExecutionContext/RuntimeServices 传递；注意验证"槽位 + 注册分支"两处扩展路径。
2. **FAST 收尾**：`_extract_pip_packages` 增加 subprocess 风格 list 匹配（评估约 0.5-1h；风险：误报/过度记录，保持成功门禁）。
3. **FAST 收尾**：`tests/test_evaluation_log.py` 增加表格列数一致性校验（本会话 3 次踩坑）。
4. **TD-009**：核实 Phase 8.4 交付状态后关闭。
5. **TD-007**：按需（subprocess fallback 已兜底）。
6. 当前 git HEAD：`e623797`（本地 master，无远程）。
