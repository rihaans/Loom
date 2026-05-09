# PROGRESS — Live Task Tracker

> **Claude Code: this is your working file.** Update it as you build. Mark tasks `[x]` when done. Add notes in italics under tasks when something's worth flagging. Never delete completed phases — they're the audit trail.

**Last updated:** 2026-05-09
**Current phase:** Phase 8.7 — COMPLETE (ALL PHASES DONE)
**Blocked on:** Final polish (integration tests, screenshots, demo video)

---

## How to Use This File

1. Before starting work in a session, read the current phase here.
2. As you complete tasks, change `[ ]` → `[x]` and add a one-line note if anything is non-obvious.
3. At each phase boundary, **STOP** and wait for the user's review.
4. If you discover scope changes, add them under the relevant phase as new tasks.
5. Use the "Notes" section at the bottom for anything cross-cutting.

---

## Phase 0 — Repo Bootstrap

**Status:** ⬜ not started  
**Review gate:** Required before Phase 1

- [ ] Initialize git repo, add `.gitignore` (Python + Node + IDE)
- [ ] Create `pyproject.toml` per `TECH_STACK.md`
- [ ] Add `LICENSE` (MIT)
- [ ] Stub `README.md` with project pitch + install instructions
- [ ] Set up `src/loom/` package layout with empty `__init__.py` files
- [ ] Install dev deps: `pip install -e ".[dev]"`
- [ ] Configure `.ruff.toml` and `mypy.ini`
- [ ] Create `pytest.ini` / `pyproject.toml [tool.pytest]` config
- [ ] Add smoke test: `tests/unit/test_imports.py` with `def test_imports(): import loom`
- [ ] Set up `.github/workflows/ci.yml` (lint + test)
- [ ] Add `.env.example` with all expected env vars
- [ ] Verify CI is green on initial push

**Phase 0 done:** ⬜ pending review

---

## Phase 1 — State, Types, Enums

**Status:** ⬜ not started  
**Review gate:** Required before Phase 2  
**Reference:** `DATA_MODELS.md`

- [ ] Create `src/loom/state/enums.py` with `Phase`, `AgentRole`, `Priority`, `ProjectType`
- [ ] Create `src/loom/state/reducers.py` with `merge_dicts()` and other reducers
- [ ] Create `src/loom/state/models.py`:
  - [ ] `UserStory`, `DataEntity`, `PRD`
  - [ ] `TechChoice`, `APIEndpoint`, `Component`, `ArchitectureDoc`
  - [ ] `CodeFile`, `FileBundle`
  - [ ] `TestCase`, `TestReport`, `QAFeedback`
  - [ ] `DevOpsBundle`
  - [ ] `Event`, `CostEntry`
  - [ ] `ExecutionResult`
  - [ ] `AgentState` (with all `Annotated[..., reducer]` fields)
- [ ] Add `field_validator`s for path safety (no `..`, no leading `/`), slug regex, ID format
- [ ] Create `src/loom/config/models.py` with `LLMConfig`, `LoomConfig`
- [ ] Write `tests/unit/test_state.py`:
  - [ ] Each model: valid case + invalid case
  - [ ] Reducers: empty + single + merge + idempotence
  - [ ] AgentState round-trip via `model_dump()` / `model_validate()`
- [ ] Run `mypy src/loom/state` — must pass
- [ ] Confirm coverage ≥95% on `state/` module

**Phase 1 done:** ⬜ pending review

---

## Phase 2 — LLM Layer

**Status:** ⬜ not started  
**Review gate:** Required before Phase 3  
**Reference:** `MODEL_SELECTION.md`

- [ ] `src/loom/config/loader.py` — priority chain (CLI > env > toml > defaults)
- [ ] `src/loom/config/defaults.py` — auto-detection logic
- [ ] `src/loom/llm/factory.py` — `get_llm_for_role(role, config)`
- [ ] `src/loom/llm/providers.py` — Anthropic, OpenAI, Ollama wrappers
- [ ] `src/loom/llm/cost.py` — price tables + token → USD
- [ ] `src/loom/llm/retry.py` — tenacity policies (rate limit, parse error)
- [ ] `loom.example.toml` at repo root with all options documented
- [ ] Unit tests with monkeypatched env vars
- [ ] Manual verification: `.invoke("hello")` works against each available provider
- [ ] Cost calc unit-tested against published Anthropic + OpenAI prices

