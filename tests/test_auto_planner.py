"""自动规划（Auto-Planner）测试。

覆盖：
  - _parse_plan_steps：编号/括号/破折号/前言后语/max_steps 截断
  - _maybe_create_plan：enabled 创建并 start_next / disabled 不动 / 外部优先 /
    LLM 异常降级 / 解析空降级
  - CLI --plan 旗标强制启用
"""

from __future__ import annotations

import pytest

from agent.config import AgentConfig
from agent.core.engine import Agent
from agent.core.planner import TaskPlan
from agent.llm.base import BaseLLMClient, EchoClient


class TestParsePlanSteps:
    """规划输出的步骤解析。"""

    def test_numbered_dot_format(self) -> None:
        """标准 1. 2. 3. 编号格式。"""
        text = "1. 创建 CSV 文件\n2. 生成分析报告\n3. 编辑报告标题"
        steps = Agent._parse_plan_steps(text, max_steps=6)
        assert steps == ["创建 CSV 文件", "生成分析报告", "编辑报告标题"]

    def test_numbered_paren_format(self) -> None:
        """1) 2) 括号编号格式。"""
        text = "1) 创建 CSV 文件\n2) 生成分析报告"
        steps = Agent._parse_plan_steps(text, max_steps=6)
        assert steps == ["创建 CSV 文件", "生成分析报告"]

    def test_dash_format(self) -> None:
        """- 破折号列表格式。"""
        text = "- 创建 CSV 文件\n- 生成分析报告"
        steps = Agent._parse_plan_steps(text, max_steps=6)
        assert steps == ["创建 CSV 文件", "生成分析报告"]

    def test_preamble_and_postamble_ignored(self) -> None:
        """前言后语被忽略，只取步骤行。"""
        text = (
            "好的，我把任务分解为以下步骤：\n"
            "1. 创建 CSV 文件\n2. 生成分析报告\n"
            "希望这个计划对你有帮助！"
        )
        steps = Agent._parse_plan_steps(text, max_steps=6)
        assert steps == ["创建 CSV 文件", "生成分析报告"]

    def test_max_steps_truncation(self) -> None:
        """超过 max_steps 时截断。"""
        text = "\n".join(f"{i}. 步骤{i}" for i in range(1, 11))
        steps = Agent._parse_plan_steps(text, max_steps=3)
        assert steps == ["步骤1", "步骤2", "步骤3"]

    def test_unparseable_returns_empty(self) -> None:
        """完全无法解析时返回空列表（降级直跑）。"""
        assert Agent._parse_plan_steps("我直接回答你的问题", max_steps=6) == []


class _PlanThenFinishClient(BaseLLMClient):
    """首次调用返回规划文本，后续调用 finish 的脚本化客户端。"""

    def __init__(self, plan_text: str | Exception) -> None:
        self._plan_text = plan_text
        self._calls = 0

    async def chat(self, messages, tools=None, **kwargs):  # noqa: ANN001, ANN202
        self._calls += 1
        if self._calls == 1:
            if isinstance(self._plan_text, Exception):
                raise self._plan_text
            return {"content": self._plan_text, "tool_calls": None}
        return {
            "content": "",
            "tool_calls": [
                {"id": "c1", "function": {"name": "finish", "arguments": '{"result": "done"}'}}
            ],
        }


class TestMaybeCreatePlan:
    """_maybe_create_plan 的创建/降级行为。"""

    def _config(self, enabled: bool) -> AgentConfig:
        config = AgentConfig()
        config.agent.planner.enabled = enabled
        return config

    @pytest.mark.asyncio
    async def test_enabled_creates_and_starts_plan(self) -> None:
        """enabled 时：LLM 分解结果转为 TaskPlan 并 start_next。"""
        client = _PlanThenFinishClient("1. 创建 CSV\n2. 生成报告\n3. 编辑标题")
        agent = Agent(llm_client=client, config=self._config(True))
        try:
            result = await agent.run("做一个销售分析任务")
            assert result == "done"
            assert agent.planner is not None
            assert len(agent.planner.steps) == 3
            assert agent.planner.steps[0].description == "创建 CSV"
        finally:
            agent._sandbox_backend.close()

    @pytest.mark.asyncio
    async def test_disabled_no_planning_call(self) -> None:
        """disabled 时：不发起规划调用，planner 为 None。"""

        class FinishOnlyClient(BaseLLMClient):
            def __init__(self) -> None:
                self.calls = 0

            async def chat(self, messages, tools=None, **kwargs):  # noqa: ANN001, ANN202
                self.calls += 1
                return {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "function": {
                                "name": "finish",
                                "arguments": '{"result": "done"}',
                            },
                        }
                    ],
                }

        client = FinishOnlyClient()
        agent = Agent(llm_client=client, config=self._config(False))
        try:
            result = await agent.run("任务")
            assert result == "done"
            assert agent.planner is None
            assert client.calls == 1  # 只有主循环那一次，无规划调用
        finally:
            agent._sandbox_backend.close()

    @pytest.mark.asyncio
    async def test_external_planner_not_overridden(self) -> None:
        """外部注入的 planner 不被自动规划覆盖。"""
        external = TaskPlan(goal="手工计划")
        external.add_step("s1", "手工步骤")
        external.start_next()
        client = _PlanThenFinishClient("1. 自动步骤不应生效")
        agent = Agent(
            llm_client=client, config=self._config(True), planner=external
        )
        try:
            await agent.run("任务")
            assert agent.planner is external
            assert agent.planner.steps[0].description == "手工步骤"
        finally:
            agent._sandbox_backend.close()

    @pytest.mark.asyncio
    async def test_llm_error_falls_back_to_direct_run(self) -> None:
        """规划调用异常时静默降级，任务直跑不失败。"""
        client = _PlanThenFinishClient(RuntimeError("api down"))
        agent = Agent(llm_client=client, config=self._config(True))
        try:
            result = await agent.run("任务")
            assert result == "done"
            assert agent.planner is None
        finally:
            agent._sandbox_backend.close()

    @pytest.mark.asyncio
    async def test_unparseable_plan_falls_back(self) -> None:
        """LLM 输出无法解析时降级直跑。"""
        client = _PlanThenFinishClient("这个任务很简单，直接做就行")
        agent = Agent(llm_client=client, config=self._config(True))
        try:
            result = await agent.run("任务")
            assert result == "done"
            assert agent.planner is None
        finally:
            agent._sandbox_backend.close()


class TestCliPlanFlag:
    """CLI --plan 旗标。"""

    def test_build_agent_plan_flag_forces_enabled(self) -> None:
        """--plan 强制启用自动规划（覆盖配置文件默认值）。"""
        from agent.cli.agent_cli import _build_agent

        config = AgentConfig()
        assert config.agent.planner.enabled is False
        agent = _build_agent(config, EchoClient(), plan=True)
        try:
            assert config.agent.planner.enabled is True
        finally:
            agent._sandbox_backend.close()
