# Feature Spec — TD-015：持久工作区（Coding Agent 形态）

> **层级**：Feature Spec
> **创建**：2026-08-22 | **v2 修订**：2026-08-22（按用户裁决简化：平铺两字段、CLI 收口关闭、litmus-ws- 前缀、bind 模式 Docker 不可用时报错不降级）
> **技术债登记**：`.kimi/vibe_specs/technical-debt-spec.md` TD-015
> **当前 phase**：Plan（等待 `Plan Approved`）
> **用户决策汇总**：① B+C 整体设计、分单元执行；② bind 强制 git 快照（非 git 目录拒绝启动）；③ 人工确认"询问但可免"；④ 跨平台尽力；⑤ 配置平铺两字段（砍 mode 枚举）；⑥ 接受 CLI 层在宿主执行 git 快照；⑦ 新卷前缀 `litmus-ws-`；⑧ bind 模式 Docker 不可用即报错，不降级 subprocess

---

## 1. 设计的大白话表述（对照现状）

**现状**：每次 `agent run`，Agent 拿到一个全新的空抽屉（随机命名的 Docker volume），用完没人扔（孤儿卷泄漏 bug）。宿主机上看不到抽屉里的任何东西。

**设计 = 三种抽屉，由两个平铺配置字段决定**：

| 配置 | 效果 | 宿主可见 | 风险 |
|---|---|---|---|
| 都不填（默认，现状） | 一次性抽屉，用完**正确**扔掉（修复泄漏） | ❌ | 无变化 |
| `volume_name: my-proj` | 贴了名字的抽屉 `litmus-ws-my-proj`，下次会话还在（单元 B） | ❌ | 无变化 |
| `host_dir: D:\myproject` | 直接操作宿主机真实项目目录（单元 C） | ✅ | 高 → 四道保险（§5） |

两字段互斥：同时填则配置校验报错。

## 2. 现状关键事实（已核实）

- 后端参数已支持固定卷名与保留：`DockerSandboxBackend(workspace_volume=..., cleanup_workspace=...)`（`docker_backend.py:53-78`）；`SandboxConfig` 无对应字段，工厂不透传（`sandbox/__init__.py:33-56`）。
- **孤儿卷泄漏**：CLI 从不调用 `sandbox_backend.close()`；`Agent.close()` 只清缓存与记忆（`engine.py:517-526`）。
- 容器加固：`network_mode="none"`、`user="nobody"`、`read_only=True`、tmpfs、volume 挂 `/workspace`（`docker_backend.py:170-192`）；创建后 chown 65534（:202-216）。
- 写边界三件套（`default_security_rules.yaml:166-191`）；read 无边界（只 deny 敏感路径）；`security.enabled` 默认 False。
- TD-008 人工确认钩子已就绪（registry 回调 + CLI y/n/a）。
- `SubprocessSandboxBackend(workspace_root=...)` 已支持外部目录。

## 3. 单元 B 详细设计（~1 天）

### 3.1 配置（平铺，贴 SandboxConfig 现有风格）

`SandboxConfig` 新增两个字段：

```python
class SandboxConfig(BaseModel):
    backend: str = "docker"
    image: str = "python:3.11-slim"
    image_registry: str | None = None
    timeout: int = 30
    memory_limit_mb: int = 256
    volume_name: str | None = None   # 持久卷名 → 实际卷 litmus-ws-<volume_name>
    host_dir: str | None = None      # 单元 C 使用；单元 B 阶段填了报"尚未支持"
```

校验（model validator）：
- `volume_name` 匹配 `^[a-zA-Z0-9_.-]+$`。
- `volume_name` 与 `host_dir` 互斥。
- `host_dir` 在单元 B 落地前报错"bind 模式随单元 C 交付"（防止半吊子可用）。

### 3.2 工厂与后端接线

- `create_sandbox_backend(config)`：
  - docker：传 `workspace_volume=f"litmus-ws-{volume_name}"`、`cleanup_workspace=(volume_name is None)`。即：默认模式 = 随机卷 + 关闭时清理（现状语义）；持久模式 = 固定卷 + 保留。
  - subprocess：`volume_name` → 报错"subprocess 后端不支持命名卷，请直接使用单元 C 的 host_dir"（砍掉 v1 臆造的 `~/.hermes/workspaces/` 约定）。
- docker volume create 幂等，跨会话复用天然成立。

### 3.3 生命周期收口（修孤儿卷，砍掉"所有权"概念）

范式：**谁创建谁关闭**。CLI 创建 Agent 与 backend，就由 CLI 关。