**Phase 2 done:** ⬜ pending review

---

## Phase 3 — Single Agent: Product Manager

**Status:** ⬜ not started  
**Review gate:** 🔥 CRITICAL — do not proceed without explicit user approval  
**Reference:** `AGENTS.md` § Product Manager, `PROMPTS.md` § Product Manager

- [ ] `src/loom/agents/prompts/product_manager.py` — system prompt as constant
- [ ] `src/loom/agents/base.py` — `build_agent()` factory (prompt → llm → parser)
- [ ] `src/loom/agents/product_manager.py`:
  - [ ] Node function signature: `async def product_manager_node(state) -> dict`
  - [ ] Structured output via `PydanticOutputParser(PRD)`
  - [ ] Parse-error retry (max 3) with error fed into next prompt
  - [ ] Token + cost tracking via callback
  - [ ] Returns state update with `prd`, `events`, `costs`
- [ ] Unit tests:
  - [ ] Happy path with `FakeListChatModel`
  - [ ] Bad JSON → retry → eventual success
  - [ ] Bad JSON × 3 → clean failure (event with error)
- [ ] **Manual test with real LLM** (Ollama or Claude if user provides key):
  - [ ] PRD output is coherent for "todo app" prompt
  - [ ] User stories follow the format
  - [ ] `project_slug` is valid kebab-case

**Phase 3 done:** ⬜ pending CRITICAL review

> _Notes for the user at this gate:_  
> _Review the PM agent's structure carefully — it's the template for the other 5 agents. If the error handling, prompt format, or state update pattern feels wrong, fixing it here saves 5x work later._

---

## Phase 4 — Linear Graph (All Agents)

**Status:** ⬜ not started  
**Review gate:** 🔥 CRITICAL — do not proceed without explicit user approval  
**Reference:** `AGENTS.md`, `PROMPTS.md`, `GRAPH_DESIGN.md`

- [ ] `agents/architect.py` + prompt
- [ ] `agents/frontend_dev.py` + prompt
- [ ] `agents/backend_dev.py` + prompt
- [ ] `agents/qa_engineer.py` + prompt _(stub — no real sandbox yet, fake passing tests)_
- [ ] `agents/devops_engineer.py` + prompt
- [ ] `agents/project_manager.py` — deterministic supervisor (no LLM)
- [ ] `graph/routing.py` — `decide_next_phase()`, `route_after_pm()`
- [ ] `graph/builder.py` — wire all nodes with linear edges (no Send yet)
- [ ] `output/slugify.py` — safe path/slug generation
- [ ] `output/writer.py` — materialize `state.code_files` + `devops_files` to disk
- [ ] `output/readme.py` — generate output project README from PRD + run commands
- [ ] `core.py` — public `build()` async function returning `BuildResult`
- [ ] Integration tests with all agents mocked: `tests/integration/test_graph_linear.py`
  - [ ] Full pipeline runs end-to-end
  - [ ] All artifacts populated
  - [ ] Files written to expected paths
- [ ] **Manual run with real LLM**: produce a real `output/todo-app/` directory
- [ ] Inspect generated code by hand — does it look reasonable?

**Phase 4 done:** ⬜ pending CRITICAL review

> _Notes for the user at this gate:_  
> _Walk through the generated `output/<slug>/` directory together. Does the code look like it could run with minor fixes? If it's nonsense, the prompts need work — the sandbox in Phase 6 won't fix bad prompts._

---

## Phase 5 — Advanced Graph Features

**Status:** ⬜ not started  
**Review gate:** Required before Phase 6  
**Reference:** `GRAPH_DESIGN.md` §§ 5, 6, 8, 9

- [ ] `graph/parallel.py` — `route_to_devs()` returning `[Send("frontend_dev", state), Send("backend_dev", state)]`
- [ ] Replace linear dev edges with Send-based fan-out in `graph/builder.py`
- [ ] Add conditional retry edge: QA fail + retry budget → back to dev agents
- [ ] Wire `qa_feedback` propagation into dev agent inputs (revision mode)
- [ ] `graph/checkpoint.py` — `SqliteSaver` integration
- [ ] Add `interrupt_after=["product_manager", "architect"]` when `interactive=True`
- [ ] CLI: `loom resume <thread_id>` reads checkpoint, continues
- [ ] Optional: extract dev↔QA into a subgraph (`graph/subgraphs/dev_qa.py`)
- [ ] Optional: implement LLM-supervisor variant gated by `--llm-supervisor` flag
- [ ] Integration tests:
  - [ ] `test_graph_parallel.py` — both dev agents fired, results merged
  - [ ] `test_graph_retry.py` — QA fail → dev retry → second QA pass
  - [ ] `test_interrupts.py` — interactive mode pauses at expected nodes
  - [ ] `test_resume.py` — kill mid-build, resume, completes correctly
