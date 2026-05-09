# PRD — Loom

## 1. Vision

Loom is a LangGraph-orchestrated multi-agent system that takes a natural-language project description and autonomously produces a working, tested, containerized MVP. Six specialized AI agents collaborate as a real software team — each with a role, structured outputs, and tools — through a typed shared state.

The output is **real, runnable code** — not a plan, not a sketch.

## 2. Target Users

| Tier | Who | Goal |
|---|---|---|
| Primary | The author | Showcase advanced LangChain/LangGraph skills to recruiters |
| Secondary | Engineers exploring agentic AI | Reference impl of a non-trivial multi-agent system |
| Tertiary | LangChain community | Learning resource for Send API, supervisor pattern, HIL |

## 3. Core User Flows

### Flow A — CLI Build (primary)

```
$ loom build "REST API for a bookstore with CRUD, search, and reviews"

✓ Project Manager initialized
→ Product Manager: drafting PRD...      [████████████] PRD ready
→ Architect: choosing stack...          [████████████] FastAPI + SQLite + pytest
→ Backend + Frontend (parallel):
   ├ Backend  [████████████] 8 files written
   └ Frontend [████████████] 5 files written
→ QA: writing & running tests...        [████░░░░░░░░] 3/8 passed
→ Backend: fixing failing test...       [████████████] retry succeeded
→ QA: re-running tests...               [████████████] 8/8 passed
→ DevOps: Dockerfile + CI/CD...         [████████████] done

✅ Build complete: ./output/bookstore-api/
   Run with: cd output/bookstore-api && docker compose up
```

### Flow B — Interactive (phase gates)

```
$ loom build "..." --interactive

[after PM] PRD ready. Review and edit, or press Enter to continue.
[after Architect] Stack: FastAPI + Postgres. Override? [y/N]
[after Dev] Code written. Inspect, then press Enter for QA.
```

### Flow C — Web Dashboard

```
$ loom ui   # opens http://localhost:3000

→ Live graph visualization (nodes light up as they execute)
→ Streaming agent output in side panels
→ Artifacts (PRD, architecture, code) in tabs
→ Token + cost meter in real time
→ Download generated project as .zip
```

### Flow D — Python SDK

```python
from loom import build

result = await build(
    description="A CLI tool that converts CSV to JSON with schema validation",
    llm="claude-sonnet-4-5",
    output_dir="./out",
    interactive=False,
)
print(result.files, result.test_report, result.cost)
```

## 4. Feature Requirements

### P0 — Must have for MVP

| ID | Feature | Acceptance |
|---|---|---|
| F1 | Six-agent pipeline | All 6 agents implemented as LangGraph nodes with structured I/O |
| F2 | LangGraph supervisor | Project Manager node routes via conditional edges |
| F3 | Parallel dev agents | Frontend + Backend run via `Send` API, results merged via reducer |
| F4 | Typed shared state | All inter-agent data is Pydantic, validated at every node boundary |
| F5 | Code execution | QA agent runs generated tests in a Docker sandbox |
| F6 | Retry-on-failure loop | Failed tests → conditional edge back to dev agents (max 2 retries) |
| F7 | File generation | Outputs are real files in `./output/<project-slug>/` |
| F8 | Provider-agnostic LLM | Anthropic / OpenAI / Ollama swappable via config |
| F9 | CLI interface | `loom build "..."` with rich/textual progress UI |
| F10 | Multi-stack output | Agents pick stack per request (FastAPI, Express, Flask, React, static, CLI) |

### P1 — Should have

| ID | Feature | Acceptance |
|---|---|---|
| F11 | Interrupts / HIL | `--interactive` pauses at phase boundaries via LangGraph interrupts |
| F12 | Streaming output | Tokens stream to CLI/dashboard via `astream_events` |
| F13 | Web dashboard | FastAPI + WebSocket backend, React frontend, live graph viz |
| F14 | Checkpointing | Builds resume from last successful agent on crash/restart |
| F15 | Token + cost tracking | Per-agent and total token/cost reporting |
| F16 | Subgraph for QA loop | The dev↔QA retry cycle is a reusable subgraph |
| F17 | Observability | LangSmith integration (optional) for tracing |

### P2 — Nice to have

| ID | Feature | Acceptance |
|---|---|---|
| F18 | Code linting | Generated code auto-formatted (black/ruff/prettier) before save |
| F19 | Project templates | Pre-defined templates that nudge agents (REST API, fullstack, CLI) |
| F20 | GitHub export | Auto-create a repo and push generated project |
| F21 | Cost-mode | "Cheap mode" forces small models everywhere |
| F22 | Multi-language | Python, JS/TS, Go (currently Py + JS) |

## 5. Non-Functional Requirements

| Category | Target |
|---|---|
| End-to-end latency | < 5 min simple, < 15 min complex |
| Token cost (Claude Sonnet) | < $1 simple, < $3 complex |
| Token cost (Ollama local) | $0 |
| Reliability | Graceful degradation — partial output if any agent fails |
| Observability | Every LLM/tool call and edge transition logged |
| Code quality | Generated code passes its own tests; passes ruff/eslint |
| Reproducibility | Same seed + input → same output (within LLM determinism) |
| Sandboxing | Generated code only executes in isolated Docker container |

## 6. Out of Scope (v1)

- Deploying generated MVPs to cloud (Vercel, Render, etc.)
- Code generation in Go, Rust, Java
- Multi-user collaboration on a single build
- Fine-tuned LLMs (off-the-shelf only)
- Git operations within the agent workflow
- IDE plugins

## 7. Success Metrics

1. ✅ Successfully produces a working MVP for **at least 4 of the 5 demo scenarios**
2. ✅ Generated tests pass on the generated code without manual intervention
3. ✅ End-to-end demo runs in < 5 minutes on screen
4. ✅ Web dashboard clearly visualizes the agent graph in motion
5. ✅ Repo gets ≥50 GitHub stars within 3 months
6. ✅ At least one mention in a LangChain newsletter / community post

## 8. Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| LLM produces unrunnable code | High | QA agent + Docker sandbox catches it; retry loop with error context |
| Token costs unbounded | Medium | Per-agent caps; cheap-mode fallback; Ollama default |
| Agents output inconsistent JSON | High | Strict Pydantic schemas + retry on parse failure |
| Demo fails during interview | Critical | Cached "demo mode" with pre-recorded successful runs |
| Docker not available on user's machine | Medium | Subprocess fallback (with safety warning) |
| LangGraph API changes | Medium | Pin exact versions; abstract our usage |
| Graph cycles infinite-loop | High | Hard retry cap; total wall-clock timeout |

## 9. Glossary

- **Agent** — A LangChain Runnable wrapping (LLM + system prompt + tools + output parser)
- **Node** — A function in the LangGraph that wraps an agent or routing logic
- **Edge** — A transition between nodes; can be conditional or parallel (Send)
- **State** — The single Pydantic object passed between all nodes
- **Artifact** — A typed output from an agent (PRD, ArchitectureDoc, CodeFile, etc.)
- **Phase** — A logical grouping of nodes (Requirements, Design, Development, Testing, Deployment)
- **Supervisor** — The Project Manager node that decides what runs next
- **Interrupt** — A LangGraph feature that pauses the graph for human input
- **Checkpoint** — Persisted state allowing resumption after interruption
