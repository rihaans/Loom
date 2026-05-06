"""Smoke test to verify the package can be imported."""


def test_agentforge_imports() -> None:
    """Verify that the main agentforge package can be imported."""
    import agentforge

    assert hasattr(agentforge, "__version__")
    assert agentforge.__version__ == "0.1.0"


def test_cli_imports() -> None:
    """Verify that the CLI module can be imported."""
    from agentforge.cli import app

    assert app is not None


def test_state_module_imports() -> None:
    """Verify that state module can be imported."""
    import agentforge.state

    assert agentforge.state is not None


def test_config_module_imports() -> None:
    """Verify that config module can be imported."""
    import agentforge.config

    assert agentforge.config is not None


def test_llm_module_imports() -> None:
    """Verify that LLM module can be imported."""
    import agentforge.llm

    assert agentforge.llm is not None


def test_agents_module_imports() -> None:
    """Verify that agents module can be imported."""
    import agentforge.agents

    assert agentforge.agents is not None


def test_graph_module_imports() -> None:
    """Verify that graph module can be imported."""
    import agentforge.graph

    assert agentforge.graph is not None


def test_sandbox_module_imports() -> None:
    """Verify that sandbox module can be imported."""
    import agentforge.sandbox

    assert agentforge.sandbox is not None
