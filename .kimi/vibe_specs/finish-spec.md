# Phase 4.3 Spec：finish Tool

> 本规格切片基于 `docs/progress-spec.md` 第 4 节任务表与 `docs/plans/2026-04-28-code-sandbox-agent.md` 中 Phase 4.3 标题推导而来。

## 目标

实现 `finish` Tool，让 Agent 能显式标记任务完成并交付最终产物，同时终止 Agent 主循环。

## 必须做（Must）

1. **新增 Tool 实现**
   - 文件：`src/agent/tools/finish.py`
   - 实现 `finish(result: str) -> ToolResult`。
   - 返回 `ToolResult(success=True, content=result)`，把 LLM 提供的最终结果透传给 Agent 主循环。

2. **注册到默认工具集**
   - 文件：`src/agent/tools/__init__.py`
   - 在 `register_default_tools()` 中追加注册 `finish`。
   - ToolSpec 的参数 schema 只包含必填字段 `result: string`。

3. **主循环识别 `finish` 并终止**
   - 文件：`src/agent/core/engine.py`
   - 修改 `Agent.run()`：当某一轮工具调用中出现名为 `finish` 的工具时，立即返回 `finish` 的 `result.content`，不再继续循环。
   - 如果存在 Planner 且当前步骤未完成，调用 `finish` 前将其标记为完成。

4. **测试**
   - 文件：`tests/test_tools.py`
   - 覆盖：
     - `finish` Tool 返回正确的 `content` 和 `success=True`。
     - `finish` 的 ToolSpec schema 正确。
     - Agent 收到 `finish` tool_call 后立即返回结果，不再继续循环。
   - 所有测试使用 mock，不依赖真实 Docker daemon。

## 严禁做（Must Not）

1. 不实现 Phase 4.4/4.5/4.6 的内容（端到端集成、错误恢复场景、配置驱动加载）。
2. 不改变其他 Tool 的现有行为。
3. 不写依赖真实 Docker daemon 的单元测试。

## 验收标准

- `python -m pytest tests/test_tools.py -v` 全部通过。
- `python -m pytest tests/ -q` 不新增失败。
- `python -m mypy src/` 零错误。
- `python -m ruff check src/ tests/` 零新增错误。
- 所有新函数有完整类型标注和中文 docstring。

## 涉及文件

- 新增：`src/agent/tools/finish.py`
- 修改：`src/agent/tools/__init__.py`
- 修改：`src/agent/core/engine.py`
- 修改：`tests/test_tools.py`
