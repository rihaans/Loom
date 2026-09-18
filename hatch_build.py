"""Build hook that bundles the dashboard into the wheel when it has been built.

`frontend/dist` is a build artifact and is not committed, so a plain
`[tool.hatch.build.targets.wheel.force-include]` entry would make the wheel
build fail on a fresh clone. This hook includes the dashboard when it exists
and quietly skips it when it doesn't - `loom ui` then serves the API only and
tells the user how to build the frontend.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class DashboardBuildHook(BuildHookInterface):
    """Include `frontend/dist` as `loom/dashboard` when it is present."""

    PLUGIN_NAME = "dashboard"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        dist = Path(self.root) / "frontend" / "dist"
        if not (dist / "index.html").is_file():
            self.app.display_waiting(
                "frontend/dist not built - wheel will not include the dashboard "
                "(build it with: cd frontend && npm install && npm run build)"
            )
            return

        force_include = build_data.setdefault("force_include", {})
        force_include[str(dist)] = "loom/dashboard"
        self.app.display_info(f"Bundling dashboard from {dist}")
