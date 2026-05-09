# MEMORY_SYSTEM — Self-Learning Across Builds

> **Status:** Phase 8.5 feature. Implement only after the core build pipeline (Phases 0–8) is stable and shipping.

This is the feature that takes Loom from "another LangGraph demo" to "this actually gets better over time." Every successful build is captured in a local vector store. On future builds, the Architect retrieves the most similar past projects and includes them as few-shot context — improving stack choices, API design, and code quality with every run.

**The headline demo:** show side-by-side a build #1 and a build #15 of the same prompt. The later one will be visibly better — fewer retries, cleaner architecture, more consistent patterns. Nobody else's agent framework demo can show this.

---

## 1. Why This Matters

### What's wrong without memory

Every Loom build today starts from zero. The Architect makes the same first-principles tradeoffs every time. If two users (or the same user twice) build "a todo app with auth," they may get FastAPI one time and Flask the next, JWT one time and sessions the next — pure LLM coin-flips. Token costs are the same on the 100th build as the 1st. Nothing accumulates.

### What memory unlocks

| Capability | Without memory | With memory |
|---|---|---|
| Stack consistency | Coin-flip per build | Converges on patterns that worked before |
| First-pass test success rate | ~60% (varies wildly) | Climbs toward 90%+ as corpus grows |
| Token cost per build | Flat | Drops 20–40% — fewer retries, tighter prompts |
| User trust | "Did the LLM get lucky?" | "It's improving the more I use it" |
| Demo value | One-shot magic | Visible learning curve |

### Why Architect is the right insertion point

The Architect's choices — stack, API design, folder layout — propagate into every downstream agent. Improving the Architect with retrieval has compounding effects on the rest of the pipeline. The dev agents could benefit too, but their inputs are already constrained by the architecture, so retrieval there has diminishing returns. **Start with Architect-only retrieval; expand later if measurements justify it.**

---

## 2. Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                          BUILD #N (current)                        │
│                                                                    │
│  User: "A todo app with auth and tags"                             │
│            │                                                       │
│            ▼                                                       │
│  ┌───────────────────┐                                             │
│  │  Product Manager  │ → PRD                                       │
│  └────────┬──────────┘                                             │
│           │                                                        │
│           ▼                                                        │
│  ┌────────────────────────────────────────────────────────┐       │
│  │  Memory Retriever  ◄─── queries vector store           │       │
│  │  - embed PRD.one_liner + must_have_features            │       │
│  │  - top-K similar past builds                            │       │
│  │  - filter by min similarity, exclude failed runs       │       │
│  │  - return MemoryContext (3 examples)                   │       │
│  └────────────┬───────────────────────────────────────────┘       │
│               │                                                    │
│               ▼                                                    │
│  ┌────────────────────┐                                            │
│  │     Architect      │ ← prompt now has memory_examples           │
│  │  (memory-aware)    │                                            │
│  └────────┬───────────┘                                            │
│           │                                                        │
│           ▼                                                        │
│           ... rest of pipeline ...                                 │
│           │                                                        │
│           ▼                                                        │
│  ┌────────────────────┐                                            │
│  │  Memory Writer     │ → upserts run into vector store            │
│  │  (post-build)      │   only if test_report.all_passed           │
│  └────────────────────┘                                            │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────────┐
│              VECTOR STORE  (.loom/memory/)                   │
│                                                                    │
│   chromadb persistent client OR lancedb table                      │
│                                                                    │
│   Per record:                                                      │
│     id           = run_id (UUID)                                   │
│     embedding    = sentence-transformers/all-MiniLM-L6-v2          │
│     content      = embedding-source text                           │
│     metadata     = {project_type, stack_summary, success, ...}     │
│     payload      = {prd, architecture, file_count, retry_count}    │
└────────────────────────────────────────────────────────────────────┘
```

## 3. Storage Choice — LanceDB

I recommend **LanceDB** over Chroma for these reasons:

| Concern | LanceDB | Chroma |
|---|---|---|
| Install footprint | Single Python package, ships its own format | Python + duckdb + sqlite layers |
| Embedded mode | First-class — file-based, zero config | Persistent client requires care |
| Performance at small scale | Equivalent | Equivalent |
| Filter + vector hybrid query | Native | Native |
| Maintainership | Steady | Active but heavier API churn |
| Disk format | Parquet-like, inspectable | Opaque |

LanceDB is in `pip install lancedb`; data lives in `./.loom/memory/lancedb/` as files you can inspect or delete. No Docker, no daemon.

If you prefer Chroma for any reason, the rest of this design is unchanged — only `MemoryStore` swaps backends.

## 4. Embedding Model

Use `sentence-transformers/all-MiniLM-L6-v2`:
- 22M params, ~80MB on disk
- 384-dim embeddings, plenty for similarity over short PRD summaries
- Runs on CPU at ~1000 docs/sec
- Bundled via `pip install sentence-transformers`
- No API call — works fully offline (consistent with Ollama-default ethos)

For users with API budget, expose a config option for OpenAI or Voyage AI embeddings, but **default must be local**.

```python
# loom/memory/embedder.py
from sentence_transformers import SentenceTransformer

