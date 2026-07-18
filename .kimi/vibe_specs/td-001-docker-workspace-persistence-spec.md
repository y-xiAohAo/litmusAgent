# TD-001 Spec：Docker 后端 Workspace 持久化

> **SDD-RIPER-ONE 阶段**：`Plan`（计划已落盘，等待 `Plan Approved` 后进入 `Execute`）  
> **对应技术债**：`.kimi/vibe_specs/technical-debt-spec.md` TD-001  
> **决策结论**：采用 **方案 B — 共享 Docker Volume + 保留容器池化**，在 `/workspace` 上提供跨调用的持久文件系统。  
> **严禁**：未收到明确的 `Plan Approved` 前，不编写实现代码。

---

## 1. Research Findings

### 1.1 当前问题

`DockerSandboxBackend` 当前为每次 `execute_code()` / `put_file()` 从预热池中获取一个独立容器，调用结束后立即销毁并补充新容器。后果：

- `file_write` 写入的文件在后续 `file_read` / `sandbox_exec` / `file_list` 中不可见。
- `get_file()` 只读取 `self._container`，但 `Agent` 从不调用 `create_container()`，导致真实场景下 `file_read` 直接返回 `None`。
- 同一 Agent 会话无法形成连续的“写 → 改 → 运行”工作区。

### 1.2 已批准的修复方向

经讨论确认，采用 **方案 B**：

- 引入命名 Docker Volume 作为 workspace。
- 每个容器创建时自动挂载该 volume 到 `/workspace`。
- 池化容器继续每次销毁，但文件通过共享 volume 持久化。
- 同步重写受影响的 `tests/test_sandbox.py`（项目开发规范）。

---

## 2. Scope

### 2.1 Must Have

1. **Workspace Volume 机制**
   - `DockerSandboxBackend` 增加 `workspace_volume` 与 `cleanup_workspace` 参数。
   - 默认 `workspace_volume` 为自动生成的唯一名称（如 `hermes-workspace-<short_id>`），避免多 session 冲突。
   - 默认 `cleanup_workspace=True`，后端关闭时自动删除 volume。

2. **容器挂载 `/workspace`**
   - `_do_create_container()` 在创建容器时挂载 workspace volume 到 `/workspace`（`mode: rw`）。
   - 保留 `/tmp` tmpfs 用于临时文件，保持现有安全参数不变。

3. **所有文件操作都走带 Volume 的容器**
   - `execute_code()`：池化容器挂载 workspace，代码可读写 `/workspace`。
   - `put_file()`：池化容器挂载 workspace，文件写入 `/workspace` 后持久化。
   - `get_file()`：改造为使用池化容器（与 `put_file` / `execute_code` 一致），确保能读取 workspace 中的文件。

4. **资源清理**
   - `close()` 中停止/移除当前容器、清理预热池、关闭 client。
   - 若 `cleanup_workspace=True`，额外删除 workspace volume。

5. **测试重写与补充**
   - 更新 `tests/test_sandbox.py` 中所有断言 `containers.create` kwargs 的测试，预期包含 `volumes`。
   - 删除或改写不再适用的池化断言（如“执行后销毁并补充新容器”仍可保留，但需确认 volume 共享）。
   - 新增测试：
     - `create_container` 默认挂载 workspace volume。
     - `put_file` / `execute_code` / `get_file` 使用同一 workspace volume 名称。
     - `close()` 在 `cleanup_workspace=True` 时删除 volume。
     - `close()` 在 `cleanup_workspace=False` 时保留 volume。

6. **工具层与提示更新**
   - 更新 `src/agent/core/tool_router.py` 的使用指导，明确告诉 LLM：持久文件应放在 `/workspace`。
   - 不需要在工具层强制路径转换（留给 TD-006 处理 workspace 边界）。

### 2.2 Non-Goals

- 不实现 subprocess 后端（TD-002）。
- 不强制将 `/tmp` 之外的路径重定向到 `/workspace`。
- 不修改 `Agent.__init__` 中后端构造逻辑（TD-003 单独处理）。
- 不引入跨进程/跨机器的分布式存储。
- 不修改文件工具（`file_read.py`、`file_write.py`、`file_edit.py`、`file_list.py`）的实现。

