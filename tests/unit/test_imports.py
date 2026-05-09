"""Smoke test to verify the package can be imported."""


def test_loom_imports() -> None:
    """Verify that the main loom package can be imported."""
    import loom

    assert hasattr(loom, "__version__")
    assert loom.__version__ == "0.1.0"


def test_cli_imports() -> None:
    """Verify that the CLI module can be imported."""
    from loom.cli import app

    assert app is not None


def test_state_module_imports() -> None:
    """Verify that state module can be imported."""
    import loom.state

    assert loom.state is not None


def test_config_module_imports() -> None:
    """Verify that config module can be imported."""
    import loom.config

    assert loom.config is not None


def test_llm_module_imports() -> None:
    """Verify that LLM module can be imported."""
    import loom.llm

    assert loom.llm is not None


def test_agents_module_imports() -> None:
    """Verify that agents module can be imported."""
    import loom.agents

    assert loom.agents is not None


def test_graph_module_imports() -> None:
    """Verify that graph module can be imported."""
    import loom.graph

    assert loom.graph is not None


def test_sandbox_module_imports() -> None:
    """Verify that sandbox module can be imported."""
    import loom.sandbox

    assert loom.sandbox is not None