class LocalEmbedder:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self._model = SentenceTransformer(model_name)
    
    def embed(self, text: str) -> list[float]:
        return self._model.encode(text, convert_to_numpy=True).tolist()
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, convert_to_numpy=True).tolist()
```

## 5. What Gets Embedded

The embedding represents what the build is "about" — not the code itself. Embed a concise descriptor:

```
{project_type} | {one_liner}
must_have: {feature1}, {feature2}, {feature3}
data_entities: {Entity1}, {Entity2}
```

Example for a todo app:
```
fullstack_web | Simple todo list with user auth and tags
must_have: signup, login, create todo, mark done, filter by tag
data_entities: User, Todo, Tag
```

This is short (≤200 tokens), captures intent and shape, and is symmetric between query (new build's PRD) and stored (past PRDs).

**Don't embed the full PRD or the code.** Code is high-volume noise; full PRDs make similar projects with different wording look dissimilar.

## 6. Data Models

```python
# loom/memory/models.py
from datetime import datetime
from pydantic import BaseModel, Field

class MemoryRecord(BaseModel):
    """A single past-build record stored in the vector DB."""
    run_id: str                      # UUID, primary key
    timestamp: datetime
    
    # Embedded
    descriptor: str                  # the text we embed
    
    # Filterable metadata
    project_type: ProjectType
    stack_summary: str               # "FastAPI+React+SQLite"
    test_passed: bool
    retry_count: int
    file_count: int
    total_cost_usd: float
    
    # Payload (returned with hits, used in few-shot context)
    one_liner: str
    must_have_features: list[str]
    data_entity_names: list[str]
    chosen_stack: list[TechChoice]
    api_endpoint_summary: list[str]  # ["GET /todos", "POST /todos", ...]
    folder_structure_keys: list[str] # top-level dirs only

class MemoryContext(BaseModel):
    """What the Architect receives in its prompt."""
    examples: list[MemoryRecord]      # top-K, ordered by similarity
    similarity_scores: list[float]    # parallel array
    
    def to_prompt_block(self) -> str:
        """Render as a few-shot block."""
        if not self.examples:
            return ""
        lines = ["# Similar past builds (use as guidance, not constraints)"]
        for i, (rec, score) in enumerate(zip(self.examples, self.similarity_scores)):
            lines.append(f"\n## Example {i+1} (similarity {score:.2f})")
            lines.append(f"Project: {rec.one_liner}")
            lines.append(f"Stack chosen: {rec.stack_summary}")
            lines.append(f"Endpoints: {', '.join(rec.api_endpoint_summary[:8])}")
            lines.append(f"Outcome: {'tests passed' if rec.test_passed else 'tests failed'} "
                        f"on {'first try' if rec.retry_count == 0 else f'retry #{rec.retry_count}'}")
        return "\n".join(lines)
```

## 7. The MemoryStore Interface

```python
# loom/memory/store.py
import lancedb
from pathlib import Path
from typing import Protocol

