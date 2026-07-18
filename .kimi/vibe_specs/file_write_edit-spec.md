# Phase 4.7 Spec：file_write / file_edit Tools

> **SDD-RIPER-ONE 阶段**：`Plan`（计划已落盘，等待用户批准后进入 `Execute`）  
> **范围**：补齐 Hermes Agent 作为 Coding Agent 最基础的文件修改能力  
> **目标**：让 Agent 能在沙箱内创建/覆盖文件（`file_write`）和做精确片段替换（`file_edit`）  
> **严禁**：本阶段只产出 Spec，不编写实现代码。未收到明确的 `Plan Approved` 前禁止进入 Execute。

---

## 1. Research Findings（现状与缺口）

### 1.1 当前已实现的工具

根据 `.kimi/vibe_specs/file_tools-spec.md`、`sandbox_exec-spec.md`、`finish-spec.md` 及 `src/agent/tools/__init__.py`，当前 Agent 默认注册的工具为：

- `sandbox_exec`：在沙箱内执行 Python 代码。
- `file_read`：读取沙箱内文件内容。
- `file_list`：列出沙箱内目录内容。
- `finish`：标记任务完成并终止主循环。
- （子系统配套工具）`context_read`、`memory_read`：分别在启用上下文压缩/长期记忆时自动注册。

### 1.2 核心缺口

作为 Coding Agent，仅有**读**和**执行**能力是不够的。LLM 要真正修改代码，至少需要：

1. **创建/覆盖文件**：把生成的代码、文本产物写入沙箱。
2. **精确编辑文件**：在已有文件中进行局部替换，而不是每次都重写整个文件。

当前缺少 `file_write` 和 `file_edit`，导致 Agent 无法完成“写代码 → 改代码 → 运行验证”的最小闭环。

### 1.3 后端能力现状

- `DockerSandboxBackend` 已提供 `put_file(container_path, content: bytes) -> bool` 和 `get_file(container_path) -> bytes | None`。
- 当前后端每次 `execute_code` / `put_file` 都会从预热池中获取新容器并立即销毁，这会导致文件在两次调用之间可能不可见。
- **本 Spec 的前提**：要么当前后端已保证同一会话内的文件持久性，要么在实现本 Phase 时同步修复后端容器生命周期（或增加共享 workspace 卷）。Spec 将工具实现与后端持久性解耦描述，但验收时必须保证跨轮文件可见。

---

## 2. Scope（范围）

### 2.1 Must Have（必须做）

1. 新增 `src/agent/tools/file_write.py`
   - 实现 `file_write(path: str, content: str, backend: DockerSandboxBackend) -> ToolResult`。
   - 将 `content` 以 UTF-8 编码后写入沙箱内 `path`（创建或覆盖）。
   - 写入成功返回简短确认；失败返回 `success=False` 与原因。

2. 新增 `src/agent/tools/file_edit.py`
   - 实现 `file_edit(path: str, old_string: str, new_string: str, backend: DockerSandboxBackend) -> ToolResult`。
   - 先读取文件，找到 `old_string` 的**唯一**出现位置并替换为 `new_string`，再写回。
   - 若 `old_string` 出现 0 次或超过 1 次，返回失败，避免误改。
   - 写回成功返回简短确认；失败返回 `success=False` 与原因。

3. 注册到默认工具集
   - 在 `src/agent/tools/__init__.py` 的 `_build_tool_specs()` 中追加 `file_write` 和 `file_edit`。
   - `register_default_tools()` 和 `register_tools_from_config()` 自动获得这两个工具。
   - 更新 `register_default_tools()` 的 docstring。

4. 接入安全策略
   - 在 `src/agent/core/engine.py` 的 `ToolRegistry._PARAMETRIC_CHECKS` 中增加：
     - `file_write: ("file/path", "write", "path")`
     - `file_edit: ("file/path", "write", "path")`
   - 在 `src/agent/core/default_security_rules.yaml` 中补充 `file/path` 的 `write` 拒绝规则（与 read 规则对应的系统敏感路径保持一致，如 `/etc/passwd`、`.ssh`、Windows SAM 等）。

5. 测试覆盖
   - 扩展 `tests/test_tools.py`（或新增 `tests/test_file_write_edit.py`）：
     - `file_write` 成功写入并可被 `file_read` 读回。
     - `file_write` 后端失败时返回 `success=False`。
     - `file_edit` 成功替换唯一匹配的字符串。
     - `file_edit` 旧字符串不存在时返回失败。
     - `file_edit` 旧字符串出现多次时返回失败（防止歧义替换）。
     - `file_edit` 目标文件不存在时返回失败。
     - ToolSpec schema 校验（`path`/`content` 必填，`path`/`old_string`/`new_string` 必填，`additionalProperties: False`）。
     - 危险路径的 `file_write` / `file_edit` 被策略拒绝。

