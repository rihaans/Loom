# Contributing to Loom

Thanks for taking a look. This document covers how to get set up, what the
project expects from a change, and where things live.

## Getting set up

```bash
git clone https://github.com/rihaans/Loom.git
cd Loom
pip install -e ".[dev]"
loom doctor          # confirms Python, an LLM provider, and Docker
```

You need **Python 3.11+** and at least one LLM provider:

| Provider | Setup |
|---|---|
| Ollama (free, local) | `ollama pull llama3.1:8b` |
| Anthropic | `export ANTHROPIC_API_KEY="sk-ant-..."` |
| OpenAI | `export OPENAI_API_KEY="sk-..."` |

Docker is optional for development but **required to run the QA sandbox**.
Without it, no tests are actually executed and reports are marked unverified.

```bash
loom sandbox build   # one-time, ~2 min
```

## Before you open a PR

CI runs these three; run them locally first:

```bash
ruff check .
ruff format --check .
mypy src/loom
pytest
```

All four must be clean. `pytest` alone should take well under a minute — the
suite uses mocked LLMs and makes no network calls.

## What a good change looks like

- **Tests come with it.** Unit tests for node logic under `tests/unit/`,
  pipeline behaviour under `tests/integration/`. Mock the LLM; never hit a
  real provider in a test.
- **Types are complete.** `mypy` runs with `disallow_untyped_defs`, so every
  function needs annotations.
- **Never overstate a result.** This matters more here than in most projects:
  Loom reports cost, test outcomes, and coverage, and every one of those has
  a failure mode where it can look confident and be wrong. If something wasn't
  measured, say so — see `TestReport.is_stub` and `pricing_status()` for the
  pattern.
- **Architecturally significant decisions get an ADR** in `docs/adrs/`. Copy
  the shape of an existing one.

## Adding an agent

1. Prompt in `src/loom/agents/prompts/<agent>.py`
2. Async node function in `src/loom/agents/<agent>.py`, returning a state-update dict
3. Wire it into `src/loom/graph/builder.py`
4. Conditional routing (if any) in `src/loom/graph/routing.py`
5. Tests in `tests/unit/test_<agent>.py`
6. An ADR if the decision is non-obvious

## Project layout

```
src/loom/
├── adr/              ← architectural decision records
├── agents/
│   ├── architect.py
│   ├── backend_dev.py
│   ├── frontend_dev.py
│   ├── product_manager.py    ← chat-mode + legacy paths
│   ├── reviewer.py           ← Code Reviewer (generator–critic, Command handoffs)
│   ├── qa_engineer.py
│   ├── devops_engineer.py
│   ├── memory_retrieve.py
│   ├── memory_persist.py
│   ├── base.py               ← build_agent_chain + structured-output binding
│   └── prompts/              ← all system prompts
├── cli/
│   ├── app.py                ← Typer CLI entry point
│   ├── chat/
│   │   ├── session.py        ← REPL loop driver
│   │   ├── renderer.py       ← rich-based output
│   │   ├── input.py          ← prompt_toolkit input
│   │   ├── commands.py       ← slash command parser
│   │   └── transcript.py     ← session persistence
│   └── tui.py                ← legacy Textual TUI
├── config/                   ← LoomConfig + per-agent LLM overrides
├── core.py                   ← public build/resume API
├── cost/                     ← cost estimation
├── graph/
│   ├── builder.py            ← StateGraph wiring
│   ├── routing.py            ← conditional edge functions
│   ├── parallel.py           ← Send API helpers
│   └── checkpoint.py         ← MemorySaver / SqliteSaver
├── llm/                      ← provider-agnostic LLM layer
├── memory/                   ← vector store + retrieval
├── observability/            ← logging, tracing, metrics
├── output/                   ← writes generated projects to disk
├── plan/                     ← cost preview without code generation
├── sandbox/                  ← Docker test runner
├── server/                   ← FastAPI dashboard backend
└── state/
    ├── enums.py              ← Phase, AgentRole, EventType, etc.
    ├── models.py             ← AgentState, PRD, ArchitectureDoc, etc.
    └── reducers.py           ← merge_dicts, merge_messages_dict, etc.

tests/
├── unit/                     ← agent + state + graph unit tests
└── integration/              ← end-to-end pipeline tests

docker/sandbox.Dockerfile     ← QA sandbox image
docs/adrs/                    ← architecture decision records
loom.example.toml             ← config template
pyproject.toml                ← deps + entry points + tooling
```

## Debugging

```bash
LOOM_CHAT_DEBUG=1 loom     # prints graph state transitions each turn
```

## Reporting bugs

Include the output of `loom doctor`, the provider and model you used, and the
full error. If it's a build-quality issue, the generated `output/<slug>/` tree
is the most useful thing you can attach.
