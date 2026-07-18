"""Tests for task planning and step progression."""


from agent.core.planner import PlanStep, StepStatus, TaskPlan


class TestPlanStep:
    """Tests for PlanStep — a single step in a task plan."""

    def test_step_creation(self):
        step = PlanStep(name="load_data", description="Load CSV into DataFrame")
        assert step.name == "load_data"
        assert step.description == "Load CSV into DataFrame"
        assert step.status == StepStatus.PENDING

    def test_step_mark_active(self):
        step = PlanStep(name="analyze", description="Analyze data")
        step.mark_active()
        assert step.status == StepStatus.ACTIVE

    def test_step_mark_completed(self):
        step = PlanStep(name="analyze", description="Analyze data")
        step.mark_active()
        step.mark_completed()
        assert step.status == StepStatus.COMPLETED

    def test_step_mark_failed(self):
        step = PlanStep(name="risky", description="Might fail")
        step.mark_active()
        step.mark_failed("data not available")
        assert step.status == StepStatus.FAILED
        assert step.error_message == "data not available"


class TestTaskPlan:
    """Tests for TaskPlan — ordered list of steps for a task."""

    def test_new_plan_is_empty(self):
        plan = TaskPlan(goal="Test")
        assert len(plan.steps) == 0
        assert plan.current_step is None
        assert not plan.is_complete()

    def test_add_step(self):
        plan = TaskPlan(goal="Do X")
        plan.add_step("a", "Thing A")
        plan.add_step("b", "Thing B")
        assert len(plan.steps) == 2
        assert plan.steps[0].name == "a"
        assert plan.steps[1].name == "b"

    def test_start_next_activates_first_step(self):
        plan = TaskPlan("Test")
        plan.add_step("step1", "First")
        plan.add_step("step2", "Second")

        step = plan.start_next()
        assert step.name == "step1"
        assert step.status == StepStatus.ACTIVE
        assert plan.current_step == step

    def test_complete_and_advance(self):
        plan = TaskPlan("Test")
        plan.add_step("step1", "First")
        plan.add_step("step2", "Second")

        plan.start_next()         # → step1 active
        plan.complete_current()    # step1 → completed

        step = plan.start_next()   # → step2 active
        assert step.name == "step2"

    def test_is_complete_when_all_done(self):
        plan = TaskPlan("Test")
        plan.add_step("a", "A")
        plan.add_step("b", "B")

        plan.start_next()
        plan.complete_current()
        plan.start_next()
        plan.complete_current()

        assert plan.is_complete()

    def test_is_not_complete_when_steps_remain(self):
        plan = TaskPlan("Test")
        plan.add_step("a", "A")
        plan.add_step("b", "B")
        plan.start_next()
        plan.complete_current()

        assert not plan.is_complete()

    def test_start_next_when_completed_returns_none(self):
        plan = TaskPlan("Test")
        plan.add_step("a", "A")
        plan.start_next()
        plan.complete_current()

        result = plan.start_next()
        assert result is None

    def test_to_progress_prompt(self):
        plan = TaskPlan("Analyze sales data")
        plan.add_step("load", "Read CSV into DataFrame")
        plan.add_step("clean", "Remove null values")
        plan.add_step("analyze", "Calculate monthly trends")

        plan.start_next()
        prompt = plan.to_progress_prompt()

        assert "Step 1/3" in prompt
        assert "Read CSV" in prompt
        assert plan.goal in prompt

    def test_completed_steps_count(self):
        plan = TaskPlan("Test")
        plan.add_step("a", "A")
        plan.add_step("b", "B")
        plan.add_step("c", "C")

        plan.start_next()
        plan.complete_current()
        plan.start_next()
        plan.complete_current()

        assert plan.completed_count() == 2


    def test_to_progress_prompt_completed_plan(self):
        """计划全部完成后不应显示越界进度（如 Step 5/4）。"""
        plan = TaskPlan("Analyze sales data")
        plan.add_step("load", "Read CSV into DataFrame")
        plan.add_step("clean", "Remove null values")
        plan.add_step("analyze", "Calculate monthly trends")

        plan.start_next()
        plan.complete_current()
        plan.start_next()
        plan.complete_current()
        plan.start_next()
        plan.complete_current()

        prompt = plan.to_progress_prompt()
        assert "Step 4/3" not in prompt  # 不允许 done+1 越界
        assert "Step 3/3" in prompt
        assert "全部完成" in prompt
        assert "准备开始" not in prompt

    def test_to_progress_prompt_not_started(self):
        """计划未启动时显示准备开始，进度为 Step 1/N。"""
        plan = TaskPlan("Analyze sales data")
        plan.add_step("load", "Read CSV into DataFrame")
        plan.add_step("clean", "Remove null values")

        prompt = plan.to_progress_prompt()
        assert "Step 1/2" in prompt
        assert "准备开始" in prompt