- `src/agent/cli/agent_cli.py`（run/chat 路径）与 `cli/chat.py`：`finally` 块调用 `agent.close()`。
- `Agent.close()`（`engine.py`）：追加关闭沙箱 backend 的调用，条件：`self._sandbox_backend` 是工厂自建的（判断方式：构造时未注入 `sandbox_backend` 参数的，记一个私有布尔标记——这是最小实现，不引入公开"所有权"概念）。backend.close() 本身已幂等、异常静默。
- Web UI（`web/app.py`）：session 为进程内常驻——首版在**进程退出钩子**（FastAPI shutdown event）里统一 close 所有 session 的 backend；session 级 TTL 回收列为 Non-Goal，文档注明限制。
- 存量孤儿卷：不自动清理；文档给出手动命令 `docker volume ls -f name=hermes-workspace` / `docker volume rm`。
- 持久卷删除路径：文档命令 `docker volume rm litmus-ws-<name>`（不做 CLI 子命令，控制范围）。

### 3.4 单元 B 验收

- `volume_name` 配置后，两个独立 Agent 会话（先后两个 backend 实例）看到同一批文件。
- 默认配置下 CLI run 结束后卷被删除（mock backend 断言 close 被调用）。
- 双字段互斥、非法名、subprocess+volume_name 三类配置报错均有测试。
- 默认配置零行为变化；全量门禁绿。

## 4. 单元 C 详细设计（2-3 天）：`host_dir` + 四道保险

### 4.1 挂载与用户模型

- `DockerSandboxBackend` 新增 `workspace_bind: str` 参数：`volumes={host_dir: {"bind": "/workspace", "mode": "rw"}}`（替代命名卷）。
- 用户模型双模：bind 模式容器以**宿主 uid:gid** 运行（POSIX: `os.getuid()/os.getgid()`）；跳过 chown 65534（不篡改宿主文件属主）。Windows Docker Desktop 经文件共享层自动映射属主，维持 nobody——首版实测并文档化。
- 加固维持：network=none、read_only + tmpfs、无特权、不挂 docker.sock。
- **Docker 不可用 → 启动报错，不降级**（用户裁决：降级到 subprocess 等于在宿主机弱隔离裸跑，更危险）。subprocess 后端用 `host_dir` 需用户显式指定 `backend: subprocess`，视为用户自担风险的显式选择，文档警示。

### 4.2 保险一：git 强制快照（宿主侧，CLI 装配层执行）

新模块 `src/agent/cli/workspace_guard.py`（放 cli 层而非 sandbox 层——它操作宿主机，不属于沙箱抽象）：

```python
def ensure_git_workspace(host_dir: str) -> None:
    """host_dir 存在、是目录、是 git 仓库、git 可执行；否则 raise ValueError(引导 git init)。"""

def snapshot_workspace(host_dir: str) -> str | None:
    """dirty 工作区自动 commit（信息 'litmus: pre-agent snapshot'，作者署名 (litmus-agent)）；
    clean 则跳过。返回快照 sha 或 None。"""
```

CLI 入口在 `host_dir` 模式启动时依次调用。回滚文档化：`git reset --hard <sha>` / `git diff`。

**已定细节（2026-08-22 澄清轮）**：

- 快照提交在**当前分支**（Aider 模式），回滚即 `git reset --hard <sha>`。
- 宿主 git 未配 `user.name`/`user.email` → 快照 commit 用 env 级 `GIT_AUTHOR_NAME="litmus-agent"` 等兜底（**不改用户 git 配置**）。【用户裁决】
- **subprocess 后端 + `host_dir` 同样强制** git 校验 + 快照（风险一致，保险一致）。【用户裁决】
- 并发：两个 Agent 同挂一个 `host_dir` 不加锁，文档明示禁止（做锁属过度设计）。

### 4.3 保险二：写操作人工确认（询问但可免）

