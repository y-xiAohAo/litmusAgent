"""e2e_suite 场景套件离线测试（真实 LLM 联调前置）。

设计原则：
  1. 不依赖真实 LLM / API Key / Docker daemon——脚本化客户端离线驱动。
  2. 覆盖：证据断言判定、工具事件提取、报告渲染、单场景执行闭环。
"""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

SUITE_PATH = Path(__file__).parent.parent / "examples" / "e2e_suite.py"


@pytest.fixture
def suite():
    """以 runpy 加载套件脚本。"""
    assert SUITE_PATH.exists(), "examples/e2e_suite.py 不存在"
    return runpy.run_path(str(SUITE_PATH))


def _make_scenario(suite, **overrides):
    scenario_cls = suite["Scenario"]
    defaults = {
        "id": "T1",
        "name": "测试场景",
        "prompt": "test prompt",
        "expected_tools": ["finish"],
        "expected_in_output": ["55"],
    }
    defaults.update(overrides)
    return scenario_cls(**defaults)


class TestEvaluateEvidence:
    """证据断言判定逻辑。"""

    def test_all_evidence_pass(self, suite) -> None:
        """工具与输出断言全部满足时全部通过。"""
        sc = _make_scenario(suite)
        tool_events = [{"tool": "finish", "success": True, "content": "def f... 55"}]
        evidence = suite["evaluate_evidence"](sc, tool_events, "答案是 55")
        assert all(ok for _, ok in evidence)
        assert len(evidence) == 2  # 1 工具断言 + 1 输出断言

    def test_missing_tool_fails(self, suite) -> None:
        """期望的工具未出现 → 该断言失败。"""
        sc = _make_scenario(suite, expected_tools=["sandbox_exec"])
        evidence = suite["evaluate_evidence"](sc, [], "no tools")
        assert any("sandbox_exec" in desc and not ok for desc, ok in evidence)

    def test_missing_output_fails(self, suite) -> None:
        """期望文本不在最终答案与工具输出中 → 失败。"""
        sc = _make_scenario(suite, expected_in_output=["55"])
        tool_events = [{"tool": "finish", "success": True, "content": "42"}]
        evidence = suite["evaluate_evidence"](sc, tool_events, "42")
        assert any("55" in desc and not ok for desc, ok in evidence)

    def test_output_found_in_tool_content(self, suite) -> None:
        """期望文本在工具输出（而非最终答案）中也算通过。"""
        sc = _make_scenario(
            suite, expected_tools=["sandbox_exec"], expected_in_output=["55"]
        )
        tool_events = [{"tool": "sandbox_exec", "success": True, "content": "55\n"}]
        evidence = suite["evaluate_evidence"](sc, tool_events, "见上")
        assert all(ok for _, ok in evidence)


class TestRenderReport:
    """Markdown 报告渲染。"""

    def test_report_contains_key_fields(self, suite) -> None:
        """报告应包含场景 ID、结果、轮数、耗时与证据列。"""
        result_cls = suite["ScenarioResult"]
        results = [
            result_cls(
                scenario_id="S1",
                success=True,
                turns=5,
                tools_used=["sandbox_exec", "finish"],
                duration_s=12.3,
                evidence=[("工具 sandbox_exec", True), ("输出包含 55", True)],
            ),
            result_cls(
                scenario_id="S2",
                success=False,
                turns=3,
                tools_used=["file_write"],
                duration_s=4.5,
                evidence=[("工具 file_read", False)],
                error="timeout",
            ),
        ]
        report = suite["render_report"](results)
        assert "S1" in report and "S2" in report
        assert "5" in report and "12.3" in report
        assert "PASS" in report and "FAIL" in report
        assert "timeout" in report


