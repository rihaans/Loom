# Architecture

How Loom is put together: what it produces, the agents, the state machine they
run on, and the subsystems around them. For the reasoning behind specific
choices, see the [architecture decision records](adrs/).

---

## What Loom Does

```
You: "build me a CLI tool that converts markdown files to PDF"
                                  │
                                  ▼
   ┌──────────────────────────────────────────────────────┐
   │  📋 Product Manager  · multi-turn chat to scope       │
   │  🧠 Memory Retriever · context from past builds       │
   │  🏗  Architect       · proposes stack, you negotiate  │
   │  💻 Frontend Dev   ─┐                                 │
   │                     ├─ run in parallel via Send API   │
   │  ⚙  Backend Dev    ─┘                                 │
   │  🔍 Code Reviewer    · critiques code, then routes:   │
   │       ↳ defect → devs   ↳ design flaw → architect     │
   │       ↳ ok → QA      (generator–critic, bounded loop) │
   │  🧪 QA Engineer     · writes + runs tests in Docker   │
   │       ↓ (fail? feedback loop, max 2 retries)          │
   │  🚀 DevOps          · Dockerfile + docker-compose + CI│
   │  📝 ADR Generator   · architectural decision records  │
   │  💾 Memory Persister · saves build to vector store    │
   └──────────────────────────────────────────────────────┘
                                  │
                                  ▼
   ./output/markdown-to-pdf/
   ├── src/                  ← runnable code
   ├── tests/                ← passing tests
   ├── Dockerfile
   ├── docker-compose.yml
   ├── .github/workflows/    ← CI
   ├── docs/adrs/            ← decision records
   └── README.md             ← run instructions
```

You can `cd` into the output folder and `docker-compose up` to run the app immediately.

---

---

## The Agents

Each agent is a node in a stateful LangGraph state machine. They exchange typed Pydantic artifacts (PRDs, ArchitectureDocs, FileBundles, ReviewReports, TestReports), not free-form chat. Artifacts are produced with the model's **native structured-output mode** (tool/JSON calling) rather than parsing JSON out of free text — see [ADR 0001](adrs/0001-native-structured-output.md).

| # | Agent | Role | Input | Output |
|---|---|---|---|---|
| 1 | **Product Manager** 📋 | Multi-turn conversational scoping | Description + your chat replies | `PRD` (user stories, features, data entities) |
| 2 | **Architect** 🏗 | Proposes stack & API design | PRD + memory context | `ArchitectureDoc` (stack, endpoints, components) |
| 3 | **Frontend Dev** 💻 | Generates UI code | PRD + Architecture | `FileBundle` of frontend files |
| 4 | **Backend Dev** ⚙ | Generates API + DB code | PRD + Architecture | `FileBundle` of backend files |
| 5 | **Code Reviewer** 🔍 | Critiques the build, then hands off | All code + PRD + Architecture | `ReviewReport` (approve / revise / escalate) |
| 6 | **QA Engineer** 🧪 | Writes & runs tests in Docker | All code | `TestReport` + retry feedback if any fail |
| 7 | **DevOps Engineer** 🚀 | Containerization + CI | All artifacts | Dockerfile, docker-compose.yml, GH Actions |

**Two more nodes** support the pipeline (not really "agents" but graph nodes):
- **Memory Retriever** 🧠 — vector-similarity search over past builds, injects context into the architect's prompt
- **Memory Persister** 💾 — stores the build artifacts back into the vector store on success

**Conversational vs. one-shot:** PM and Architect run in *conversational mode* during chat (multi-turn back-and-forth, then commit); the other five run in *one-shot mode* (single LLM call → artifact). When invoked via `loom build "..."` everything runs one-shot.

**The generator–critic loop:** after the developers produce code, the **Code Reviewer** judges it as a whole against the PRD and architecture and returns a `ReviewReport`. Based on its verdict it issues a LangGraph `Command` handoff — approve → QA, code defect → back to the targeted developer(s), or design defect → *upstream* to the Architect to revise the stack. The loop is bounded by `max_review_iterations` so it always terminates, and a reviewer failure degrades gracefully to QA. See [ADR 0002](adrs/0002-code-reviewer-generator-critic-loop.md) and [ADR 0003](adrs/0003-command-based-handoffs.md).

---

## Workflow

