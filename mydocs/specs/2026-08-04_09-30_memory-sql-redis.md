# SDD Spec: 记忆系统存储升级（SQL 后端 + Redis 检索缓存）

- **Spec 层级**: Feature Spec
- **创建时间**: 2026-08-04 09:30
- **当前 Phase**: EXECUTE（验收阶段）
- **Approval Status**: `APPROVED — 2026-08-04 用户批准 Plan`
- **关联**: 用户指示（补齐传统后端能力证据：MySQL/Redis）；b6 压力测试（检索性能基线）

## 0. Open Questions

- [ ] None（MySQL/Redis 双容器经 Docker Desktop 在本机已可用；CI 容器化验证为可选项，见 §4.3 Step 7）

## 1. Requirements (Context)

- **Goal**: 为记忆系统提供生产级存储与缓存能力——SQL 后端（SQLite 测试 / MySQL 验证）替代 JSONL 文件扫描，Redis 缓存注入热路径——形成传统后端能力的真实工程证据。
- **In-Scope**:
  1. `SqlMemoryStore`（SQLAlchemy Core）：实现 `MemoryStore` 全部接口，SQLite/MySQL 双数据库兼容。
  2. **行为一致性测试套件**：同一组 store 契约测试对 JSONL 与 SQL 两个后端参数化复跑。
  3. Redis 检索缓存：`inject()` 结果缓存，generation 版本号失效（写入/清理自动失效）。
  4. 存储后端工厂接线（config 选择 jsonl/sql）+ 缓存开关。
  5. 真实验证：Docker MySQL + Redis 容器集成运行 + b6 子集（T103/T111）SQL 后端复验。
- **Out-of-Scope**:
  - MQ/分布式任务队列（动机不成立，已与用户确认放弃）。
  - 向量数据库/embedding 检索。
  - 既有 JSONL 后端的任何行为变更（保持默认，纯新增）。
  - 生产级部署编排（K8s 等）。

### 用户已决项（2026-08-04）

- 方向确认：「看看 redis 和 mysql 怎么做」→ SQL 后端 + Redis 缓存都做；MQ 明确放弃。

## 1.1 Context Sources

- Requirement Source: 用户职业定位（LLM/Agent 校招）需补齐传统后端证据；面试叙事需"从真实需求长出来"
- Code Refs: `src/agent/core/memory.py:126-142`（MemoryStore 抽象接口五方法）、`:94-109`（MemoryQuery 结构）、`:164-184`（JSONL 实现 save）、`:252`（cleanup）、`src/agent/core/runtime.py:81-93`（装配点）
- 依赖调研: venv 当前无 sqlalchemy/redis/pymysql/fakeredis（全 MISSING，需新增依赖）
- Docker: daemon 可用（29.6.1），TD-007 镜像源机制已有

## 1.7 Minimum Chaos Unit Assessment

- Final Goal: `store_backend: sql` 时记忆系统全功能运行于 SQLite/MySQL；Redis 缓存开启后 inject 命中提速且写后失效正确
- Current Task Unit: 1 个 SQL store + 1 个缓存层 + 契约测试套件 + 容器化验收
- Why small enough: 接口已定（五方法），纯新增实现与可选层，默认配置不变
- Verification Evidence: 契约测试双后端全绿；fakeredis 单测；Docker MySQL/Redis 集成验收；b6 子集 SQL 复验通过
- Failure / Rework Plan: SQL 方言差异（SQLite/MySQL）→ 收敛到 SQLAlchemy Core 表达式；缓存失效错误 → generation 单点失效逻辑简化
- User Decision: 待批准

## 2. Research Findings

### 2.1 接口与实现面

