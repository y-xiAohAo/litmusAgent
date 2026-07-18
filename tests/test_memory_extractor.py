"""RuleMemoryExtractor 单元测试。"""

from __future__ import annotations

from agent.core.memory import (
    MemoryCategory,
    MemoryEntry,
    RuleMemoryExtractor,
)
from agent.core.state import AgentState
from agent.core.trace import AgentTrace


def _trace_with_event(event_type: str, payload: dict) -> AgentTrace:
    """创建一个只包含单个事件的 Trace。"""
    trace = AgentTrace()
    step = trace.add_step(0)
    step.add_event(event_type, payload)
    return trace


def _extract(trace: AgentTrace, state: AgentState | None = None) -> list[MemoryEntry]:
    """便捷调用 RuleMemoryExtractor。"""
    extractor = RuleMemoryExtractor()
    return extractor.extract(trace, state or AgentState(), {"run_id": "run-1"})


def test_rule_extractor_extracts_pip_install() -> None:
    """sandbox_exec 成功执行 pip install 时应生成 environment 记忆。"""
    trace = _trace_with_event(
        "tool_execution",
        {
            "tool": "sandbox_exec",
            "arguments": {"command": "pip install pandas numpy==1.24"},
            "success": True,
            "content": "Successfully installed pandas numpy",
        },
    )
    entries = _extract(trace)

    assert len(entries) == 1
    entry = entries[0]
    assert entry.category == MemoryCategory.ENVIRONMENT
    assert entry.content["packages"] == [
        {"name": "pandas", "version": None},
        {"name": "numpy", "version": None},
    ]
    assert "pandas" in entry.tags
    assert "numpy" in entry.tags
    assert entry.source_run_id == "run-1"


def test_rule_extractor_ignores_pip_install_failure() -> None:
    """pip install 失败时不应记录 environment。"""
    trace = _trace_with_event(
        "tool_execution",
        {
            "tool": "sandbox_exec",
            "arguments": {"command": "pip install pandas"},
            "success": False,
            "content": "Could not find a version",
        },
    )
    entries = _extract(trace)
    assert all(e.category != MemoryCategory.ENVIRONMENT for e in entries)


def test_rule_extractor_extracts_workspace_paths() -> None:
    """工具输出中的 /workspace/ 和 /tmp/ 路径应生成 artifacts 记忆。"""
    trace = _trace_with_event(
        "tool_execution",
        {
            "tool": "sandbox_exec",
            "arguments": {"command": "python generate.py"},
            "success": True,
            "content": "Saved report to /workspace/report.md\n"
                       "Debug log at /tmp/debug.txt",
        },
    )
    entries = _extract(trace)

    artifacts = [e for e in entries if e.category == MemoryCategory.ARTIFACTS]
    assert len(artifacts) == 2
    paths = {e.content["path"] for e in artifacts}
    assert paths == {"/workspace/report.md", "/tmp/debug.txt"}


def test_rule_extractor_extracts_state_artifacts() -> None:
    """AgentState.artifacts 中的产物也应被提取。"""
    trace = AgentTrace()
    state = AgentState()
    state.add_artifact("chart.png", {"type": "image", "description": "销售趋势图"})

    entries = _extract(trace, state)

    artifacts = [e for e in entries if e.category == MemoryCategory.ARTIFACTS]
    assert len(artifacts) == 1
    assert artifacts[0].content["path"] == "chart.png"
    assert artifacts[0].content["type"] == "image"


def test_rule_extractor_extracts_failure_pattern() -> None:
    """同一 step 内 error_classification + reflection 应生成 failure_patterns。"""
    trace = AgentTrace()
    step = trace.add_step(0)
    step.add_event(
        "tool_execution",
        {
            "tool": "sandbox_exec",
            "arguments": {"command": "python main.py"},
            "success": False,
            "content": "ModuleNotFoundError: No module named 'pandas'",
        },
    )
    step.add_event(
        "error_classification",
        {
            "severity": "RECOVERABLE",
            "action": "CHECK_CONTEXT",
            "hint": "检查环境是否已安装 pandas",
        },
    )
    step.add_event(
        "reflection",
        {
            "tool_name": "sandbox_exec",
            "exc_type": "ModuleNotFoundError",
            "signature": "pandas",
            "count": 1,
            "severity": "RECOVERABLE",
            "action": "CHECK_CONTEXT",
            "hint": "建议先安装 pandas 再执行代码",
        },
    )

    entries = _extract(trace)

    failures = [e for e in entries if e.category == MemoryCategory.FAILURE_PATTERNS]
    assert len(failures) == 1
    entry = failures[0]
    assert entry.content["tool"] == "sandbox_exec"
    assert entry.content["exc_type"] == "ModuleNotFoundError"
    assert entry.content["signature_detail"] == {"missing_module": "pandas"}
    assert entry.content["recovery"] == "CHECK_CONTEXT"
    assert "pandas" in entry.tags


def test_rule_extractor_ignores_unrelated_events() -> None:
    """无关事件不应产生任何记忆。"""
    trace = _trace_with_event(
        "llm_request",
        {"messages_count": 3, "tools_count": 2, "system_prompt_summary": ""},
    )
    entries = _extract(trace)
    assert entries == []


def test_rule_extractor_parses_pip_options_correctly() -> None:
    """pip install 命令中的选项和引号应被正确过滤。"""
    extractor = RuleMemoryExtractor()
    command = "pip install --upgrade 'pandas' numpy \"requests>=2.0\" -q"
    packages = extractor._parse_pip_packages(command)
    assert set(packages) == {"pandas", "numpy", "requests"}


def test_rule_extractor_extracts_generic_absolute_paths() -> None:
    """带扩展名的绝对路径也能被识别为产物。"""
    trace = _trace_with_event(
        "tool_execution",
        {
            "tool": "file_read",
            "arguments": {"path": "/data/output.json"},
            "success": True,
            "content": "Wrote /data/output.json",
        },
    )
    entries = _extract(trace)
    artifacts = [e for e in entries if e.category == MemoryCategory.ARTIFACTS]
    assert any(e.content["path"] == "/data/output.json" for e in artifacts)
