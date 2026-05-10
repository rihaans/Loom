# GRAPH_DESIGN — The LangGraph State Machine

This is the heart of Loom. The system is one `StateGraph[AgentState]` with conditional routing, parallel fan-out, and a self-correcting subgraph.

---

## 1. Graph Topology

```
                          ┌─────────┐
                          │  START  │
                          └────┬────┘
                               │
                               ▼
                       ┌───────────────┐
                  ┌───►│project_manager│◄──────────────┐
                  │    │  (supervisor) │               │
                  │    └───────┬───────┘               │
                  │            │                        │
                  │     conditional edge                │
                  │     (decides next phase)            │
                  │            │                        │
        ┌─────────┼────────────┼──────────────┐        │
        │         │            │              │        │
        ▼         ▼            ▼              ▼        │
┌────────────┐ ┌────────┐ ┌─────────┐ ┌────────────┐   │
│ product_   │ │architect│ │route_to_│ │qa_engineer │   │
│ manager    │ │         │ │devs     │ │            │   │
└─────┬──────┘ └────┬────┘ └────┬────┘ └─────┬──────┘   │
      │             │           │             │          │
      │             │     ┌─────┴─────┐       │          │
      │             │     │ Send API  │       │          │
      │             │     │ (parallel)│       │          │
      │             │     ├──────┬────┤       │          │
      │             │     ▼      ▼    │       │          │
      │             │ ┌────────┐┌────────┐    │          │
      │             │ │frontend││backend │    │          │
      │             │ │  _dev  ││  _dev  │    │          │
      │             │ └────┬───┘└───┬────┘    │          │
      │             │      └────┬───┘         │          │
      │             │           │             │          │
      └─────────────┴───────────┴─────────────┘          │
                               │                         │
                               └─────────────────────────┘
                               (loop back to PM)

      project_manager (when phase==deployment)
                               │
                               ▼
                       ┌───────────────┐
                       │devops_engineer│
                       └───────┬───────┘
                               │
                               ▼
                          ┌─────────┐
                          │   END   │
                          └─────────┘
```

## 2. Node Inventory

| Node | Type | Reads from state | Writes to state |
|---|---|---|---|
| `project_manager` | Supervisor | `phase`, `prd`, `architecture`, `code_files`, `test_report`, `retry_count` | `phase`, `events` |
| `product_manager` | Worker | `description` | `prd`, `messages`, `events`, `costs` |
| `architect` | Worker | `description`, `prd` | `architecture`, `messages`, `events`, `costs` |
| `route_to_devs` | Routing fn | `prd`, `architecture` | (returns `Send[]`, no state write) |
| `frontend_dev` | Worker | `prd`, `architecture`, `qa_feedback?` | `code_files["frontend"]`, `events`, `costs` |
| `backend_dev` | Worker | `prd`, `architecture`, `qa_feedback?` | `code_files["backend"]`, `events`, `costs` |
| `qa_engineer` | Worker | `prd`, `architecture`, `code_files` | `test_report`, `qa_feedback`, `events`, `costs` |
| `devops_engineer` | Worker | `architecture`, `code_files` | `devops_files`, `events`, `costs` |

## 3. The Supervisor Logic (project_manager)

The supervisor is the brain. It examines state and decides the next phase. **It never produces artifacts itself** — only routing decisions.

```python
def project_manager(state: AgentState) -> dict:
    """Pure routing logic — no LLM call, deterministic."""
    
    # Decide next phase based on what's been done
    if state.prd is None:
        next_phase = Phase.REQUIREMENTS
    elif state.architecture is None:
        next_phase = Phase.DESIGN
    elif not state.code_files or "frontend" not in state.code_files:
        next_phase = Phase.DEVELOPMENT
    elif state.test_report is None:
        next_phase = Phase.TESTING
    elif state.test_report.passed is False and state.retry_count < MAX_RETRIES:
        next_phase = Phase.DEVELOPMENT  # retry with feedback
    elif not state.devops_files:
        next_phase = Phase.DEPLOYMENT
    else:
        next_phase = Phase.DONE
    
    return {
        "phase": next_phase,
        "events": [Event(type="phase_transition", phase=next_phase)],
    }
```

**Note:** The supervisor is deterministic Python, not an LLM call. This keeps routing predictable and saves tokens. (An LLM-based supervisor is opt-in via `--llm-supervisor` for users who want to learn that pattern.)

## 4. Conditional Edge from Supervisor

```python
def route_after_pm(state: AgentState) -> str:
    return {
        Phase.REQUIREMENTS: "product_manager",
        Phase.DESIGN: "architect",
        Phase.DEVELOPMENT: "route_to_devs",
        Phase.TESTING: "qa_engineer",
        Phase.DEPLOYMENT: "devops_engineer",
        Phase.DONE: END,
    }[state.phase]

graph.add_conditional_edges(
    "project_manager",
    route_after_pm,
    {
        "product_manager": "product_manager",
        "architect": "architect",
        "route_to_devs": "route_to_devs",
        "qa_engineer": "qa_engineer",
        "devops_engineer": "devops_engineer",
        END: END,
    },
)
```

## 5. Parallel Fan-Out (Send API)

```python
from langgraph.types import Send

def route_to_devs(state: AgentState) -> list[Send]:
    """Launch frontend and backend in parallel."""
    return [
        Send("frontend_dev", state),
        Send("backend_dev", state),
    ]

graph.add_node("route_to_devs", route_to_devs)
graph.add_edge("frontend_dev", "project_manager")
graph.add_edge("backend_dev", "project_manager")
```

