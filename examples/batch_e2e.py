"""批量 E2E 评测 Runner（Batch E2E Benchmark）。

用途：
  对 BATCH_TASKS 批量执行真实 LLM 评测，按机制臂（full / no-reflect）形成
  对照，聚合成功率、轮数、token 成本与失败分类，输出 Markdown 报告。
  （full 臂 = 反思开启；两臂 planner 均关闭，与 evaluation-log A/B v3 口径一致。）

运行方式：
  # 冒烟（零成本，不调用 LLM / Docker，仅验证任务集与报告链路）
  python examples/batch_e2e.py --echo

  # 全批真实运行（20 任务 × 2 臂，串行）
  python examples/batch_e2e.py

  # 子集试点
  python examples/batch_e2e.py --only T01,T11 --arms full

安全约定：
  - API Key 仅从环境变量读取，不落盘、不打印。
  - 原始结果逐行写入 mydocs/reports/batch1_raw.jsonl（崩溃可续查）。
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent import Agent
from agent.config import AgentConfig
from agent.core.reflective_advisor import ReflectiveAdvisor
from agent.llm import OpenAIClient

try:
    from batch_tasks import BATCH_TASKS, BatchTask
except ImportError:  # 测试以 importlib 动态加载时，脚本目录不在 sys.path
    sys.path.insert(0, str(Path(__file__).parent))
    from batch_tasks import BATCH_TASKS, BatchTask

ARMS: tuple[str, ...] = ("full", "no-planner", "no-reflect")
MEMORY_ARMS: tuple[str, ...] = ("mem", "no-mem")
STRESS_ARMS: tuple[str, ...] = ("mem-default", "mem-semantic")
ALL_ARMS: tuple[str, ...] = ARMS + MEMORY_ARMS + STRESS_ARMS + ("mem-qe", "mem-sql")
SET_ARMS: dict[str, tuple[str, ...]] = {"b5": MEMORY_ARMS, "b6": STRESS_ARMS}
TASK_SETS: dict[str, tuple[str, str]] = {
    "b1": ("batch_tasks", "BATCH_TASKS"),
    "b2": ("batch_tasks_b2", "BATCH2_TASKS"),
    "b3": ("batch_tasks_b3", "BATCH3_TASKS"),
    "b4": ("batch_tasks_b4", "BATCH4_TASKS"),
    "b5": ("batch_tasks_b5", "BATCH5_TASKS"),
    "b6": ("batch_tasks_b6", "BATCH6_TASKS"),
}
DEFAULT_TASK_SET = "b6"
REPORTS_DIR = Path("mydocs/reports")
JUDGE_PASS_SCORE = 4


def _ensure_utf8_stdout() -> None:
    """Windows 终端强制 UTF-8 输出（GBK 无法编码 ✅/❌ 等字符）。"""
    try:
        if isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout.reconfigure(encoding="utf-8")
        if isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

JUDGE_TEMPLATE = """你是严格、简明的评审。请根据评分标准对产物打分。

【任务要求】
{task_prompt}

【产物内容】
{artifact}

【评分标准】
{rubric}

