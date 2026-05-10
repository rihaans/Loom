# PLAN_COMMAND — `loom plan` Workflow

> **Status:** Phase 8.6 feature. Implement after the core build pipeline is stable.

A new top-level CLI command — `loom plan` — that runs only the cheap planning agents (PM + Architect), prints a structured plan, and asks the user whether to proceed to a full build. This decouples *deciding what to build* from *spending tokens to build it*.

---

## 1. Why This Exists

Today, every `loom build` runs the entire pipeline. If the user dislikes the Architect's stack choice, they've already spent the cost of the dev agents producing code on top of that bad choice. The retry loop helps with bugs, not with disagreement at the design level.

`loom plan` is a **cheap, abortable preview**:

| Metric | `build` (full) | `plan` (preview) |
|---|---|---|
| Wall-clock time | 3–10 min | 30–60 sec |
| Token cost (Claude Sonnet) | $0.50–$3.00 | $0.10–$0.20 |
| Output | Full project | A reviewable plan in your terminal |
| User can iterate? | Slow (re-run whole pipeline) | Fast (re-prompt PM/Architect only) |

This makes Loom feel less like a black box and more like a collaborator. Recruiters who see the plan-first workflow recognize it immediately as good UX design — same instinct as a senior engineer writing a design doc before writing code.

## 2. User Flows

### 2.1 Plan-only (terminal command)

```
$ loom plan "A REST API for a bookstore with reviews and search"

✓ Product Manager done (4.1s, $0.04)
✓ Architect done       (8.7s, $0.09)

╭──────────────────────────────────────────────────────────────────╮
│  PLAN: bookstore-api                                             │
│  A REST API for managing books, authors, and user reviews.       │
╰──────────────────────────────────────────────────────────────────╯

📋 Scope (P0)
   • Sign up and log in
   • Browse books, view detail, see reviews
   • Post a 1–5 star review with a comment
   • Search books by title or author
   • View per-book average rating

🏗  Stack
   Backend     FastAPI 0.115 — async, native Pydantic, fast iteration
   Frontend    none (REST API only)
   Database    SQLite via SQLAlchemy
   Auth        JWT (python-jose)
   Tests       pytest + httpx

📡 API Endpoints (12)
   POST   /auth/signup           Create account
   POST   /auth/login            Get JWT
   GET    /books                 List books
   GET    /books/{id}            Book detail
   GET    /books/search?q=…      Search
   GET    /books/{id}/reviews    List reviews
   POST   /books/{id}/reviews    Create review (auth)
   ... 5 more

🗂  Data Entities
   User     id, email, password_hash, created_at
   Book     id, title, author, isbn, cover_url
   Review   id, book_id, user_id, rating, comment, created_at

💰 Estimated build cost: $0.42–$0.65  (~3 min wall-clock)
🧠 Memory: 2 similar past builds will be used as references

What next?
  [B] Build now              [E] Edit & rebuild plan
  [S] Save plan, build later [Q] Quit
›
```

### 2.2 Iterate on the plan

```
› E

What would you like to change? (enter free-text feedback)
› use Postgres instead of SQLite, and add a /books/popular endpoint
   that returns books sorted by review count

  Re-running Architect with your feedback...
  ✓ Architect done (6.2s, $0.07)

[ updated plan re-rendered with Postgres + new endpoint ]

What next? [B/E/S/Q] ›
```

The PM is NOT re-run during `E` — only the Architect. Saves tokens and avoids the PRD churning under the user's feet. To re-run PM, exit and start a fresh `plan` invocation.

### 2.3 Save and resume

```
› S
✓ Plan saved. Resume with:
   loom build --from-plan plans/bookstore-api-2026-05-08.json
```

Plans are JSON files containing `(prd, architecture, memory_context, run_id)` — feed back into the build pipeline to skip the PM and Architect phases entirely.

### 2.4 Web dashboard equivalent

The dashboard's Build form gets a toggle: **"Plan first"** (default on). The plan view is the same data, rendered as a styled component with inline-edit affordances and a big green **Build** button.

## 3. Architecture

`loom plan` and `loom build --from-plan` use the **same underlying graph** as `build` — just with different entry/exit points and an interactive interrupt in between.

