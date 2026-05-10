# FILE_STRUCTURE — Project Tree

```
loom/
├── README.md                          # User-facing readme
├── LICENSE                            # MIT
├── pyproject.toml                     # Package metadata + deps
├── requirements.txt                   # Pinned via pip-compile
├── requirements-dev.txt               # Dev deps
├── .env.example                       # Template for API keys
├── .gitignore
├── .ruff.toml                         # Lint config
├── loom.example.toml            # Example user config
│
├── docker/                            # Sandbox + dashboard images
│   ├── sandbox.Dockerfile             # Pre-built test runner image
│   └── dashboard.Dockerfile           # Web dashboard image (optional)
│
├── docs/                              # All documentation (these docs)
│   ├── README.md                      # Index
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── GRAPH_DESIGN.md
│   ├── AGENTS.md
│   ├── PROMPTS.md
│   ├── DATA_MODELS.md
│   ├── TECH_STACK.md
│   ├── MODEL_SELECTION.md
│   ├── SANDBOX.md
│   ├── FILE_STRUCTURE.md
│   ├── UI_SPEC.md
│   ├── TESTING_STRATEGY.md
│   ├── DEMO_SCENARIOS.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── PROGRESS.md
│   └── images/                        # Generated graph diagrams, screenshots
│
├── src/loom/                    # Main package
│   ├── __init__.py                    # exports build(), LoomConfig
│   ├── __main__.py                    # python -m loom → CLI
│   │
│   ├── cli/                           # CLI entry points
│   │   ├── __init__.py
│   │   ├── app.py                     # Typer app, command registration
│   │   ├── commands/
│   │   │   ├── build.py               # `loom build "..."`
│   │   │   ├── ui.py                  # `loom ui`
│   │   │   ├── sandbox.py             # `loom sandbox build/test/shell`
│   │   │   ├── resume.py              # `loom resume <thread_id>`
│   │   │   └── config.py              # `loom config show/edit`
│   │   └── tui.py                     # Textual live progress UI
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   ├── loader.py                  # CLI flags > env > toml > defaults
│   │   ├── models.py                  # LoomConfig, LLMConfig
│   │   └── defaults.py                # built-in defaults, profile presets
│   │
│   ├── state/
│   │   ├── __init__.py
│   │   ├── models.py                  # AgentState, all artifacts
│   │   ├── reducers.py                # add_messages, merge_dicts, etc.
│   │   └── enums.py                   # Phase, AgentRole, Priority
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── factory.py                 # get_llm_for_role()
│   │   ├── providers.py               # provider-specific configs
│   │   ├── retry.py                   # tenacity policies
│   │   └── cost.py                    # token → USD calculator
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py                    # build_agent() factory
│   │   ├── prompts/
│   │   │   ├── __init__.py
│   │   │   ├── product_manager.py
│   │   │   ├── architect.py
│   │   │   ├── frontend_dev.py
│   │   │   ├── backend_dev.py
│   │   │   ├── qa_engineer.py
│   │   │   ├── devops_engineer.py
│   │   │   ├── supervisor.py          # for optional LLM supervisor
│   │   │   └── local.py               # concise variants for small Ollama models
│   │   ├── product_manager.py         # node function
│   │   ├── architect.py
│   │   ├── frontend_dev.py
│   │   ├── backend_dev.py
│   │   ├── qa_engineer.py
│   │   ├── devops_engineer.py
│   │   └── project_manager.py         # supervisor (deterministic)
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── sandbox_exec.py            # @tool wrapping SandboxRunner
│   │   ├── web_search.py              # Tavily wrapper (optional)
│   │   └── file_writer.py             # post-graph file materialization
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── builder.py                 # builds the StateGraph
│   │   ├── routing.py                 # decide_next_phase(), route_after_pm()
│   │   ├── parallel.py                # route_to_devs() Send fan-out
│   │   └── checkpoint.py              # SqliteSaver wrapper
│   │
│   ├── sandbox/
│   │   ├── __init__.py
│   │   ├── runner.py                  # SandboxRunner (Docker)
│   │   ├── subprocess_runner.py       # SubprocessRunner (unsafe fallback)
│   │   └── factory.py                 # get_sandbox()
│   │
│   ├── output/
│   │   ├── __init__.py
│   │   ├── writer.py                  # writes state.code_files + devops_files
│   │   ├── slugify.py                 # safe path generation
│   │   └── readme.py                  # generates README.md for output project
│   │
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── logging.py                 # structlog setup
│   │   ├── events.py                  # Event emitter
│   │   ├── streaming.py               # astream_events → typed events
│   │   └── langsmith.py               # optional LangSmith integration
│   │
│   ├── server/                        # Web dashboard backend
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app
│   │   ├── routes/
│   │   │   ├── builds.py              # POST /api/build, GET /api/runs
│   │   │   ├── artifacts.py           # GET /api/artifacts/{run_id}
│   │   │   └── ws.py                  # /ws/{run_id} WebSocket
│   │   ├── models.py                  # API request/response models
│   │   └── runner.py                  # async background tasks
│   │
│   └── core.py                        # build() — main public API
│
├── frontend/                          # Web dashboard React app
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── api/
│   │   │   ├── client.ts              # axios instance
│   │   │   └── ws.ts                  # WebSocket hook
│   │   ├── components/
│   │   │   ├── GraphView.tsx          # reactflow viz of agent graph
│   │   │   ├── AgentNode.tsx          # custom node component
│   │   │   ├── BuildForm.tsx          # input prompt
│   │   │   ├── ArtifactPanel.tsx      # tabs: PRD / Architecture / Code / Tests
│   │   │   ├── CostMeter.tsx          # live token/cost display
│   │   │   └── EventLog.tsx           # streaming event timeline
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   ├── Build.tsx              # active build view
│   │   │   └── Runs.tsx               # past runs list
│   │   ├── store/
│   │   │   └── buildStore.ts          # zustand store
│   │   └── styles/
│   │       └── globals.css
│   └── public/
│       └── favicon.svg
│
├── tests/                             # Tests for Loom itself
│   ├── conftest.py                    # fixtures
│   ├── unit/
│   │   ├── test_state.py
│   │   ├── test_routing.py
│   │   ├── test_prompts.py
│   │   ├── test_llm_factory.py
│   │   ├── test_output_parsers.py
│   │   └── test_sandbox.py
│   ├── integration/
│   │   ├── test_graph_linear.py       # full happy path with mocked LLMs
│   │   ├── test_graph_parallel.py     # Send API fan-out
│   │   ├── test_graph_retry.py        # QA failure → dev retry
│   │   ├── test_interrupts.py         # HIL pause/resume
│   │   └── test_sandbox_real.py       # actual Docker exec (slow, opt-in)
│   ├── e2e/
│   │   └── test_demo_scenarios.py     # @pytest.mark.slow + real LLMs
│   ├── fixtures/
│   │   ├── mock_llm.py                # FakeListChatModel responses
│   │   ├── sample_prds.py
│   │   └── sample_architectures.py
│   └── snapshots/                     # pytest-snapshot files
│
├── examples/                          # Pre-built demo scenarios
│   ├── 01_todo_app.md                 # input + expected output description
│   ├── 02_url_shortener.md
│   ├── 03_book_review_site.md
│   ├── 04_csv_to_json_cli.md
│   ├── 05_kanban_board.md
│   └── cached_runs/                   # pre-recorded successful runs for reliable demos
│       ├── todo_app_state.json
│       └── ...
│
├── scripts/
│   ├── build_sandbox.sh               # docker build wrapper
│   ├── compile_deps.sh                # pip-compile
│   └── generate_graph_diagram.py      # exports docs/images/graph.png
│
└── .github/
    └── workflows/
        ├── ci.yml                     # lint + test on PR
        ├── sandbox_image.yml          # build & publish sandbox image to ghcr
        └── release.yml                # PyPI on tag
```

