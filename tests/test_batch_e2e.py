"""batch_e2e 批量评测 Runner 离线测试。

设计原则：
  1. 不依赖真实 LLM / API Key / Docker daemon——echo 合成结果 + 纯函数单测。
  2. 覆盖：任务集完整性、判分脚本语法、失败分类规则、judge 分数解析、
     聚合与报告渲染、echo 冒烟闭环。
"""

from __future__ import annotations

import ast
import runpy
from pathlib import Path

import pytest

RUNNER_PATH = Path(__file__).parent.parent / "examples" / "batch_e2e.py"
TASKS_PATH = Path(__file__).parent.parent / "examples" / "batch_tasks.py"


@pytest.fixture(scope="module")
def runner():
    """以 runpy 加载批量 Runner 脚本。"""
    assert RUNNER_PATH.exists(), "examples/batch_e2e.py 不存在"
    return runpy.run_path(str(RUNNER_PATH))


@pytest.fixture(scope="module")
def tasks_module():
    """以 runpy 加载任务集脚本。"""
    assert TASKS_PATH.exists(), "examples/batch_tasks.py 不存在"
    return runpy.run_path(str(TASKS_PATH))


class TestTaskSetIntegrity:
    """任务集结构完整性（Batch 1：20 任务）。"""

    def test_task_count_and_unique_ids(self, tasks_module):
        """任务集应为 20 个且 id 唯一。"""
        tasks = tasks_module["BATCH_TASKS"]
        ids = [t.id for t in tasks]
        assert len(tasks) == 20
        assert len(set(ids)) == 20

    def test_exactly_one_judge_method(self, tasks_module):
        """每个任务的 verify_script 与 judge_rubric 必须恰居其一。"""
        for task in tasks_module["BATCH_TASKS"]:
            has_script = task.verify_script is not None
            has_rubric = task.judge_rubric is not None
            assert has_script != has_rubric, f"{task.id} 判分方式不唯一"

    def test_judge_tasks_have_artifact_path(self, tasks_module):
        """开放类任务必须声明 /workspace 下的产物路径。"""
        for task in tasks_module["BATCH_TASKS"]:
            if task.judge_rubric is not None:
                assert task.artifact_path.startswith("/workspace/"), task.id

    def test_category_and_difficulty_valid(self, tasks_module):
        """分类与难度取值合法，且五类均有覆盖。"""
        categories = {t.category for t in tasks_module["BATCH_TASKS"]}
        assert categories == {"算法", "文件处理", "数据分析", "多步链路", "开放报告"}
        for task in tasks_module["BATCH_TASKS"]:
            assert task.difficulty in {"L1", "L2", "L3"}, task.id

    def test_verify_scripts_are_valid_python(self, tasks_module):
        """所有判分脚本必须是可解析的 Python。"""
        for task in tasks_module["BATCH_TASKS"]:
            if task.verify_script is not None:
                ast.parse(task.verify_script)


class TestClassifyFailure:
    """失败分类规则。"""

    def test_error_with_timeout_keyword(self, runner):
        """异常含 timeout 应归类超时。"""
        cls = runner["classify_failure"](judge="error", error="httpx.ReadTimeout: boom")
        assert cls == "超时"

    def test_generic_error_is_environment(self, runner):
        """其他异常应归类环境。"""
        cls = runner["classify_failure"](judge="error", error="docker.errors.APIError: boom")
        assert cls == "环境"

    def test_turns_exhausted_is_timeout(self, runner):
        """轮数耗尽（未报错）应归类超时。"""
        cls = runner["classify_failure"](judge="assert", turns=12, max_turns=12)
        assert cls == "超时"

    def test_syntax_error_in_verify_output(self, runner):
        """判分输出含 SyntaxError 应归类语法。"""
        cls = runner["classify_failure"](
            judge="assert", verify_stderr="SyntaxError: invalid syntax"
        )
        assert cls == "语法"

    def test_unknown_tool_preference(self, runner):
        """判分输出含未知工具应归类工具偏好。"""
        cls = runner["classify_failure"](judge="assert", verify_stdout="未知工具: bash")
        assert cls == "工具偏好"

    def test_default_is_logic(self, runner):
        """其余判分未过应归类逻辑。"""
        cls = runner["classify_failure"](
            judge="assert", verify_stdout="FAIL: '1,2' != expected", turns=5, max_turns=12
        )
        assert cls == "逻辑"