---

## 3. Architecture & Strategy

```text
┌─────────────────────────────────────────┐
│         DockerSandboxBackend            │
│  workspace_volume = "hermes-ws-abc123"  │
└───────────────────┬─────────────────────┘
                    │ 所有容器共享该 volume
        ┌───────────┼───────────┐
        ▼           ▼           ▼
   ┌────────┐  ┌────────┐  ┌────────┐
   │Container│  │Container│  │Container│  ← 池化，用完即毁
   │/workspace│  │/workspace│  │/workspace│
   └────────┘  └────────┘  └────────┘
        ▲           ▲           ▲
        │  execute_code()        │
        │  put_file(path)        │
        │  get_file(path)        │
        └────────────────────────┘
```

### 3.1 关键设计决策

- **命名 volume 而非 bind mount**：避免 Windows 宿主机路径、权限、WSL2 转换问题，兼容 Docker Desktop 默认后端。
- **每个 backend 实例独立 volume**：通过 UUID 后缀命名，避免多 Agent session 互相污染。
- **`/workspace` 作为持久区，`/tmp` 保持临时区**：既提供持久工作区，又保留现有 `/tmp` 语义和安全限制。
- **`get_file()` 与 `put_file()` / `execute_code()` 使用同一容器获取/释放机制**：保证所有操作都挂载 workspace。

---

## 4. Detailed Design & Implementation

### 4.1 修改文件

#### `src/agent/sandbox/docker_backend.py`

**构造函数签名变更**：

```python
class DockerSandboxBackend:
    def __init__(
        self,
        image: str = "python:3.11-slim",
        timeout: int = 30,
        workspace_volume: str | None = None,
        cleanup_workspace: bool = True,
    ) -> None:
        ...
        self.workspace_volume: str = (
            workspace_volume or f"hermes-workspace-{uuid.uuid4().hex[:8]}"
        )
        self.cleanup_workspace: bool = cleanup_workspace
```

**`_do_create_container()` 增加 volume 挂载**：

```python
create_kwargs: dict[str, Any] = {
    "image": self.image,
    "command": command,
    "detach": True,
    "stdin_open": True,
    "tty": False,
    "network_mode": network_mode,
    "user": user,
    "read_only": read_only,
    "volumes": {
        self.workspace_volume: {"bind": "/workspace", "mode": "rw"},
    },
}
```

> 注意：若调用方自定义了 `tmpfs`，仍保留；`volumes` 与 `tmpfs` 可共存。

**`get_file()` 改造为使用池化容器**：

```python
async def get_file(self, container_path: str) -> bytes | None:
    client = self._get_client()
    if client is None:
        return None

    container: Container | None = None
    try:
        container = await self._acquire_container()
        if container is None:
            return None

        data, _stat = await asyncio.to_thread(
            container.get_archive,
            container_path,
        )
        ...
    except Exception:
        return None
    finally:
        if container is not None:
            await self._release_and_replenish(container)
```

**`close()` 增加 volume 清理**：

```python
def close(self) -> None:
    # 1. 移除当前容器
    # 2. 清理预热池
    # 3. 关闭 client
    # 4. 若 cleanup_workspace=True，删除 workspace volume
    ...
```

### 4.2 修改文件

#### `tests/test_sandbox.py`

- 更新 `Mock client` fixture 或各个测试中的 `mock_client.containers.create.return_value`：由于 `get_file()` 现在也会走池化，部分测试可能需要允许 `containers.create` 被多次调用并返回同一 mock。
- 更新断言 `containers.create` kwargs 的测试，预期包含：
  ```python
  "volumes": {
      backend.workspace_volume: {"bind": "/workspace", "mode": "rw"},
  }
  ```