## File Count Summary

| Layer | Files | LoC estimate |
|---|---|---|
| Core (agents, graph, state) | ~30 | ~2500 |
| Tools + sandbox | ~8 | ~600 |
| CLI | ~10 | ~600 |
| Server (API) | ~8 | ~500 |
| Frontend (React) | ~20 | ~1500 |
| Tests | ~25 | ~2000 |
| Docs | 16 | n/a |
| **Total Python+TS** | ~100 | ~7700 |

## Critical Files (touch these first)

When implementing, the order is:

1. `src/loom/state/models.py` — defines all types
2. `src/loom/agents/prompts/*` — all prompts
3. `src/loom/llm/factory.py` — LLM provider selection
4. `src/loom/agents/<each>.py` — node functions
5. `src/loom/graph/builder.py` — wires everything together
6. `src/loom/output/writer.py` — materializes files
7. `src/loom/cli/commands/build.py` — CLI entry
8. Tests for each layer

The web dashboard comes after the CLI works end-to-end.

## What Goes In `__init__.py` Files

Most `__init__.py` files re-export the public API of their module:

```python
# src/loom/__init__.py
from loom.core import build, BuildResult
from loom.config.models import LoomConfig, LLMConfig
from loom.state.models import AgentState, PRD, ArchitectureDoc

__all__ = ["build", "BuildResult", "LoomConfig", "LLMConfig",
           "AgentState", "PRD", "ArchitectureDoc"]
__version__ = "0.1.0"
```

Keep them thin — no logic, just re-exports.