6. 文档同步
   - 更新 `docs/configuration.md` 中 `tools.enabled` 的示例，补充 `file_write`、`file_edit`。
   - 更新 `src/agent/core/tool_router.py` 的 `build_routing_prompt()`，增加写/编辑工具的使用指导。

### 2.2 Non-Goals（本阶段不做）

- **不实现 `file_delete`**：删除可由 `sandbox_exec` 临时完成，后续如需再单独开 Spec。
- **不实现多文件 patch / diff 工具**：先保证单文件精确替换可用。
- **不引入行号编辑、正则替换等高级编辑语义**：降低复杂度，先用 `old_string`/`new_string` 覆盖 80% 场景。
- **不改写 Agent 主循环核心逻辑**：仅扩展工具注册与策略映射。
- **不写依赖真实 Docker daemon 的单元测试**：继续使用 mock backend。

---

## 3. Architecture & Strategy（架构与策略）

### 3.1 工具层定位

```text
LLM tool_call(file_write,  {"path": "/workspace/main.py", "content": "..."})
          ↓
file_write(path, content, backend)
          ↓
backend.put_file(path, content.encode("utf-8"))
          ↓
ToolResult(success=True, content="已写入 /workspace/main.py（123 字符）")

LLM tool_call(file_edit, {"path": "/workspace/main.py",
                          "old_string": "def foo():",
                          "new_string": "def foo(x: int):"})
          ↓
file_edit(path, old_string, new_string, backend)
          ↓
old_content = backend.get_file(path)
count = old_content.count(old_string)
if count != 1: 失败
new_content = old_content.replace(old_string, new_string, 1)
backend.put_file(path, new_content.encode("utf-8"))
          ↓
ToolResult(success=True, content="已编辑 /workspace/main.py，替换 1 处")
```

### 3.2 设计决策

- **复用 `backend.put_file` / `backend.get_file`**：不新增后端方法，保持沙箱层稳定。
- **编辑采用“唯一匹配”语义**：`old_string` 必须且只能出现一次。这是防止 LLM 用模糊片段误改多处的最小安全措施。
- **路径参数走现有 `file/path` 策略**：`file_write` 与 `file_edit` 共享 `file_read`/`file_list` 的策略通道，只增加 `write` operation 的映射。
- **默认即启用**：与 `file_read`/`file_list` 一样，写入默认工具集，用户仍可通过 `tools.enabled` 关闭。

---

## 4. Detailed Design & Implementation（详细设计与实现）

### 4.1 新增文件

#### `src/agent/tools/file_write.py`

```python
async def file_write(
    path: str,
    content: str,
    backend: DockerSandboxBackend,
) -> ToolResult:
    """在沙箱内创建或覆盖指定文件。

    Args:
        path: 沙箱内目标路径，例如 "/workspace/main.py"。
        content: 要写入的 UTF-8 文本内容。
        backend: 用于写入文件的 Docker 沙箱后端实例。

    Returns:
        成功时返回 ToolResult(content=确认信息, success=True)；
        写入失败时返回 ToolResult(content=错误说明, success=False)。
    """
```

**Schema（ToolSpec）**：

```json
{
  "type": "object",
  "properties": {
    "path": {"type": "string", "description": "沙箱内目标文件路径"},
    "content": {"type": "string", "description": "要写入的完整文本内容"}
  },
  "required": ["path", "content"],
  "additionalProperties": false
}
```

#### `src/agent/tools/file_edit.py`

```python
async def file_edit(
    path: str,
    old_string: str,
    new_string: str,
    backend: DockerSandboxBackend,
) -> ToolResult:
    """在沙箱内对文件进行精确的字符串替换编辑。

    要求 old_string 在文件中必须且只能出现一次，防止歧义替换。

    Args:
        path: 沙箱内目标文件路径。
        old_string: 要被替换的原始字符串片段。
        new_string: 用于替换的新字符串片段。
        backend: 用于读写文件的 Docker 沙箱后端实例。

    Returns:
        成功时返回 ToolResult(content=确认信息, success=True)；
        失败时返回 ToolResult(content=错误说明, success=False)。
    """
```

**Schema（ToolSpec）**：

```json
{
  "type": "object",
  "properties": {
    "path": {"type": "string", "description": "沙箱内目标文件路径"},
    "old_string": {"type": "string", "description": "要被替换的原始字符串片段，必须在文件中唯一出现"},
    "new_string": {"type": "string", "description": "用于替换的新字符串片段"}
  },
  "required": ["path", "old_string", "new_string"],
  "additionalProperties": false
}
```