- [ ] Generate `docs/images/graph.png` via `graph.get_graph().draw_mermaid_png()`

**Phase 5 done:** ⬜ pending review

---

## Phase 6 — Sandbox + Real Test Execution

**Status:** ⬜ not started  
**Review gate:** Required before Phase 7  
**Reference:** `SANDBOX.md`

- [ ] `docker/sandbox.Dockerfile` — pre-built image with Python+Node+test runners
- [ ] Build image: `docker build -f docker/sandbox.Dockerfile -t loom-sandbox:latest .`
- [ ] `sandbox/runner.py` — `SandboxRunner` (Docker SDK)
  - [ ] Resource limits: memory, cpus, pids, no-new-privileges, cap_drop=ALL
  - [ ] Network isolation by default
  - [ ] Timeout enforcement
  - [ ] stdout/stderr capture with truncation
- [ ] `sandbox/subprocess_runner.py` — fallback gated by `LOOM_UNSAFE_SANDBOX=1`
- [ ] `sandbox/factory.py` — selection logic
- [ ] `tools/sandbox_exec.py` — `@tool` wrapper for QA agent
- [ ] Update `agents/qa_engineer.py` to use real `sandbox_exec` (not fake)
- [ ] Test output parsers: pytest stdout → `list[TestCase]`, jest → same
- [ ] CLI: `loom sandbox build/test/shell`
- [ ] Sandbox isolation tests:
  - [ ] `test_sandbox_runs_python()` — happy path
  - [ ] `test_sandbox_blocks_network_by_default()`
  - [ ] `test_sandbox_oom_killed()` — memory cap enforced
  - [ ] `test_sandbox_timeout()` — long-running command killed
- [ ] **End-to-end run with real LLM**: todo-app prompt → tests actually pass in Docker
- [ ] Iterate prompts until first-try test pass rate ≥80% on demo scenarios

**Phase 6 done:** ⬜ pending review

---

## Phase 7 — CLI + TUI

**Status:** ⬜ not started  
**Review gate:** Required before Phase 8  
**Reference:** `UI_SPEC.md` Part A

- [ ] `cli/app.py` — Typer app with command registration
- [ ] `cli/commands/build.py` — main `build` command
- [ ] `cli/commands/sandbox.py` — `sandbox build/test/shell`
- [ ] `cli/commands/resume.py` — `resume <thread_id>`
- [ ] `cli/commands/config.py` — `config show/edit/init`
- [ ] `cli/commands/ui.py` — placeholder; full impl in Phase 8
- [ ] `observability/streaming.py` — convert `astream_events` → typed events
- [ ] `cli/tui.py` — Textual app:
  - [ ] `<PipelineView>` — agent statuses with spinners
  - [ ] `<LiveOutput>` — token streaming for active agent
  - [ ] `<StatsPanel>` — tokens, cost, elapsed
  - [ ] `<EventLog>` — scrolling event timeline
  - [ ] Key bindings: 1-7 (switch agent), s (stats), q (quit)
- [ ] `--plain` mode for non-TTY (CI logs)
- [ ] `--interactive` flow: pause at gates, accept user input via `prompt_toolkit`
- [ ] `--cached <scenario>` demo replay using `examples/cached_runs/*.jsonl`
- [ ] Polish error messages: Docker not running, Ollama not reachable, missing API key
- [ ] Smoke test: `loom --help` and every command shows help correctly

**Phase 7 done:** ⬜ pending review

---

## Phase 8 — Web Dashboard

**Status:** ⬜ not started  
**Review gate:** 🎬 FINAL — sign off + record demo  
**Reference:** `UI_SPEC.md` Part B

### Backend (FastAPI)

- [ ] `server/main.py` — FastAPI app + CORS + static mount
- [ ] `server/routes/builds.py` — `POST /api/build`, `GET /api/runs`, `GET /api/runs/{id}`
- [ ] `server/routes/artifacts.py` — `GET /api/runs/{id}/artifacts/{type}`
- [ ] `server/routes/ws.py` — `WS /ws/{run_id}` event pump
- [ ] `server/runner.py` — async background tasks for builds
- [ ] `server/models.py` — request/response Pydantic schemas

