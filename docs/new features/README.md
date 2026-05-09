# Loom — Autonomous Software Development Team

> A multi-agent system built on **LangChain + LangGraph** that takes a natural-language project description and produces a working, tested, containerized MVP. Six specialized AI agents collaborate as a real software team would.

---

## 🚀 What Claude Code Should Do

You are about to implement this project. Here is your workflow:

1. **Read every doc in this directory in order.** They are organized for a reason.
2. **Open `PROGRESS.md`.** That is your task list. Mark items as you complete them.
3. **Stop after each phase boundary** (described in `IMPLEMENTATION_PLAN.md`). The user wants to review.
4. **Never skip the schema/state design.** All agents communicate via typed Pydantic state. Get this wrong and everything else breaks.
5. **The user is advanced** with LangChain/LangGraph. Use challenging patterns: `Send` API for parallelism, conditional edges, interrupts, checkpointing, subgraphs. Don't dumb it down.
6. **Default to Ollama** for local dev (no API budget). Make it pluggable so the user can drop in Claude/OpenAI keys later.

---

## 📚 Documentation Map

### Core specs (read first, in this order)

| # | File | Purpose |
|---|---|---|
| 00 | [`README.md`](./README.md) | This file — overview |
| 01 | [`PRD.md`](./PRD.md) | Product Requirements — what we're building and why |
| 02 | [`ARCHITECTURE.md`](./ARCHITECTURE.md) | System architecture, layers, request flow |
| 03 | [`GRAPH_DESIGN.md`](./GRAPH_DESIGN.md) | The LangGraph state machine (the core of the project) |
| 04 | [`AGENTS.md`](./AGENTS.md) | Each agent's role, inputs, outputs, tools, behaviors |
| 05 | [`PROMPTS.md`](./PROMPTS.md) | All system prompts (copy-paste ready) |
| 06 | [`DATA_MODELS.md`](./DATA_MODELS.md) | Pydantic models — the source of truth for inter-agent contracts |
| 07 | [`TECH_STACK.md`](./TECH_STACK.md) | Every dependency, version pin, why it's chosen |
| 08 | [`MODEL_SELECTION.md`](./MODEL_SELECTION.md) | Which LLM for which agent, with cost/quality tradeoffs |
| 09 | [`SANDBOX.md`](./SANDBOX.md) | Docker-based code execution sandbox design |
| 10 | [`FILE_STRUCTURE.md`](./FILE_STRUCTURE.md) | Full project tree with every file's purpose |
| 11 | [`UI_SPEC.md`](./UI_SPEC.md) | CLI + Web dashboard specification |
| 12 | [`TESTING_STRATEGY.md`](./TESTING_STRATEGY.md) | How we test agents, the graph, and the system |
| 13 | [`DEMO_SCENARIOS.md`](./DEMO_SCENARIOS.md) | 5 demo project ideas to ship with the repo |

### Differentiator features (Phase 8.5–8.7 — implement after core pipeline is stable)

| # | File | Purpose |
|---|---|---|
| 14 | [`MEMORY_SYSTEM.md`](./MEMORY_SYSTEM.md) | Self-learning across builds via vector retrieval — the killer feature |
| 15 | [`PLAN_COMMAND.md`](./PLAN_COMMAND.md) | `loom plan` — cheap, abortable preview before full build |
| 16 | [`ADR_GENERATION.md`](./ADR_GENERATION.md) | Auto-write Architectural Decision Records into output projects |

### Build tracking

| # | File | Purpose |
|---|---|---|
| 17 | [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) | Phased build order with phase-gate reviews |
| 18 | [`PROGRESS.md`](./PROGRESS.md) | **Your live task tracker — update as you build** |

---

## 🎯 Why This Project

Built as a portfolio piece to demonstrate mastery of:
- **LangGraph state machines** — cyclic graphs, conditional routing, parallel execution, interrupts
- **LangChain agent patterns** — structured output, tool use, streaming
- **Multi-agent orchestration** — supervisor pattern, artifact-passing, retry logic
- **Real software workflows** — PRD → design → code → test → deploy
- **Production engineering** — Docker sandboxing, observability, cost tracking, error recovery
- **Self-improving systems** — vector-based memory that makes builds better over time (Phase 8.5)

---

## 🧠 The 30-Second Pitch

```
User: "Build me a URL shortener with analytics"
        │
        ▼
┌──────────────────────────────────────────────────┐
│  🎯 Project Manager (LangGraph supervisor)        │
│  Routes work, handles retries, tracks progress    │
└──────────────────────────────────────────────────┘
        │
        ▼
  📋 Product Manager → PRD + user stories
        ▼
  🧠 Memory Retriever → similar past builds (Phase 8.5)
        ▼
  🏗️  Architect      → Tech stack + system design
        ▼
  ┌─────────────────┬─────────────────┐  ← Send API parallel fan-out
  💻 Frontend Dev   ⚙️  Backend Dev    │
  ↓                 ↓                  │
  React code        FastAPI code       │
  └─────────────────┴─────────────────┘
        ▼
  🧪 QA Engineer   → Tests + executes them in Docker
        ▼
  (if tests fail → loop back to devs with error context, max 2 retries)
        ▼
  🚀 DevOps        → Dockerfile, docker-compose, GitHub Actions CI
        ▼
  📝 ADR Generator → Architectural Decision Records (Phase 8.7)
        ▼
  💾 Memory Persister → save to vector DB for future builds (Phase 8.5)
        ▼
  📦 Working MVP delivered
```

---

## ⚡ Quick Start (after implementation)

```bash
# Install
pip install -e ".[dev]"

# Pick your LLM (defaults to Ollama if none set)
export ANTHROPIC_API_KEY="..."   # recommended
# or
export OPENAI_API_KEY="..."
# or just have ollama running locally

# Plan first (cheap preview), then build
loom plan "A todo app with auth and a clean React UI"
# review plan in terminal, press B to build

# Or build immediately
loom build "..."

# Watch via web dashboard
loom ui
```

---

## 📝 License

MIT
