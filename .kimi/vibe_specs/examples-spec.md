# 示例场景脚本规格说明 — Task 10.4「示例场景脚本」

> **适用范围**：`examples/` 目录、`tests/test_examples.py`、相关文档。  
> **目标**：提供若干可运行的示例脚本，展示 Hermes Agent 的典型使用场景。  
> **版本**：v1.0（Phase 10.4）

---

## 1. 背景与目标

Phase 10.1~10.3 已经提供完整的 CLI（`agent run`、`agent chat`、`agent config`）。Phase 10.4 需要在 `examples/` 目录下补充可运行脚本，让新用户无需阅读源码即可理解：

- 如何用 `Agent` 类编写一个最小 Agent。
- 如何进行一次性的任务运行。
- 如何结合 YAML 配置使用 Agent。

当前项目尚未接入真实 LLM API key，因此所有示例必须能在无 API key 环境下直接运行，采用 `EchoClient` 或 CLI `--echo` 模式；同时在注释中说明如何切换到真实 LLM。

---

## 2. 范围

### 2.1 必须做（Must Have）

1. 新建/更新 `examples/` 下的示例脚本（2-3 个）。
2. 每个示例脚本使用 `agent` CLI 或 `Agent` 类。
3. 所有示例脚本在无 API key 环境下可直接运行。
4. 中文注释与 docstring、完整类型标注、`mypy strict` 通过、`ruff` 通过。
5. 新增 `tests/test_examples.py`，验证：
   - 示例脚本可导入。
   - 示例脚本的入口函数/代码路径可运行。
   - 示例配置文件（如有）可被 `load_config()` 正确解析。
6. 更新文档：
   - `docs/progress-spec.md`：Task 10.4 状态改为 ✅ 完成。
   - `CODEMAP.md`：`examples/` 目录说明更新。
   - `docs/session-context.md`：当前任务更新。
   - `docs/learning-journal.md`：新增 Phase 10.4 教学内容。
7. Commit：`feat: add example scenario scripts`。

### 2.2 严禁做（Must Not）

1. **不修改** `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager`。
2. **不引入** 新依赖。
3. **不做** 交互模式增强、Docker 一键启动、README 重写（后续 Task）。
4. **不要求** 示例必须调用真实 LLM（避免示例因缺 API key 而无法运行）。

### 2.3 可选做（Nice to Have）

1. 在示例注释中提供切换到真实 LLM 的说明。
2. 提供一个最小 YAML 配置文件示例。

---

## 3. 示例脚本设计

### 3.1 `examples/simple_agent.py`

**目标**：展示 `Agent` 类的最小使用方式 + 自定义 tool。

**内容**：
- 使用 `EchoClient` 作为 LLM 客户端。
- 注册一个 `greet` tool。
- 调用 `agent.run()` 并打印回复。

**运行方式**：
```bash
python examples/simple_agent.py
```

### 3.2 `examples/run_once.py`

**目标**：展示如何模拟一次性任务运行（对应 CLI `agent run`）。

**内容**：
- 构造 `Agent` + `EchoClient`。
- 给 Agent 一个提示，打印回复。
- 注释中附带 CLI 用法：
  ```bash
  # 无 API key 时测试
  agent run "帮我写一个排序算法" --echo
  # 有 API key 后
  agent run "帮我写一个排序算法" --config examples/config.yaml
  ```

**运行方式**：
```bash
python examples/run_once.py
```

### 3.3 `examples/with_config.py` + `examples/config.yaml`

**目标**：展示如何结合 YAML 配置使用 Agent。

**内容**：
- `examples/config.yaml`：最小配置，包含 `llm`、`agent`、`sandbox` 示例字段。
- `examples/with_config.py`：
  - 使用 `load_config()` 加载 YAML。
  - 使用 `EchoClient` 运行，避免缺 API key 失败。
  - 注释说明：去掉 `EchoClient` 两行，即可使用配置中的真实 LLM。

**运行方式**：
```bash
python examples/with_config.py
```

---

## 4. 测试策略

采用 TDD：

1. 先写 `tests/test_examples.py`，预期失败（示例文件尚未创建或路径不存在）。
2. 实现示例脚本与配置文件。
3. 跑测试，修复直至全绿。
4. 跑完整质量门禁。

测试要点：

- 使用 `importlib.import_module()` 验证脚本可导入。
- 调用示例脚本的入口函数（如 `main()`）验证可运行。
- 验证 `examples/config.yaml` 可被 `load_config()` 解析，且字段正确。
- 不测试真实 LLM 输出（使用 EchoClient）。

---

## 5. 验收标准

| 检查项 | 通过标准 |
|--------|---------|
| 单元测试 | `pytest tests/test_examples.py -v` 全部通过 |
| 全部测试 | `pytest tests/ -q` 保持 468 passed, 1 skipped 以上 |
| 类型检查 | `mypy src/` 无新增错误 |
| Lint | `ruff check src/ tests/` 全绿 |
| 示例可运行 | `python examples/simple_agent.py`、`python examples/run_once.py`、`python examples/with_config.py` 均正常输出 |
| 文档同步 | `docs/progress-spec.md`、`CODEMAP.md`、`docs/session-context.md`、`docs/learning-journal.md` 已更新 |
| 核心 untouched | `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager` 无修改 |

---

## 6. 风险与回滚

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| 示例脚本依赖未导出的内部 API | 低 | 中 | 测试覆盖导入与运行，及时发现 |
| EchoClient 行为变更导致示例输出变化 | 低 | 低 | 测试只验证可运行，不严格断言输出内容 |
| 配置文件字段变更导致示例失效 | 低 | 中 | 测试验证 `load_config()` 能解析示例 YAML |

**回滚策略**：若出现不可快速修复的问题，执行 `git checkout HEAD -- examples/ tests/test_examples.py` 回退改动。

---

## 7. 相关文件

- `examples/simple_agent.py`（修改/增强）
- `examples/run_once.py`（新建）
- `examples/with_config.py`（新建）
- `examples/config.yaml`（新建）
- `tests/test_examples.py`（新建）
