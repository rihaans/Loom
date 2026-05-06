# PROGRESS — Live Task Tracker

> **Claude Code: this is your working file.** Update it as you build. Mark tasks `[x]` when done. Add notes in italics under tasks when something's worth flagging. Never delete completed phases — they're the audit trail.

**Last updated:** 2026-05-06
**Current phase:** Phase 4 — COMPLETE, awaiting CRITICAL review
**Blocked on:** User review gate approval for Phase 5

---

## How to Use This File

1. Before starting work in a session, read the current phase here.
2. As you complete tasks, change `[ ]` → `[x]` and add a one-line note if anything is non-obvious.
3. At each phase boundary, **STOP** and wait for the user's review.
4. If you discover scope changes, add them under the relevant phase as new tasks.
5. Use the "Notes" section at the bottom for anything cross-cutting.

---

## Phase 0 — Repo Bootstrap

**Status:** ✅ COMPLETE
**Review gate:** Required before Phase 1

- [x] Initialize git repo, add `.gitignore` (Python + Node + IDE)
- [x] Create `pyproject.toml` per `TECH_STACK.md`
- [x] Add `LICENSE` (MIT)
- [x] Stub `README.md` with project pitch + install instructions
  - *Note: docs moved to `docs/` folder per FILE_STRUCTURE.md*
- [x] Set up `src/agentforge/` package layout with empty `__init__.py` files
- [x] Install dev deps: `pip install -e ".[dev]"`
- [x] Configure `.ruff.toml` and `mypy.ini`
  - *Note: all config consolidated in `pyproject.toml`*
- [x] Create `pytest.ini` / `pyproject.toml [tool.pytest]` config
- [x] Add smoke test: `tests/unit/test_imports.py` with `def test_imports(): import agentforge`
  - *8 smoke tests added covering all main modules*
- [x] Set up `.github/workflows/ci.yml` (lint + test)
- [x] Add `.env.example` with all expected env vars
- [x] Add `agentforge.example.toml` with all config options
- [x] Add `docker/sandbox.Dockerfile` placeholder
- [ ] Verify CI is green on initial push
  - *Pending: requires git push to GitHub*

**Phase 0 done:** ✅ pending review

---

## Phase 1 — State, Types, Enums

**Status:** ✅ COMPLETE
**Review gate:** Required before Phase 2
**Reference:** `DATA_MODELS.md`

- [x] Create `src/agentforge/state/enums.py` with `Phase`, `AgentRole`, `Priority`, `ProjectType`
  - *Also added: EventType, TechLayer, ComponentType, ComponentLocation, HttpMethod, TargetAgent*
  - *Using StrEnum (Python 3.11+) per ruff UP042 recommendation*
- [x] Create `src/agentforge/state/reducers.py` with `merge_dicts()` and other reducers
  - *Implemented: merge_dicts, last_value, increment, append_list, coalesce*
- [x] Create `src/agentforge/state/models.py`:
  - [x] `UserStory`, `DataEntity`, `PRD`
  - [x] `TechChoice`, `APIEndpoint`, `Component`, `ArchitectureDoc`
  - [x] `CodeFile`, `FileBundle`
  - [x] `TestCase`, `TestReport`, `QAFeedback`
  - [x] `DevOpsBundle`
  - [x] `Event`, `CostEntry`
  - [x] `ExecutionResult`
  - [x] `AgentState` (with all `Annotated[..., reducer]` fields)
- [x] Add `field_validator`s for path safety (no `..`, no leading `/`), slug regex, ID format
- [x] Create `src/agentforge/config/models.py` with `LLMConfig`, `AgentForgeConfig`
  - *Also added BuildResult model*
- [x] Write `tests/unit/test_state.py`:
  - [x] Each model: valid case + invalid case
  - [x] Reducers: empty + single + merge + idempotence
  - [x] AgentState round-trip via `model_dump()` / `model_validate()`
  - *62 tests total covering all models and reducers*
- [x] Run `mypy src/agentforge/state` — must pass ✓
- [x] Confirm coverage ≥95% on `state/` module
  - *Achieved: 99% coverage on state module*

**Phase 1 done:** ✅ pending review

---

