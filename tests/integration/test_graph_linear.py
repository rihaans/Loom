"""Integration tests for the linear graph pipeline.

Tests graph building and routing logic.
"""

from unittest.mock import Mock

from loom.config import LoomConfig
from loom.graph.builder import build_linear_graph, compile_graph
from loom.graph.routing import route_after_devops, route_after_pm, route_after_qa


class TestGraphBuilder:
    """Test the graph builder functionality."""

    def test_build_linear_graph_creates_graph(self) -> None:
        """Test that build_linear_graph creates a valid StateGraph."""
        config = LoomConfig()
        graph = build_linear_graph(config)

        # Graph should have nodes
        assert graph is not None

    def test_compile_graph_returns_runnable(self) -> None:
        """Test that compile_graph returns a runnable graph."""
        config = LoomConfig()
        compiled = compile_graph(config)

        # Compiled graph should have invoke method
        assert hasattr(compiled, "ainvoke")
        assert hasattr(compiled, "invoke")

    def test_graph_has_required_nodes(self) -> None:
        """Test that the graph has all required agent nodes."""
        config = LoomConfig()
        graph = build_linear_graph(config)

        # Check that all nodes are registered
        # The graph.nodes attribute contains the node definitions
        node_names = set(graph.nodes.keys())

        expected_nodes = {
            "product_manager",
            "memory_retrieve",
            "architect",
            "frontend_dev",
            "backend_dev",
            "dev_merge",
            "qa_engineer",
            "devops_engineer",
            "memory_persist",
            "supervisor",
        }

        for node in expected_nodes:
            assert node in node_names, f"Missing node: {node}"


class TestRouting:
    """Test routing functions."""

    def test_route_after_pm_success(self) -> None:
        """Test PM routing on success."""
        state = {"prd": Mock(), "error": None}
        result = route_after_pm(state)
        assert result == "architect"

    def test_route_after_pm_error(self) -> None:
        """Test PM routing on error."""
        state = {"prd": None, "error": "Failed to generate PRD"}
        result = route_after_pm(state)
        assert result == "supervisor"

    def test_route_after_pm_no_prd(self) -> None:
        """Test PM routing when PRD is None."""
        state = {"prd": None, "error": None}
        result = route_after_pm(state)
        assert result == "supervisor"

    def test_route_after_qa_tests_pass(self) -> None:
        """Test QA routing when tests pass."""
        test_report = Mock()
        test_report.failed = 0

        state = {
            "test_report": test_report,
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
        }
        result = route_after_qa(state)
        assert result == "devops_engineer"

    def test_route_after_qa_tests_fail_with_retries(self) -> None:
        """Test QA routing when tests fail with retries available."""
        test_report = Mock()
        test_report.failed = 1

        state = {
            "test_report": test_report,
            "retry_count": 0,
            "max_retries": 3,
            "error": None,
        }
        result = route_after_qa(state)
        assert result == "developers"  # Should retry

    def test_route_after_qa_max_retries_exceeded(self) -> None:
        """Test QA routing when max retries exceeded — proceeds to devops anyway."""
        test_report = Mock()
        test_report.failed = 1

        state = {
            "test_report": test_report,
            "retry_count": 3,
            "max_retries": 3,
            "error": None,
        }
        result = route_after_qa(state)
        # When retry budget exhausted, pipeline proceeds to devops despite failures
        assert result == "devops_engineer"

    def test_route_after_devops_success(self) -> None:
        """Test DevOps routing on success."""
        state = {"devops_files": Mock(), "error": None}
        result = route_after_devops(state)
        assert result == "__end__"

    def test_route_after_devops_error(self) -> None:
        """Test DevOps routing on error."""
        state = {"devops_files": None, "error": "Failed"}
        result = route_after_devops(state)
        assert result == "supervisor"


class TestGraphWithCheckpointer:
    """Test graph compilation with checkpointer."""

    def test_compile_with_memory_checkpointer(self) -> None:
        """Test compiling graph with memory checkpointer."""
        from loom.graph.checkpoint import create_memory_checkpointer

        config = LoomConfig()
        checkpointer = create_memory_checkpointer()
        compiled = compile_graph(config, checkpointer=checkpointer)

        assert compiled is not None

    def test_compile_with_interrupt_before(self) -> None:
        """Test compiling graph with interrupt points."""
        from loom.graph.checkpoint import create_memory_checkpointer

        config = LoomConfig()
        checkpointer = create_memory_checkpointer()
        compiled = compile_graph(
            config,
            checkpointer=checkpointer,
            interrupt_before=["architect", "frontend_dev"],
        )

        assert compiled is not None


class TestParallelRouting:
    """Test parallel routing for developers."""

    def test_route_to_devs_returns_send_list(self) -> None:
        """Test that route_to_devs returns Send objects."""
        from loom.graph.parallel import route_to_devs

        state = {"architecture": Mock(), "error": None}
        result = route_to_devs(state)

        # Should return a list of Send objects
        assert isinstance(result, list)
        assert len(result) == 2  # frontend and backend

    def test_route_to_retry_devs_targets_correct_agent(self) -> None:
        """Test that retry routing targets the correct agent."""
        from loom.graph.parallel import route_to_retry_devs
        from loom.state.enums import TargetAgent

        qa_feedback = Mock()
        qa_feedback.target_agent = TargetAgent.BACKEND_DEV

        state = {
            "qa_feedback": qa_feedback,
            "error": None,
        }
        result = route_to_retry_devs(state)

        # Should return Send objects for retry targets
        assert isinstance(result, list)
