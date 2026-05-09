# IMPLEMENTATION_PLAN — Phased Build Order

This is the build order. **Phase boundaries are review gates** — Claude Code stops at each one for the user to review before continuing.

There are 8 phases. Estimated total: 3-6 weeks of focused work.

---

## Phase Overview

| # | Phase | Outcome | Review Gate |
|---|---|---|---|
| 0 | Repo bootstrap | Project scaffolds, CI passes (no actual code yet) | Yes |
| 1 | State + types | All Pydantic models, reducers, enums | Yes |
| 2 | LLM layer | Provider factory, cost tracking, retry policies | Yes |
| 3 | Single agent (PM) | Product Manager agent works end-to-end | **Critical review** |
| 4 | Linear graph | All 6 agents wired in a linear graph (no parallelism) | **Critical review** |
| 5 | Advanced graph | Send API, retry loop, interrupts, checkpoints | Yes |
| 6 | Sandbox + execution | QA actually runs generated tests in Docker | Yes |
| 7 | CLI + TUI | Full CLI experience with rich progress UI | Yes |
| 8 | Web dashboard | FastAPI + React frontend | Final review |

---

## Phase 0 — Repo Bootstrap

**Duration:** ~half day

### Tasks
- [ ] Initialize repo: `pyproject.toml`, `.gitignore`, `LICENSE`, `README.md`
- [ ] Set up `src/loom/` package layout
- [ ] Install dev dependencies (ruff, mypy, pytest)
- [ ] Configure `ruff.toml`, `mypy.ini`, `pytest.ini`
- [ ] Create empty modules matching `FILE_STRUCTURE.md`
- [ ] Add a smoke test: `def test_imports(): import loom`
- [ ] Set up `.github/workflows/ci.yml` running lint + tests
- [ ] Create `.env.example`

### Done when
- `pip install -e ".[dev]"` succeeds
- `pytest` passes (only the smoke test exists)
- `ruff check .` passes
- CI is green on a push

**🛑 REVIEW GATE 0** — Confirm repo structure before proceeding.

---

## Phase 1 — State, Types, Enums

**Duration:** 1-2 days

### Tasks
- [ ] Implement `state/enums.py` (Phase, AgentRole, Priority, ProjectType)
- [ ] Implement `state/models.py` — every Pydantic model from `DATA_MODELS.md`
- [ ] Implement `state/reducers.py` (merge_dicts, etc.)
- [ ] Implement `AgentState` with proper `Annotated[..., reducer]` fields
- [ ] Add `field_validator` for path safety, slug format, etc.
- [ ] Write unit tests for every model — valid + invalid cases
- [ ] Write unit tests for reducers — concat, dict-merge, idempotence

### Done when
- All schemas in `DATA_MODELS.md` exist as Python classes
- `pytest tests/unit/test_state.py` has ≥95% coverage
- `mypy src/loom/state` passes

**🛑 REVIEW GATE 1** — Confirm schemas before agents are built.

---

## Phase 2 — LLM Layer

**Duration:** 1-2 days

### Tasks
- [ ] Implement `config/models.py` (LoomConfig, LLMConfig)
- [ ] Implement `config/loader.py` (CLI flags > env > toml > defaults)
- [ ] Implement `config/defaults.py` with auto-detect logic
- [ ] Implement `llm/factory.py` — `get_llm_for_role()`
- [ ] Implement `llm/providers.py` — Anthropic, OpenAI, Ollama wrappers
- [ ] Implement `llm/cost.py` with current price tables
- [ ] Implement `llm/retry.py` — tenacity policies for rate limits, parse errors
- [ ] Add `loom.example.toml` with all options documented
- [ ] Unit tests with mocked env vars

### Done when
- `get_llm_for_role(AgentRole.PM, config)` returns a working LLM for all 3 providers
- Auto-detection picks the right provider when only one API key is set
- Cost calculation matches Anthropic/OpenAI published prices
- A simple `.invoke("hi")` works against each provider

**🛑 REVIEW GATE 2** — Confirm LLM layer before building agents.

---

## Phase 3 — Single Agent: Product Manager

**Duration:** 2-3 days. **The hardest, most important phase.**

This is the template for all other agents. Get it right.

### Tasks
- [ ] Write the PM system prompt in `agents/prompts/product_manager.py`
- [ ] Implement `agents/base.py` with `build_agent()` factory
- [ ] Implement `agents/product_manager.py` — node function:
  - Takes `AgentState`
  - Reads `description`
  - Calls LLM with structured output → `PRD`
  - Returns state update with `prd`, `events`, `costs`