class MemoryStore(Protocol):
    def upsert(self, record: MemoryRecord, embedding: list[float]) -> None: ...
    def search(self, query_embedding: list[float], k: int = 3,
               filters: dict | None = None) -> list[tuple[MemoryRecord, float]]: ...
    def count(self) -> int: ...
    def clear(self) -> None: ...
    def export(self, path: Path) -> None: ...
    def import_(self, path: Path) -> int: ...   # returns count imported


class LanceDBStore:
    TABLE_NAME = "build_memory"
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(db_path))
        self._ensure_table()
    
    def _ensure_table(self) -> None:
        if self.TABLE_NAME not in self._db.table_names():
            # Bootstrap with empty schema by inserting a placeholder + deleting
            # See lancedb docs for proper PyArrow schema if you want it stricter.
            schema = self._build_schema()
            self._db.create_table(self.TABLE_NAME, schema=schema)
    
    def upsert(self, record: MemoryRecord, embedding: list[float]) -> None:
        table = self._db.open_table(self.TABLE_NAME)
        row = {**record.model_dump(), "vector": embedding}
        # LanceDB upsert via merge_insert
        table.merge_insert("run_id").when_matched_update_all() \
             .when_not_matched_insert_all().execute([row])
    
    def search(self, query_embedding: list[float], k: int = 3,
               filters: dict | None = None) -> list[tuple[MemoryRecord, float]]:
        table = self._db.open_table(self.TABLE_NAME)
        q = table.search(query_embedding).limit(k * 3)  # over-fetch for filtering
        
        # Apply filters
        where = ["test_passed = true"]   # always exclude failures
        if filters:
            if "project_type" in filters:
                where.append(f"project_type = '{filters['project_type']}'")
        if where:
            q = q.where(" AND ".join(where))
        
        results = q.to_list()[:k]
        return [
            (MemoryRecord(**{k: v for k, v in r.items() if k != "vector" and k != "_distance"}),
             1.0 - r["_distance"])  # convert distance to similarity
            for r in results
        ]
    
    def count(self) -> int:
        return self._db.open_table(self.TABLE_NAME).count_rows()
    
    def clear(self) -> None:
        self._db.drop_table(self.TABLE_NAME)
        self._ensure_table()
```

## 8. Wiring Into the Graph

Two new graph nodes: `memory_retrieve` (before Architect) and `memory_persist` (terminal).

```python
# loom/agents/memory_retrieve.py
from loom.memory.store import get_memory_store
from loom.memory.embedder import get_embedder

async def memory_retrieve_node(state: AgentState) -> dict:
    """Inject MemoryContext into state before the Architect runs."""
    if not state.config.get("memory_enabled", True):
        return {"memory_context": MemoryContext(examples=[], similarity_scores=[])}
    if state.prd is None:
        return {}  # nothing to retrieve against
    
    descriptor = build_descriptor(state.prd)
    embedder = get_embedder(state.config)
    store = get_memory_store(state.config)
    
    if store.count() == 0:
        return {"memory_context": MemoryContext(examples=[], similarity_scores=[])}
    
    embedding = embedder.embed(descriptor)
    hits = store.search(
        embedding,
        k=state.config.get("memory_top_k", 3),
        filters={"project_type": state.prd.project_type.value},
    )
    
    # Filter out very weak matches — better to have no example than a misleading one
    min_sim = state.config.get("memory_min_similarity", 0.55)
    filtered = [(rec, score) for rec, score in hits if score >= min_sim]
    
    return {
        "memory_context": MemoryContext(
            examples=[rec for rec, _ in filtered],
            similarity_scores=[score for _, score in filtered],
        ),
        "events": [Event(type="memory_retrieved", payload={
            "candidates_searched": store.count(),
            "hits_above_threshold": len(filtered),
        })],
    }


def build_descriptor(prd: PRD) -> str:
    return (
        f"{prd.project_type.value} | {prd.one_liner}\n"
        f"must_have: {', '.join(prd.must_have_features[:6])}\n"
        f"data_entities: {', '.join(e.name for e in prd.data_entities[:6])}"
    )
