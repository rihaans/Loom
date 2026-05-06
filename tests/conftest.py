"""Pytest fixtures and configuration."""

import pytest


@pytest.fixture
def sample_description() -> str:
    """Return a sample project description for testing."""
    return "A simple todo app with CRUD operations"