- `MemoryStore` 抽象五方法：`save` / `query(MemoryQuery)` / `delete` / `cleanup(max_age)` / `list_entries`；`MemoryQuery` 支持 categories/tags/text/top_k/time_range——text 重叠打分目前在 Python 侧（`_rank_entries`），SQL 后端只需返回候选集，排序逻辑复用不动。
- 装配点在 `runtime.py:81-93`：当前硬编码 `StructuredMemoryStore`——改为按 `memory.store_backend` 选择的工厂。
- 序列化：`MemoryEntry` ↔ dict 已有（`_entry_to_dict`/`_entry_from_dict`），SQL 层直接用 JSON 列存 content/tags。

### 2.2 技术选型（依赖决策）

| 选项 | 结论 |
|---|---|
| **SQLAlchemy Core**（新增 1 依赖） | **选用**：一套代码双数据库（SQLite 测试 / MySQL 验证），方言问题由它吸收；业界标准，简历叙事最强 |
| sqlite3 裸写 | 排除：MySQL 故事弱，方言手写痛苦 |
| pymysql 裸写 | 排除：测试依赖 MySQL 容器，不密闭 |

- Redis 选 **redis-py**（运行时依赖）+ **fakeredis**（dev 依赖，密闭单测）。
- **TD-012 教训**：`requirements.txt` 与 `pyproject.toml` 同步更新（本次新增 sqlalchemy / redis / fakeredis(dev)）。

### 2.3 缓存设计（Redis）

- **缓存对象**：`inject(user_input)` 的最终注入文本（检索+组装的结果）。
- **键设计**：`hermes:mem:inj:{root_hash}:{sha1(user_input)}`；**generation 版本号**：`hermes:mem:gen:{root_hash}` 写入/清理时 INCR——键内含 gen，天然全量失效，无逐键失效复杂度。
- **TTL**：300s 兜底防陈旧。
- **失败降级**：Redis 不可达 → 直接走原路径（缓存是增强，永非依赖）。
- 缓存 `search()` 结果暂不做（工具路径调用频次低，inject 是每轮必走的热路径）。

### 2.4 风险

- SQLAlchemy 新依赖体积（轻量 Core，无 ORM 开销）。
- Docker MySQL 首次拉镜像（TD-007 镜像源机制可复用）。
- 双后端行为差异（排序/时间精度）——契约测试套件兜底。

## 3. Innovate (Optional: Options & Decision)

### Fork 1: SQL 实现路线
- A. **SQLAlchemy Core 双库** → 选 A（§2.2 调研结论）
- B/C. 裸写 sqlite3 / pymysql → 否

### Fork 2: 缓存粒度
- A. **inject 结果缓存 + generation 失效** → 选 A：热路径、失效逻辑最简
- B. 检索结果缓存（search/L1）：调用频次低，缓存收益小 → 否（本批不做）

### Fork 3: 测试策略
- A. **契约套件参数化（jsonl/sql）+ fakeredis + Docker 真实容器验收** → 选 A：一致性证据最硬
- B. 仅 fakeredis + SQLite：MySQL 验证缺失 → 否（故事不完整）

## 4. Plan (Contract)

### 4.1 File Changes

- `pyproject.toml` + `requirements.txt`（修改，**双文件同步**）：`sqlalchemy>=2.0`、`redis>=5.0`；dev 增加 `fakeredis>=2.20`
- `src/agent/config.py`（修改）：`MemoryConfig` 增加 `store_backend: str = "jsonl"`、`sql_url: str | None = None`、`cache_enabled: bool = False`、`redis_url: str = "redis://localhost:6379/0"`
- `src/agent/core/memory_sql_store.py`（**新增**）：`SqlMemoryStore(MemoryStore)`
- `src/agent/core/memory.py`（修改）：`MemoryManager` 增加可选 `cache`（inject 缓存 + generation 失效 + TTL + 降级）
- `src/agent/core/runtime.py`（修改）：store 工厂（jsonl/sql）+ cache 装配
- `tests/test_memory_store_contract.py`（**新增**）：参数化契约套件（jsonl + sql-sqlite）
- `tests/test_memory_cache.py`（**新增**）：fakeredis 缓存单测（命中/失效/降级）
- `docker-compose.yml`（修改）：mysql + redis 服务（验收环境）
- `docs/configuration.md`（修改）：新配置项
- `.kimi/vibe_specs/technical-debt-spec.md` / `docs/evaluation-log.md` / `docs/session-context.md`（同步）