class TestParseJudgeScore:
    """judge 分数解析。"""

    def test_parse_normal(self, runner):
        """标准格式应解析出整数分数。"""
        assert runner["parse_judge_score"]("点评……\nSCORE: 4") == 4
        assert runner["parse_judge_score"]("SCORE:5") == 5

    def test_parse_out_of_range_or_missing(self, runner):
        """越界分数或缺失标记应返回 None。"""
        assert runner["parse_judge_score"]("SCORE: 7") is None
        assert runner["parse_judge_score"]("没有分数行") is None


class TestEchoSmoke:
    """echo 冒烟（零成本合成结果）。"""

    async def test_run_one_echo(self, runner, tasks_module):
        """echo 模式应返回合成的成功结果且不耗 token。"""
        task = tasks_module["BATCH_TASKS"][0]
        result = await runner["run_one"](task, "full", echo=True)
        assert result.success is True
        assert result.judge == "echo"
        assert result.tokens == 0

    def test_render_report_with_echo_results(self, runner, tasks_module):
        """合成结果应能渲染出含双臂与任务行的报告。"""
        batch_task = tasks_module["BATCH_TASKS"][0]
        results = [
            runner["BatchRunResult"](batch_task.id, arm, True, "echo", 0, 0, 0.0, "", "")
            for arm in ("full", "no-reflect")
        ]
        report = runner["render_report"](results, tag="test")
        assert "full" in report and "no-reflect" in report
        assert "1/1" in report
        assert batch_task.id in report

    def test_summarize_aggregation(self, runner):
        """聚合数学：成功率、轮数、token、失败分布。"""
        cls = runner["BatchRunResult"]
        results = [
            cls("T01", "full", True, "assert", 3, 100, 10.0, "", ""),
            cls("T02", "full", False, "assert", 5, 200, 20.0, "逻辑", "FAIL"),
        ]
        summary = runner["summarize"](results)["full"]
        assert summary.runs == 2
        assert summary.passed == 1
        assert summary.total_turns == 8
        assert summary.total_tokens == 300
        assert summary.failure_classes == {"逻辑": 1}


# ---------------------------------------------------------------------------
# Batch 2：b2 任务集与三臂
# ---------------------------------------------------------------------------

TASKS_B2_PATH = Path(__file__).parent.parent / "examples" / "batch_tasks_b2.py"


@pytest.fixture(scope="module")
def tasks_b2():
    """以 runpy 加载 b2 任务集脚本。"""
    assert TASKS_B2_PATH.exists(), "examples/batch_tasks_b2.py 不存在"
    return runpy.run_path(str(TASKS_B2_PATH))