先给出不超过 3 句的点评，然后最后一行输出：SCORE: <1-5 的整数>"""


@dataclass
class BatchRunResult:
    """单次 task×arm 运行结果。

    Attributes:
        task_id: 任务编号。
        arm: 机制臂（full / no-reflect）。
        success: 是否通过判分。
        judge: 判分方式（assert / llm-judge / echo / error）。
        turns: Agent 实际轮数。
        tokens: 本次运行累计 token（prompt + completion）。
        duration_s: 运行耗时（秒）。
        failure_class: 失败分类（空串表示无失败）。
        detail: 判分细节或错误摘要（截断）。
    """

    task_id: str
    arm: str
    success: bool
    judge: str
    turns: int
    tokens: int
    duration_s: float
    failure_class: str
    detail: str
    tools: str = ""  # 实际被调用的工具名序列（逗号分隔）
    sample: int = 1  # 第几次采样（重复采样用于区分稳定失败与模型抖动）


def extract_tool_names(agent: Agent) -> list[str]:
    """从 Agent trace 提取被调用的工具名序列（tool_execution 事件）。"""
    names: list[str] = []
    for step in agent.get_trace().steps:
        for event in step.events:
            if event.event_type == "tool_execution":
                payload = event.payload or {}
                names.append(str(payload.get("tool", "unknown")))
    return names


def parse_judge_score(text: str) -> int | None:
    """从 judge 回复中解析 1-5 的整数分数，解析失败返回 None。"""
    match = re.search(r"SCORE:\s*([1-5])", text)
    return int(match.group(1)) if match else None


def classify_failure(
    *,
    judge: str,
    verify_stdout: str = "",
    verify_stderr: str = "",
    turns: int = 0,
    max_turns: int = 12,
    error: str = "",
) -> str:
    """对失败样本做确定性分类（超时 / 环境 / 语法 / 工具偏好 / 逻辑）。

    规则优先级：异常错误 → 轮数耗尽 → 判分输出信号 → 默认逻辑。
    """
    haystack = f"{error}\n{verify_stdout}\n{verify_stderr}".lower()
    if error:
        if "timeout" in haystack or "timed out" in haystack:
            return "超时"
        return "环境"
    if turns >= max_turns:
        return "超时"
    if "未知工具" in haystack or "unknown tool" in haystack:
        return "工具偏好"
    if "syntaxerror" in haystack or "indentationerror" in haystack:
        return "语法"
    return "逻辑"


def build_agent(
    task: BatchTask,
    arm: str,
    client: OpenAIClient,
    memory_root: str | None = None,
) -> Agent:
    """按机制臂构造 Agent。

    臂定义（对照设计，两两指向 full）：
      full:       planner 开 + 反思开（默认 advisor）；
      no-planner: planner 关 + 反思开（隔离 planner 贡献）；
      no-reflect: planner 开 + 反思关（高阈值 advisor 确定性关闭，隔离反思贡献）；
      mem:        planner 开 + 反思开 + 记忆开（memory_root 注入，跨会话召回测量）；
      no-mem:     planner 开 + 反思开 + 记忆关（记忆对照臂）。
    """
    config = AgentConfig()
    config.agent.max_turns = task.max_turns
    advisor = None
    if arm in ("full", "no-reflect", "mem", "no-mem"):
        config.agent.planner.enabled = True
    if arm == "no-reflect":
        advisor = ReflectiveAdvisor(
            reflection_threshold=10**9,
            escalate_threshold=10**9,
        )
    if arm == "mem":
        config.agent.memory.enabled = True
        # TD-013：mem 臂同时开启 LLM 对话事实提取（additive，产物类任务不受影响）。
        config.agent.memory.llm_extraction_enabled = True
        if memory_root is not None:
            config.agent.memory.memory_root = memory_root
    if arm in ("mem-default", "mem-semantic"):
        # Batch 6 压力臂：只测检索层（不开 LLM 提取，避免 phase B 自提取噪声）。
        config.agent.memory.enabled = True
        config.agent.memory.semantic_retrieval = arm == "mem-semantic"
        if memory_root is not None:
            config.agent.memory.memory_root = memory_root
    if arm == "mem-qe":
        # 查询扩展验收臂：记忆开 + QE 开（同样不开 LLM 提取）。
        config.agent.memory.enabled = True
        config.agent.memory.query_expansion_enabled = True
        if memory_root is not None:
            config.agent.memory.memory_root = memory_root
    if arm == "mem-sql":
        # SQL 后端验收臂：记忆开 + SQL 存储（SQLite 文件随 memory_root）。
        config.agent.memory.enabled = True
        config.agent.memory.store_backend = "sql"
        if memory_root is not None:
            config.agent.memory.sql_url = f"sqlite:///{memory_root}/memory.db"
    return Agent(
        llm_client=client,
        config=config,
        max_turns=task.max_turns,
        reflective_advisor=advisor,
    )


def seed_memory(root: Path, task: BatchTask, backend: str = "jsonl") -> None:
    """程序化预置记忆库（Batch 6 压力测试，零 API 成本）。

    写入目标事实（seed_facts）+ 相似干扰（seed_decoys）+ 确定性背景噪声
    （noise_count 条 svc-i/param-i）。目标条目按 target_age_days 回填时间
    （深埋控制：store.save 会刷新 updated_at，需事后改写时间戳）；
    噪声条目年龄分布在最近一天内，保证全部比目标新（recency 把目标顶出
    L0 注入窗口，检索必须靠 L1/L2/搜索）。

    backend="sql" 时经 SqlMemoryStore 预置（b6 SQL 后端验收路径）。
    """
    from agent.core.memory import MemoryCategory, MemoryEntry, MemoryStore
    from agent.core.memory import StructuredMemoryStore

    store: MemoryStore
    if backend == "sql":
        from agent.core.memory_sql_store import ENTRIES_TABLE, SqlMemoryStore

        sql_store = SqlMemoryStore(f"sqlite:///{root / 'memory.db'}")
        store = sql_store
    else:
        sql_store = None
        store = StructuredMemoryStore(root)

    def _age_file(entry: MemoryEntry, days: float) -> None:
        ts = datetime.now(timezone.utc) - timedelta(days=days)
        if sql_store is not None:
            import sqlalchemy as sa

            with sql_store._engine.begin() as conn:
                conn.execute(
                    sa.update(ENTRIES_TABLE)
                    .where(ENTRIES_TABLE.c.entry_id == entry.entry_id)
                    .values(updated_at=ts, created_at=ts)
                )
        else:
            file_path = root / entry.category.value / f"{entry.entry_id}.jsonl"
            data = json.loads(file_path.read_text(encoding="utf-8"))
            data["created_at"] = ts.isoformat()
            data["updated_at"] = ts.isoformat()
            file_path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")

    for i, fact in enumerate(task.seed_facts):
        entry = MemoryEntry(
            entry_id=f"seed-target-{i}",
            category=MemoryCategory.PREFERENCES,
            content={"fact": fact},
            summary=fact,
            tags=["seed", "target"],
        )
        store.save(entry)
        _age_file(entry, task.target_age_days)
    for i, fact in enumerate(task.seed_decoys):
        entry = MemoryEntry(
            entry_id=f"seed-decoy-{i}",
            category=MemoryCategory.PREFERENCES,
            content={"fact": fact},
            summary=fact,
            tags=["seed", "decoy"],
        )
        store.save(entry)
        _age_file(entry, 0.5)
    for i in range(task.noise_count):
        fact = f"服务 svc-{i:03d} 的参数 param-{i:03d} = {(i * 7) % 100}"
        entry = MemoryEntry(
            entry_id=f"seed-noise-{i:03d}",
            category=MemoryCategory.PREFERENCES,
            content={"fact": fact},
            summary=fact,
            tags=["seed", "noise"],
        )
        store.save(entry)
        _age_file(entry, i / max(task.noise_count, 1))


async def judge_artifact(
    task: BatchTask,
    client: OpenAIClient,
    artifact: str,
) -> tuple[bool, str]:
    """LLM-judge：按 rubric 对产物打分，≥JUDGE_PASS_SCORE 为通过。"""
    prompt = JUDGE_TEMPLATE.format(
        task_prompt=task.prompt,
        artifact=artifact[:8000] if artifact else "（产物缺失：文件未生成）",
        rubric=task.judge_rubric or "",
    )
    response = await client.chat(
        [{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    text = response["content"]
    score = parse_judge_score(text)
    return (score is not None and score >= JUDGE_PASS_SCORE), text


async def run_one(
    task: BatchTask,
    arm: str,
    echo: bool = False,
    sample: int = 1,
) -> BatchRunResult:
    """执行单次 task×arm 运行并判分。echo 模式返回合成结果（零成本冒烟）。"""
    start = time.monotonic()
    if echo:
        return BatchRunResult(task.id, arm, True, "echo", 0, 0, 0.0, "", "", sample=sample)

    client = OpenAIClient.from_env()
    judge = "error"
    detail = ""
    turns = 0
    failure_class = ""
    success = False
    tools_used: list[str] = []
    try:
        if task.prompt_b:
            # 两阶段执行（跨会话记忆测量）：phase A 教学 → 新 Agent phase B 查询。
            # phase B 无对话历史，记忆是唯一信息通道（仿 e2e_suite S6 模式）。
            judge = "answer-assert"
            memory_root = tempfile.mkdtemp(prefix="batch-mem-")
            answer = ""
            try:
                for prompt in (task.prompt, task.prompt_b):
                    agent = build_agent(task, arm, client, memory_root=memory_root)
                    try:
                        answer = await agent.run(prompt) or ""
                        turns += len(agent.get_trace().steps)
                        tools_used.extend(extract_tool_names(agent))
                    finally:
                        agent._sandbox_backend.close()
            finally:
                shutil.rmtree(memory_root, ignore_errors=True)
            answer_flat = answer.replace(" ", "").replace("　", "")
            missing_facts = [
                f for f in task.expected_in_answer
                if f.replace(" ", "") not in answer_flat
            ]
            missing_tools = [t for t in task.expected_tools if t not in tools_used]
            success = not missing_facts and not missing_tools
            detail = answer.strip()[:200]
            if missing_facts:
                detail += f" | 答案缺少事实: {','.join(missing_facts)}"
                failure_class = "逻辑"
            elif missing_tools:
                detail += f" | 缺少工具: {','.join(missing_tools)}"
                failure_class = "工具偏好"
        else:
            memory_root: Path | None = None
            if task.noise_count or task.seed_facts or task.seed_decoys:
                memory_root = Path(tempfile.mkdtemp(prefix="batch-seed-"))
                seed_memory(
                    memory_root,
                    task,
                    backend="sql" if arm == "mem-sql" else "jsonl",
                )
            try:
                agent = build_agent(
                    task,
                    arm,
                    client,
                    memory_root=str(memory_root) if memory_root else None,
                )
                try:
                    answer = await agent.run(task.prompt)
                    turns = len(agent.get_trace().steps)
                    tools_used = extract_tool_names(agent)
                    if task.verify_script is not None:
                        judge = "assert"
                        result = await agent._sandbox_backend.execute_code(task.verify_script)
                        artifact_ok = result.exit_code == 0
                        missing = [t for t in task.expected_tools if t not in tools_used]
                        success = artifact_ok and not missing
                        detail = (result.stdout + result.stderr).strip()[:220]
                        if missing:
                            detail += f" | 缺少工具: {','.join(missing)}"
                        if not success:
                            if missing:
                                failure_class = "工具偏好"
                            else:
                                failure_class = classify_failure(
                                    judge=judge,
                                    verify_stdout=result.stdout,
                                    verify_stderr=result.stderr,
                                    turns=turns,
                                    max_turns=task.max_turns,
                                )
                    elif task.expected_in_answer:
                        judge = "answer-assert"
                        answer = answer or ""
                        answer_flat = answer.replace(" ", "").replace("　", "")
                        missing_facts = [
                            f for f in task.expected_in_answer
                            if f.replace(" ", "") not in answer_flat
                        ]
                        missing_tools = [t for t in task.expected_tools if t not in tools_used]
                        success = not missing_facts and not missing_tools
                        detail = answer.strip()[:200]
                        if missing_facts:
                            detail += f" | 答案缺少事实: {','.join(missing_facts)}"
                            failure_class = "逻辑"
                        elif missing_tools:
                            detail += f" | 缺少工具: {','.join(missing_tools)}"
                            failure_class = "工具偏好"
                    else:
                        judge = "llm-judge"
                        artifact = ""
                        if task.artifact_path:
                            raw = await agent._sandbox_backend.get_file(task.artifact_path)
                            artifact = raw.decode("utf-8", errors="replace") if raw else ""
                        success, detail = await judge_artifact(task, client, artifact)
                        detail = detail.strip()[:300]
                        if not success:
                            failure_class = classify_failure(
                                judge=judge, turns=turns, max_turns=task.max_turns
                            )
                finally:
                    agent._sandbox_backend.close()
            finally:
                if memory_root is not None:
                    shutil.rmtree(memory_root, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001 —— 失败样本也要如实记录
        detail = f"{type(exc).__name__}: {exc}"[:300]
        failure_class = classify_failure(judge=judge, error=detail)
    finally:
        tokens = client.usage_totals["total_tokens"]
        await client.close()

    return BatchRunResult(
        task_id=task.id,
        arm=arm,
        success=success,
        judge=judge,
        turns=turns,
        tokens=tokens,
        duration_s=round(time.monotonic() - start, 1),
        failure_class=failure_class,
        detail=detail,
        tools=",".join(tools_used),
        sample=sample,
    )


@dataclass
class BatchSummary:
    """单臂聚合指标。"""

    runs: int = 0
    passed: int = 0
    total_turns: int = 0
    total_tokens: int = 0
    failure_classes: dict[str, int] = field(default_factory=dict)


def summarize(results: list[BatchRunResult]) -> dict[str, BatchSummary]:
    """按机制臂聚合指标。"""
    out: dict[str, BatchSummary] = {}
    for r in results:
        summary = out.setdefault(r.arm, BatchSummary())
        summary.runs += 1
        summary.passed += int(r.success)
        summary.total_turns += r.turns
        summary.total_tokens += r.tokens
        if r.failure_class:
            key = r.failure_class
            summary.failure_classes[key] = summary.failure_classes.get(key, 0) + 1
    return out


def render_report(
    results: list[BatchRunResult],
    tag: str = "",
    arms: tuple[str, ...] = ARMS,
) -> str:
    """渲染 Markdown 聚合报告（分臂成功率/轮数/token/失败分布 + 明细表）。"""
    summaries = summarize(results)
    lines = [
        f"# 批量 E2E 评测报告 {tag}".rstrip(),
        "",
        f"- 运行时间：{time.strftime('%Y-%m-%d %H:%M')}",
        "- 模型：环境变量 `OPENAI_MODEL` 指向的 OpenAI 兼容端点；judge 与执行同模型（temperature=0）",
        "- 采样说明：每 task×arm 单样本（Batch 1 口径）",
        "",
        "## 聚合指标",
        "",
        "| 机制臂 | 成功率 | 平均轮数 | 总 token | 平均 token/run | 失败分类分布 |",
        "|---|---|---|---|---|---|",
    ]
    for arm in arms:
        s = summaries.get(arm)
        if s is None or s.runs == 0:
            continue
        rate = f"{s.passed}/{s.runs}（{s.passed / s.runs:.0%}）"
        avg_turns = f"{s.total_turns / s.runs:.1f}"
        avg_tokens = f"{s.total_tokens / s.runs:.0f}"
        dist = "、".join(f"{k}×{v}" for k, v in sorted(s.failure_classes.items())) or "—"
        lines.append(f"| {arm} | {rate} | {avg_turns} | {s.total_tokens} | {avg_tokens} | {dist} |")

    if any(r.sample > 1 for r in results):
        lines += [
            "",
            "## 采样一致性（每格为该任务的采样结果序列）",
            "",
            "| 任务 | " + " | ".join(arms) + " |",
            "|---|" + "---|" * len(arms),
        ]
        task_ids = list(dict.fromkeys(r.task_id for r in results))
        for tid in task_ids:
            row = [tid]
            for arm in arms:
                cell = "".join(
                    "✅" if r.success else "❌"
                    for r in results
                    if r.task_id == tid and r.arm == arm
                )
                row.append(cell or "—")
            lines.append("| " + " | ".join(row) + " |")

    lines += [
        "",
        "## 明细",
        "",
        "| 任务 | 臂 | 采样 | 判分 | 结果 | 轮数 | token | 耗时s | 失败分类 | 工具序列 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        mark = "✅" if r.success else "❌"
        tools = r.tools[:40] + "…" if len(r.tools) > 40 else r.tools
        lines.append(
            f"| {r.task_id} | {r.arm} | {r.sample} | {r.judge} | {mark} | {r.turns} "
            f"| {r.tokens} | {r.duration_s} | {r.failure_class or '—'} | {tools or '—'} |"
        )
    return "\n".join(lines) + "\n"


async def run_batch(
    tasks: list[BatchTask],
    arms: tuple[str, ...],
    echo: bool,
    raw_path: Path,
    samples: int = 1,
) -> list[BatchRunResult]:
    """串行执行批量任务，逐行落 JSONL；infra 错误（judge=error）重试一次。

    samples > 1 时每个 task×arm 重复采样（区分稳定失败与模型抖动）。
    """
    results: list[BatchRunResult] = []
    with raw_path.open("a", encoding="utf-8") as fh:
        for arm in arms:
            for task in tasks:
                for sample in range(1, samples + 1):
                    result = await run_one(task, arm, echo=echo, sample=sample)
                    if result.judge == "error" and not echo:
                        print(f"[{arm}] {task.id}#{sample} infra 错误，重试一次：{result.detail[:80]}")
                        result = await run_one(task, arm, echo=echo, sample=sample)
                    results.append(result)
                    record = asdict(result)
                    record["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                    fh.flush()
                    mark = "PASS" if result.success else "FAIL"
                    print(
                        f"[{arm}] {task.id}#{sample} {mark} judge={result.judge} "
                        f"turns={result.turns} tokens={result.tokens} {result.duration_s}s"
                    )
    return results


def _load_tasks(set_name: str) -> list[BatchTask]:
    """按 --set 加载任务集（b1 冻结复跑 / b2 高难版）。"""
    if set_name not in TASK_SETS:
        raise SystemExit(f"未知任务集：{set_name}（可选：{list(TASK_SETS)}）")
    module_name, attr = TASK_SETS[set_name]
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        sys.path.insert(0, str(Path(__file__).parent))
        module = importlib.import_module(module_name)
    return list(getattr(module, attr))


def _select_tasks(
    tasks: list[BatchTask],
    only: str | None,
    limit: int | None,
) -> list[BatchTask]:
    """按 --only / --limit 过滤任务。"""
    if only:
        wanted = {item.strip() for item in only.split(",") if item.strip()}
        tasks = [t for t in tasks if t.id in wanted]
    if limit is not None:
        tasks = tasks[:limit]
    return tasks


def _check_real_run_readiness() -> None:
    """真实运行前置检查：API Key + Docker daemon。"""
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("未检测到 OPENAI_API_KEY；结构验证请用 --echo 冒烟。")
    import docker

    try:
        docker.from_env().ping()
    except Exception as exc:
        raise SystemExit(f"Docker daemon 不可达：{exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器。"""
    parser = argparse.ArgumentParser(description="批量 E2E 评测 Runner")
    parser.add_argument("--echo", action="store_true", help="冒烟模式：合成结果，零成本")
    parser.add_argument(
        "--set",
        default=DEFAULT_TASK_SET,
        dest="task_set",
        help=f"任务集（{list(TASK_SETS)}，默认 {DEFAULT_TASK_SET}）",
    )
    parser.add_argument("--only", default=None, help="只跑指定任务，逗号分隔（如 T01,T11）")
    parser.add_argument("--arms", default=None, help="只跑指定机制臂，逗号分隔（如 full）")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 个任务")
    parser.add_argument("--samples", type=int, default=1, help="每 task×arm 采样次数（默认 1）")
    parser.add_argument("--tag", default="", help="报告标题附加标签")
    return parser