### 4.2 修改文件

#### `src/agent/tools/__init__.py`

- 导入 `file_write` 和 `file_edit`。
- 在 `_build_tool_specs()` 的字典中追加 `"file_write"` 和 `"file_edit"` 两个 `ToolSpec`。
- 更新 `register_default_tools()` 的 docstring，列出新增工具。

#### `src/agent/core/engine.py`

- 在 `ToolRegistry._PARAMETRIC_CHECKS` 中追加：
  ```python
  "file_write": ("file/path", "write", "path"),
  "file_edit": ("file/path", "write", "path"),
  ```

#### `src/agent/core/default_security_rules.yaml`

- 为敏感路径补充 `operation: write` 的拒绝规则，与现有 `operation: read` 规则成对出现。

#### `src/agent/core/tool_router.py`

- 在 `build_routing_prompt()` 的使用指导中补充：
  - 需要创建新文件或覆盖整个文件时，使用 `file_write`。
  - 需要修改已有文件的局部内容时，使用 `file_edit`。

#### `docs/configuration.md`

- 在工具配置示例中列出 `file_write` 和 `file_edit`。

#### `tests/test_tools.py`（推荐扩展）

- 在 `MockSandboxBackend` 中增加 `async def put_file(self, path: str, content: bytes) -> bool` 与内部文件字典的写支持。
- 新增测试类 `TestFileWriteTool`、`TestFileEditTool`、`TestFileWriteEditSpec`。

### 4.3 执行 Checklist（Plan Approved 后逐项执行）

1. 创建 `src/agent/tools/file_write.py` 与 `src/agent/tools/file_edit.py`，含完整类型标注与中文 docstring。
2. 修改 `src/agent/tools/__init__.py`，完成注册。
3. 修改 `src/agent/core/engine.py`，追加参数级策略检查映射。
4. 修改 `src/agent/core/default_security_rules.yaml`，补充 write 敏感路径规则。
5. 修改 `src/agent/core/tool_router.py` 的使用指导文案。
6. 扩展 `tests/test_tools.py` 的 mock backend 与测试用例。
7. 更新 `docs/configuration.md`。
8. 跑 `pytest tests/test_tools.py -v` 与 `pytest tests/ -q`，修复失败。
9. 跑 `mypy src/` 与 `ruff check src/ tests/`，修复类型与风格问题。
10. 更新 `docs/progress-spec.md`、`docs/session-context.md`、`CODEMAP.md`（如项目要求）。

---

## 5. Acceptance Criteria（验收标准）

- `pytest tests/test_tools.py -v` 全部通过，新增 `file_write` / `file_edit` 测试不少于 8 个断言场景。
- `pytest tests/ -q` 不新增失败，保持当前基线（520 passed, 1 skipped 以上）。
- `mypy src/` 零新增错误。
- `ruff check src/ tests/` 零新增错误。
- `register_default_tools()` 注册的默认工具集合包含 `file_write`、`file_edit`。
- `tools.enabled` 配置可单独启用/禁用这两个工具。
- 危险路径的 `file_write` / `file_edit` 在启用安全策略时被拒绝。
- 文档与代码实现一致。

---

## 6. Risks & Mitigations（风险与缓解）

| 风险 | 可能性 | 影响 | 缓解措施 |
|---|---|---|---|
| 后端容器不持久，导致写完后读不到 | 中 | 高 | 验收时必须验证跨轮文件可见；如后端不满足，同步修复容器生命周期或增加 workspace 卷挂载。 |
| LLM 提供的 `old_string` 不唯一，导致编辑反复失败 | 高 | 中 | 错误信息明确告知出现次数，引导 LLM 提供更精确片段；未来可扩展 `expected_replacements` 参数。 |
| 写入敏感系统路径 | 低 | 高 | 通过 `file/path` write 策略拒绝；默认规则覆盖常见敏感路径。 |
| `content` 过大撑爆上下文 | 中 | 中 | 写入操作本身不返回大内容；如产物超长，仍由 Phase 7 上下文压缩机制外迁。 |

---

## 7. STOP-and-Wait Protocol（阶段门禁）

本文件为 **SDD-RIPER-ONE Plan 阶段产物**。根据规范：

> **No Spec, No Code；No Approval, No Execute。**

在收到用户明确的 `Plan Approved` 或等价许可之前，**禁止**执行以下动作：

- 不创建 `file_write.py`、`file_edit.py`。
- 不修改 `src/agent/tools/__init__.py`、`src/agent/core/engine.py`、安全规则、测试、文档。
- 不运行任何与本次改动相关的实现代码。

**下一步动作**：请用户审阅本 Spec，确认或修订范围后回复 `Plan Approved`，再进入 Execute 阶段。