```
loom plan  ──► graph.compile(interrupt_after=["architect"])
                        │
                        ▼
                  product_manager → architect → INTERRUPT
                        │
                        ▼
                  print plan, await user input
                        │
                        ├── B → graph.update_state(...)
                        │       graph.astream_events(None, ...)   ← resumes
                        │
                        ├── E → re-invoke architect with feedback message
                        │
                        ├── S → serialize state, write to plans/*.json
                        │
                        └── Q → discard, exit


loom build --from-plan ──► load plan JSON → seed AgentState →
                                   graph.compile(checkpointer=...)
                                   astream_events starts at memory_retrieve
                                   (skips PM + Architect — already done)
```

This is **exactly** the LangGraph interrupt pattern from Phase 5. Plan mode is `--interactive` with a richer UI applied at one specific gate. **Don't build a separate graph.** Reuse what's already there.

## 4. Saved Plan Format

```json
{
  "version": 1,
  "created_at": "2026-05-08T14:23:00Z",
  "loom_version": "0.4.0",
  "thread_id": "1f2e7c34-...",
  "description": "A REST API for a bookstore with reviews and search",
  "prd": { /* full PRD */ },
  "architecture": { /* full ArchitectureDoc */ },
  "memory_context": { /* MemoryContext, may be empty */ },
  "config": {
    "llm_default": { "provider": "anthropic", "model": "claude-sonnet-4-5" },
    "memory": { "enabled": true }
  },
  "estimated_cost_usd": [0.42, 0.65],
  "estimated_duration_sec": [120, 240]
}
```

Saved plans live in `./plans/` by default. Filename convention: `{project_slug}-{YYYY-MM-DD}.json`. Idempotent if rerun on the same day with the same slug — appends `-1`, `-2`.

## 5. Cost & Time Estimation

The plan view shows an estimate so users know what they're committing to. Compute it from:

```python
def estimate_build_cost(state: AgentState) -> tuple[float, float]:
    """Returns (low, high) USD estimate for completing the build from this state."""
    pricing = get_pricing(state.config)
    
    # Base estimates per agent in tokens (input + output combined, P50 / P90 from past runs)
    base_tokens = {
        "frontend_dev": (8000, 18000),
        "backend_dev":  (10000, 22000),
        "qa_engineer":  (6000, 14000),
        "devops":       (3000, 6000),
    }
    
    # Adjust based on PRD size
    complexity_mult = 1.0 + 0.15 * len(state.prd.user_stories) / 5
    if state.architecture.stack_summary().has_frontend:
        agents_to_run = list(base_tokens.keys())
    else:
        agents_to_run = ["backend_dev", "qa_engineer", "devops"]
    
    low = sum(pricing.cost_for(a, base_tokens[a][0]) * complexity_mult for a in agents_to_run)
    high = sum(pricing.cost_for(a, base_tokens[a][1]) * complexity_mult * 1.4  # retry buffer
               for a in agents_to_run)
    return (round(low, 2), round(high, 2))
```

**Calibrate the base_tokens dict from real runs** logged via `costs[]` in `AgentState`. Update once per release. Don't ship hardcoded fantasy numbers.

For Ollama-default users, cost shows as **`$0.00 (local)`** with a duration estimate only.

## 6. CLI Implementation