async def main() -> int:
    """CLI 入口：过滤任务 → 批量执行 → 渲染并落盘报告。"""
    _ensure_utf8_stdout()
    args = build_parser().parse_args()
    tasks = _select_tasks(_load_tasks(args.task_set), args.only, args.limit)
    default_arms = SET_ARMS.get(args.task_set, ARMS)
    arms = tuple(a.strip() for a in args.arms.split(",")) if args.arms else default_arms
    if not tasks:
        print("没有匹配的任务。")
        return 1
    invalid = [a for a in arms if a not in ALL_ARMS]
    if invalid:
        print(f"未知机制臂：{invalid}（可选：{list(ALL_ARMS)}）")
        return 1
    if not args.echo:
        _check_real_run_readiness()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = REPORTS_DIR / f"{args.task_set}_raw.jsonl"
    print(
        f"批量评测启动：任务集 {args.task_set}，{len(tasks)} 任务 × "
        f"{len(arms)} 臂 × {args.samples} 采样，echo={args.echo}"
    )

    results = await run_batch(tasks, arms, args.echo, raw_path, samples=args.samples)
    report = render_report(results, tag=args.tag, arms=arms)
    report_path = REPORTS_DIR / f"{args.task_set}_report_{time.strftime('%Y%m%d_%H%M')}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n报告已写入 {report_path}\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
