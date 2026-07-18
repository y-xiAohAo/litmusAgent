# README 重写规格说明 — Task 10.6「README 重写」

> **适用范围**：`README.md`、相关测试与文档。  
> **目标**：让新用户能快速理解项目价值、安装方式与基本用法。  
> **版本**：v1.0（Phase 10.6）

---

## 1. 背景与目标

当前 `README.md` 是项目早期模板，存在以下问题：

1. 代码示例错误：
   - `from agent.core import Agent` 路径不正确。
   - `agent.run(...)` 是异步函数，缺少 `asyncio.run()`。
2. 未体现项目核心差异点：代码沙箱执行、自我纠错、Docker 依赖。
3. 缺少 CLI 使用说明。
4. 安装步骤未区分普通用户与开发者。

Phase 10.6 要重写 `README.md`，使其成为用户的第一份可靠指南。

---

## 2. 范围

### 2.1 必须做（Must Have）

1. 重写 `README.md`，包含以下章节：
   - 项目简介（一句话价值 + 核心能力）
   - 核心特性（代码沙箱、自我纠错、CLI、配置驱动等）
   - 前置条件（Python >= 3.10、Docker Desktop/Engine、可选 OpenAI API key）
   - 安装步骤（pip install -e ".[dev]"）
   - 快速开始
     - CLI 方式：`agent run "..." --echo`
     - 代码方式：使用 `Agent` + `EchoClient`
   - Docker 一键启动：`python scripts/setup-docker.py`、`docker compose up -d`
   - 项目结构
   - 开发命令（make test / make lint / make check）
   - 许可证
2. 修正现有 README 中的错误代码示例。
3. 新增 `tests/test_readme.py`：
   - 验证 `README.md` 存在。
   - 验证关键章节标题存在。
   - 验证 README 中的 Python 代码片段可解析（不执行，仅语法检查）。
4. 中文为主，关键术语保留英文。
5. 更新文档：
   - `docs/progress-spec.md`：Task 10.6 状态改为 ✅ 完成。
   - `CODEMAP.md`：README 说明更新（如有）。
   - `docs/session-context.md`：当前任务更新。
   - `docs/learning-journal.md`：新增 Phase 10.6 教学内容。
6. Commit：`docs: rewrite README.md`。

### 2.2 严禁做（Must Not）

1. **不修改** `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager`。
2. **不引入** 新依赖。
3. **不做** 架构图（10.7）/ 使用文档（10.8）/ Demo 录制（10.9）。
4. **不改动** `Makefile` 或 CI 配置。

### 2.3 可选做（Nice to Have）

1. 在 README 中添加徽章（badges）：CI status、Python version、License。
2. 添加 CONTRIBUTING 简要说明。

---

## 3. README 结构草案

```markdown
# Hermes Agent

> 具备自我纠错能力的代码沙箱 Agent：让 LLM 写代码、在隔离沙箱中执行、观察结果、修正并交付产物。

## 核心特性

- **代码沙箱执行**：通过 `sandbox_exec` tool 在 Docker 容器中安全运行 LLM 生成的代码。
- **自我纠错循环**：Agent 观察工具执行结果，自动修复代码错误。
- **交互式 CLI**：支持 `agent run` 单次运行与 `agent chat` 多轮对话。
- **配置驱动**：通过 YAML 配置文件管理模型、沙箱、安全策略。
- **长期记忆**：跨任务保留环境状态、用户偏好与失败模式（默认关闭）。
- **安全策略引擎**：可配置地拦截高危代码、文件操作与记忆读写。

## 前置条件

- Python >= 3.10（推荐 3.11）
- Docker Desktop 或 Docker Engine（用于代码沙箱）
- OpenAI API key（可选，示例使用 `--echo` 模式无需 key）

## 安装

```bash
git clone <repo-url>
cd hermes-agent
pip install -e ".[dev]"
```

## 快速开始

### CLI 方式

```bash
# 无需 API key，使用 EchoClient 测试
agent run "帮我写一个快速排序算法" --echo

# 使用真实 LLM（需设置 OPENAI_API_KEY）
agent run "帮我写一个快速排序算法"

# 交互模式
agent chat --echo
```

### Python 代码方式

```python
import asyncio
from agent import Agent
from agent.llm import EchoClient

async def main():
    agent = Agent(llm_client=EchoClient())
    response = await agent.run("帮我写一个快速排序算法")
    print(response)

asyncio.run(main())
```

## Docker 一键启动

```bash
# 检查 Docker 环境并拉取默认镜像
python scripts/setup-docker.py

# 在容器内运行（自动安装项目依赖）
docker compose up -d
docker compose exec hermes agent run "帮我写一个快速排序算法" --echo
```

## 项目结构

...

## 开发

```bash
make test   # 运行测试
make lint   # 代码检查
make check  # 类型检查
```

## 许可证

MIT
```

---

## 4. 测试策略

1. 先写 `tests/test_readme.py`，预期失败（README 结构不满足）。
2. 重写 `README.md`。
3. 跑测试，修复直至全绿。
4. 跑完整质量门禁。

测试要点：

- 使用 `pathlib` 读取 `README.md`。
- 使用 `re` 检查关键标题是否存在。
- 使用 `ast.parse()` 验证 README 中 Python 代码片段语法正确。
- 不执行代码片段（避免调用真实 API 或 Docker）。

---

## 5. 验收标准

| 检查项 | 通过标准 |
|--------|---------|
| README 存在 | `README.md` 存在且非空 |
| 关键章节 | 包含「核心特性」「安装」「快速开始」「项目结构」「开发」「许可证」 |
| 代码示例正确 | README 中 Python 代码片段可被 `ast.parse()` 解析 |
| 单元测试 | `pytest tests/test_readme.py -v` 全部通过 |
| 全部测试 | `pytest tests/ -q` 保持 483 passed, 1 skipped 以上 |
| 类型检查 | `mypy src/` 无新增错误 |
| Lint | `ruff check src/ tests/` 全绿 |
| 文档同步 | `docs/progress-spec.md`、`CODEMAP.md`、`docs/session-context.md`、`docs/learning-journal.md` 已更新 |
| 核心 untouched | `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager` 无修改 |

---

## 6. 风险与回滚

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| README 中代码示例后续过期 | 中 | 中 | `tests/test_readme.py` 语法检查；后续 Task 持续维护 |
| 章节标题被修改导致测试失败 | 低 | 低 | 测试使用稳健的正则匹配 |

**回滚策略**：若出现不可快速修复的问题，执行 `git checkout HEAD -- README.md tests/test_readme.py` 回退改动。

---

## 7. 相关文件

- `README.md`（修改）
- `tests/test_readme.py`（新建）
- `docs/progress-spec.md`、`CODEMAP.md`、`docs/session-context.md`、`docs/learning-journal.md`（修改）

---

## 8. 文档更新清单

Task 10.6 完成后需同步：

- [ ] `docs/progress-spec.md`：Task 10.6 状态改为 ✅ 完成
- [ ] `CODEMAP.md`：README 说明更新
- [ ] `docs/session-context.md`：当前任务更新
- [ ] `docs/learning-journal.md`：新增 Phase 10.6 教学内容

---

*Generated: 2026-07-12 | Spec version: 1.0*