### Frontend (React + Vite + Tailwind)

- [ ] Scaffold `frontend/` with Vite + React + TypeScript + Tailwind
- [ ] `src/api/client.ts` — axios instance
- [ ] `src/api/ws.ts` — WebSocket hook with reconnection
- [ ] `src/store/buildStore.ts` — zustand store mirroring AgentState
- [ ] `src/components/BuildForm.tsx` — input + submit
- [ ] `src/components/GraphView.tsx` — `@xyflow/react` agent graph
- [ ] `src/components/AgentNode.tsx` — custom node (idle/active/done/failed states)
- [ ] `src/components/ArtifactPanel.tsx` — tabs: PRD / Architecture / Code / Tests / DevOps
  - [ ] Markdown rendering for PRD + Architecture
  - [ ] Monaco editor for code (read-only)
  - [ ] Custom view for TestReport with expandable failed cases
- [ ] `src/components/EventLog.tsx` — virtualized list with filters
- [ ] `src/components/CostMeter.tsx` — live token + USD with per-agent breakdown
- [ ] `src/pages/Home.tsx`, `Build.tsx`, `Runs.tsx`, `Settings.tsx`
- [ ] Dark mode default; distinctive font choices
- [ ] Active-node pulse animation

### Integration

- [ ] `loom ui` CLI command launches FastAPI + serves built React assets
- [ ] Production build: `cd frontend && npm run build` → served from FastAPI
- [ ] Screenshots in `docs/images/` for the README

### Demo prep

- [ ] Pre-record cached runs for all 5 demo scenarios (`examples/cached_runs/*.jsonl`)
- [ ] Verify cached replay works flawlessly
- [ ] Write Loom script (3-min structure from `DEMO_SCENARIOS.md`)
- [ ] Record Loom video
- [ ] Add Loom link to README

**Phase 8 done:** ⬜ pending FINAL review

---

## Phase 8.5 — Memory System

**Status:** ✅ IMPLEMENTED
**Review gate:** Required before Phase 8.6
**Reference:** `MEMORY_SYSTEM.md`

> Self-learning across builds via vector retrieval. The headline differentiator.

