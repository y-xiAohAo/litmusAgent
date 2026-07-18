"""任务规划器 —— 把用户目标拆成有序、可追踪的步骤。

核心设计思想：
  与其让 LLM 在心里默默盘算"接下来做什么"（隐式规划），
  不如给 Agent 一个显式的任务清单。好处有三：

  1. 可观测：用户和开发者都能看到"Agent 现在在做什么"
  2. 可恢复：如果某一步崩了，知道哪些完成了，从哪里重来
  3. 可提示：可以把进度信息注入 LLM 的 prompt，提升规划质量

Planner 不是 AI 调度器 —— 它只是一个状态机。
LLM 负责"决定做什么"，Planner 负责"记住做了哪些"。

StepStatus 生命周期：
  PENDING → ACTIVE → COMPLETED  (正常流程)
  PENDING → ACTIVE → FAILED      (失败流程)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StepStatus(Enum):
    """一个计划步骤的生命周期状态。

    使用 Enum 而非字符串常量的原因：
      - 类型安全：不能错误地把 "done" 赋值给 status
      - IDE 自动补全：输入 StepStatus. 就能看到所有选项
      - 易于扩展：将来可以加 SKIPPED、RETRYING 等状态
    """

    PENDING = "pending"        # 尚未开始
    ACTIVE = "active"          # 正在执行
    COMPLETED = "completed"    # 执行成功
    FAILED = "failed"          # 执行失败（有错误信息）


@dataclass
class PlanStep:
    """任务计划中的一个原子步骤。

    name 和 description 的区别：
      - name: 短标识符，机器可读（如 "load_data"）
      - description: 人类可读的描述（如 "读取 sales.csv 并加载到 DataFrame"）
      name 用于代码逻辑（if step.name == "load_data"），
      description 用于注入 LLM prompt 和展示给用户。

    error_message 只在 status == FAILED 时有值，
    存储失败的详细原因（如 "文件不存在：data.csv"）。
    """

    name: str
    description: str
    status: StepStatus = StepStatus.PENDING
    error_message: str | None = None

    def mark_active(self) -> None:
        """标记步骤为"正在执行"。

        通常在 start_next() 中自动调用，不应手动调用。
        """
        self.status = StepStatus.ACTIVE

    def mark_completed(self) -> None:
        """标记步骤为"执行成功"。

        只要步骤没有抛异常就应该调用，即使返回值不是预期的。
        （逻辑错误的检测应该在 Agent 主循环中处理，不在 Planner 层）
        """
        self.status = StepStatus.COMPLETED

    def mark_failed(self, message: str) -> None:
        """标记步骤为"执行失败"，并记录原因。

        Args:
            message: 失败原因（如 "内存不足，无法加载全部数据"）
        """
        self.status = StepStatus.FAILED
        self.error_message = message


@dataclass
class TaskPlan:
    """一个任务的有序步骤列表，配合状态机管理执行进度。

    使用示例：
        plan = TaskPlan(goal="分析销售数据")
        plan.add_step("load", "读取 sales.csv")
        plan.add_step("clean", "清理缺失值")
        plan.add_step("analyze", "按月统计")

        while not plan.is_complete():
            step = plan.start_next()     # 激活下一个步骤
            # ... Agent 执行 step ...
            plan.complete_current()      # 标记完成

    current_step 总是指向当前正在执行的步骤（status=ACTIVE 的那个）。
    同一时间只有一个步骤是 ACTIVE —— 这是顺序执行模型，不是并行。

    为什么 is_complete() 要求至少有一个步骤？
      空计划不算"完成"——如果没有步骤，说明规划还没开始。
      all([]) 在 Python 中返回 True（空集合的"所有元素满足条件"是真空真），
      但我们的语义是"没有任何步骤被完成"，所以显式检查 len > 0。
    """

    goal: str                              # 任务目标（如 "分析 sales.csv"）
    steps: list[PlanStep] = field(default_factory=list)  # 步骤列表
    current_step: PlanStep | None = None   # 当前正在执行的步骤

    def add_step(self, name: str, description: str) -> PlanStep:
        """在计划末尾追加一个步骤。

        步骤按添加顺序执行，不支持乱序或跳过。
        如果需要更复杂的依赖关系，应该在上层（Agent 主循环）处理。

        Args:
            name:        步骤名称（如 "load_data"）
            description: 步骤描述（如 "用 pandas 读取 CSV 文件"）

        Returns:
            新创建的 PlanStep 对象（可进一步配置，如设置 expected_output）
        """
        step = PlanStep(name=name, description=description)
        self.steps.append(step)
        return step

    def start_next(self) -> PlanStep | None:
        """激活下一个待执行的步骤并返回。

        遍历 steps 列表，找到第一个 status == PENDING 的步骤，
        将其标记为 ACTIVE，设置 current_step，然后返回。

        如果所有步骤都是 COMPLETED 或 FAILED，返回 None。

        不会跳过 FAILED 的步骤——如果需要重试失败步骤，
        应该在上层先将其 status 重置为 PENDING。
        """
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                step.mark_active()
                self.current_step = step
                return step
        self.current_step = None
        return None

    def complete_current(self) -> None:
        """将当前正在执行的步骤标记为完成。

        只处理 status == ACTIVE 的步骤，
        防止重复标记或标记未开始的步骤。
        """
        if self.current_step and self.current_step.status == StepStatus.ACTIVE:
            self.current_step.mark_completed()

    def is_complete(self) -> bool:
        """所有步骤都完成了吗？

        要求至少有一个步骤（空计划不算完成），
        且所有步骤的 status 都是 COMPLETED。
        """
        return len(self.steps) > 0 and all(
            s.status == StepStatus.COMPLETED for s in self.steps
        )

    def completed_count(self) -> int:
        """返回已完成的步骤数量（用于进度条显示）。"""
        return sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)

    def to_progress_prompt(self) -> str:
        """生成进度摘要，可以注入到 LLM 的 system prompt 中。

        示例输出：
            Goal: 分析 sales.csv
            Progress: Step 2/4 — 清理缺失值

        这段文本告诉 LLM "你正在做哪个任务，做到哪一步了"，
        帮助 LLM 做出更准确的下一步决策。
        """
        total = len(self.steps)
        done = self.completed_count()
        if (
            self.current_step is not None
            and self.current_step.status == StepStatus.ACTIVE
        ):
            # 正常执行中：当前步骤 = done + 1（天然不越界）
            step_no = done + 1
            current_desc = self.current_step.description
        elif total > 0 and done >= total:
            # 全部完成：封顶显示，避免 Step (total+1)/total 越界
            step_no = total
            current_desc = "全部完成"
        else:
            # 未启动或异常中断后无当前步骤
            step_no = done + 1
            current_desc = "准备开始..."
        return (
            f"Goal: {self.goal}\n"
            f"Progress: Step {step_no}/{total} — {current_desc}"
        )