- [ ] Handle parse errors with retry (max 3 attempts with error in next prompt)
- [ ] Token counting + cost calculation per call
- [ ] Unit test: mock LLM returning good JSON → PRD parses correctly
- [ ] Unit test: mock LLM returning bad JSON → retries, eventually fails clean
- [ ] Integration test: run PM with FakeListChatModel → state updated correctly
- [ ] **Manual test with real LLM**: run PM against Claude Sonnet, verify PRD quality

### Done when
- Calling `await product_manager_node(state)` returns a state with valid PRD
- Tests pass for happy path + parse retry + final failure
- A real Claude call produces a PRD that's clearly better than what GPT-3.5 would produce (quality bar)

**🛑 CRITICAL REVIEW GATE 3** — User reviews:
- The PRD output quality from a real LLM call
- The agent code structure (will be replicated 5x)
- The error handling pattern

Do NOT proceed until this is solid.

---

## Phase 4 — Linear Graph (All Agents)

**Duration:** 4-7 days

Replicate the PM pattern for the other 5 agents and wire them in a linear graph (no parallelism, no retry yet).

### Tasks
- [ ] Implement `agents/architect.py` (mirrors PM structure)
- [ ] Implement `agents/frontend_dev.py`
- [ ] Implement `agents/backend_dev.py`
- [ ] Implement `agents/qa_engineer.py` (without sandbox yet — fake passing tests)
- [ ] Implement `agents/devops_engineer.py`
- [ ] Implement `agents/project_manager.py` (deterministic supervisor)
- [ ] Implement `graph/routing.py` — `decide_next_phase()`, `route_after_pm()`
- [ ] Implement `graph/builder.py` — wire all nodes with linear edges
- [ ] Implement `output/writer.py` — materialize state.code_files to disk
- [ ] Implement `output/readme.py` — generate output project README
- [ ] Implement `core.py` — public `build()` function
- [ ] Integration test with all agents mocked: full graph runs end-to-end
- [ ] Manual test with real LLMs: produces an actual project

