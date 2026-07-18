"""Tests for Agent execution state management."""


from agent.core.state import AgentState, ExecutionContext


class TestAgentState:
    """Tests for AgentState — tracks high-level execution progress."""

    def test_initial_state(self):
        """New AgentState should have sensible defaults."""
        state = AgentState()
        assert state.phase is None
        assert state.current_step is None
        assert state.artifacts == {}

    def test_set_phase(self):
        """Should track execution phase changes."""
        state = AgentState()
        state.set_phase("planning")
        assert state.phase == "planning"

    def test_set_phase_with_step(self):
        """Should track both phase and current step."""
        state = AgentState()
        state.set_phase("executing", step="load_data")
        assert state.phase == "executing"
        assert state.current_step == "load_data"

    def test_phase_transitions(self):
        """Should allow transitions between phases."""
        state = AgentState()
        state.set_phase("planning")
        state.set_phase("executing", step="step1")
        state.set_phase("executing", step="step2")
        assert state.phase == "executing"
        assert state.current_step == "step2"

    def test_complete_transition(self):
        """Marking complete should clear current_step."""
        state = AgentState()
        state.set_phase("executing", step="do_thing")
        state.set_phase("finished")
        assert state.phase == "finished"
        assert state.current_step is None

    def test_add_artifact(self):
        """Should track artifacts produced during execution."""
        state = AgentState()
        state.add_artifact("chart.png", {"type": "image", "path": "/tmp/chart.png"})
        assert "chart.png" in state.artifacts
        assert state.artifacts["chart.png"]["type"] == "image"

    def test_multiple_artifacts(self):
        """Should track multiple artifacts independently."""
        state = AgentState()
        state.add_artifact("a.txt", {"size": 100})
        state.add_artifact("b.png", {"size": 200})
        assert len(state.artifacts) == 2


class TestExecutionContext:
    """Tests for ExecutionContext — key-value store for sandbox/runtime context."""

    def test_initial_context_is_empty(self):
        """New context should have no keys."""
        ctx = ExecutionContext()
        assert ctx.get("anything") is None

    def test_set_and_get(self):
        """Should store and retrieve simple values."""
        ctx = ExecutionContext()
        ctx.set("packages_installed", ["pandas", "numpy"])
        assert ctx.get("packages_installed") == ["pandas", "numpy"]

    def test_get_missing_returns_none(self):
        """Missing keys should return None."""
        ctx = ExecutionContext()
        assert ctx.get("nonexistent") is None

    def test_get_with_default(self):
        """Should support default values for missing keys."""
        ctx = ExecutionContext()
        assert ctx.get("missing", default=42) == 42

    def test_clear(self):
        """Should reset all stored values."""
        ctx = ExecutionContext()
        ctx.set("a", 1)
        ctx.set("b", 2)
        ctx.clear()
        assert ctx.get("a") is None
        assert ctx.get("b") is None

    def test_overwrite(self):
        """Setting the same key again should overwrite."""
        ctx = ExecutionContext()
        ctx.set("status", "running")
        ctx.set("status", "done")
        assert ctx.get("status") == "done"

    def test_multiple_independent_keys(self):
        """Multiple keys should not interfere with each other."""
        ctx = ExecutionContext()
        ctx.set("x", 10)
        ctx.set("y", 20)
        assert ctx.get("x") == 10
        assert ctx.get("y") == 20
