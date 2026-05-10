# Loom — Documentation Index

> A multi-agent system built on **LangChain + LangGraph** that takes a natural-language project description and produces a working, tested, containerized MVP. Six specialized AI agents collaborate as a real software team would.

This folder is the **single source of truth** for the Loom project. Phases 0–8.7 are implemented and tested (~11.5K LoC, 259 passing tests). Phase 9 (the new chat REPL entry point) is next.

---

## 🚀 What Claude Code Should Do

You are about to extend this project with the chat REPL feature (Phase 9). Here is your workflow:

1. **First, run the migration in `_MIGRATION.md`** if it's still present. That doc moves the old `docs/` and `docs/new features/` into this consolidated `.docs/` folder, then deletes itself.
2. **Read this README**, then `PROGRESS.md` to see current status.
3. **Read `IMPLEMENTATION_PLAN.md` end-to-end** before writing code. The Phase 9 plan has three internal review gates (9.A, 9.B, 9.C) — stop at each.
4. **Read the spec docs in the order given in the doc map below.**
5. **Update `PROGRESS.md` after every meaningful task.** Mark `[ ]` → `[x]`. Add notes when something's non-obvious.
6. **Stop at every phase boundary** and ask for review.
7. **Never break the legacy `loom build "..."` path.** Phase 9 *adds*; it does not replace.

---

## 📚 Documentation Map

### Build planning & status

| File | Purpose |
|---|---|
| [`PROGRESS.md`](./PROGRESS.md) | **Live task tracker — update this as you build** |
| [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) | Phase-by-phase build order with review gates |

### Core architecture (Phases 0–8 reference)

| File | Purpose |
|---|---|
| [`PRD.md`](./PRD.md) | Product Requirements — what we're building and why |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | System architecture, layers, request flow |
| [`GRAPH_DESIGN.md`](./GRAPH_DESIGN.md) | The LangGraph state machine (the core of the project) |
| [`AGENTS.md`](./AGENTS.md) | Each agent's role, inputs, outputs, tools, behaviors |
| [`PROMPTS.md`](./PROMPTS.md) | All system prompts (copy-paste ready) |
| [`DATA_MODELS.md`](./DATA_MODELS.md) | Pydantic models — source of truth for inter-agent contracts |
| [`TECH_STACK.md`](./TECH_STACK.md) | Every dependency, version pin, why it's chosen |
| [`MODEL_SELECTION.md`](./MODEL_SELECTION.md) | Which LLM for which agent |
| [`SANDBOX.md`](./SANDBOX.md) | Docker-based code execution sandbox |
| [`FILE_STRUCTURE.md`](./FILE_STRUCTURE.md) | Project tree with every file's purpose |
| [`UI_SPEC.md`](./UI_SPEC.md) | CLI + Web dashboard specification |
| [`TESTING_STRATEGY.md`](./TESTING_STRATEGY.md) | How we test agents, the graph, and the system |
| [`DEMO_SCENARIOS.md`](./DEMO_SCENARIOS.md) | 5 demo project ideas to ship with the repo |

### Differentiator features (Phases 8.5–8.7, all shipped)

| File | Purpose |
|---|---|
| [`MEMORY_SYSTEM.md`](./MEMORY_SYSTEM.md) | Self-learning across builds via vector retrieval |
| [`PLAN_COMMAND.md`](./PLAN_COMMAND.md) | `loom plan "..."` — non-interactive build preview |
| [`ADR_GENERATION.md`](./ADR_GENERATION.md) | Auto-write Architectural Decision Records |

### Phase 9 — Chat REPL (the new primary entry point)

| File | Purpose |
|---|---|
| [`CHAT_INTERFACE.md`](./CHAT_INTERFACE.md) | The new `loom` (no args) chat REPL — full spec |
| [`CONVERSATIONAL_AGENTS.md`](./CONVERSATIONAL_AGENTS.md) | How PM and Architect become multi-turn |

---

## 🎯 Why This Project

Built as a portfolio piece to demonstrate mastery of:
- **LangGraph state machines** — cyclic graphs, conditional routing, parallel execution, interrupts
- **LangChain agent patterns** — structured output, tool use, streaming, multi-turn conversations
- **Multi-agent orchestration** — supervisor pattern, artifact-passing, retry logic
- **Real software workflows** — PRD → design → code → test → deploy
- **Production engineering** — Docker sandboxing, observability, cost tracking, error recovery
- **Self-improving systems** — vector-based memory that makes builds better over time
- **Conversational UX** — the chat REPL is what makes Loom feel like a teammate

---

## 🧠 The Two Entry Points

### `loom` (chat REPL — the primary, recommended interface)

```
$ loom

  ╭─ Loom — your AI software team ────────────────────────╮
  │ Type your idea, or /help for commands.                 │
  ╰────────────────────────────────────────────────────────╯

  You ▸ build me an expense tracker

  📋 Product Manager
  Happy to help! A couple of questions:
    • Personal use, or shared with a partner?
    • Receipt photo uploads, or just text entry?
    • Reporting needs — monthly / category / CSV?

  You ▸ personal, just text, monthly + CSV

  📋 Product Manager
  ⠋ drafting PRD...

  [PRD panel rendered]

  Look good? (yes / edit / restart)
```

You converse with each agent. PM clarifies requirements. Architect proposes a stack. Devs run in parallel. QA tests in Docker. DevOps containerizes. You can interrupt, change direction, or accept defaults at any point.

See `CHAT_INTERFACE.md` for the full spec.

### `loom build "..."` (one-shot — for CI / scripts)

```bash
loom build "A todo app with auth and a clean React UI"
loom build "..." --interactive    # pause at phase gates
loom plan "..."                   # preview-only, no code generation
```

The pre-Phase-9 entry point. Still fully supported. Used when you don't want a conversation — automation, batch builds, scripted demos.

---

## 🧠 The 30-Second Pitch

```
User: "Build me a URL shortener with analytics"
        │
        ▼
┌──────────────────────────────────────────────────┐
│  📋 Product Manager (multi-turn chat)            │
│  Asks clarifying questions, drafts PRD on confirm │
└──────────────────────────────────────────────────┘
        │
        ▼
  🧠 Memory Retriever → similar past builds
        │
        ▼
  🏗️  Architect (proposes, accepts revisions)
        │
        ▼
  ┌─────────────────┬─────────────────┐  ← Send API parallel fan-out
  💻 Frontend Dev   ⚙️  Backend Dev    │
  └─────────────────┴─────────────────┘
        │
        ▼
  🧪 QA Engineer → Tests in Docker sandbox
        │
        ▼ (if tests fail → loop back to devs, max 2 retries)
        ▼
  🚀 DevOps → Dockerfile + docker-compose + GitHub Actions
        │
        ▼
  📝 ADR Generator → Architecture decision records
        ▼
  💾 Memory Persister → save to vector DB
        ▼
  📦 Working MVP delivered
```

---

## ⚡ Quick Start

```bash
# Install
pip install -e ".[dev,memory]"

# Pick your LLM (defaults to Ollama if no API key set)
export ANTHROPIC_API_KEY="..."   # recommended
# or
export OPENAI_API_KEY="..."
# or
ollama pull qwen2.5-coder:7b

# Start a chat session
loom

# Or run non-interactively
loom build "your idea here"
```

---

## 📝 License

MIT