class TestB2TaskSetIntegrity:
    """b2 任务集结构完整性（Batch 2：T21-T40）。"""

    def test_task_count_and_unique_ids(self, tasks_b2):
        """b2 应为 20 个任务且 id 唯一、不与 b1 重叠。"""
        tasks = tasks_b2["BATCH2_TASKS"]
        ids = [t.id for t in tasks]
        assert len(tasks) == 20
        assert len(set(ids)) == 20
        assert all(id_.startswith("T2") or id_.startswith("T3") or id_ == "T40" for id_ in ids)

    def test_exactly_one_judge_method(self, tasks_b2):
        """每个任务的 verify_script 与 judge_rubric 必须恰居其一。"""
        for task in tasks_b2["BATCH2_TASKS"]:
            assert (task.verify_script is not None) != (task.judge_rubric is not None), task.id

    def test_judge_tasks_have_artifact_path(self, tasks_b2):
        """b2 开放类任务必须声明 /workspace 下的产物路径。"""
        judge_tasks = [t for t in tasks_b2["BATCH2_TASKS"] if t.judge_rubric is not None]
        assert len(judge_tasks) == 2
        for task in judge_tasks:
            assert task.artifact_path.startswith("/workspace/"), task.id

    def test_categories_cover_known_weaknesses(self, tasks_b2):
        """b2 必须覆盖 file_edit 专项（针对 S4 已知弱点）。"""
        categories = {t.category for t in tasks_b2["BATCH2_TASKS"]}
        assert "file_edit 专项" in categories
        assert "陷阱数据" in categories

    def test_verify_scripts_are_valid_python(self, tasks_b2):
        """所有判分脚本必须是可解析的 Python。"""
        for task in tasks_b2["BATCH2_TASKS"]:
            if task.verify_script is not None:
                ast.parse(task.verify_script)


class TestBuildAgentArms:
    """三臂构造：planner 开关与反思 advisor 阈值。"""

    def _build(self, runner, arm: str):
        from agent.llm import EchoClient

        tasks_mod = runpy.run_path(str(TASKS_B2_PATH))
        task = tasks_mod["BATCH2_TASKS"][0]
        agent = runner["build_agent"](task, arm, EchoClient())
        return agent

    def test_full_arm_enables_planner(self, runner):
        """full 臂应开启 planner 且使用默认阈值 advisor。"""
        agent = self._build(runner, "full")
        try:
            assert agent._planner_enabled is True
            assert agent.reflective_advisor.reflection_threshold == 2
        finally:
            agent._sandbox_backend.close()

    def test_no_planner_arm_disables_planner(self, runner):
        """no-planner 臂应关闭 planner 且反思开启。"""
        agent = self._build(runner, "no-planner")
        try:
            assert agent._planner_enabled is False
            assert agent.reflective_advisor.reflection_threshold == 2
        finally:
            agent._sandbox_backend.close()

    def test_no_reflect_arm_disables_reflection(self, runner):
        """no-reflect 臂应开启 planner 且 advisor 阈值拉满。"""
        agent = self._build(runner, "no-reflect")
        try:
            assert agent._planner_enabled is True
            assert agent.reflective_advisor.reflection_threshold == 10**9
        finally:
            agent._sandbox_backend.close()

    def test_render_report_three_arms(self, runner):
        """三臂合成结果应全部出现在报告聚合表中。"""
        cls = runner["BatchRunResult"]
        results = [
            cls("T21", arm, True, "echo", 0, 0, 0.0, "", "")
            for arm in ("full", "no-planner", "no-reflect")
        ]
        report = runner["render_report"](results, tag="b2")
        for arm in ("full", "no-planner", "no-reflect"):
            assert f"| {arm} |" in report


# ---------------------------------------------------------------------------
# Batch 3：工具路径断言
# ---------------------------------------------------------------------------


class _StubEvent:
    def __init__(self, event_type: str, tool: str) -> None:
        self.event_type = event_type
        self.payload = {"tool": tool}


class _StubStep:
    def __init__(self, events: list) -> None:
        self.events = events


class _StubTrace:
    def __init__(self, steps: list) -> None:
        self.steps = steps


class _StubAgent:
    def __init__(self, trace: _StubTrace) -> None:
        self._trace = trace

    def get_trace(self) -> _StubTrace:
        return self._trace