```

Updated graph topology:

```
project_manager
       │
       ▼
product_manager
       │
       ▼
project_manager  ←── unchanged
       │
       ▼
memory_retrieve  ←── NEW
       │
       ▼
architect (now reads state.memory_context)
       │
       ... unchanged ...
```

And at the end:

```python
async def memory_persist_node(state: AgentState) -> dict:
    """Persist this run to memory if it succeeded."""
    if not state.config.get("memory_enabled", True):
        return {}
    if state.test_report is None or not state.test_report.all_passed:
        # Don't memorize failures — they'd poison future builds
        return {"events": [Event(type="memory_skipped", payload={"reason": "tests_failed"})]}
    
    record = MemoryRecord.from_state(state)
    embedder = get_embedder(state.config)
    store = get_memory_store(state.config)
    embedding = embedder.embed(record.descriptor)
    store.upsert(record, embedding)
    
    return {"events": [Event(type="memory_persisted", payload={"run_id": record.run_id})]}
```

Add as final node before END:

```
devops_engineer → memory_persist → END
```

## 9. Updating the Architect Prompt

Append a few-shot block when memory_context is non-empty. Modify `agents/prompts/architect.py`:

```python
ARCHITECT_SYSTEM_PROMPT = """
You are a Principal Software Architect ...
[existing content]
"""

ARCHITECT_USER_TEMPLATE = """
PRD:
{prd_json}

{memory_block}

Produce the ArchitectureDoc.
"""

# In agents/architect.py:
def build_architect_input(state: AgentState) -> dict:
    memory_block = ""
    if state.memory_context and state.memory_context.examples:
        memory_block = state.memory_context.to_prompt_block()
        memory_block = (
            f"{memory_block}\n\n"
            f"These are reference examples from past successful builds, not "
            f"strict requirements. Choose what fits this project's needs."
        )
    return {
        "prd_json": state.prd.model_dump_json(indent=2),
        "memory_block": memory_block,
    }
```

The "guidance, not constraints" framing matters — without it, smaller models (Ollama) will copy past stacks even when they don't fit.

## 10. State Updates

Add to `AgentState`:

```python
class AgentState(BaseModel):
    # ... existing fields ...
    memory_context: MemoryContext | None = None
```

Add to `LoomConfig`:

```python
class MemoryConfig(BaseModel):
    enabled: bool = True
    db_path: str = ".loom/memory/lancedb"
    embedder: Literal["local", "openai", "voyage"] = "local"
    embedder_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    top_k: int = 3
    min_similarity: float = 0.55
    only_persist_passing: bool = True   # never store failed runs

class LoomConfig(BaseModel):
    # ... existing fields ...
    memory: MemoryConfig = MemoryConfig()
```

## 11. CLI Surface

```bash
loom memory show              # how many records, oldest, newest, breakdown by project_type
loom memory list              # paginated list of all records
loom memory search "todo app" # ad-hoc search to debug retrieval
loom memory clear             # wipe everything (with confirmation)
loom memory export memory.jsonl
loom memory import memory.jsonl
loom memory disable           # turn off for this project (writes to .loom.toml)
```

The export/import lets users **share trained memory** — a recruiter could import your "100 successful builds" memory bundle and watch it work on novel prompts. Big demo lever.

## 12. Disk Layout

```
~/.loom/                       # user-global (default location)
└── memory/
    └── lancedb/
        ├── build_memory.lance/
        │   ├── data/
        │   ├── _versions/
        │   └── _indices/
        └── .config

# OR project-local if user prefers:
./.loom/
└── memory/
    └── lancedb/
        └── ...