### 4.2 Signatures

```python
# src/agent/core/memory_sql_store.py
class SqlMemoryStore(MemoryStore):
    """SQLAlchemy Core 实现的记忆存储（SQLite 测试 / MySQL 验证）。

    表结构 entries：entry_id PK、category、uri、summary、tags(JSON)、
    content(JSON)、source_run_id、stale、created_at、updated_at；
    索引 (category, updated_at)。text 检索复用 Python 侧重叠打分
    （SQL 层只负责候选集过滤，与 JSONL 后端职责一致）。
    """

    def __init__(self, url: str) -> None: ...
    def save(self, entry: MemoryEntry) -> MemoryEntry: ...
    def query(self, query: MemoryQuery) -> list[MemoryEntry]: ...
    def delete(self, entry_id: str) -> bool: ...
    def cleanup(self, max_age: timedelta | None = None) -> int: ...
    def list_entries(self, category: MemoryCategory | None = None) -> list[MemoryEntry]: ...
```

```python
# src/agent/core/memory.py（MemoryManager 注入缓存，构造新增可选参数）
cache: Any | None = None  # redis 风格客户端（get/setex/incr），duck-typed

def inject(self, user_input: str) -> str:
    """命中缓存直接返回；未命中走原路径并写入缓存（含 generation 键）。
    Redis 不可达时静默降级为原路径。"""

def _bump_cache_generation(self) -> None:
    """record()/cleanup() 后调用：INCR generation，旧缓存键天然失效。"""
```

### 4.3 Implementation Checklist

- [ ] 1. 依赖安装（venv）+ 双文件同步（pyproject/requirements）
- [ ] 2. `memory_sql_store.py`：SQLAlchemy Core 建表 + 五方法实现
- [ ] 3. `test_memory_store_contract.py`：契约套件参数化（jsonl + sql-sqlite）——save/query(text/tags/category/top_k/time_range)/delete/cleanup/list 全方法行为一致
- [ ] 4. Redis 缓存层 + `test_memory_cache.py`（fakeredis：命中/写后失效/cleanup 失效/不可达降级/TTL）
- [ ] 5. runtime 工厂 + config 装配 → 门禁三件套全绿（默认 jsonl 行为不变）
- [ ] 6. Docker MySQL + Redis 容器集成验收：SQL store 在真实 MySQL 跑契约关键路径；Redis 真实容器缓存命中
- [ ] 7. b6 子集复验（T103/T111 × mem-default × 1 采样，SQL 后端）：记忆检索在 SQL 后端功能正确
- [ ] 8. 文档三件套 + 总表 + 回写本 Spec §5/§6/§7

### 4.4 Spec Review Notes

- 未执行 `review_spec`；如需预审请指示。

### 4.5 Route Alignment (Water Flow Check)

- Original assumption: 需要为后端能力新建一套存储
- Current route: 抽象接口早已存在（TD-005/TD-009 的遗产），纯新增实现 + 可选缓存层
- Scope impact: 默认配置行为不变（jsonl + 无缓存）

## 5. Execute Log