class TestExtractToolNames:
    """从 Agent trace 提取工具名序列。"""

    def test_extracts_only_tool_execution_events(self, runner):
        """只提取 tool_execution 事件，按顺序返回工具名。"""
        agent = _StubAgent(
            _StubTrace(
                [
                    _StubStep([_StubEvent("tool_execution", "file_write")]),
                    _StubStep(
                        [
                            _StubEvent("llm_call", ""),
                            _StubEvent("tool_execution", "sandbox_exec"),
                        ]
                    ),
                ]
            )
        )
        assert runner["extract_tool_names"](agent) == ["file_write", "sandbox_exec"]

    def test_empty_trace_returns_empty(self, runner):
        """空 trace 应返回空列表。"""
        agent = _StubAgent(_StubTrace([]))
        assert runner["extract_tool_names"](agent) == []


class TestExpectedToolsCompat:
    """expected_tools 字段兼容性（b1/b2 默认空 = 无工具断言）。"""

    def test_b1_b2_tasks_default_no_expected_tools(self, tasks_module, tasks_b2):
        """b1/b2 任务必须全部 expected_tools 为空（历史口径不变）。"""
        for task in tasks_module["BATCH_TASKS"]:
            assert task.expected_tools == [], task.id
        for task in tasks_b2["BATCH2_TASKS"]:
            assert task.expected_tools == [], task.id

    def test_run_result_default_tools_empty(self, runner):
        """BatchRunResult 的 tools 字段默认空串（位置参数构造兼容）。"""
        result = runner["BatchRunResult"](
            "T41", "full", True, "assert", 3, 100, 10.0, "", ""
        )
        assert result.tools == ""


# ---------------------------------------------------------------------------
# Batch 3：b3 任务集完整性
# ---------------------------------------------------------------------------

TASKS_B3_PATH = Path(__file__).parent.parent / "examples" / "batch_tasks_b3.py"


@pytest.fixture(scope="module")
def tasks_b3():
    """以 runpy 加载 b3 任务集脚本。"""
    assert TASKS_B3_PATH.exists(), "examples/batch_tasks_b3.py 不存在"
    return runpy.run_path(str(TASKS_B3_PATH))


class TestB3TaskSetIntegrity:
    """b3 任务集结构完整性（Batch 3：T41-T60）。"""

    def test_task_count_and_unique_ids(self, tasks_b3):
        """b3 应为 20 个任务且 id 唯一。"""
        tasks = tasks_b3["BATCH3_TASKS"]
        ids = [t.id for t in tasks]
        assert len(tasks) == 20
        assert len(set(ids)) == 20

    def test_exactly_one_judge_method(self, tasks_b3):
        """每个任务的 verify_script 与 judge_rubric 必须恰居其一。"""
        for task in tasks_b3["BATCH3_TASKS"]:
            assert (task.verify_script is not None) != (task.judge_rubric is not None), task.id

    def test_file_edit_tasks_have_tool_assertion(self, tasks_b3):
        """file_edit 专项任务必须全部带 expected_tools=['file_edit']。"""
        fe_tasks = [t for t in tasks_b3["BATCH3_TASKS"] if t.category == "file_edit 专项"]
        assert len(fe_tasks) == 6
        for task in fe_tasks:
            assert task.expected_tools == ["file_edit"], task.id

    def test_other_tasks_have_no_tool_assertion(self, tasks_b3):
        """非 file_edit 任务不带工具断言（避免过度约束）。"""
        others = [t for t in tasks_b3["BATCH3_TASKS"] if t.category != "file_edit 专项"]
        for task in others:
            assert task.expected_tools == [], task.id

    def test_prompts_have_no_step_enumeration(self, tasks_b3):
        """开放式 prompt 不得含步骤枚举标记（恢复 planner 测量条件）。"""
        for task in tasks_b3["BATCH3_TASKS"]:
            assert "1) " not in task.prompt, task.id
            assert "第一步" not in task.prompt, task.id

    def test_verify_scripts_are_valid_python(self, tasks_b3):
        """所有判分脚本必须是可解析的 Python。"""
        for task in tasks_b3["BATCH3_TASKS"]:
            if task.verify_script is not None:
                ast.parse(task.verify_script)


