# Phase 9 开发接力文档：安全策略引擎

> **本文档目标**：为下一个 session 提供足够上下文，使其能在 Phase 8.4 已完成基线上推进 Phase 9。
>
> **状态**：规划文档 / 待审批后实施。
>
> **最后更新**：2026-07-10

---

## 1. 当前基线（进入 Phase 9 之前的状态）

### 1.1 已完成交付

| Phase | 状态 | 关键文件 |
|-------|------|----------|
| Phase 1-6 | ✅ 完成 | 核心引擎、错误恢复、Agent Trace 等 |
| Phase 7 | ✅ 完成 | 上下文压缩（context_cache / compressor 等） |
| Phase 8.1-8.3 | ✅ 完成 | 长期记忆 MVP：`memory.py`、主循环集成、`memory_read` |
| Phase 8.4 | ✅ 完成 | 记忆审计、用户反馈、冲突检测、CLI、Markdown 导出 |

### 1.2 质量基线

```bash
python -m pytest tests/ -q        # 373 passed, 1 skipped（tiktoken 未安装）
python -m mypy src/               # Success: no issues found in 33 source files
python -m ruff check src/ tests/  # All checks passed!
```

- Git 分支：`master`
- Python：>= 3.10，建议 3.11
- 记忆默认关闭：`MemoryConfig.enabled = False`

### 1.3 默认行为（必须保持）

- `MemoryConfig.enabled` 默认 `False`，未启用时 Phase 1~7 行为不变。
- 记忆注入/记录/读取失败必须内部捕获异常，**不阻塞主循环**。
- 安全策略引擎默认也应**关闭或宽松**，不破坏现有行为。
- 所有安全失败应返回可理解的 `ToolResult(success=False)`，而不是抛异常阻塞主循环。

---

## 2. Phase 9 范围与边界

### 2.1 来源

原始计划 `docs/plans/2026-04-28-code-sandbox-agent.md` §Phase 9：

> 把代码执行、文件操作、网络访问等安全规则系统化，形成可配置的策略引擎。

`docs/progress-spec.md` 与 `.kimi/vibe_specs/long_term_memory-spec.md` 进一步说明：

> Phase 9 安全策略将来包裹记忆；`memory_read` 走 URI 校验；未来策略引擎只需限制 category/读写权限。

### 2.2 推荐优先级

| 优先级 | 模块 | 内容 | 理由 |
|--------|------|------|------|
| P0 | 策略核心 | `PolicyEngine` / `SecurityPolicy` + `PolicyRule` + `PolicyDecision` | 奠定所有安全检查基础 |
| P0 | 工具执行策略 | 在 `ToolRegistry.execute()` 前拦截危险调用 | 直接保护 Agent 行为 |
| P1 | 代码执行策略 | `sandbox_exec` 前置规则：禁用的 import / builtins / 网络操作 | 减少沙箱逃逸风险 |
| P1 | 文件操作策略 | `file_read` / `file_list` 路径白名单/黑名单 | 防止读取宿主机敏感路径 |
| P1 | 记忆策略 | 在 `MemoryManager` 读写路径接入 category/权限检查 | 为 Phase 8.5 Agent 记忆工具做准备 |
| P2 | Docker 安全策略 | 通过 `security_opt` / seccomp 传递策略到容器 | 与现有 DockerBackend 安全参数衔接 |
| P2（可选） | 审计日志 | 记录策略决策到 Trace 事件 | 便于事后审计 |

### 2.3 严禁做

- 不替换现有 `ToolRegistry` / `DockerSandboxBackend` / `MemoryManager`，只通过前置检查或可选参数接入。
- 不默认启用严格策略，避免破坏现有测试与示例。
- 不让安全策略失败阻塞主循环；策略拒绝应返回 `ToolResult(success=False, content="策略拒绝：...")`。
- 不引入重量级依赖（如 OPA、复杂 DSL）。
- 不修改现有 Tool 的函数签名；通过注册时包装或 `ToolRegistry` 层拦截。

---

## 3. 推荐设计草案

### 3.1 数据模型

新增 `src/agent/core/security.py`：

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PolicyAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REVIEW = "review"  # 允许但记录审计日志


@dataclass
class PolicyDecision:
    action: PolicyAction
    reason: str = ""