The pipeline is a [LangGraph state machine](https://langchain-ai.github.io/langgraph/) — a directed graph with conditional routing, parallel execution, and retry loops:

```
                    ┌──────────────────┐
   START ─────────▶ │ Product Manager  │ ◀──────┐
                    └─────────┬────────┘         │ self-loop
                              │                  │ (chat turns)
                              ▼                  │
                    ┌──────────────────┐         │
                    │ Memory Retriever │         │
                    └─────────┬────────┘         │
                              ▼                  │
                    ┌──────────────────┐         │
                    │    Architect     │ ────────┘
                    └─────────┬────────┘
                              │
                ┌─────────────┴─────────────┐   ▲          ▲
                │   parallel via Send API   │   │ escalate  │ revise
                ▼                           ▼   │ (design)  │ (code)
       ┌──────────────┐            ┌──────────────┐         │
       │ Frontend Dev │            │  Backend Dev │ ◀───────┤
       └───────┬──────┘            └──────┬───────┘         │
               └────────────┬─────────────┘                 │
                            ▼                                │
                    ┌──────────────┐   not approved?         │
                    │ Code Reviewer│ ────────────────────────┘
                    └──────┬───────┘   (Command handoff, max N)
                           │ approved
                           ▼
                    ┌──────────────┐
                    │ QA Engineer  │ ──────┐
                    └──────┬───────┘       │ tests fail?
                           │               │ feedback loop
                           │ pass          │ (max 2 retries)
                           ▼               │
                    ┌──────────────┐       │
                    │   DevOps     │ ◀─────┘
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │ Memory Persist│
                    └──────┬───────┘
                           ▼
                          END
```

(The reviewer's "escalate" edge routes back up to the Architect, which then re-fans to the developers — omitted from the ASCII for clarity; see [ADR 0002](adrs/0002-code-reviewer-generator-critic-loop.md).)

**Key LangGraph patterns used:**
- **Conditional edges** — routing decisions based on state (e.g., did tests pass?)
- **`Command` handoffs** — the Code Reviewer node returns `Command(goto=…, update=…)` to dynamically route to QA, a developer (`Send`), or the architect — the modern post-conditional-edge idiom
- **Send API** — Frontend & Backend devs run truly in parallel; also used to fan revisions back to specific devs
- **Generator–critic loop** — the reviewer critiques dev output and bounces it back, bounded by `max_review_iterations`
- **`interrupt_after`** — chat REPL pauses after each PM/Architect turn so you can talk
- **Checkpointing** — state persists between turns so you can resume sessions
- **Retry loops** — QA failure feeds error context back to devs, up to N attempts

---

---

## Architecture

### Tech stack

- **Python 3.11+** — async-first
- **LangChain + LangGraph** — agent orchestration, state machine
- **Pydantic v2** — typed contracts between agents
- **Typer + Rich + prompt_toolkit** — CLI and chat REPL
- **FastAPI + React** — optional web dashboard (`loom ui`)
- **Docker** — code execution sandbox for QA tests
- **SQLite + LanceDB** — checkpointing and vector memory
- **pytest** — 500 tests covering state, agents, graph, the review loop, and chat flow

### How agents talk

Agents don't free-form chat with each other. They exchange **typed Pydantic artifacts** through shared graph state:

```
PM             →  PRD                 →  Architect
Architect      →  ArchitectureDoc     →  Frontend + Backend Devs
Devs           →  FileBundle          →  Code Reviewer
Code Reviewer  →  ReviewReport        →  QA  ·  or back to Devs  ·  or up to Architect
QA             →  TestReport          →  DevOps (or back to Devs)
DevOps         →  DevOpsBundle        →  Memory Persist → END
```

Artifacts are produced via native structured output (`with_structured_output`), so the model is constrained to the schema rather than emitting JSON as free text. If a provider lacks structured output, Loom falls back to a text parser; on bad output the agent retries with the parse error fed back as feedback (up to 3 attempts per agent). See [ADR 0001](adrs/0001-native-structured-output.md).

### State management

The graph schema is `LoomGraphState` — a TypedDict with `Annotated` reducers per field. Each field is its own LangGraph **channel**:

- `code_files` uses `merge_dicts` (frontend + backend writers can both contribute)
- `agent_messages` uses `merge_messages_dict` (per-agent chat history accumulates across turns)
- `events` and `costs` use `append_list` (audit trail)
- Most other fields use last-write-wins

This is what makes the chat REPL's per-turn state injection work cleanly — `update_state({"pending_user_input": ...})` only writes that one channel and leaves everything else alone.

### Memory system

Past builds are stored in a vector database (LanceDB or in-memory fallback). Before the Architect runs, the Memory Retriever does a semantic search and injects a "similar past builds" block into the prompt — so the Architect can learn from prior decisions.

```bash
loom memory list                # list stored builds
loom memory search "fastapi"    # semantic search
loom memory export memory.jsonl # export
loom memory import memory.jsonl # import
```

### Sandbox

QA tests run inside a Docker container with:
- 512 MB memory limit
- 90s timeout
- No network access
- Read-only mount of generated code

If Docker isn't available, Loom emits a test report flagged `is_stub` — nothing was executed, `all_passed` is False, and no coverage figure is reported. The CLI surfaces this as a warning, and `--require-sandbox` turns it into a hard failure. `loom sandbox build` constructs the Docker image (Python 3.12 + Node 20 + common test runners).

---
