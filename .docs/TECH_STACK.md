# TECH_STACK — Dependencies & Why

## Core (mandatory)

| Package | Version | Purpose |
|---|---|---|
| `python` | ≥3.11 | Pattern matching, better typing, Pydantic 2 perf |
| `langchain` | ^0.3 | Prompt templates, runnables, output parsers |
| `langchain-core` | ^0.3 | Base abstractions |
| `langchain-anthropic` | ^0.3 | Claude integration |
| `langchain-openai` | ^0.2 | GPT integration |
| `langchain-ollama` | ^0.2 | Ollama integration |
| `langgraph` | ^0.2 | THE state machine library |
| `langgraph-checkpoint-sqlite` | latest | Durable checkpointing |
| `pydantic` | ^2.9 | Schemas + validation |
| `pydantic-settings` | ^2.5 | Config from env/files |

## CLI

| Package | Version | Purpose |
|---|---|---|
| `typer` | ^0.12 | CLI framework (built on Click) |
| `rich` | ^13.8 | Beautiful terminal output |
| `textual` | ^0.83 | TUI for live progress |
| `tomli-w` | ^1.0 | Writing config files |

## Web Dashboard

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | ^0.115 | API server |
| `uvicorn[standard]` | ^0.32 | ASGI server |
| `websockets` | ^13.1 | WebSocket support |
| `python-multipart` | ^0.0.12 | File uploads |

The frontend is a separate React app:

| Package | Purpose |
|---|---|
| `react` ^18 | UI |
| `vite` ^5 | Bundler/dev server |
| `@xyflow/react` ^12 | Graph visualization (formerly reactflow) |
| `tailwindcss` ^3 | Styling |
| `zustand` ^4 | State management |
| `axios` ^1 | HTTP client |

## Observability

| Package | Version | Purpose |
|---|---|---|
| `structlog` | ^24.4 | Structured logging |
| `langsmith` | ^0.1 | Optional tracing (opt-in) |

## Sandboxing

| Package | Version | Purpose |
|---|---|---|
| `docker` | ^7.1 | Python Docker SDK |

(Docker Engine itself must be installed on the host — not a Python dep.)

## Tools (for agents)

| Package | Version | Purpose |
|---|---|---|
| `tavily-python` | ^0.5 | Web search for Architect (optional) |
| `tenacity` | ^9.0 | Retry decorators |

## Dev / Test

| Package | Version | Purpose |
|---|---|---|
| `pytest` | ^8.3 | Testing |
| `pytest-asyncio` | ^0.24 | Async test support |
| `pytest-cov` | ^5.0 | Coverage |
| `ruff` | ^0.6 | Linting + formatting |
| `mypy` | ^1.11 | Type checking |
| `respx` | ^0.21 | HTTP mocking |
| `freezegun` | ^1.5 | Time mocking |

## pyproject.toml

```toml
[project]
name = "loom"
version = "0.1.0"
description = "Autonomous software development team built on LangGraph"
requires-python = ">=3.11"
dependencies = [
    "langchain~=0.3.0",
    "langchain-core~=0.3.0",
    "langchain-anthropic~=0.3.0",
    "langchain-openai~=0.2.0",
    "langchain-ollama~=0.2.0",
    "langgraph~=0.2.0",
    "langgraph-checkpoint-sqlite",
    "pydantic~=2.9",
    "pydantic-settings~=2.5",
    "typer~=0.12",
    "rich~=13.8",
    "textual~=0.83",
    "fastapi~=0.115",
    "uvicorn[standard]~=0.32",
    "websockets~=13.1",
    "structlog~=24.4",
    "docker~=7.1",
    "tenacity~=9.0",
    "tomli-w~=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest~=8.3",
    "pytest-asyncio~=0.24",
    "pytest-cov~=5.0",
    "ruff~=0.6",
    "mypy~=1.11",
    "respx~=0.21",
    "freezegun~=1.5",
]
search = ["tavily-python~=0.5"]
tracing = ["langsmith~=0.1"]

[project.scripts]
loom = "loom.cli:app"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "ASYNC", "RUF"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

## Pinning Strategy

- **Core LangChain/LangGraph**: tilde-pin (`~=0.2.0`) — these break often
- **Pydantic**: caret (`^2.9`) — stable enough
- **CLI/UI libs**: caret — minor bumps are safe
- **Dev tools**: latest stable

Run `pip-compile` to lock to a `requirements.txt` for reproducible CI.

## Why Not...

| Alternative | Why we didn't pick it |
|---|---|
| CrewAI | Less control over state, weaker primitives for cyclic graphs |
| AutoGen | Conversation-centric model doesn't fit artifact-passing pattern |
| Pure LangChain agents | No native graph structure, can't express our retry loop cleanly |
| OpenAI Swarm | Too new, less mature, limited provider support |
| Custom orchestration | Would reinvent LangGraph poorly |
