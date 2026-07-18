# Phase 4.1 Spec：sandbox_exec Tool

> 本规格切片来自 `docs/progress-spec.md` 第 4 节，用于约束本次编码任务的边界。

## 目标

实现 `sandbox_exec` Tool，让 Agent 能通过 Tool 调用在沙箱中执行 Python 代码，并把执行结果（stdout / stderr / 成功标志）返回给 LLM。

## 必须做（Must）

1. **新增 Tool 实现**
   - 文件：`src/agent/tools/sandbox_exec.py`
   - 实现 `sandbox_exec` 异步函数，接收 `code: str` 与 `backend: DockerSandboxBackend` 参数。
   - 内部调用 `DockerSandboxBackend.execute_code()`。
   - 返回 `ToolResult`，`success` 反映执行结果，`content` 承载 stdout（成功）或 stderr（失败）。

2. **提供默认工具注册函数**
   - 文件：`src/agent/tools/__init__.py`
   - 提供 `register_default_tools(registry, backend)`，把 `sandbox_exec` 注册到指定的 `ToolRegistry`。
   - 注册的 `ToolSpec` 参数 schema 必须包含必填字段 `code: string`。

3. **Agent 默认加载**
   - 文件：`src/agent/core/engine.py`
   - `Agent.__init__` 接受可选 `sandbox_backend` 参数；未传入时创建默认 `DockerSandboxBackend`。
   - 在构造时调用 `register_default_tools(self.tools, self._sandbox_backend)`，让 Agent 默认具备 `sandbox_exec` 能力。
   - `ToolRegistry.execute` 需要支持异步 handler 以及 handler 直接返回 `ToolResult` 的情况。

4. **新增测试**
   - 文件：`tests/test_tools.py`
   - 覆盖：成功返回 stdout、失败返回 stderr、`ToolSpec` schema 正确。
   - 所有测试使用 mock 后端，不依赖真实 Docker daemon。

## 严禁做（Must Not）

1. 不实现 `file_read` / `file_list` / `finish`（留给 Phase 4.2–4.3）。
2. 不修改 Agent 主循环的核心逻辑（只允许扩展 tools 注册与执行适配）。
3. 不写依赖真实 Docker daemon 的单元测试。

## 验收标准

- `python -m pytest tests/test_tools.py -v` 全部通过。
- `python -m pytest tests/ -q` 不新增失败。
- `python -m mypy src/` 零错误。
- `python -m ruff check src/ tests/` 零新增错误。
- 所有新函数有完整类型标注和中文 docstring。

## 涉及文件

- 新增：`src/agent/tools/sandbox_exec.py`
- 修改：`src/agent/tools/__init__.py`
- 修改：`src/agent/core/engine.py`（支持异步 handler / ToolResult，Agent 默认加载）
- 新增：`tests/test_tools.py`
- 可能修改：`tests/test_integration.py`（移除手动注册的 mock `sandbox_exec`，改用注入的 mock 后端）

## 依赖接口

```python
# src/agent/sandbox/docker_backend.py
class DockerSandboxBackend:
    async def execute_code(
        self,
        code: str,
        timeout: int | None = None,
    ) -> ExecutionResult:
        ...

@dataclasses.dataclass
class ExecutionResult:
    exit_code: int
    stdout: str
    stderr: str
    success: bool
```

`execute_code` 会自动管理容器生命周期，调用者只需传入 `code` 并读取返回的 `ExecutionResult`。