- [x] Step 1: 依赖安装（sqlalchemy/redis/fakeredis/pymysql/cryptography）+ pyproject/requirements **双文件同步**（TD-012 教训）
- [x] Step 2: `memory_sql_store.py`（SQLAlchemy Core：entries 表 + (category,updated_at) 索引 + upsert + JSON 列）；模块级共享分词/拼文本函数提取（`memory.py` 两处类内重复逻辑保持不动，新代码用共享函数）
- [x] Step 3: `test_memory_store_contract.py` 契约套件（11 用例 × 2 后端 = 22 全绿）：save/get/query（category/tags/text/top-k/time_range）/delete/cleanup/list_recent 行为一致
- [x] Step 4: Redis 缓存层（generation 失效 + TTL 300s + 静默降级）+ `test_memory_cache.py`（fakeredis 4 用例：命中/写后失效/清理失效/不可达降级）
- [x] Step 5: runtime 工厂（jsonl/sql）+ cache 装配（不可达降级）+ config 四字段 → **786 passed / mypy 48 / ruff 全绿**
- [x] Step 6: Docker MySQL 8.0 + Redis 7 容器（compose `memory` profile，经镜像源拉取）；真实容器集成验收：MySQL save/get/query/delete 全通、Redis 缓存命中与 generation 失效全通
- [x] Step 7: b6 子集 SQL 后端复验（T103/T111 × mem-sql）**双 PASS**——全 Agent 链路在 SQL 后端端到端正确
- [x] Step 8: 文档三件套 + 总表同步；本 Spec §6/§7 回写

## 6. Review Verdict

- Review Matrix (Mandatory):
| Axis | Key Checks | Verdict | Evidence |
|---|---|---|---|
| Spec Quality & Requirement Completion | SQL 后端全接口实现 + 双后端行为一致（契约套件）+ Redis 缓存 generation 失效/降级 + 默认行为不变 | PASS | 契约 22 项全绿；缓存 4 用例；Docker 验收 |
| Spec-Code Fidelity | 文件/签名/checklist 与 Plan 一致（pymysql/cryptography 依赖补录见 §7） | PASS | checklist 8/8；786 passed / mypy 48 / ruff 全绿 |
| Code Intrinsic Quality | 缓存静默降级有测试；契约套件参数化是本项目最强一致性证据；真实容器验收非 mock | PASS | §5 Step 3/4/6 |
- Overall Verdict: **PASS**
- Blocking Issues: 无
- Regression risk: Low（默认 jsonl + 无缓存，存量 786 测试锁定）
- Follow-ups:
  1. 简历"存储与缓存工程"bullet 并入（R3 流程，文案已在讨论中定稿）
  2. Batch 7 候选：T73 显著性 / LLM 提取质量审计 / 200+ 条压力
  3. CI 容器化验收（GitHub Actions services: mysql/redis）——可选加固

## 7. Plan-Execution Diff

- 依赖补录：`pymysql` + `cryptography`（MySQL 驱动及其认证依赖，Plan 4.1 未列——双文件同步已执行）
- mem-sql 臂为 Plan 外新增（b6 复验所需的最小通道），`seed_memory` 相应支持双后端预置
- **跟进（2026-08-04 接口审查后）**：`list_recent` 由鸭子类型提升为 `MemoryStore` ABC 抽象方法（接口审查发现它此前靠 `hasattr` 约定），`_recency_fallback` 同步移除 hasattr 分支直接调用；契约套件本已覆盖该方法，行为不变（786 全绿）
- 其余无偏差。

## 8. Archive Record

- Archive Mode: `snapshot`
- Audience: `both`
- Source Targets:
  - `mydocs/specs/2026-08-04_09-30_memory-sql-redis.md`
  - `docs/evaluation-log.md`（2026-08-04 存储升级验收行）
- Archive Outputs:
  - `mydocs/archive/2026-08-04_10-00_memory-sql-redis_human.md`
  - `mydocs/archive/2026-08-04_10-00_memory-sql-redis_llm.md`
- Key Distilled Knowledge: 契约套件参数化 = 可插拔的最强证据；generation 单点失效 > 逐键失效；SQL 过滤/Python 打分的职责切分与 JSONL 一致；克制（不上 MQ）也是证据。

## 9. Project Sync Candidates

- 候选：「SQL 后端 + Redis 缓存的接入模式（工厂 + duck-typed 缓存 + generation 失效）」→ 收口归档
- Sync decision: Not synced