```

Default to **user-global** (`~/.loom/`) so memory accumulates across all projects. Allow `--memory-scope=project` to keep memory inside `./.loom/`.

## 13. Failure Modes & Handling

| Failure | Handling |
|---|---|
| Embedder model not downloaded | First-run download with progress bar; cache in `~/.cache/torch/sentence_transformers/` |
| LanceDB corrupted | Auto-detect via `count()` raising; offer `loom memory repair` (rebuild from export) |
| Disk full | Catch `OSError` in upsert; warn user, continue without persisting |
| Embedding dim mismatch | Detect at startup (compare expected vs table schema); fail loudly with migration hint |
| Memory enabled but `pip install lancedb` not done | Detect at import; print install hint; auto-disable for this run |
| User uses a different embedder mid-corpus | Block — embeddings from different models aren't comparable. Force `loom memory clear` first. |

## 14. Privacy & Safety

- All data is **local-only by default**. No phone-home.
- Generated *code* is NOT stored — only PRD, architecture metadata, and stack choice. (Code recall would create a license-attribution mess and balloon disk usage.)
- Provide `loom memory redact <run_id>` to scrub a specific record (e.g., if a PRD contained internal project names).
- `loom memory export` produces JSONL the user can inspect before sharing.

## 15. Demoing the Learning Curve

Pre-record this for the README and Loom:

1. Wipe memory: `loom memory clear`
2. Run build #1 of "todo app with tags": shows zero retrieval, takes 2.3 retries, costs $0.55
3. Run builds #2-10 with diverse prompts (book reviews, URL shortener, kanban, etc.) — all stored
4. Run build #11 of "task tracker with categories" — semantically near "todo app with tags"
5. Show in the dashboard: **Memory Retriever** node lights up, finds 3 prior matches, similarity 0.78 / 0.71 / 0.62
6. The Architect's choices match the prior stack; **0 retries**, cost $0.32

Side-by-side animation of build #1 vs build #11 is the money shot. Caption: *"Loom gets faster and cheaper the more you use it."*

## 16. Measuring Whether It Actually Helps

Build a small eval harness in `scripts/eval_memory.py`:

```
- Take 20 prompts from examples/eval_set/
- Run each twice: once with memory disabled, once with memory enabled (warmed corpus of 50 builds)
- Measure: avg retry_count, avg cost, avg total time, % of stacks that match the chosen "best" stack
- Plot results in docs/images/memory_eval.png
```

If the numbers don't move, **don't ship the feature** — kill it and keep the rest of the project clean. Only ship features that survive measurement.

## 17. Implementation Checklist

Phase 8.5 tasks (mirrors `IMPLEMENTATION_PLAN.md`):

- [ ] Add `lancedb`, `sentence-transformers` to `[project.optional-dependencies] memory`
- [ ] Implement `loom/memory/models.py` (MemoryRecord, MemoryContext, MemoryConfig)
- [ ] Implement `loom/memory/embedder.py` (LocalEmbedder, OpenAIEmbedder)
- [ ] Implement `loom/memory/store.py` (LanceDBStore)
- [ ] Implement `loom/memory/factory.py` (`get_memory_store`, `get_embedder`)
- [ ] Add `MemoryRecord.from_state(state)` constructor — extracts the right fields
- [ ] Implement `agents/memory_retrieve.py` and `agents/memory_persist.py`
- [ ] Add `memory_context` field to `AgentState`
- [ ] Wire both nodes into `graph/builder.py` (between PM and Architect; after DevOps)
- [ ] Update Architect prompt to read `{memory_block}` placeholder
- [ ] Implement CLI commands: `loom memory show/list/search/clear/export/import/disable`
- [ ] Unit tests for store (in-memory mode), embedder (with cached small model)
- [ ] Integration test: warm corpus with 5 records, run build, assert MemoryContext non-empty
- [ ] Eval harness `scripts/eval_memory.py`
- [ ] Pre-record the side-by-side demo for the README

## 18. What This Doc Does NOT Cover (Future Work)

- **Code-level retrieval** — embedding individual functions/files for the dev agents. Next iteration.
- **Per-agent memory** — QA could remember which test patterns flake. Phase 9+.
- **Federated memory** — sharing memory across users without central server. Out of scope for portfolio.
- **Online learning** — fine-tuning a model on past builds. Out of scope; memory retrieval gives 80% of the value at 1% of the complexity.
