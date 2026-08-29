# 归档：记忆系统存储升级（SQL 后端 + Redis 缓存）— Human 视角

- **日期**：2026-08-04
- **Feature Spec**：`mydocs/specs/2026-08-04_09-30_memory-sql-redis.md`
- **Commit**：`77bfd56`

## 背景与目标

为记忆系统提供生产级存储与缓存能力，补齐传统后端工程证据（MySQL/Redis）。关键叙事约束：必须从真实需求长出来——b6 压力测试（100 条目）已经把"JSONL 文件全扫"的扩展性问题摆在了台面上。

## 方案与决策

- **SQL 后端**：`SqlMemoryStore`（SQLAlchemy Core，SQLite 测试 / MySQL 部署），实现既有 `MemoryStore` 抽象五方法。选型排除裸写 sqlite3/pymysql（方言痛苦、测试不密闭）。
- **一致性证据**：契约测试套件 11 用例 × 2 后端参数化复跑（save/get/query/delete/cleanup/list_recent 全方法）——这是本次最强的工程质量证据，使"可插拔"不止于声称。
- **Redis 缓存**：每轮 `inject()` 结果按 generation 键缓存（写入/清理 INCR generation，旧键天然失效）+ TTL 300s + 不可达静默降级。明确不做 MQ（吞吐无需求，克制是证据）。
- **装配**：runtime 工厂（jsonl 默认 / sql 可选）+ 四配置项；docker-compose `memory` profile（mysql:8.0 + redis:7-alpine）。

## 结果与证据

- 契约套件 22 项全绿；真实 MySQL/Redis 容器集成验收通过（非 mock）
- b6 子集 mem-sql 臂端到端双 PASS（全 Agent 链路在 SQL 后端正确）
- 门禁：786 passed / mypy 48 / ruff 全绿；依赖 sqlalchemy/redis/pymysql/cryptography 双文件同步

## 面试叙事口径

- 为什么升级：记忆条目上千后 JSONL 全扫 O(N) 读文件是瓶颈；抽象接口让替换平滑
- 为什么双库：SQLite 密闭测试，MySQL 生产部署，契约套件保证行为一致
- 为什么不做 MQ/向量库：100 条压力数据显示字面检索已满足——测量驱动引入基础设施

## Trace to Sources

- Spec 全程：`mydocs/specs/2026-08-04_09-30_memory-sql-redis.md`（§5/§6/§7）
- 验收记录：`docs/evaluation-log.md` 2026-08-04 存储升级验收行
- 契约套件：`tests/test_memory_store_contract.py`
- 压力基线：`docs/batch-e2e-batch6-report.md`