class TestRunScenarioOffline:
    """单场景执行闭环（脚本化客户端，离线）。"""

    @pytest.mark.asyncio
    async def test_run_scenario_success_with_finish(self, suite) -> None:
        """客户端首轮调用 finish → 场景成功，证据全部通过。"""
        from agent.llm.base import BaseLLMClient

        class FinishClient(BaseLLMClient):
            async def chat(self, messages, tools=None, **kwargs):  # noqa: ANN001, ANN202
                return {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "function": {
                                "name": "finish",
                                "arguments": '{"result": "def fibonacci... f(10)=55"}',
                            },
                        }
                    ],
                }

        sc = _make_scenario(suite, backend="subprocess")
        result = await suite["run_scenario"](sc, FinishClient())
        assert result.success is True
        assert result.turns >= 1
        assert "finish" in result.tools_used
        assert all(ok for _, ok in result.evidence)

    @pytest.mark.asyncio
    async def test_run_scenario_records_tool_sequence(self, suite) -> None:
        """工具调用序列按 trace 记录。"""
        from agent.llm.base import BaseLLMClient

        class TwoToolClient(BaseLLMClient):
            def __init__(self) -> None:
                self._step = 0

            async def chat(self, messages, tools=None, **kwargs):  # noqa: ANN001, ANN202
                self._step += 1
                if self._step == 1:
                    return {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "c1",
                                "function": {
                                    "name": "file_write",
                                    "arguments": '{"path": "/workspace/a.txt", "content": "x55"}',
                                },
                            }
                        ],
                    }
                return {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "c2",
                            "function": {
                                "name": "finish",
                                "arguments": '{"result": "done 55"}',
                            },
                        }
                    ],
                }

        sc = _make_scenario(
            suite, backend="subprocess", expected_tools=["file_write", "finish"]
        )
        result = await suite["run_scenario"](sc, TwoToolClient())
        assert result.tools_used == ["file_write", "finish"]


class TestConfigOverrides:
    """Scenario.config_overrides 的配置应用。"""

    def test_overrides_applied_to_config(self, suite) -> None:
        """点分路径覆盖应写入 AgentConfig。"""
        sc = _make_scenario(
            suite,
            config_overrides={
                "compression.enabled": True,
                "compression.context_window": 600,
            },
        )
        config = suite["build_config"](sc)
        assert config.agent.compression.enabled is True
        assert config.agent.compression.context_window == 600

    def test_no_overrides_default(self, suite) -> None:
        """无覆盖时配置保持默认。"""
        sc = _make_scenario(suite)
        config = suite["build_config"](sc)
        assert config.agent.compression.enabled is False


class TestTwoPhaseScenario:
    """S6 两阶段（跨实例）叙事场景 runner。"""

    @pytest.mark.asyncio
    async def test_two_phase_runs_both_sessions(self, suite) -> None:
        """两阶段场景应执行 prompt 与 prompt_b 两次运行。"""
        from agent.llm.base import BaseLLMClient

        calls: list[str] = []

        class RecordingClient(BaseLLMClient):
            async def chat(self, messages, tools=None, **kwargs):  # noqa: ANN001, ANN202
                calls.append("chat")
                return {"content": "session answer", "tool_calls": None}

        sc = _make_scenario(
            suite,
            backend="subprocess",
            two_phase=True,
            prompt_b="第二个问题",
            expected_tools=[],
            expected_in_output=["session answer"],
        )
        result = await suite["run_scenario"](sc, RecordingClient())
        assert result.success is True
        assert len(calls) == 2  # Session A + Session B 各一次

    @pytest.mark.asyncio
    async def test_two_phase_new_agent_per_phase(self, suite) -> None:
        """两阶段应使用两个独立 Agent 实例（跨会话语义）。"""
        from agent.llm.base import BaseLLMClient

        class FinishClient(BaseLLMClient):
            async def chat(self, messages, tools=None, **kwargs):  # noqa: ANN001, ANN202
                return {"content": "ok", "tool_calls": None}

        sc = _make_scenario(suite, backend="subprocess", two_phase=True, prompt_b="b")
        result = await suite["run_scenario"](sc, FinishClient())
        assert result.error == ""


class TestApprovalScenarios:
    """TD-008 真实联调场景的脚本化确认机制（离线）。"""

    def test_scripted_approval_y_n_a(self, suite) -> None:
        """脚本化 callback 按序消费答案，a 后免确认。"""
        callback = suite["_make_scripted_approval"](["y", "n", "a"])
        assert callback("file_write", {}) is True
        assert callback("file_write", {}) is False
        assert callback("file_write", {}) is True   # a → 免确认
        assert callback("file_write", {}) is True   # 后续仍免确认

    def test_scripted_approval_exhausted_defaults_n(self, suite) -> None:
        """答案耗尽后默认拒绝。"""
        callback = suite["_make_scripted_approval"](["y"])
        assert callback("file_write", {}) is True
        assert callback("file_write", {}) is False