- `HumanApprovalConfig.enabled` 改为 `bool | None = None`（None = 未显式配置——解决"默认值与显式 false 不可区分"问题）。
- 装配规则：`host_dir` 模式且 `enabled is None` → 按 True 生效（tools 默认 `["file_write", "file_edit"]`）；用户显式配置优先，显式关闭时 warning 日志提示风险。
- CLI y/n/**a**（本会话免确认）语义沿用。

**入口差异（2026-08-22 澄清轮，均为用户裁决）**：

- **Web UI**：无确认界面。web 入口检测到 `host_dir` 且审批未显式关闭 → **拒绝启动**并报错引导（显式 `human_approval.enabled: false` 才放行，风险自担）。
- **一次性 `agent run` 非交互场景（无 TTY / 管道）**：审批回调检测无 TTY 时**默认拒写**，拒绝原因回传 LLM（可改走其他路径）；交互 TTY 下正常 y/n/a。

### 4.4 保险三：敏感文件 read deny

- bind 模式装配时经 `_apply_workspace_override` 同款机制追加 read deny 规则（优先级 90）：
  `**/.env*`、`**/.ssh/**`、`**/*.{pem,key}`、`**/id_rsa*`、`**/.git/**`。
- read 不加 catch-all（项目文件需可读）；write 边界三件套语义不变（容器内只允许 `/workspace`）。
- `host_dir` 模式且 `security.enabled` 未显式配置 → 按 True 生效；显式关闭打 warning。

### 4.5 保险四：启动横幅

CLI 启动时打印：挂载路径、快照 sha（若有）、写确认状态、回滚命令提示。

### 4.5b 已定实现细节（澄清轮）

- bind 模式容器设 `HOME=/tmp`（tmpfs 可写；宿主 uid 在容器内无 passwd 条目，避免 HOME 指向只读层）。
- 容器加固维持：read_only rootfs + tmpfs + network=none + 无特权。

### 4.6 单元 C 验收

- 临时 git 仓库 bind 挂载：Agent 写文件 → 宿主实时可见、git status 可见改动、属主正确（POSIX）。
- 非 git 目录 → 明确报错拒绝启动；dirty 仓库 → 自动快照且横幅显示 sha；git 身份未配置 → 快照以 litmus-agent 署名兜底成功且不改用户配置。
- `.env` 读取被策略拒绝且原因回传 LLM。
- 写操作触发确认，`a` 后会话内免确认；显式 `human_approval.enabled: false` 时尊重配置并打 warning。
- Web + `host_dir` + 审批未显式关 → 拒绝启动并报错引导；非交互（无 TTY）run → 写操作默认拒绝且原因回传 LLM。
- subprocess + `host_dir` → git 校验与快照同样强制。
- Docker 不可用 + `host_dir` → 明确报错。
- 全量门禁绿 + 真实 Docker 手工验证记录（任一平台）。

## 5. In Scope / Out of Scope

**In**：§3 单元 B 全部；§4 单元 C 全部（Docker 后端为主，subprocess 显式 opt-in）。

**Out**：`/undo` `/diff` 会话内 git 命令；userns-remap；网络白名单（TD-010）；Web UI session TTL 回收与 bind 专属交互；named 卷 CLI 管理子命令；Windows bind 深度适配（尽力 + 文档化）。

## 6. File Changes

**单元 B**：`config.py`（+2 字段与校验）、`sandbox/__init__.py`（工厂接线）、`core/engine.py`（close 追加沙箱关闭 + 私有标记）、`cli/agent_cli.py` / `cli/chat.py` / `web/app.py`（收口）、`tests/test_workspace_config.py`（新）、`tests/test_engine.py` / `test_cli.py`（增补）、`docs/configuration.md`。

**单元 C**：`sandbox/docker_backend.py`（workspace_bind + uid 双模 + 跳过 chown）、`cli/workspace_guard.py`（新）、装配层（runtime.py/引擎构造路径：默认开 security 与 human_approval、注入 read deny）、`cli` 横幅、`tests/test_bind_workspace.py` + `tests/test_workspace_guard.py`（新）、`docs/configuration.md` / `docs/usage.md`。

## 7. 风险表

| 风险 | 等级 | 缓解 |
|---|---|---|
| bind 模式 LLM 误写宿主文件 | 🔴 | git 快照回滚 + 写确认默认开 + 挂载点边界 + 敏感文件 read deny |
| 容器 uid 与宿主属主错配 | 🟠 | POSIX 传宿主 uid；Windows 实测文档化 |
| 快照 commit 混入用户 git 流 | 🟠 | 只对 dirty 快照、署名可审计、文档给回滚命令 |
| 孤儿卷泄漏（现有 bug） | 🟠 | 单元 B close 链路收口 |
| 用户显式关安全件 | 🟡 | warning 日志 + 文档危险面警示 |
| Windows 路径转换 | 🟡 | POSIX 优先，Windows 限制文档化 |

## 8. Done Contract

- 单元 B：§3.4 全部 + 全量门禁绿（基线 807）。
- 单元 C：§4.6 全部 + 全量门禁绿 + 真实 Docker 手工验证记录。

## 9. Open Questions

- 无阻塞项。read deny 含 `.git/**` 已按"LLM 无需读 git 内部对象"定案（如需放开后续加配置）。

## Resume / Handoff

- **单元 B**：✅ 已完成（2026-08-22）。改动：`config.py`（`volume_name`/`host_dir` 平铺字段 + 校验）、`sandbox/__init__.py`（工厂接线 `litmus-ws-<name>` + cleanup 语义）、`engine.py`（`_owns_sandbox_backend` 私有标记 + close 收口自建 backend）、`agent_cli.py`/`chat.py` finally 收口、`web/app.py` shutdown 统一 close、`tests/test_workspace_config.py`（13 用例）、`docs/configuration.md`。
- **Validation（实测复核）**：`pytest tests/ -q` = 820 passed, 1 skipped（+13）；mypy 50 文件零错误；ruff 全绿。
- **同行 CR（2026-08-22，独立评审 agent）**：结论 SHIP；🟠×2（cmd_run 缺配置错误兜底、falsy 注入 backend 陷阱）+ close 三段无隔离脆弱点 + 测试缺口（web shutdown/chat 路径/异常路径零覆盖）。
- **CR 回炉（同日完成）**：两条 🟠 已修（cmd_run 补 try/except、`_build_agent` ValueError 友好化；`is not None` 显式判断）；`Agent.close()` 三段 try/except 隔离；过时注释修正；新增 10 个测试（falsy 注入、CLI 友好错误×3、close 隔离×2、web shutdown×2、异常/chat 路径 close×2），`test_workspace_config.py` 现 23 例。回炉后基线 **830 passed, 1 skipped**，mypy/ruff 全绿。
- **偏差**：close 链路测试放 `test_workspace_config.py`（Spec 提到的 `test_engine.py` 不存在）；跨实例卷复用由工厂参数断言替代真实 Docker 集成验证；web 用 FastAPI 旧式 shutdown 钩子（与现有版本兼容）。
- **单元 C**：✅ 代码完成（2026-08-22）。改动：`config.py`（host_dir 放开 + `is_bind_mode()`/`resolve_*()` 装配推导 + `HumanApprovalConfig.enabled` 三态 None 哨兵 + `SecurityConfig.bind_read_deny` 与 `_apply_bind_read_deny()`）、`docker_backend.py`（`workspace_bind` + `_host_bind_user()` uid 双模 + 跳过 chown + `HOME=/tmp`）、`sandbox/__init__.py`（工厂接线 + Docker 不可用报错不降级）、`cli/workspace_guard.py`（新建：git 校验 + dirty 快照 + litmus-agent env 署名兜底）、`agent_cli.py`（`_prepare_bind_workspace` + 非 TTY 默认拒写回调 + 横幅）、`web/app.py`（`AGENT_CONFIG` + bind 拒绝启动转 400）。
- **Validation（实测复核）**：`pytest tests/ -q` = 863 passed, 1 skipped（新增 34 例：guard 8 + bind 26，真实 git 路径用 tmp_path+git CLI 实测）；mypy 51 文件零错误；ruff 全绿。
- **偏差**：① `SecurityConfig.enabled` 保持 bool 未改三态，显式性用 pydantic `model_fields_set` 判断（语义等价）；② web 原本不读 YAML，新增 `AGENT_CONFIG` 环境变量；③ 快照执行 `git add -A` 含未跟踪文件（保证可审计）；④ read deny 实际落地为正则形式 `^\.env|`(^|/)\.env` 等 5 条。
- **真实 Docker 手工验证（2026-08-22 完成，Windows 11 + Docker Desktop 29.7.2 + WSL2 2.7.12）**：临时 git 仓库 + bind 模式实测 10/10 通过——非 git 目录拒绝启动；dirty 自动快照（sha 可见、署名 `litmus-agent`、快照后 clean）；容器内写 `/workspace` → 宿主目录实时可见且 git status 可见改动；`.env` 读取被策略拒绝（"禁止读取 .env 等环境密钥文件"）；命名卷 `litmus-ws-td015-verify` 跨 backend 实例文件可见（对照组）。验证后卷已清理。**TD-015 完全闭环。**
- **环境备注**：本机 Docker Desktop 装在用户目录（`AppData\Local\Programs\DockerDesktop`），不在 PATH；Windows 下 bind 挂载属主经 Docker Desktop 文件共享层自动映射，无需 uid 传递（与设计预期一致）。
- **下一步**：无。TD-015 关闭。
