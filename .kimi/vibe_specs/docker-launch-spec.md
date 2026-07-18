# Docker 一键启动规格说明 — Task 10.5「Docker 一键启动」

> **适用范围**：`scripts/`、`docker-compose.yml`、相关测试与文档。  
> **目标**：降低用户准备 Docker 运行环境的成本，提供一键检查/启动能力。  
> **版本**：v1.0（Phase 10.5）

---

## 1. 背景与目标

Hermes Agent 的核心能力（代码沙箱执行）依赖 Docker。新用户常遇到两类问题：

1. Docker daemon 没启动，运行 Agent 时工具调用报 `Docker client unavailable`。
2. 默认镜像 `python:3.11-slim` 未提前拉取，首次执行时等待时间长。

Phase 10.5 要提供**一键启动/检查脚本**，让用户在运行 Agent 前能快速确认环境就绪。

---

## 2. 范围

### 2.1 必须做（Must Have）

1. 创建 `scripts/setup-docker.py`：
   - 检查 Docker daemon 是否可达（ping）。
   - 检查默认镜像 `python:3.11-slim` 是否已存在。
   - 若不存在则尝试拉取。
   - 输出清晰的中文结果信息。
   - 返回退出码：`0` 就绪，`1` 未就绪。
2. 创建 `docker-compose.yml`：
   - 定义 `hermes` 服务，基于 `python:3.11-slim`。
   - 挂载项目源码、Docker socket、`.hermes` 工作目录。
   - 安装项目为 editable 模式。
   - 透传 `OPENAI_API_KEY` 环境变量。
3. 创建 `tests/test_docker_launch.py`：
   - 验证 `scripts/setup-docker.py` 可导入，关键函数存在。
   - 使用 Mock 测试 Docker 不可用、镜像已存在、镜像需拉取三种场景。
   - 验证 `docker-compose.yml` 是合法 YAML。
4. 中文注释与 docstring、完整类型标注、`mypy strict` 通过、`ruff` 通过。
5. 更新文档：
   - `docs/progress-spec.md`：Task 10.5 状态改为 ✅ 完成。
   - `CODEMAP.md`：`scripts/` 与 `docker-compose.yml` 说明更新。
   - `docs/session-context.md`：当前任务更新。
   - `docs/learning-journal.md`：新增 Phase 10.5 教学内容。
6. Commit：`feat: add Docker one-click startup scripts`。

### 2.2 严禁做（Must Not）

1. **不修改** `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager`。
2. **不引入** 新 Python 依赖（使用已有的 `docker` 包）。
3. **不替代** 现有 `agent` CLI；一键启动只为准备环境。
4. **不做** README 重写 / Demo 录制（后续 Task）。
5. **不要求** 测试环境必须有 Docker daemon（使用 Mock）。

### 2.3 可选做（Nice to Have）

1. 提供 `scripts/setup-docker.sh` / `setup-docker.ps1` 等 wrapper，方便不同平台直接双击运行。
2. 在 `setup-docker.py` 中增加 `--image` 参数覆盖默认镜像。

---

## 3. 模块结构

```
D:\djh\hermes\project1
├── docker-compose.yml           # Docker Compose 运行配置
├── scripts/
│   ├── setup.sh                 # 已有：venv 与依赖安装
│   ├── hermes-memory.py         # 已有：记忆 CLI 入口
│   └── setup-docker.py          # 新增：Docker 环境检查与镜像准备
└── tests/
    └── test_docker_launch.py    # 新增：Docker 启动脚本测试
```

### 3.1 `scripts/setup-docker.py` 接口设计

```python
def check_docker_available(client: DockerClient | None = None) -> bool:
    """检查 Docker daemon 是否可达。"""


def ensure_image(
    image: str,
    client: DockerClient | None = None,
) -> tuple[bool, str]:
    """确保指定镜像已存在；不存在则尝试拉取。

    返回：
        (是否成功, 状态信息)
    """


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：检查 Docker 并准备默认镜像。"""
```

### 3.2 `docker-compose.yml` 设计

```yaml
services:
  hermes:
    image: python:3.11-slim
    container_name: hermes-agent
    volumes:
      - .:/app
      - /var/run/docker.sock:/var/run/docker.sock
      - .hermes:/app/.hermes
    working_dir: /app
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
    command: ["tail", "-f", "/dev/null"]
```

> Windows 上 Docker socket 路径不同，注释中说明可根据环境调整。

---

## 4. 数据流

```
用户运行：python scripts/setup-docker.py
    ↓
创建 docker.from_env() 客户端
    ↓
client.ping() 检查 daemon 是否可达
    ↓
不可达 → 输出错误 → 退出码 1
    ↓
可达 → 检查本地是否存在 python:3.11-slim
    ↓
存在 → 输出 "镜像已就绪" → 退出码 0
    ↓
不存在 → client.images.pull(image)
    ↓
拉取成功 → 输出 "镜像拉取完成" → 退出码 0
    ↓
拉取失败 → 输出错误 → 退出码 1
```

---

## 5. 关键设计决策

1. **用 Python 脚本而非纯 Shell**：跨平台（Windows/Linux/Mac）更友好，且可复用项目已有的 `docker` 依赖。
2. **默认镜像与 Agent 配置一致**：`python:3.11-slim`，与 `AgentConfig` 默认值相同。
3. **测试使用 Mock Docker client**：不依赖真实 Docker daemon，CI 环境也能跑。
4. **docker-compose.yml 主要用于开发/演示**：不替代 `agent` CLI，用户仍可在宿主机直接运行 `agent run ...`。

