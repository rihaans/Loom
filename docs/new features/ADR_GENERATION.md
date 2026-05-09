# ADR_GENERATION — Architectural Decision Records in Output Projects

> **Status:** Phase 8.7 feature. Small, low-risk addition that significantly raises perceived quality of generated projects.

After every successful build, Loom writes ADRs (Architectural Decision Records) into the *output* project — one ADR per significant choice the Architect made. This makes generated projects look like real codebases maintained by senior engineers, not LLM dumps.

---

## 1. Why This Matters

A generated project today contains code, tests, Dockerfile, README, CI config. A reader looking at the repo can see *what* was built. They can't see *why* a particular stack was chosen, or what alternatives were considered.

Adding ADRs answers the "why" — and signals two things to anyone evaluating your portfolio:

1. **You understand professional engineering practices.** ADRs are a standard pattern in mature shops (Michael Nygard's format). Recruiters and senior engineers recognize them on sight.
2. **Loom isn't just generating code — it's documenting reasoning.** That's a meaningfully harder thing to build, and it shows.

**The cost is tiny.** The Architect already produces `rationale` for every TechChoice. We're just rendering that data into ADR markdown files. No new LLM calls if we structure it right.

## 2. What an ADR Looks Like

Standard Nygard format. One file per decision, in `docs/adrs/` of the output project:

```markdown
# ADR-0001: Use FastAPI for the Backend

**Status:** Accepted
**Date:** 2026-05-08
**Decided by:** Loom Architect agent

## Context

This project requires a REST API to support a bookstore management application
with 12 endpoints, JWT authentication, and full-text search. The team needs
fast iteration during development and a tight feedback loop with the QA agent.

## Decision

We will use **FastAPI 0.115** as the backend framework.

## Alternatives Considered

- **Flask 3.0** — simpler and more familiar, but lacks native async support and
  requires extra plumbing for OpenAPI docs and request validation.
- **Express.js 4** — would force a TypeScript/JavaScript stack, splitting the
  language between frontend and backend; not justified for an API-only project.

## Consequences

**Positive:**
- Native Pydantic integration matches our data validation strategy.
- Auto-generated OpenAPI docs at `/docs` simplify QA's test generation.
- async-first design supports future scaling without rework.

**Negative:**
- Slightly steeper learning curve than Flask for contributors unfamiliar with async.
- Smaller ecosystem of off-the-shelf middleware compared to Express.

## References

- FastAPI documentation: https://fastapi.tiangolo.com
- See also: ADR-0003 (Database choice), ADR-0005 (Auth approach)
```

## 3. What Decisions Become ADRs

Not every TechChoice deserves an ADR. Filter by **whether a reasonable engineer would ask "why this and not that?"** about it.

| Decision type | ADR? | Reason |
|---|---|---|
| Backend framework (FastAPI vs Flask vs Express) | ✅ | Significant downstream impact |
| Frontend framework (React vs Vue vs vanilla) | ✅ | Significant downstream impact |
| Database (SQLite vs Postgres vs in-memory) | ✅ | Affects deployment + data semantics |
| Auth approach (JWT vs sessions vs none) | ✅ | Security implication |
| Testing framework | ✅ | Affects how others extend the project |
| Project structure / layering | ✅ | Affects every contributor |
| CSS framework (if any) | ❌ | Cosmetic, low downstream impact |
| Specific Python version | ❌ | Boring, written in pyproject.toml |
| Linter (ruff) | ❌ | Convention, not a decision |
| Container base image | ⚠️ | Only if non-default (e.g., distroless or alpine) |

Rule of thumb: **6–10 ADRs** per project. Less than 6 looks token; more than 10 looks like noise.

## 4. Generating ADRs

Two approaches; we pick the cheaper one.

### Option A — Pure mapping (no extra LLM calls) ✅ recommended

The Architect already gives us `rationale` per TechChoice. We have enough structured data to mechanically generate ADRs without a second LLM call:

```python
# loom/adr/generator.py

ADR_TEMPLATE = """# ADR-{number:04d}: {title}

**Status:** Accepted
**Date:** {date}
**Decided by:** Loom Architect agent

## Context

{context}

## Decision

We will use **{technology} {version}** for {layer}.

## Alternatives Considered

{alternatives}

## Consequences

{consequences}

## References

{references}
"""

def generate_adrs(state: AgentState) -> dict[str, str]:
    """Returns {path: content} for ADR files."""
    decisions = filter_significant_decisions(state.architecture.stack)
    adrs = {}
    
    for i, choice in enumerate(decisions, start=1):
        adrs[f"docs/adrs/{i:04d}-{slugify(choice.layer)}-{slugify(choice.technology)}.md"] = (
            ADR_TEMPLATE.format(
                number=i,
                title=f"Use {choice.technology} for the {choice.layer.title()}",
                date=date.today().isoformat(),
                context=build_context(state, choice),
                technology=choice.technology,
                version=choice.version,
                layer=choice.layer,
                alternatives=build_alternatives(choice),
                consequences=build_consequences(choice),
                references=build_references(choice, decisions),
            )
        )
    
    # Add an index ADR
    adrs["docs/adrs/0000-index.md"] = build_index(decisions)
    return adrs
```

The "alternatives" and "consequences" sections need *some* domain content. Embed a small lookup table — keyed by `(layer, technology)` → short alternatives list and pros/cons — in `loom/adr/knowledge.py`. This is hardcoded but maintainable; covers ~30 (layer, technology) pairs which is enough.

```python
# loom/adr/knowledge.py
ADR_KNOWLEDGE = {
    ("backend", "FastAPI"): {
        "alternatives": [
            ("Flask", "simpler and more familiar, but lacks native async and "
                      "requires extra plumbing for OpenAPI docs and validation."),
            ("Express.js", "would split the language between frontend and backend; "
                           "not justified for a pure API project."),
        ],
        "positives": [
            "Native Pydantic integration matches our data validation strategy.",
            "Auto-generated OpenAPI docs at `/docs` simplify QA test generation.",
            "Async-first design supports future scaling without rework.",
        ],
        "negatives": [
            "Slightly steeper learning curve for contributors unfamiliar with async.",
            "Smaller middleware ecosystem than Express.",
        ],
    },
    ("backend", "Flask"): { /* ... */ },
    ("frontend", "React+Vite"): { /* ... */ },
    # ... etc
}
```

When a (layer, technology) pair isn't in the table, fall back to a generic template using only the Architect's `rationale` field. The ADR is still useful, just less rich.

**Total cost: zero additional LLM calls.**

### Option B — LLM-generated ADRs (rejected for v1)

Tempting but worse: spawn a tiny ADR-writer agent that reads architecture + PRD and produces ADRs as a FileBundle. Adds $0.05–$0.10 per build, adds a node to the graph, adds another failure mode (parse errors). Pure-mapping wins on every axis except richness, and the richness gap is small. **Don't do this in v1.** Revisit in v2 if user feedback says ADRs feel cookie-cutter.

## 5. Where ADRs Live

In the **output project**, not in Loom itself:

```
output/bookstore-api/
├── README.md
├── backend/
├── frontend/
├── tests/
├── docs/                          ← NEW
│   └── adrs/                      ← NEW
│       ├── 0000-index.md
│       ├── 0001-backend-fastapi.md
│       ├── 0002-frontend-react.md
│       ├── 0003-database-sqlite.md
│       ├── 0004-auth-jwt.md
│       ├── 0005-testing-pytest.md
│       └── 0006-folder-structure.md
├── Dockerfile
└── docker-compose.yml
```

The output README gets a new section:

```markdown
## Architecture Decisions

This project's design choices are documented as ADRs in `docs/adrs/`:

| # | Decision |
|---|---|
| [0001](docs/adrs/0001-backend-fastapi.md) | Use FastAPI for the Backend |
| [0002](docs/adrs/0002-frontend-react.md) | Use React + Vite for the Frontend |
| [0003](docs/adrs/0003-database-sqlite.md) | Use SQLite for Data Storage |
| ... | |
```

## 6. The Index ADR

`0000-index.md` is the table of contents:

```markdown
# Architecture Decision Records

This directory contains ADRs (Architectural Decision Records) for {project_name}.
Each ADR captures a significant design decision: the context, what was decided,
alternatives considered, and consequences.

## ADRs

| # | Decision | Status |
|---|---|---|
| 0001 | [Use FastAPI for the Backend](0001-backend-fastapi.md) | Accepted |
| 0002 | [Use React + Vite for the Frontend](0002-frontend-react.md) | Accepted |
| ... | | |

## When to Add a New ADR

Add a new ADR when you make a decision that:
- Has significant downstream impact on contributors
- A reasonable engineer might second-guess
- Future maintainers would benefit from the reasoning behind

## Format

We follow Michael Nygard's ADR format: Context → Decision → Alternatives →
Consequences → References. Number files sequentially. Mark superseded ADRs
with `Status: Superseded by ADR-NNNN`.
```

## 7. Wiring Into the Pipeline

Two integration points:

### 7.1 Post-graph file materialization

In `loom/output/writer.py`, after writing `state.code_files` and `state.devops_files`:

```python
def write_outputs(state: AgentState, output_dir: Path) -> None:
    # ... existing writes ...
    
    # Generate and write ADRs
    if state.config.adr.enabled:
        adrs = generate_adrs(state)
        for path, content in adrs.items():
            full_path = output_dir / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content)
        state.events.append(Event(
            type="adrs_generated",
            payload={"count": len(adrs)},
        ))
```

### 7.2 README integration

Update `loom/output/readme.py` to insert the "Architecture Decisions" section if ADRs were generated:

```python
def render_readme(state: AgentState) -> str:
    sections = [
        render_header(state),
        render_run_instructions(state),
        render_features(state),
    ]
    if state.config.adr.enabled:
        sections.append(render_adr_index_section(state))
    sections.append(render_footer(state))
    return "\n\n".join(sections)
```

## 8. Configuration

Add to `LoomConfig`:

```python
class ADRConfig(BaseModel):
    enabled: bool = True
    min_significance: Literal["all", "significant", "critical"] = "significant"
    # "all"        — every TechChoice gets an ADR (5–15)
    # "significant"— filter via the rules in §3 (6–10) ← default
    # "critical"   — only backend, frontend, db, auth (4)

class LoomConfig(BaseModel):
    # ... existing ...
    adr: ADRConfig = ADRConfig()
```

CLI flag: `loom build "..." --no-adrs` to disable for a single run.

## 9. Tests

```python
# tests/unit/test_adr_generation.py
def test_generates_adr_for_each_significant_choice():
    state = sample_state_with_full_arch()
    adrs = generate_adrs(state)
    
    # Index plus per-decision ADRs
    assert "docs/adrs/0000-index.md" in adrs
    assert any("backend" in path for path in adrs)
    assert any("frontend" in path for path in adrs)
    assert any("database" in path for path in adrs)
    
    # Numbered sequentially with no gaps
    numbered = sorted(p for p in adrs if p != "docs/adrs/0000-index.md")
    nums = [int(Path(p).stem.split("-")[0]) for p in numbered]
    assert nums == list(range(1, len(nums) + 1))


def test_unknown_tech_falls_back_to_generic_template():
    state = sample_state_with_unknown_tech("backend", "RocketRails")
    adrs = generate_adrs(state)
    backend_adr = next(c for p, c in adrs.items() if "backend" in p and "0001" in p)
    
    # Should still be a valid ADR even without ADR_KNOWLEDGE entry
    assert "RocketRails" in backend_adr
    assert "## Decision" in backend_adr
    assert "## Alternatives Considered" in backend_adr
    # Generic alternatives section should explain we don't have curated data
    # but still link to architect's rationale


def test_adr_index_lists_all_adrs():
    state = sample_state_with_full_arch()
    adrs = generate_adrs(state)
    index = adrs["docs/adrs/0000-index.md"]
    
    # Every ADR file should be linked from the index
    for path in adrs:
        if path != "docs/adrs/0000-index.md":
            filename = Path(path).name
            assert filename in index


def test_adrs_respect_disabled_config(tmp_path):
    """When config.adr.enabled = False, no ADR files are written."""
    state = sample_state_with_full_arch()
    state.config = state.config.model_copy(update={"adr": ADRConfig(enabled=False)})
    
    write_outputs(state, tmp_path)
    assert not (tmp_path / "docs" / "adrs").exists()
```

## 10. Implementation Checklist

Phase 8.7 tasks:

- [ ] Add `loom/adr/__init__.py`
- [ ] Implement `loom/adr/generator.py` (`generate_adrs`, `filter_significant_decisions`)
- [ ] Build `loom/adr/knowledge.py` — start with the 12 most common (layer, tech) pairs:
  - `(backend, FastAPI)`, `(backend, Flask)`, `(backend, Express.js)`
  - `(frontend, React+Vite)`, `(frontend, Vue 3)`, `(frontend, vanilla)`
  - `(database, SQLite)`, `(database, Postgres)`, `(database, in-memory)`
  - `(auth, JWT)`, `(auth, session cookies)`, `(auth, none)`
- [ ] Implement generic-fallback rendering for missing knowledge entries
- [ ] Implement `loom/adr/index.py` — generates `0000-index.md`
- [ ] Wire `generate_adrs` into `loom/output/writer.py`
- [ ] Update `loom/output/readme.py` to insert ADR index section
- [ ] Add `ADRConfig` to `loom/config/models.py`
- [ ] Add `--no-adrs` CLI flag in `cli/commands/build.py`
- [ ] Unit tests (above)
- [ ] Integration test: full build produces ADR files in `output/<slug>/docs/adrs/`
- [ ] Add screenshot of an ADR to the README (visual proof)
- [ ] Mention ADRs in the Loom video — quick scroll through `docs/adrs/` after the build completes

## 11. Future Extensions (not in v1)

- **Superseded ADRs across builds** — when a project is rebuilt with different choices, mark old ADRs as Superseded and link to the replacement.
- **ADR-aware retrieval** — during memory retrieval (see `MEMORY_SYSTEM.md`), surface ADRs from past similar projects so the Architect can cite them.
- **Per-feature ADRs** — let the dev agents add ADRs for non-trivial implementation choices (e.g., "Used optimistic locking for concurrent edits").
- **Lightweight ADR linter** — verifies ADRs in committed projects stay numbered consecutively, no broken refs.