### Done when
- `await build("a todo app")` returns a state with all artifacts
- Files are written to `output/todo-app/`
- The output project has a coherent structure (even if it doesn't run yet — sandbox is Phase 6)

**🛑 CRITICAL REVIEW GATE 4** — User reviews:
- Full end-to-end run with real LLM
- Quality of generated code (will it run with manual fixes?)
- Cost per build

---

## Phase 5 — Advanced Graph Features

**Duration:** 3-5 days

Add the LangGraph features that make this project impressive.

### Tasks
- [ ] Convert dev agents to parallel via Send API in `graph/parallel.py`
- [ ] Add conditional retry edge (QA fail → dev agents with feedback)
- [ ] Add `qa_feedback` propagation to dev agents
- [ ] Implement `graph/checkpoint.py` with SqliteSaver
- [ ] Add interrupts for `--interactive` mode (after PM, after Architect)
- [ ] Add `loom resume <thread_id>` CLI command
- [ ] Optional: extract dev↔QA loop into a subgraph
- [ ] Optional: implement LLM-supervisor variant
- [ ] Integration tests: parallel execution, retry loop, interrupts, resume after crash
- [ ] Generate Mermaid diagram of the final graph (`docs/images/graph.png`)

### Done when
- Parallel dev execution verified by inspecting events (frontend & backend start within 100ms of each other)
- Retry loop works: forced QA failure → dev agents called twice → second pass succeeds
- Crash mid-build, run `resume`, build completes
- `--interactive` pauses correctly and accepts user-edited PRD

**🛑 REVIEW GATE 5** — Confirm advanced features.

---

## Phase 6 — Sandbox + Real Test Execution

**Duration:** 2-4 days

Make the QA agent actually run the tests in Docker.

### Tasks
- [ ] Write `docker/sandbox.Dockerfile`
- [ ] Implement `sandbox/runner.py` (SandboxRunner)
- [ ] Implement `sandbox/subprocess_runner.py` (fallback)
- [ ] Implement `sandbox/factory.py` (selection logic)
- [ ] Implement `tools/sandbox_exec.py` (LangChain @tool)
- [ ] Update QA agent to use `sandbox_exec` tool instead of mocking
- [ ] Implement test output parsers (pytest output → TestCase[], jest output → TestCase[])
- [ ] Add `loom sandbox build/test/shell` CLI commands
- [ ] Test sandbox isolation: network blocked, OOM kill, timeout
- [ ] Run end-to-end: real LLM produces code, QA runs real tests in Docker
- [ ] Iterate prompts until tests pass on first try ≥80% of the time

### Done when
- `loom sandbox build` builds the image
- `loom sandbox test` runs a hello-world successfully
- A full build with real LLMs results in **passing tests** for the todo-app scenario
- Network isolation verified by test

**🛑 REVIEW GATE 6** — Confirm real validation works.

---

## Phase 7 — CLI + TUI

**Duration:** 3-5 days

Make the experience delightful at the command line.

### Tasks
- [ ] Implement `cli/app.py` (Typer app with commands)
- [ ] Implement `cli/commands/build.py` (the main command)
- [ ] Implement `cli/commands/sandbox.py`
- [ ] Implement `cli/commands/resume.py`
- [ ] Implement `cli/commands/config.py`
- [ ] Implement `observability/streaming.py` (astream_events → typed events)
- [ ] Implement `cli/tui.py` with Textual:
  - Pipeline view (agent statuses)
  - Live output panel (token streaming)
  - Stats panel (tokens, cost, time)
  - Event log
- [ ] Implement `--plain` mode for non-TTY contexts
- [ ] Implement `--interactive` mode flow
- [ ] Implement caching mechanism for `--cached <scenario>` demo replay
- [ ] Polish error messages (especially Docker/Ollama not running)

### Done when
- `loom --help` shows all commands clearly
- `loom build "..."` shows a beautiful TUI
- `--plain` works in pipes / CI
- Cached demo plays back smoothly

**🛑 REVIEW GATE 7** — Confirm CLI experience.

---

## Phase 8 — Web Dashboard

**Duration:** 5-10 days

The showcase piece for the Loom video.

### Tasks
- [ ] Implement `server/main.py` (FastAPI app)
- [ ] Implement `server/routes/builds.py` (POST /api/build, GET /api/runs)
- [ ] Implement `server/routes/ws.py` (WebSocket pump)
- [ ] Implement `server/runner.py` (background tasks)
- [ ] Scaffold React app: `frontend/` with Vite + Tailwind
- [ ] Implement `<BuildForm />` (input + submit)
- [ ] Implement `<GraphView />` with `@xyflow/react`
- [ ] Implement `<AgentNode />` custom nodes with state-driven styling
- [ ] Implement `<ArtifactPanel />` with tabs and Monaco editor
- [ ] Implement `<EventLog />` with virtualization
- [ ] Implement `<CostMeter />`
- [ ] Implement `useBuildWebSocket()` hook
- [ ] Implement zustand store for build state
- [ ] Style polish: dark mode, distinctive fonts, animations on active nodes
- [ ] `loom ui` CLI command launches both backend and frontend dev servers
- [ ] Build production assets, serve from FastAPI for one-process deploy
- [ ] Take screenshots for the README

### Done when
- `loom ui` opens browser with working dashboard
- Submitting a build streams events in real-time
- Graph viz lights up nodes as they execute
- All artifacts viewable
- Looks good on Loom (the actual goal)

**🛑 FINAL REVIEW GATE 8** — Sign off, record demo, ship.

---

## Time Budget by Skill Level

| Phase | Beginner LangGraph | Advanced LangGraph |
|---|---|---|
| 0-2 | 3-4 days | 1-2 days |
| 3 | 4-5 days (steep curve) | 2 days |
| 4 | 7-10 days | 4-5 days |
| 5 | 7-10 days | 3-4 days |
| 6 | 4-5 days | 2-3 days |
| 7 | 5-7 days | 3-4 days |
| 8 | 10-14 days | 5-7 days |
| **Total** | **6-8 weeks** | **3-4 weeks** |

User self-identifies as **advanced** → expect the lower bound.

---

## Critical Discipline Rules

1. **Never skip a review gate.** They exist to catch architecture mistakes early.
2. **Never proceed to advanced features (Phase 5+) before the linear graph (Phase 4) works end-to-end.**
3. **Mock LLMs for unit/integration tests. Reserve real LLM calls for E2E + manual verification.**
4. **Keep the prompt files in version control.** Prompt regressions are real bugs.
5. **Test on Ollama early.** If your prompts only work with Claude, you've over-fit. Smaller models will catch ambiguity.
6. **Update PROGRESS.md after every meaningful task.** That's how Claude Code communicates progress.