# ---------------------------------------------------------------------------
# Batch 4：重复采样
# ---------------------------------------------------------------------------


class TestSamples:
    """--samples 重复采样机制。"""

    async def test_run_batch_samples_loop(self, runner, tasks_b3, tmp_path):
        """samples=2 时每任务每臂应产出 2 条结果，sample 序号 1/2。"""
        tasks = tasks_b3["BATCH3_TASKS"][:1]
        results = await runner["run_batch"](
            tasks, ("full",), True, tmp_path / "raw.jsonl", samples=2
        )
        assert len(results) == 2
        assert [r.sample for r in results] == [1, 2]

    def test_consistency_view_in_report(self, runner):
        """samples>1 时报告应含采样一致性视图。"""
        cls = runner["BatchRunResult"]
        results = [
            cls("T61", "full", True, "assert", 3, 100, 10.0, "", "", "", 1),
            cls("T61", "full", False, "assert", 5, 200, 20.0, "逻辑", "", "", 2),
        ]
        report = runner["render_report"](results, tag="b4")
        assert "采样一致性" in report
        assert "✅❌" in report

    def test_no_consistency_view_for_single_sample(self, runner):
        """单采样时不渲染一致性视图（向后兼容）。"""
        cls = runner["BatchRunResult"]
        results = [cls("T01", "full", True, "echo", 0, 0, 0.0, "", "")]
        report = runner["render_report"](results)
        assert "采样一致性" not in report


# ---------------------------------------------------------------------------
# Batch 4：b4 任务集完整性
# ---------------------------------------------------------------------------

TASKS_B4_PATH = Path(__file__).parent.parent / "examples" / "batch_tasks_b4.py"


@pytest.fixture(scope="module")
def tasks_b4():
    """以 runpy 加载 b4 任务集脚本。"""
    assert TASKS_B4_PATH.exists(), "examples/batch_tasks_b4.py 不存在"
    return runpy.run_path(str(TASKS_B4_PATH))


class TestB4TaskSetIntegrity:
    """b4 任务集结构完整性（Batch 4：T61-T80，L5）。"""

    def test_task_count_and_unique_ids(self, tasks_b4):
        """b4 应为 20 个任务且 id 唯一。"""
        tasks = tasks_b4["BATCH4_TASKS"]
        ids = [t.id for t in tasks]
        assert len(tasks) == 20
        assert len(set(ids)) == 20

    def test_exactly_one_judge_method(self, tasks_b4):
        """每个任务的 verify_script 与 judge_rubric 必须恰居其一。"""
        for task in tasks_b4["BATCH4_TASKS"]:
            assert (task.verify_script is not None) != (task.judge_rubric is not None), task.id

    def test_categories_and_judge_count(self, tasks_b4):
        """长链路 10 + 错误注入 10，judge 恰为 2 个。"""
        tasks = tasks_b4["BATCH4_TASKS"]
        categories = [t.category for t in tasks]
        assert categories.count("长链路") == 10
        assert categories.count("错误注入") == 10
        judges = [t for t in tasks if t.judge_rubric is not None]
        assert len(judges) == 2
        for task in judges:
            assert task.artifact_path.startswith("/workspace/"), task.id

    def test_expected_tools_only_on_edit_tasks(self, tasks_b4):
        """仅 T67/T69 带 file_edit 工具路径断言。"""
        with_tools = [t.id for t in tasks_b4["BATCH4_TASKS"] if t.expected_tools]
        assert sorted(with_tools) == ["T67", "T69"]
        for task in tasks_b4["BATCH4_TASKS"]:
            if task.expected_tools:
                assert task.expected_tools == ["file_edit"], task.id

    def test_verify_scripts_are_valid_python(self, tasks_b4):
        """所有判分脚本必须是可解析的 Python。"""
        for task in tasks_b4["BATCH4_TASKS"]:
            if task.verify_script is not None:
                ast.parse(task.verify_script)