```python
# loom/cli/commands/plan.py
import typer
from rich.prompt import Prompt
from loom.cli.commands.shared import resolve_config
from loom.graph import build_graph
from loom.cli.tui import PlanRenderer

@app.command()
async def plan(
    description: str = typer.Argument(..., help="What to build"),
    output: Path | None = typer.Option(None, "--save", help="Save plan to this path"),
    auto_build: bool = typer.Option(False, "--auto-build", help="Skip the prompt and build immediately"),
    config_path: Path | None = typer.Option(None, "--config"),
):
    config = resolve_config(config_path, override_interactive=True)
    graph = build_graph(config, interrupt_after=["architect"])
    
    initial = AgentState(description=description, interactive=True)
    thread_id = str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": thread_id}}
    
    # Run PM and Architect
    async for _ in graph.astream_events(initial, config=cfg, version="v2"):
        pass  # CLI streams progress separately via observability layer
    
    state = graph.get_state(cfg).values
    PlanRenderer().render(state)
    
    if auto_build:
        choice = "B"
    else:
        choice = Prompt.ask("\n[B] Build  [E] Edit  [S] Save  [Q] Quit", choices=["B","E","S","Q"], default="B")
    
    if choice == "Q":
        raise typer.Exit(0)
    if choice == "S":
        save_plan(state, output or default_plan_path(state))
        typer.echo(f"✓ Plan saved. Resume with: loom build --from-plan {path}")
        raise typer.Exit(0)
    if choice == "E":
        feedback = Prompt.ask("What would you like to change?")
        # Re-invoke Architect with feedback
        graph.update_state(cfg, {"architect_feedback": feedback})
        async for _ in graph.astream_events(None, config=cfg, version="v2"):
            pass
        # Re-render and re-prompt — recurse or loop
        return await plan_loop(graph, cfg)  # extracted helper
    if choice == "B":
        # Resume the graph; remaining nodes (memory_retrieve → devs → QA → DevOps) run
        async for _ in graph.astream_events(None, config=cfg, version="v2"):
            pass
        final = graph.get_state(cfg).values
        print_build_summary(final)


@app.command()
async def build_from_plan(
    plan_path: Path = typer.Argument(..., help="Path to a saved plan.json"),
):
    plan = load_plan(plan_path)
    config = LoomConfig(**plan["config"])
    graph = build_graph(config)
    
    initial = AgentState(
        description=plan["description"],
        prd=PRD(**plan["prd"]),
        architecture=ArchitectureDoc(**plan["architecture"]),
        memory_context=MemoryContext(**plan["memory_context"]),
        phase=Phase.DEVELOPMENT,   # PM and Architect already done
    )
    thread_id = plan["thread_id"]  # same id → idempotent re-runs of saved plans
    cfg = {"configurable": {"thread_id": thread_id}}
    
    async for _ in graph.astream_events(initial, config=cfg, version="v2"):
        pass
    print_build_summary(graph.get_state(cfg).values)
```

## 7. The "Edit" Branch — Architect Feedback

When a user picks `E`, you don't want to re-run the whole Architect from scratch — they may only want to swap one technology. Extend the Architect prompt with a feedback channel:

```python
# In agents/prompts/architect.py
ARCHITECT_USER_TEMPLATE = """
PRD:
{prd_json}

{memory_block}

{feedback_block}

Produce the ArchitectureDoc.
"""

# In agents/architect.py
def build_architect_input(state: AgentState) -> dict:
    feedback_block = ""
    if state.architecture_feedback:
        feedback_block = (
            f"# User feedback on previous architecture\n"
            f"You previously proposed:\n{state.architecture.summary()}\n\n"
            f"The user requested these changes:\n{state.architecture_feedback}\n\n"
            f"Produce a revised ArchitectureDoc that addresses the feedback "
            f"while keeping unchanged decisions stable."
        )
    return {
        "prd_json": state.prd.model_dump_json(indent=2),
        "memory_block": memory_block,
        "feedback_block": feedback_block,
    }
```

Add `architecture_feedback: str | None = None` to `AgentState`.

After the revised architect runs, **clear `architecture_feedback`** so it doesn't bleed into later runs.

## 8. The PlanRenderer (Rich)

```python
# loom/cli/tui/plan_renderer.py
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

class PlanRenderer:
    def render(self, state: AgentState) -> None:
        console = Console()
        console.print(Panel(
            f"[bold]{state.prd.project_name}[/bold]\n{state.prd.one_liner}",
            title="PLAN",
            border_style="cyan",
        ))
        
        # Scope
        console.print("\n[bold]📋 Scope (P0)[/bold]")
        for s in state.prd.user_stories:
            if s.priority == Priority.P0:
                console.print(f"   • {s.goal}")
        
        # Stack
        console.print("\n[bold]🏗  Stack[/bold]")
        stack_table = Table(show_header=False, box=None, padding=(0, 1))
        stack_table.add_column(style="bold cyan")
        stack_table.add_column()
        stack_table.add_column(style="dim")
        for tc in state.architecture.stack:
            stack_table.add_row(tc.layer.title(), f"{tc.technology} {tc.version}", tc.rationale)
        console.print(stack_table)
        
        # Endpoints
        if state.architecture.api_endpoints:
            console.print(f"\n[bold]📡 API Endpoints ({len(state.architecture.api_endpoints)})[/bold]")
            for ep in state.architecture.api_endpoints[:8]:
                console.print(f"   [bold]{ep.method:6}[/bold] {ep.path:30} {ep.description}")
            if len(state.architecture.api_endpoints) > 8:
                console.print(f"   [dim]... {len(state.architecture.api_endpoints) - 8} more[/dim]")
        
        # Data entities
        # ... similar
        
        # Cost estimate
        low, high = estimate_build_cost(state)
        console.print(f"\n[bold]💰 Estimated cost:[/bold] ${low:.2f}–${high:.2f}")
        
        # Memory hits
        if state.memory_context and state.memory_context.examples:
            n = len(state.memory_context.examples)
            console.print(f"[bold]🧠 Memory:[/bold] {n} similar past build{'s' if n != 1 else ''} used as references")
```