---

## 6. 验收标准

| 检查项 | 通过标准 |
|--------|---------|
| 单元测试 | `pytest tests/test_docker_launch.py -v` 全部通过 |
| 全部测试 | `pytest tests/ -q` 保持 475 passed, 1 skipped 以上 |
| 类型检查 | `mypy src/` 无新增错误 |
| Lint | `ruff check src/ tests/` 全绿 |
| setup-docker.py | `python scripts/setup-docker.py` 在有 Docker 时返回 0，无 Docker 时返回 1 并提示 |
| docker-compose.yml | `python -c "import yaml; yaml.safe_load(open('docker-compose.yml', encoding='utf-8'))"` 不报错 |
| 文档同步 | `docs/progress-spec.md`、`CODEMAP.md`、`docs/session-context.md`、`docs/learning-journal.md` 已更新 |
| 核心 untouched | `Agent.run()`、`ToolRegistry`、`DockerSandboxBackend`、`MemoryManager` 无修改 |

---

## 7. 测试策略

采用 TDD：

1. 先写 `tests/test_docker_launch.py`，预期失败（脚本不存在）。
2. 实现 `scripts/setup-docker.py` 与 `docker-compose.yml`。
3. 跑测试，修复直至全绿。
4. 跑完整质量门禁。

测试要点：

- 用 `unittest.mock.MagicMock` 模拟 Docker client 的 `ping()`、`images.list()`、`images.pull()`。
- 覆盖 Docker 不可达、镜像已存在、镜像需拉取且成功、镜像拉取失败四种场景。
- 验证 `main()` 的退出码与输出信息。

---

## 8. 风险与回滚

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| Windows Docker socket 路径差异 | 中 | 中 | `docker-compose.yml` 注释说明；主要交付物是 `setup-docker.py`，不依赖 socket 挂载 |
| 测试环境缺少 docker-py | 低 | 低 | 项目已依赖 `docker>=7.0.0` |
| 真实 Docker 拉取慢导致测试超时 | 低 | 中 | 测试使用 Mock，不触发真实 pull |

**回滚策略**：若出现不可快速修复的问题，执行 `git checkout HEAD -- scripts/setup-docker.py docker-compose.yml tests/test_docker_launch.py` 回退改动。

---

## 9. 相关文件

- `scripts/setup-docker.py`（新建）
- `docker-compose.yml`（新建）
- `tests/test_docker_launch.py`（新建）
- `docs/progress-spec.md`、`CODEMAP.md`、`docs/session-context.md`、`docs/learning-journal.md`（修改）
- `src/agent/sandbox/docker_backend.py`（只读，参考默认镜像名）
- `src/agent/config.py`（只读，参考默认配置）

---

## 10. 文档更新清单

Task 10.5 完成后需同步：

- [ ] `docs/progress-spec.md`：Task 10.5 状态改为 ✅ 完成
- [ ] `CODEMAP.md`：scripts/ 目录增加 `setup-docker.py` 说明
- [ ] `docs/session-context.md`：当前任务更新
- [ ] `docs/learning-journal.md`：新增 Phase 10.5 教学内容
- [ ] `docs/session-context.md` 中过时的 "subprocess 沙箱后端" 描述同步修正

*注：`docs/session-context.md` 中 Phase 10.4 关键设计决策第 3 点仍写"配置文件示例使用 subprocess 沙箱后端"，与 Phase 10.4 最终实现不符，本次 Task 一并修正。*

---

*Generated: 2026-07-12 | Spec version: 1.0*


## 11. 待解决问题

### 11.1 Docker Hub 连接受限导致镜像拉取失败

**现象**：在部分用户环境（包括当前开发机）中，`docker pull python:3.11-slim` 失败，错误信息包含：

```text
Docker Desktop has no HTTPS proxy: connecting to registry-1.docker.io:443 ... failed to respond.
```

**原因**：Docker daemon 已运行，但无法连接到 Docker Hub 镜像仓库。可能是网络、防火墙、代理或 IPv6 配置问题。

**当前处理**：
- `scripts/setup-docker.py` 在拉取失败时返回退出码 1，并输出排查建议（检查网络、配置镜像加速器/HTTPS proxy、手动拉取、导入离线镜像）。
- 测试使用 Mock，不依赖真实 Docker Hub。

**后续需要解决**：
1. **是否让 Agent 自动处理镜像缺失**：当前 `DockerSandboxBackend.execute_code()` 不会自动拉取镜像，未来可考虑在 `ensure_image()` 或 `execute_code()` 中加入自动重试/拉取机制。
2. **是否支持镜像源配置**：允许用户通过环境变量或配置文件指定镜像加速器地址（如 `DOCKER_MIRROR`）。
3. **是否提供离线/预置镜像方案**：为企业/内网环境提供 `docker load` 一键导入脚本。
4. **subprocess 后端的替代方案**：`config.sandbox.backend` 的 `subprocess` 选项尚未落地，落地后可作为无 Docker Hub 访问场景的 fallback。

**记录位置**：本 spec、CODEMAP.md 已知问题、session-context.md 接力重点。
