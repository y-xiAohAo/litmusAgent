# Phase 4.2 Spec：file_read / file_list Tools

> 本规格切片基于 `docs/progress-spec.md` 第 4 节任务表与 `docs/plans/2026-04-28-code-sandbox-agent.md` 中 Phase 4.2 标题推导而来。

## 目标

实现 `file_read` 与 `file_list` 两个 Tools，让 Agent 能通过 Tool 调用查看沙箱内的文件内容（`file_read`）和目录列表（`file_list`）。

## 必须做（Must）

1. **新增 Tool 实现**
   - 文件：`src/agent/tools/file_read.py`
     - 实现 `file_read(path: str, backend: DockerSandboxBackend) -> ToolResult`。
     - 内部调用 `DockerSandboxBackend.get_file()` 读取文件内容。
     - 将读取到的 `bytes` 按 UTF-8 解码为字符串；文件不存在或读取失败时返回 `success=False`。
   - 文件：`src/agent/tools/file_list.py`
     - 实现 `file_list(path: str, backend: DockerSandboxBackend) -> ToolResult`。
     - 内部调用 `DockerSandboxBackend.execute_code()`，在沙箱内执行 `os.listdir(path)`。
     - 将结果列表用换行拼接为字符串返回；执行失败时返回 `success=False`。

2. **注册到默认工具集**
   - 文件：`src/agent/tools/__init__.py`
   - 在 `register_default_tools()` 中追加注册 `file_read` 和 `file_list`。
   - 两个 ToolSpec 的参数 schema 均只包含必填字段 `path: string`。

3. **测试**
   - 文件：`tests/test_tools.py`
   - 覆盖：
     - `file_read` 成功读取文件内容。
     - `file_read` 文件不存在时返回失败。
     - `file_list` 成功列出目录。
     - `file_list` 目录不存在或执行失败时返回失败。
     - `file_read` / `file_list` 的 ToolSpec schema 正确。
   - 所有测试使用 mock 后端，不依赖真实 Docker daemon。

## 严禁做（Must Not）

1. 不实现 `finish` Tool（留给 Phase 4.3）。
2. 不修改 Agent 主循环的核心逻辑（只扩展 tools 注册）。
3. 不写依赖真实 Docker daemon 的单元测试。

## 验收标准

- `python -m pytest tests/test_tools.py -v` 全部通过。
- `python -m pytest tests/ -q` 不新增失败。
- `python -m mypy src/` 零错误。
- `python -m ruff check src/ tests/` 零新增错误。
- 所有新函数有完整类型标注和中文 docstring。

## 涉及文件

- 新增：`src/agent/tools/file_read.py`
- 新增：`src/agent/tools/file_list.py`
- 修改：`src/agent/tools/__init__.py`
- 修改：`tests/test_tools.py`

## 依赖接口

```python
# src/agent/sandbox/docker_backend.py
class DockerSandboxBackend:
    async def get_file(self, container_path: str) -> bytes | None:
        """读取容器内文件，失败或不存在返回 None。"""

    async def execute_code(
        self,
        code: str,
        timeout: int | None = None,
    ) -> ExecutionResult:
        """在容器内执行 Python 代码。"""
```

`file_read` 依赖 `get_file()` 读取二进制内容；`file_list` 依赖 `execute_code()` 运行目录列表脚本。