- 删除/改写不再成立的断言（如 `test_execute_code_replenishes_pool_after_execution` 仍可保留，但需验证补充的新容器也挂载同一 volume）。
- 新增测试类 `TestDockerSandboxBackendWorkspace`：
  - `test_create_container_mounts_workspace_volume`
  - `test_put_file_uses_workspace_volume`
  - `test_get_file_uses_workspace_volume`
  - `test_close_removes_workspace_volume_when_cleanup_enabled`
  - `test_close_keeps_workspace_volume_when_cleanup_disabled`

#### `src/agent/core/tool_router.py`

更新 `build_routing_prompt()` 使用指导：

```text
- 需要创建新文件或覆盖整个文件时，使用 `file_write`，路径建议放在 `/workspace`
- 需要修改已有文件的局部内容时，使用 `file_edit`，路径建议放在 `/workspace`
- 需要读取或查看文件时，使用 `file_list` 或 `file_read`，路径建议放在 `/workspace`
```

#### `docs/session-context.md` / `docs/evaluation-log.md`

- TD-001 状态更新为“进行中 / 已完成”。
- 移除或更新已知技术债描述。

---

## 5. Execution Checklist（Plan Approved 后执行）

1. 修改 `DockerSandboxBackend.__init__`，新增 `workspace_volume` / `cleanup_workspace`。
2. 修改 `_do_create_container()`，挂载 workspace volume 到 `/workspace`。
3. 改造 `get_file()` 使用 `_acquire_container()` / `_release_and_replenish()`。
4. 修改 `close()`，增加 volume 清理逻辑。
5. 更新 `tests/test_sandbox.py` 中受影响的现有测试。
6. 新增 `TestDockerSandboxBackendWorkspace` 测试类。
7. 更新 `src/agent/core/tool_router.py` 使用指导。
8. 运行 `pytest tests/test_sandbox.py -v`，修复失败。
9. 运行 `pytest tests/test_tools.py -v`，确认文件工具仍通过。
10. 运行完整质量门禁：`pytest tests/ -q`、`mypy src/`、`ruff check src/ tests/`。
11. 更新 `docs/session-context.md`、`docs/evaluation-log.md`、`.kimi/vibe_specs/technical-debt-spec.md` 中 TD-001 状态。

---

## 6. Acceptance Criteria

- `pytest tests/test_sandbox.py -v` 全部通过。
- `pytest tests/test_tools.py -v` 全部通过（文件工具基于 backend 契约仍成立）。
- `pytest tests/ -q` 不新增失败，保持 532 passed, 1 skipped 基线。
- `mypy src/` 零错误。
- `ruff check src/ tests/` 全绿。
- 新增测试覆盖：volume 挂载、同一 volume 名称共享、`close()` 清理/保留 volume。
- `tool_router.py` 中明确提示 LLM 使用 `/workspace` 存放持久文件。

---

## 7. Risks & Mitigations

| 风险 | 可能性 | 影响 | 缓解 |
|---|---|---|---|
| 大量 sandbox 测试需要重写 | 高 | 中 | 按 checklist 逐项更新；保持 mock 行为与真实 Docker 语义一致 |
| Windows Docker Desktop 下 named volume 权限问题 | 中 | 中 | 使用 named volume 而非 bind mount；在测试/文档中说明 |
| `/workspace` 与现有 `/tmp` 路径语义混淆 | 中 | 中 | 通过 `ToolRouter` 提示明确；不强制重定向路径 |
| volume 未及时清理导致磁盘泄漏 | 中 | 中 | 默认 `cleanup_workspace=True`；`close()` 中捕获异常不阻塞 |
| `get_file()` 改造后读取非 workspace 路径的行为变化 | 低 | 低 | `get_file` 仍接受任意容器路径，只是操作容器改为池化 |

---

## 8. STOP-and-Wait Protocol

本 Spec 处于 **SDD-RIPER-ONE Plan 阶段**。根据规范：

> **No Approval, No Execute.**

在收到你明确的 `Plan Approved` 之前，**禁止**进行任何代码修改。

**下一步动作**：请审阅本 Spec，确认设计细节后回复 `Plan Approved`，再进入 Execute 阶段。