LangGraph waits for **both** dev agents to finish before re-entering `project_manager`. Their outputs merge via the `code_files` dict-merge reducer.

## 6. The Retry Loop

When QA finds failing tests, the supervisor sends control back to the dev agents with `qa_feedback` populated:

```
qa_engineer (tests fail, retry_count < 2)
        │
        ▼
project_manager  (sees test_report.passed == False, increments retry)
        │
        ▼
route_to_devs    (re-fans-out, but now state.qa_feedback contains errors)
        │
        ├──► frontend_dev  (reads qa_feedback, fixes)
        └──► backend_dev   (reads qa_feedback, fixes)
        │
        ▼
project_manager  (back to TESTING phase)
        │
        ▼
qa_engineer  (re-runs tests in fresh sandbox)
```

After `MAX_RETRIES` (default 2), if tests still fail, the supervisor advances to `DEPLOYMENT` anyway with a warning logged. Better to ship something than nothing for a demo.

## 7. Subgraph: Dev↔QA Cycle (Optional Extraction)

For cleaner code, the dev↔QA loop can be extracted into a subgraph:

```python
dev_qa_subgraph = StateGraph(AgentState)
dev_qa_subgraph.add_node("route_to_devs", route_to_devs)
dev_qa_subgraph.add_node("frontend_dev", frontend_dev)
dev_qa_subgraph.add_node("backend_dev", backend_dev)
dev_qa_subgraph.add_node("qa_engineer", qa_engineer)

dev_qa_subgraph.set_entry_point("route_to_devs")
dev_qa_subgraph.add_edge("frontend_dev", "qa_engineer")
dev_qa_subgraph.add_edge("backend_dev", "qa_engineer")
dev_qa_subgraph.add_conditional_edges(
    "qa_engineer",
    lambda s: "retry" if not s.test_report.passed and s.retry_count < 2 else "done",
    {"retry": "route_to_devs", "done": END},
)

# Use in main graph as a single node
main_graph.add_node("dev_qa", dev_qa_subgraph.compile())
```

This pattern is encouraged in v2 once the flat graph is working.

## 8. Interrupts (Human-in-the-Loop)

When `interactive=True`, the graph pauses after PM and Architect for user review:

```python
graph = builder.compile(
    checkpointer=SqliteSaver.from_conn_string("checkpoints.db"),
    interrupt_after=["product_manager", "architect"] if interactive else [],
)

# Run
config = {"configurable": {"thread_id": run_id}}
async for event in graph.astream_events(initial_state, config=config):
    yield event

# After interrupt, user can inspect/edit state
current = graph.get_state(config)
# Modify if desired
graph.update_state(config, {"prd": edited_prd})
# Resume
async for event in graph.astream_events(None, config=config):
    yield event
```

## 9. Checkpointing

LangGraph's `SqliteSaver` persists state after every node:

```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver.from_conn_string(".loom/checkpoints.db")
graph = builder.compile(checkpointer=checkpointer)
```

Every run gets a unique `thread_id` (UUID). `loom resume <thread_id>` picks up where it left off. Enables time-travel debugging too — replay from any saved node.

## 10. Streaming

The CLI and dashboard both consume `graph.astream_events(state, version="v2")`:

| Event type | When | What we do with it |
|---|---|---|
| `on_chain_start` (node) | Node begins | Light up the node in the graph viz |
| `on_chat_model_stream` | LLM token | Stream into the side panel for that agent |
| `on_chain_end` (node) | Node finishes | Mark complete, update artifact panel |
| `on_tool_start` | Tool invoked | Show tool call indicator |
| `on_tool_end` | Tool finishes | Show result |

## 11. Reducers Recap

```python
from typing import Annotated
from operator import add
from langgraph.graph.message import add_messages

class AgentState(BaseModel):
    description: str
    phase: Phase
    prd: PRD | None = None
    architecture: ArchitectureDoc | None = None
    code_files: Annotated[dict[str, FileBundle], merge_dicts] = {}
    test_report: TestReport | None = None
    qa_feedback: QAFeedback | None = None
    devops_files: DevOpsBundle | None = None
    retry_count: int = 0
    messages: Annotated[list[BaseMessage], add_messages] = []
    events: Annotated[list[Event], add] = []
    costs: Annotated[list[CostEntry], add] = []
```

## 12. Visualizing the Graph

LangGraph can export Mermaid:

```python
graph.get_graph().draw_mermaid_png(output_file_path="docs/graph.png")
```

This image goes in the README. The web dashboard's React frontend renders the same graph live with `@xyflow/react`.

## 13. Implementation Checklist for Claude Code

- [ ] Define `AgentState` first (fully typed Pydantic)
- [ ] Define all reducers
- [ ] Implement supervisor as **pure Python**, no LLM
- [ ] Add nodes one at a time, test each in isolation
- [ ] Add edges (linear path first, then conditional)
- [ ] Add Send API parallel fan-out
- [ ] Add retry conditional edge
- [ ] Add checkpointing
- [ ] Add interrupts (gated by `interactive` flag)
- [ ] Verify with `graph.get_graph().draw_ascii()` after each phase

Do NOT add HIL or subgraphs until the linear graph runs end-to-end.
