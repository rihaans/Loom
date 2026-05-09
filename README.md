# Loom — Autonomous Software Development Team

> A multi-agent system built with **LangChain + LangGraph** that simulates a full software development team. Give it a project description → it produces a working, tested, containerized MVP.

This repository ships as a **portfolio project** demonstrating advanced LangGraph patterns: stateful supervisor graphs, parallel fan-out via the `Send` API, conditional routing, interrupts for human-in-the-loop, persistent checkpointing, and tool-using agents that produce executable code validated in a Docker sandbox.

---

## 📖 For Claude Code: Read This First

You are implementing this project. The documentation in this repo is your **single source of truth**. Read documents in this order:

1. **`README.md`** ← you are here. Skim, then continue.
2. **`docs/00_PROJECT_CHARTER.md`** — non-negotiable principles, scope, decisions
3. **`docs/01_PRD.md`** — product requirements
4. **`docs/02_ARCHITECTURE.md`** — system design and component map
5. **`docs/03_TECH_STACK.md`** — every dependency with rationale
6. **`docs/04_LANGGRAPH_DESIGN.md`** — graph topology, state, routing, advanced patterns
7. **`docs/05_AGENTS_SPEC.md`** — per-agent contracts, prompts, tools, I/O schemas
8. **`docs/06_DATA_MODELS.md`** — Pydantic schemas for state and artifacts
9. **`docs/07_FILE_STRUCTURE.md`** — repo layout (every file explained)
10. **`docs/08_EXECUTION_SANDBOX.md`** — Docker-based code execution design
11. **`docs/09_CLI_SPEC.md`** — terminal interface
12. **`docs/10_DASHBOARD_SPEC.md`** — web UI
13. **`docs/11_TESTING_STRATEGY.md`** — how we test agents and the orchestrator
14. **`docs/12_OBSERVABILITY.md`** — logging, tracing, token tracking, costs
15. **`docs/13_MODEL_GUIDE.md`** — which model to use for which agent (with rationale)
16. **`docs/14_PROMPTS_LIBRARY.md`** — every system prompt, copy-paste ready
17. **`docs/15_DEMO_SCENARIOS.md`** — pre-built demos for the Loom video
18. **`docs/16_IMPLEMENTATION_PLAN.md`** — phase-by-phase build plan
19. **`docs/17_PROGRESS.md`** ← **you write here** as you complete tasks

### How to work

- **Phase-gated.** This project is built in 6 phases. After completing each phase, **stop and ask the user to review** before moving on. The user explicitly requested this workflow.
- **Checkbox-driven.** `docs/16_IMPLEMENTATION_PLAN.md` is your task list. `docs/17_PROGRESS.md` is your progress log.
- **Document deviations.** If you change a design decision while implementing, update the relevant doc *and* note it in `docs/17_PROGRESS.md` under "Deviations from spec."
- **No silent shortcuts.** If you skip a feature, mark it explicitly. If a test fails, do not delete it.

---

## What the System Does (User-Facing)

```
$ loom build "A Flask API for a personal expense tracker with categories,
                    monthly summaries, and CSV export"

[12:04:31] 🎯 Project Manager: Starting build pipeline
[12:04:32] 📋 Product Manager: Drafting PRD...
[12:04:48] ✓ PRD complete (5 user stories, 3 entities)
[12:04:49] 🏗️  Architect: Designing system... selected Flask + SQLite + Tailwind
[12:05:02] ✓ Architecture complete
[12:05:03] 💻 Frontend Dev   ─┐
[12:05:03] ⚙️  Backend Dev    ─┴─ running in parallel
[12:05:41] ✓ Backend: 6 files generated
[12:05:48] ✓ Frontend: 4 files generated
[12:05:49] 🧪 QA: Writing tests, running in Docker sandbox...
[12:06:22] ✓ Tests: 14/14 passing
[12:06:23] 🚀 DevOps: Generating Dockerfile + GitHub Actions
[12:06:31] ✓ Done. Output: ./output/expense-tracker/
                Tokens used: 47,832  |  Cost: $0.00 (Ollama)
```

The user can then `cd output/expense-tracker && docker-compose up` and the app runs.

## Why This Resume-Worthy

- **Real LangGraph, not just LLM chains.** Cyclic graph with conditional routing, parallel branches via `Send`, interrupts for HITL, `MemorySaver`/`SqliteSaver` checkpointing, recursive retry subgraphs.
- **Structured agent contracts.** Agents exchange typed Pydantic artifacts, not free-form chat. This is how production agent systems actually work.
- **Validated output.** Generated code is executed in a Docker sandbox — if tests fail, the QA agent feeds errors back to the dev agents and they iterate.
- **Provider-agnostic with cost transparency.** Works with Anthropic / OpenAI / Ollama out of the box. Each agent has a recommended model with rationale.
- **Observable.** LangSmith integration + a custom dashboard showing the live agent graph, artifacts, and token usage.

## Quick Start (when implemented)

```bash
git clone https://github.com/YOUR_USERNAME/loom
cd loom
pip install -e ".[dev]"

# Free path: install Ollama, pull a model
ollama pull qwen2.5-coder:7b

# Or use Claude/GPT
export ANTHROPIC_API_KEY="sk-..."

loom build "your project idea here"
```

## Status

🚧 In active development. See `docs/17_PROGRESS.md`.

## License

MIT