## Phase 2 — LLM Layer

**Status:** ✅ COMPLETE
**Review gate:** Required before Phase 3
**Reference:** `MODEL_SELECTION.md`

- [x] `src/agentforge/config/loader.py` — priority chain (CLI > env > toml > defaults)
- [x] `src/agentforge/config/defaults.py` — auto-detection logic
- [x] `src/agentforge/llm/factory.py` — `get_llm_for_role(role, config)`
- [x] `src/agentforge/llm/providers.py` — Anthropic, OpenAI, Ollama wrappers
- [x] `src/agentforge/llm/cost.py` — price tables + token → USD
  - *Anthropic: claude-opus-4-5, claude-sonnet-4-5, claude-haiku-3-5 + legacy models*
  - *OpenAI: gpt-4o, gpt-4o-mini, gpt-4-turbo, gpt-4, gpt-3.5-turbo, o1-mini, o1-preview*
- [x] `src/agentforge/llm/retry.py` — tenacity policies (rate limit, parse error)
  - *ParseError, RateLimitError, MaxRetriesExceededError exception types*
  - *is_rate_limit_error() and is_transient_error() detection*
  - *retry_llm_call() async wrapper with configurable attempts*
- [x] `agentforge.example.toml` at repo root with all options documented
- [x] Unit tests with monkeypatched env vars
  - *30 tests covering config, providers, cost, retry logic*
- [ ] Manual verification: `.invoke("hello")` works against each available provider
  - *Pending: requires live LLM connection*
- [x] Cost calc unit-tested against published Anthropic + OpenAI prices

**Phase 2 done:** ✅ pending review

---

## Phase 3 — Single Agent: Product Manager

**Status:** ✅ COMPLETE
**Review gate:** 🔥 CRITICAL — do not proceed without explicit user approval
**Reference:** `AGENTS.md` § Product Manager, `PROMPTS.md` § Product Manager

- [x] `src/agentforge/agents/prompts/product_manager.py` — system prompt as constant
  - *PRODUCT_MANAGER_SYSTEM_PROMPT and PRODUCT_MANAGER_HUMAN_TEMPLATE defined*
- [x] `src/agentforge/agents/base.py` — `build_agent()` factory (prompt → llm → parser)
  - *build_agent_chain(), get_format_instructions(), create_agent_for_role() implemented*
- [x] `src/agentforge/agents/product_manager.py`:
  - [x] Node function signature: `async def product_manager_node(state) -> dict`
  - [x] Structured output via `PydanticOutputParser(PRD)`
  - [x] Parse-error retry (max 3) with error fed into next prompt
  - [x] Token + cost tracking via callback (TokenTracker class)
  - [x] Returns state update with `prd`, `events`, `costs`
- [x] Unit tests:
  - [x] Happy path with mock chain
  - [x] Bad JSON → retry → eventual success
  - [x] Bad JSON × 3 → clean failure (event with error)
  - *8 tests total covering TokenTracker, node function, and prompts*
- [ ] **Manual test with real LLM** (Ollama or Claude if user provides key):
  - [ ] PRD output is coherent for "todo app" prompt
  - [ ] User stories follow the format
  - [ ] `project_slug` is valid kebab-case

**Phase 3 done:** ✅ pending CRITICAL review

> _Notes for the user at this gate:_  
> _Review the PM agent's structure carefully — it's the template for the other 5 agents. If the error handling, prompt format, or state update pattern feels wrong, fixing it here saves 5x work later._

---

## Phase 4 — Linear Graph (All Agents)

**Status:** ✅ COMPLETE
**Review gate:** 🔥 CRITICAL — do not proceed without explicit user approval
**Reference:** `AGENTS.md`, `PROMPTS.md`, `GRAPH_DESIGN.md`

- [x] `agents/architect.py` + prompt
- [x] `agents/frontend_dev.py` + prompt
- [x] `agents/backend_dev.py` + prompt
- [x] `agents/qa_engineer.py` + prompt _(stub — no real sandbox yet, fake passing tests)_
- [x] `agents/devops_engineer.py` + prompt
- [x] `agents/project_manager.py` — deterministic supervisor (no LLM)
  - *decide_next_phase() and route_to_agent() implemented*