@dataclass
class PolicyRule:
    """单条策略规则。

    Attributes:
        resource: 资源类型，如 "tool", "sandbox/code", "file/path", "memory/category".
        operation: 操作类型，如 "execute", "read", "write", "delete".
        pattern: 匹配模式（字符串或正则，按 resource 解释）。
        action: 命中后的决策。
        reason: 人类可读的原因。
        priority: 规则优先级，数字越大越优先。
    """

    resource: str
    operation: str
    pattern: str
    action: PolicyAction
    reason: str = ""
    priority: int = 0


class PolicyEngine:
    """策略引擎：按 resource + operation + pattern 评估请求。"""

    def __init__(self, rules: list[PolicyRule] | None = None) -> None:
        self._rules = rules or []

    def evaluate(
        self,
        resource: str,
        operation: str,
        subject: str,
        context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """评估单个请求是否被允许。

        匹配逻辑：
          1. 过滤 resource 与 operation 同时匹配的规则。
          2. 按 priority 降序排列。
          3. 取第一条 pattern 匹配 subject 的规则返回其决策。
          4. 无匹配时返回 ALLOW（默认放行）。
        """
        ...

    def add_rule(self, rule: PolicyRule) -> None: ...
```

### 3.2 配置扩展

在 `src/agent/config.py` 新增 `SecurityConfig`：

```python
class SecurityConfig(BaseModel):
    """安全策略配置（Phase 9）。

    默认宽松，避免破坏现有行为。
    """

    enabled: bool = False
    default_action: str = "allow"  # allow / deny
    rules: list[dict[str, Any]] = Field(default_factory=list)
    # 预设规则开关
    block_subprocess: bool = True
    block_network_in_sandbox: bool = True
    block_os_import: bool = True
    memory_read_only_categories: list[str] = Field(default_factory=list)
```

并在 `AgentConfig` 中聚合：

```python
class AgentConfig(BaseModel):
    # ... existing fields ...
    security: SecurityConfig = Field(default_factory=SecurityConfig)
```

### 3.3 集成点

#### A. `ToolRegistry.execute()` 前置检查

在 `ToolRegistry.execute()` 中添加策略检查：

```python
async def execute(self, call: ToolCall) -> ToolResult:
    if self._policy is not None:
        decision = self._policy.evaluate(
            resource="tool", operation="execute", subject=call.name,
            context={"arguments": call.arguments},
        )
        if decision.action == PolicyAction.DENY:
            return ToolResult(
                tool_call_id=call.id,
                content=f"策略拒绝：{decision.reason}",
                success=False,
            )
    # ... existing logic ...
```

注意：策略拒绝不抛异常，LLM 能看到原因并可能自我修正。

#### B. `sandbox_exec` 代码静态扫描

在 `sandbox_exec()` 中对 `code` 做静态检查：

```python
async def sandbox_exec(
    code: str, backend: DockerSandboxBackend, policy: PolicyEngine | None = None
) -> ToolResult:
    if policy is not None:
        decision = policy.evaluate(
            resource="sandbox/code", operation="execute", subject=code
        )
        if decision.action == PolicyAction.DENY:
            return ToolResult(...)
    result = await backend.execute_code(code)
    ...
```

静态扫描能力（P1）：
- 检查禁用 import：`import os`, `import subprocess`, `import socket` 等。
- 检查禁用 builtins：`__import__`, `exec`, `eval`, `compile` 等。
- 检查网络相关调用：`requests.get`, `urllib` 等。

#### C. 文件操作路径策略

在 `file_read` / `file_list` 中检查路径：

```python
decision = policy.evaluate(
    resource="file/path", operation="read", subject=path
)
```

默认规则（P1）：
- 禁止读取 `/etc/passwd`, `~/.ssh`, 宿主机 `C:\Users\...` 敏感路径。
- 允许 `/workspace/`、`/tmp/` 等沙箱内路径。

#### D. 记忆读写策略

在 `MemoryManager` 中接入：

```python
def record(self, trace, state, run_metadata=None) -> list[MemoryEntry]:
    if not self._config.enabled:
        return []
    entries = self._extractor.extract(...)
    filtered = []
    for entry in entries:
        decision = self._policy.evaluate(
            resource="memory/category",
            operation="write",
            subject=entry.category.value,
        )
        if decision.action == PolicyAction.DENY:
            _logger.warning("策略拒绝写入记忆：%s", decision.reason)
            continue
        filtered.append(entry)
    # ... save filtered ...
```

读取侧（`inject`, `read`）同理检查 `memory/category` 的 `read` 操作。

### 3.4 默认规则集

当 `SecurityConfig.enabled=True` 且未提供自定义规则时，启用以下内置规则：

| resource | operation | pattern | action | reason |
|----------|-----------|---------|--------|--------|
| `tool` | `execute` | `sandbox_exec` | ALLOW | 沙箱执行是核心能力 |
| `sandbox/code` | `execute` | `import\s+(os\|subprocess\|socket)` | DENY | 禁止高风险系统调用 |
| `file/path` | `read` | `/etc/passwd` | DENY | 禁止读取系统用户文件 |
| `file/path` | `read` | `.*\.ssh.*` | DENY | 禁止读取 SSH 密钥 |
| `memory/category` | `write` | `environment` | ALLOW | 允许写入环境记忆 |
| `memory/category` | `write` | `preferences` | ALLOW | 允许写入用户偏好 |

---

## 4. 建议任务拆分

| 子任务 | 内容 | 涉及文件 | 验收标准 |
|--------|------|----------|----------|
| 9.1 | 策略核心：`PolicyEngine` / `PolicyRule` / `PolicyDecision` | `src/agent/core/security.py` | 单元测试覆盖 allow/deny/review、优先级、默认放行 |
| 9.2 | 配置扩展：`SecurityConfig` + `AgentConfig.security` | `src/agent/config.py` | 默认关闭；可从 YAML 加载规则 |
| 9.3 | `ToolRegistry` 前置策略检查 | `src/agent/core/engine.py` | 拒绝时返回 `ToolResult(success=False)` |
| 9.4 | `sandbox_exec` 代码静态扫描 | `src/agent/tools/sandbox_exec.py` | 测试覆盖禁用 import / builtins |
| 9.5 | 文件操作路径策略 | `src/agent/tools/file_read.py`、`file_list.py` | 测试覆盖敏感路径拒绝 |
| 9.6 | 记忆读写策略 | `src/agent/core/memory.py` | 测试覆盖 category 拒绝 |
| 9.7 | DockerBackend 安全策略透传（可选） | `src/agent/sandbox/docker_backend.py` | 通过 `security_opt` 应用 seccomp |
| 9.8 | 文档同步 | `docs/progress-spec.md`、`docs/session-context.md`、`CODEMAP.md` | 与实现一致 |

---

## 5. 测试策略

- **单元测试**：`tests/test_security_policy.py` 覆盖 `PolicyEngine` 所有决策路径。
- **集成测试**：
  - `tests/test_tool_security.py`：通过 `ToolRegistry` 验证工具拦截。
  - `tests/test_sandbox_security.py`：验证 `sandbox_exec` 静态扫描。
  - `tests/test_memory_security.py`：验证记忆 category 读写限制。
- **兼容性测试**：安全策略关闭时，所有 Phase 1-8 测试行为不变。

---

## 6. 关键决策与开放问题

### 已确定

1. 不替换现有组件，只通过前置检查接入。
2. 默认关闭，避免破坏现有行为。
3. 策略拒绝返回 `ToolResult(success=False)`，不抛异常。
4. 不引入外部策略引擎或 DSL。

### 待确认

1. **默认策略强度**：是默认宽松（仅高危操作拒绝）还是默认严格（仅白名单允许）？
   - 建议：默认宽松，因为项目当前定位是研究/开发框架。
2. **审计日志**：是否需要在 Trace 中记录策略决策？
   - 建议：P2，先实现核心决策再补充审计。
3. **LLM 可见性**：策略拒绝原因是否完整返回给 LLM？
   - 建议：是，便于 LLM 自我修正。

---

## 7. 恢复开发状态

```bash
cd /d/djh/hermes/project1
python -m pytest tests/ -q      # 确认 373 passed, 1 skipped
python -m mypy src/             # 确认无类型错误
python -m ruff check src/ tests/ # 确认 lint 通过
git log --oneline -5            # 确认在 Phase 8.4 提交之后
```

---

## 8. 参考

- Phase 9 原始计划：`docs/plans/2026-04-28-code-sandbox-agent.md` §Phase 9
- 长期记忆 spec：`.kimi/vibe_specs/long_term_memory-spec.md`
- 当前上下文：`docs/session-context.md`
- 代码地图：`CODEMAP.md`