## 9. Tests

```python
# tests/integration/test_plan_command.py
async def test_plan_then_build(patched_llm, tmp_path):
    """Plan → Save → Build From Plan → assert no PM/Architect re-run."""
    config = LoomConfig(output_dir=str(tmp_path))
    
    # Phase 1: plan
    graph = build_graph(config, interrupt_after=["architect"])
    state_a = AgentState(description="todo app", interactive=True)
    cfg = {"configurable": {"thread_id": "test"}}
    async for _ in graph.astream_events(state_a, config=cfg, version="v2"):
        pass
    
    interrupted = graph.get_state(cfg).values
    assert interrupted.prd is not None
    assert interrupted.architecture is not None
    assert interrupted.test_report is None  # haven't built yet
    
    # Phase 2: save
    save_plan(interrupted, tmp_path / "plan.json")
    assert (tmp_path / "plan.json").exists()
    
    # Phase 3: build from plan, count LLM calls
    initial_calls = patched_llm.call_count
    final_state = await build_from_plan(tmp_path / "plan.json")
    
    # PM and Architect should NOT have run again
    assert patched_llm.call_count - initial_calls < 6  # frontend, backend, QA, DevOps, ~max 1 retry
    assert final_state.prd == interrupted.prd  # same PRD, not regenerated
    assert final_state.test_report is not None


async def test_plan_edit_only_reruns_architect(patched_llm, tmp_path):
    """E branch: user feedback re-runs only Architect, not PM."""
    # ... setup ...
    initial_pm_calls = patched_llm.calls_for("product_manager")
    apply_architect_feedback(state, "use Postgres")
    final = await rerun_architect(state)
    assert patched_llm.calls_for("product_manager") == initial_pm_calls  # PM untouched
```

## 10. Implementation Checklist

Phase 8.6 tasks:

- [ ] Add `architecture_feedback: str | None` field to `AgentState`
- [ ] Update `agents/prompts/architect.py` with `{feedback_block}` placeholder
- [ ] Update `agents/architect.py` to render feedback block; clear field after success
- [ ] Implement `loom/cost/estimator.py` — `estimate_build_cost(state)`
- [ ] Calibrate `base_tokens` from real cost data in `costs[]` (write a script: `scripts/calibrate_estimates.py`)
- [ ] Implement `loom/cli/tui/plan_renderer.py`
- [ ] Implement `loom/cli/commands/plan.py` — `plan` and `build_from_plan` commands
- [ ] Implement plan serialization: `save_plan()` / `load_plan()`
- [ ] Add `plans/` to `.gitignore` of generated projects (it's user data, not source)
- [ ] Web dashboard: add "Plan first" toggle to BuildForm; render plan view; add inline-edit + Build button
- [ ] Tests: plan-then-build, edit-only-reruns-architect, save-and-resume idempotency
- [ ] Update README with `loom plan "..."` as the primary CLI example
- [ ] Update Loom script to demo plan-first workflow

## 11. Future Extensions (not in v1)

- **Multi-shot edit** — let the user keep tweaking through several rounds of feedback before committing.
- **Diff view on edit** — show what changed between the previous architecture and the revised one (table-based, color-coded).
- **Plan-only mode for CI** — `--auto-build=false --output plan.json` for automation that wants to gate on human approval before spending.
- **Compare plans** — `loom plan diff plan-a.json plan-b.json`.