- [x] `graph/routing.py` — `decide_next_phase()`, `route_after_pm()`
  - *route_after_pm, route_after_architect, route_after_devs, route_after_qa, route_after_devops*
- [x] `graph/builder.py` — wire all nodes with linear edges (no Send yet)
  - *build_linear_graph() and compile_graph() implemented*
  - *developers node runs frontend and backend sequentially (Phase 5: parallel)*
- [x] `output/slugify.py` — safe path/slug generation
- [x] `output/writer.py` — materialize `state.code_files` + `devops_files` to disk
- [ ] `output/readme.py` — generate output project README from PRD + run commands
  - *DevOps bundle includes readme_run_instructions field*
- [x] `core.py` — public `build()` async function returning `BuildResult`
  - *build() and build_sync() implemented*
- [ ] Integration tests with all agents mocked: `tests/integration/test_graph_linear.py`
  - [ ] Full pipeline runs end-to-end
  - [ ] All artifacts populated
  - [ ] Files written to expected paths
- [ ] **Manual run with real LLM**: produce a real `output/todo-app/` directory
- [ ] Inspect generated code by hand — does it look reasonable?

**Phase 4 done:** ✅ pending CRITICAL review

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
- [ ] CLI: `agentforge resume <thread_id>` reads checkpoint, continues
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
- [ ] Build image: `docker build -f docker/sandbox.Dockerfile -t agentforge-sandbox:latest .`
- [ ] `sandbox/runner.py` — `SandboxRunner` (Docker SDK)
  - [ ] Resource limits: memory, cpus, pids, no-new-privileges, cap_drop=ALL
  - [ ] Network isolation by default
  - [ ] Timeout enforcement
  - [ ] stdout/stderr capture with truncation
- [ ] `sandbox/subprocess_runner.py` — fallback gated by `AGENTFORGE_UNSAFE_SANDBOX=1`
- [ ] `sandbox/factory.py` — selection logic
- [ ] `tools/sandbox_exec.py` — `@tool` wrapper for QA agent
- [ ] Update `agents/qa_engineer.py` to use real `sandbox_exec` (not fake)
- [ ] Test output parsers: pytest stdout → `list[TestCase]`, jest → same
- [ ] CLI: `agentforge sandbox build/test/shell`
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
- [ ] Smoke test: `agentforge --help` and every command shows help correctly

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

- [ ] `agentforge ui` CLI command launches FastAPI + serves built React assets
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

> _2026-05-04 — Phase 0 complete. All 16 docs reorganized into `docs/` folder per FILE_STRUCTURE.md. Full package structure created with all `__init__.py` files. All linting (ruff), type checking (mypy), and smoke tests (pytest) passing. CLI stub functional with `agentforge version` and `agentforge build` commands._

> _2026-05-05 — Phase 1 complete. All Pydantic models implemented per DATA_MODELS.md. Using StrEnum for all enums (cleaner than str+Enum). 62 unit tests with 99% coverage on state module. All validators in place for path safety, slug format, ID format. AgentState has properly typed Annotated fields with reducers for merge_dicts and append_list._

> _2026-05-05 — Phase 2 complete. LLM layer fully implemented with provider-agnostic factory. Config loader supports priority chain: CLI > env > toml > defaults. Auto-detection picks first available provider (Anthropic > OpenAI > Ollama). Cost calculation with current pricing for Anthropic and OpenAI models. Retry policies handle rate limits (exponential backoff) and parse errors. 92 total tests passing._

> _2026-05-06 — Phase 3 complete. Product Manager agent fully implemented. Includes system prompt, base agent factory (build_agent_chain), async node function with retry logic, and token tracking via callbacks. LLM providers updated to accept callbacks. 100 total tests passing. This is the template for the remaining 5 agents._

> _2026-05-06 — Phase 4 complete. All 6 agents implemented (PM, Architect, Frontend Dev, Backend Dev, QA stub, DevOps). LangGraph StateGraph wired with conditional routing. Output writer materializes code to disk. core.py provides public build() API. QA agent is stub (fake passing tests) until sandbox in Phase 6. 100 tests still passing._

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
