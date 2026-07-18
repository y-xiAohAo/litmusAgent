# Phase 4.6 配置驱动的 Tool 加载规格切片

> 来源：`docs/progress-spec.md` 第 4 节 Phase 4.6 + 项目上下文补全
> 状态：已批准，进入实现
> 批准人：用户（回复 "放行"）

---

## 目标

让 Agent 加载哪些 Tool 可以通过配置控制，而不是在代码中写死。用户可以根据场景决定启用哪些能力（例如只启用 `sandbox_exec` 和 `finish`，禁用文件操作）。

---

## 必须做

1. **扩展 `AgentConfig`**
   - 新增 `ToolsConfig` 配置类，包含 `enabled: list[str] | None = None`。
   - `enabled` 为 `None` 时启用所有默认工具；为列表时只启用列表中的工具。
   - 将 `tools: ToolsConfig` 加入 `AgentConfig`。

2. **实现配置驱动的工具注册函数**
   - 在 `src/agent/tools/__init__.py` 中新增 `register_tools_from_config(registry, backend, config)`。
   - 根据 `config.tools.enabled` 决定注册哪些工具。
   - 未知工具名应被忽略，并记录日志警告。

3. **修改 `Agent.__init__`**
   - 增加可选参数 `config: AgentConfig | None = None`。
   - 传入 `config` 时，根据配置注册工具。
   - 未传 `config` 时，保持向后兼容，调用 `register_default_tools()` 注册所有工具。

4. **测试覆盖**
   - 配置 `enabled=None` 时注册所有默认工具。
   - 配置 `enabled=["sandbox_exec", "finish"]` 时只注册这两个工具。
   - 配置包含未知工具名时，已知工具正常注册，未知工具被忽略。
   - 通过 YAML 加载配置并验证工具注册行为。

---

## 严禁做

1. 不修改四个 Tool 的实现（`sandbox_exec.py`、`file_read.py`、`file_list.py`、`finish.py`）。
2. 不修改 `Agent.run()` 主循环核心逻辑。
3. 不引入复杂插件系统或动态导入机制。
4. 不写依赖真实 Docker daemon 的测试。

---

## 验收标准

1. `python -m pytest tests/test_config.py -v` 新增测试全部通过。
2. `python -m pytest tests/ -q` 不新增失败，总通过数 > 171。
3. `python -m mypy src/` 零错误。
4. `python -m ruff check src/ tests/` 零新增错误。
5. 所有新增代码有完整类型标注和中文注释。

---

## 涉及文件

- **主要修改**：
  - `src/agent/config.py`
  - `src/agent/tools/__init__.py`
  - `src/agent/core/engine.py`
- **测试**：
  - `tests/test_config.py`
