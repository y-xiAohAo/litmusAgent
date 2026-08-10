# 归档：记忆系统存储升级（SQL 后端 + Redis 缓存）— LLM 视角

> 用途：后续会话维护/扩展存储层。只记约束、契约、触点与坑。

## 核心约束（未来任务必须遵守）

1. **新 store 实现必须过契约套件**：`tests/test_memory_store_contract.py` 是唯一行为基准——任何第三后端（Postgres 等）先过 11 用例参数化再谈接入。
2. **缓存是增强不是依赖**：任何缓存路径异常都必须静默降级为原路径；禁止让主流程依赖 Redis 可用性。
3. **默认配置不变**：`store_backend=jsonl` + `cache_enabled=false` 是基线；存量 786 测试是行为锁定。
4. **双文件依赖同步**：改 `pyproject.toml` 依赖必须同步 `requirements.txt`（TD-012 教训）。

## 触点

| 触点 | 位置 | 说明 |
|---|---|---|
| SQL store | `src/agent/core/memory_sql_store.py` | SQLAlchemy Core；entries 表 + (category,updated_at) 索引；upsert；JSON 列 |
| 契约套件 | `tests/test_memory_store_contract.py` | 参数化 jsonl/sql；`_age_entry` 双后端时间戳回填法 |
| 缓存层 | `memory.py` MemoryManager `inject/_cache_*` | generation 键：`hermes:mem:gen:{ns}`；注入键含 gen + sha1(input)；TTL 300s |
| 装配 | `runtime.py:81-118` | store 工厂 + cache ping 降级 |
| 分词共享 | `memory.py` 模块级 `_tokenize_text/_entry_text_of/_ensure_aware_dt` | 注意：类内还有两份历史重复实现（JSONL store 与 Manager 各一），勿新增第三份 |
| 验收环境 | `docker-compose.yml` profile `memory` | `docker compose --profile memory up -d` |

## 已验证事实

- SQLite/MySQL 双库契约一致（11 用例 × 2 后端）
- SQLAlchemy `DateTime(timezone=True)` 在 SQLite 回读为 naive——必须 `_ensure_aware_dt` 补时区
- mem-sql 臂端到端（b6 T103/T111）PASS；786 passed / mypy 48 / ruff 全绿
- 镜像拉取受限时走 `docker.m.daocloud.io`（TD-007 机制复用有效）

## Anti-patterns（不要这么做）

- ❌ 在 SQL 层做 text 重叠打分（职责切分与 JSONL 一致：SQL 过滤、Python 打分）
- ❌ 逐键缓存失效（generation 单点失效才是正确复杂度）
- ❌ 为凑技术栈上 MQ（吞吐无需求；评估过并明确放弃）
- ❌ 新增分词/拼文本的第三处实现（用模块级共享函数）

## 下一步钩子

- CI 容器化验收（GitHub Actions services: mysql/redis）
- 第三后端候选（Postgres）——先过契约套件
- Batch 7：T73 显著性 / LLM 提取质量审计 / 200+ 条压力

## Trace to Sources

- Spec：`mydocs/specs/2026-08-04_09-30_memory-sql-redis.md`
- 归档（human 叙事）：`mydocs/archive/2026-08-04_10-00_memory-sql-redis_human.md`
- 测试：`tests/test_memory_store_contract.py`、`tests/test_memory_cache.py`
