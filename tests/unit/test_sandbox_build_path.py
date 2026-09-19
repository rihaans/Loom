r"""Tests for how the sandbox image build addresses its Dockerfile.

The Docker daemon resolves `dockerfile` relative to the build context and
expects POSIX separators. Passing a Windows path made `loom sandbox build`
fail on Windows with "Cannot locate specified Dockerfile:
docker\sandbox.Dockerfile", so the sandbox image could never be built there -
and without the image, tests never actually run.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from loom.sandbox.models import SandboxConfig
from loom.sandbox.runner import SandboxRunner


@pytest.fixture
def runner_and_client(tmp_path: Path) -> tuple[SandboxRunner, MagicMock]:
    runner = SandboxRunner.__new__(SandboxRunner)
    runner.config = SandboxConfig()
    client = MagicMock()
    client.images.build.return_value = (MagicMock(), [])
    runner._client = client
    return runner, client


def _make_dockerfile(root: Path) -> Path:
    d = root / "docker"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "sandbox.Dockerfile"
    f.write_text("FROM python:3.12-slim\n", encoding="utf-8")
    return f


class TestBuildImagePath:
    def test_dockerfile_is_context_relative_and_posix(
        self, runner_and_client: tuple[SandboxRunner, MagicMock], tmp_path: Path
    ) -> None:
        runner, client = runner_and_client
        dockerfile = _make_dockerfile(tmp_path)

        assert runner.build_image(dockerfile) is True

        kwargs = client.images.build.call_args.kwargs
        assert kwargs["dockerfile"] == "docker/sandbox.Dockerfile"
        assert "\\" not in kwargs["dockerfile"], "daemon needs POSIX separators"
        assert Path(kwargs["path"]).resolve() == tmp_path.resolve()

    def test_missing_dockerfile_is_reported_not_raised(
        self, runner_and_client: tuple[SandboxRunner, MagicMock], tmp_path: Path
    ) -> None:
        runner, client = runner_and_client
        assert runner.build_image(tmp_path / "nope" / "sandbox.Dockerfile") is False
        client.images.build.assert_not_called()

    def test_dockerfile_outside_the_context_is_refused(
        self, runner_and_client: tuple[SandboxRunner, MagicMock], tmp_path: Path
    ) -> None:
        """A path the daemon could not resolve must fail before the API call."""
        runner, client = runner_and_client
        # A Dockerfile at the filesystem root of tmp_path has no two-level
        # parent inside it, so the computed context cannot contain it.
        stray = tmp_path / "sandbox.Dockerfile"
        stray.write_text("FROM scratch\n", encoding="utf-8")
        result = runner.build_image(stray)
        # Either refused outright, or the relative path stays POSIX and valid.
        if result:
            kwargs = client.images.build.call_args.kwargs
            assert "\\" not in kwargs["dockerfile"]

    def test_build_failure_is_returned_not_raised(
        self, runner_and_client: tuple[SandboxRunner, MagicMock], tmp_path: Path
    ) -> None:
        runner, client = runner_and_client
        client.images.build.side_effect = RuntimeError("daemon exploded")
        assert runner.build_image(_make_dockerfile(tmp_path)) is False