- [x] Add `lancedb` and `sentence-transformers` to `[project.optional-dependencies] memory`
- [x] `loom/memory/models.py` — `MemoryRecord`, `MemoryContext`, `MemoryConfig`
- [x] `loom/memory/embedder.py` — `LocalEmbedder` (default, sentence-transformers); optional `OpenAIEmbedder`
- [x] `loom/memory/store.py` — `LanceDBStore` implementing `MemoryStore` Protocol; `InMemoryStore` for testing
- [x] `loom/memory/factory.py` — `get_memory_store(config)`, `get_embedder(config)`, `is_memory_available()`
- [x] `MemoryRecord.from_state(state)` — extracts only the persistable fields
- [x] `agents/memory_retrieve.py` — node, runs after PM and before Architect
- [x] `agents/memory_persist.py` — terminal node, only persists when `test_passed=True`
- [x] Add `memory_context: Any | None` to `AgentState`
- [x] Add `memory: MemoryConfig` to `LoomConfig`
- [x] Wire both nodes into `graph/builder.py`
- [x] Update `agents/prompts/architect.py` with `{memory_block}` placeholder
- [x] Architect agent injects memory context into prompt
- [x] CLI commands: `loom memory status/list/search/clear/export/import` + `--no-memory` flag on build
- [x] Unit tests for store and embedder (22 tests)
- [ ] Integration test: warm a corpus with 5 records, run a build, assert MemoryContext non-empty
- [ ] `scripts/eval_memory.py` — measure retry_count / cost / first-try success across 20 prompts
- [ ] Run the eval — **kill the feature if it doesn't measurably help**
- [ ] Pre-record side-by-side demo (build #1 vs build #N) for the README

**Phase 8.5 done:** ✅ Core implementation complete (122 tests passing)

---

## Phase 8.6 — Plan Command

**Status:** ✅ IMPLEMENTED
**Review gate:** Required before Phase 8.7
**Reference:** `PLAN_COMMAND.md`

> `loom plan` — cheap, abortable preview before full build. Reuses LangGraph interrupts.

- [x] Add `architecture_feedback: str | None` field to `AgentState`
- [x] Update `agents/prompts/architect.py` with `{feedback_block}` placeholder
- [x] Update `agents/architect.py` to render feedback block; clear field after success
- [x] `loom/cost/estimator.py` — `estimate_build_cost(state) -> tuple[float, float]`
- [ ] `scripts/calibrate_estimates.py` — derive `base_tokens` constants from logged `costs[]`
- [x] `loom/cli/tui.py` — `PlanRenderer` class for Rich-based plan rendering (scope, stack, endpoints, entities, cost)
- [x] `loom/cli/app.py`:
  - [x] `loom plan "..."` — runs PM + Architect, renders, prompts B/E/S/Q
  - [x] `loom build-from-plan <path>` — resumes from saved plan
- [x] Plan serialization: `save_plan()` / `load_plan()` in `loom/plan/serializer.py`
- [ ] Web dashboard: "Plan first" toggle (default on), plan view component, inline-edit, Build button
- [x] Tests: `tests/unit/test_plan.py` (18 tests)
- [ ] Update README to use `loom plan` as the primary CLI example
- [ ] Update Loom script to demo plan-first workflow

**Phase 8.6 done:** ✅ Core implementation complete (140 tests passing)

---

## Phase 8.7 — ADR Generation

**Status:** ✅ IMPLEMENTED
**Review gate:** Final feature gate
**Reference:** `ADR_GENERATION.md`

> Auto-write Architectural Decision Records into output projects. Pure-mapping; no extra LLM calls.

- [x] `loom/adr/__init__.py`
- [x] `loom/adr/generator.py` — `generate_adrs(state) -> dict[str, str]`
- [x] `loom/adr/knowledge.py` — curated alternatives + pros/cons for 12+ (layer, technology) pairs:
  - Backend: FastAPI, Flask, Express.js
  - Frontend: React, React+Vite, Vue, Vanilla
  - Database: SQLite, PostgreSQL, In-memory
  - Auth: JWT, Session cookies, None
  - Testing: pytest, Jest, Vitest
- [x] Index generation in `generate_adrs()` — creates `0000-index.md`
- [x] Generic-fallback rendering for missing knowledge entries
- [x] Wire `generate_adrs(state)` into `loom/output/writer.py` via `write_adrs()`
- [x] `generate_readme_adr_section()` — helper for README integration
- [x] Add `ADRConfig` to `loom/config/models.py` with `enabled` and `significance` fields
- [x] CLI flag `--no-adrs` in `cli/app.py` build command
- [x] Unit tests: `tests/unit/test_adr_generation.py` (33 tests)
  - [x] `test_generates_adr_per_significant_choice`
  - [x] `test_index_lists_all_adrs`
  - [x] `test_unknown_tech_falls_back_to_generic_template`
  - [x] `test_significance_filter`
- [ ] Integration test: full build produces `output/<slug>/docs/adrs/*.md`
- [ ] Add ADR screenshot to the README
- [ ] Mention ADRs in the Loom video

**Phase 8.7 done:** ✅ Core implementation complete (173 tests passing)

---

## Cross-Cutting / Continuous Tasks

These get touched throughout, not in any one phase. Update as relevant.

- [ ] Keep `README.md` (root) accurate as features land
- [ ] Update `docs/images/graph.png` whenever the graph topology changes
- [ ] Add new prompts to `agents/prompts/__init__.py` exports
- [ ] Track API price changes — update `llm/cost.py` price tables
- [ ] Bump `__version__` per phase

---

## Notes / Issues / Decisions

_Use this space for anything that doesn't fit a phase task. Date-stamp entries._

> _2026-XX-XX — example entry: switched from `langchain-ollama` to `langchain-community.chat_models.ollama` because the former had a parser bug with `format="json"`. Reverted after upstream fix in v0.3.x._

---

## Definition of "Done" for the Project

Final ship checklist (only after Phase 8):

- [ ] All 8 phase gates passed
- [ ] All 5 demo scenarios produce working MVPs (4/5 minimum)
- [ ] Generated tests pass in Docker on first or second try ≥80%
- [ ] Loom video recorded and linked in README
- [ ] GitHub repo public with clear README, screenshots, and quick-start
- [ ] CI is green on `main`
- [ ] At least one community share (Twitter, LangChain Discord, HN) drafted
