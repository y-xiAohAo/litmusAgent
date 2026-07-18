# 使用文档规格说明 — Task 10.8「使用文档」

> **适用范围**：`docs/usage.md`、`docs/configuration.md`、相关测试与文档。  
> **目标**：提供深入的 CLI 与配置使用文档，帮助用户从「能跑起来」到「能灵活运用」。  
> **版本**：v1.0（Phase 10.8）

---

## 1. 背景与目标

`README.md` 已经提供了 5 分钟快速开始，但很多场景需要更详细的说明：

1. CLI 有哪些全局参数和子命令？
2. YAML 配置文件每个字段的含义是什么？
3. 如何编写自定义 tool？
4. 如何切换 EchoClient 和 OpenAIClient？
5. 安全策略和长期记忆怎么配置？

Phase 10.8 要补充这些深度文档，降低用户从入门到熟练的门槛。

---

## 2. 范围

### 2.1 必须做（Must Have）

1. 创建 `docs/usage.md`：
   - CLI 完整参考：
     - `agent run` 子命令及参数（--config、--model、--api-key、--echo、--plain 等）
     - `agent chat` 子命令及参数
     - `agent config` 子命令
     - 全局参数：`--version`、`--plain`
   - Python API 使用：
     - 使用 `Agent` + `EchoClient`
     - 使用 `Agent` + `OpenAIClient`
     - 注册自定义 tool
     - 加载 YAML 配置
   - 常见场景示例
2. 创建 `docs/configuration.md`：
   - YAML 配置文件整体结构
   - `llm` 配置项详解
   - `agent` 配置项详解
   - `sandbox` 配置项详解
   - `tools` 配置项详解
   - `security` 配置项详解
   - `memory` 配置项详解
   - 完整配置示例
3. 创建 `tests/test_usage_docs.py`：
   - 验证 `docs/usage.md` 和 `docs/configuration.md` 存在。
   - 验证关键章节标题存在。
   - 验证 Python 代码块可被 `ast.parse()` 解析。
4. 中文为主，关键术语保留英文。
5. 更新文档：
   - `docs/progress-spec.md`：Task 10.8 状态改为 ✅ 完成。
   - `CODEMAP.md`：`docs/usage.md` 和 `docs/configuration.md` 说明更新。
   - `docs/session-context.md`：当前任务更新。
   - `docs/learning-journal.md`：新增 Phase 10.8 教学内容。
6. Commit：`docs: add usage and configuration guides`。

### 2.2 严禁做（Must Not）

1. **不修改** `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager`。
2. **不引入** 新依赖。
3. **不做** Demo 录制（10.9）。
4. **不改动** `README.md`、`docs/architecture.md`。

### 2.3 可选做（Nice to Have）

1. 增加 `docs/custom-tool.md` 专门讲解自定义 tool 开发。
2. 在 README 中增加指向 `docs/usage.md` 和 `docs/configuration.md` 的链接。

---

## 3. 文档结构草案

### 3.1 `docs/usage.md`

```markdown
# 使用指南

## CLI 使用

### agent run
### agent chat
### agent config
### 全局参数

## Python API 使用

### 使用 EchoClient
### 使用 OpenAIClient
### 加载 YAML 配置
### 注册自定义 tool

## 常见问题
```

### 3.2 `docs/configuration.md`

```markdown
# 配置说明

## 配置文件结构

## llm
## agent
## sandbox
## tools
## security
## memory

## 完整示例
```

---

## 4. 测试策略

1. 先写 `tests/test_usage_docs.py`，预期失败（文档文件不存在）。
2. 实现 `docs/usage.md` 与 `docs/configuration.md`。
3. 跑测试，修复直至全绿。
4. 跑完整质量门禁。

测试要点：

- 读取两个 Markdown 文件。
- 检查关键章节标题存在。
- 提取 Python 代码块并用 `ast.parse()` 检查语法。
- 不执行代码块。

---

## 5. 验收标准

| 检查项 | 通过标准 |
|--------|---------|
| 文件存在 | `docs/usage.md` 和 `docs/configuration.md` 存在且非空 |
| 关键章节 | usage.md 包含 CLI 使用、Python API 使用；configuration.md 包含各配置节说明 |
| 代码示例 | 所有 Python 代码块可被 `ast.parse()` 解析 |
| 单元测试 | `pytest tests/test_usage_docs.py -v` 全部通过 |
| 全部测试 | `pytest tests/ -q` 保持 496 passed, 1 skipped 以上 |
| 类型检查 | `mypy src/` 无新增错误 |
| Lint | `ruff check src/ tests/` 全绿 |
| 文档同步 | `docs/progress-spec.md`、`CODEMAP.md`、`docs/session-context.md`、`docs/learning-journal.md` 已更新 |
| 核心 untouched | `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager` 无修改 |

---

## 6. 风险与回滚

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| 文档内容后续与代码不同步 | 中 | 中 | 测试检查代码块语法；大改时同步更新 |
| 配置字段未来变更 | 中 | 中 | configuration.md 保持与 `AgentConfig` 一致 |

**回滚策略**：若出现不可快速修复的问题，执行 `git checkout HEAD -- docs/usage.md docs/configuration.md tests/test_usage_docs.py` 回退改动。

---

## 7. 相关文件

- `docs/usage.md`（新建）
- `docs/configuration.md`（新建）
- `tests/test_usage_docs.py`（新建）
- `docs/progress-spec.md`、`CODEMAP.md`、`docs/session-context.md`、`docs/learning-journal.md`（修改）
- `src/agent/cli/agent_cli.py`（只读，参考 CLI 参数）
- `src/agent/config.py`（只读，参考配置字段）

---

## 8. 文档更新清单

Task 10.8 完成后需同步：

- [ ] `docs/progress-spec.md`：Task 10.8 状态改为 ✅ 完成
- [ ] `CODEMAP.md`：新增 usage.md / configuration.md 说明
- [ ] `docs/session-context.md`：当前任务更新
- [ ] `docs/learning-journal.md`：新增 Phase 10.8 教学内容

---

*Generated: 2026-07-12 | Spec version: 1.0*
