# UI_SPEC — CLI & Web Dashboard

Two interfaces, one shared event stream from LangGraph.

---

## Part A — CLI (Textual TUI)

### Layout

```
┌─ AgentForge ─────────────────────────────────────────────────────────┐
│                                                                       │
│  Building: "REST API for a bookstore with CRUD and search"           │
│                                                                       │
│  ┌─ Pipeline ──────────────────────────────────────────────────┐    │
│  │  ✓ Project Manager     [routed to: Architect]                │    │
│  │  ✓ Product Manager     [PRD ready: 8 user stories]           │    │
│  │  ⠋ Architect           [choosing stack...      ]             │    │
│  │  ○ Frontend Dev                                                │    │
│  │  ○ Backend Dev                                                 │    │
│  │  ○ QA Engineer                                                 │    │
│  │  ○ DevOps Engineer                                             │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌─ Live Output (Architect) ────────────────────────────────────┐    │
│  │ Choosing FastAPI + SQLite for fast iteration. The data model │    │
│  │ requires Books, Authors, Reviews. I'll define 12 endpoints   │    │
│  │ across these resources, with /api/search for full-text...    │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌─ Stats ─────────────────┐ ┌─ Events ─────────────────────────┐  │
│  │ Tokens used: 12,543      │ │ 14:32:01 PM started               │  │
│  │ Cost: $0.18              │ │ 14:32:18 PM done (4.2s)           │  │
│  │ Elapsed: 1m 24s          │ │ 14:32:18 Routed to Architect      │  │
│  │ Phase: design            │ │ 14:32:19 Architect started        │  │
│  └────────────────────────┘ └────────────────────────────────────┘  │
│                                                                       │
│  Press Ctrl+C to abort  •  --interactive for HIL  •  --ui for web    │
└──────────────────────────────────────────────────────────────────────┘
```

### Key bindings

| Key | Action |
|---|---|
| `Ctrl+C` | Abort build (saves checkpoint, can resume) |
| `q` | Quit (after build complete) |
| `1-7` | Switch live output panel to specific agent |
| `s` | Toggle stats panel |
| `e` | Toggle event log expansion |

### Implementation

Built on `textual`:

```python
# agentforge/cli/tui.py
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, ProgressBar
from textual.containers import Vertical, Horizontal

class BuildTUI(App):
    CSS_PATH = "tui.css"
    BINDINGS = [("q", "quit", "Quit"), ("s", "toggle_stats", "Stats")]
    
    def __init__(self, build_stream):
        super().__init__()
        self.build_stream = build_stream
    
    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield PipelineView(id="pipeline")
            yield LiveOutput(id="output")
            with Horizontal():
                yield StatsPanel(id="stats")
                yield EventLog(id="events")
        yield Footer()
    
    async def on_mount(self):
        async for event in self.build_stream:
            self.dispatch_event(event)
```

### Non-TUI fallback

For CI / non-interactive shells, `agentforge build "..." --plain` produces simple log output:

```
[14:32:01] PM started
[14:32:18] PM done — PRD: 8 stories
[14:32:19] Architect started
[14:32:45] Architect done — Stack: FastAPI + SQLite
[14:32:46] Backend Dev + Frontend Dev started (parallel)
[14:33:12] Backend Dev done — 8 files
[14:33:21] Frontend Dev done — 5 files
[14:33:22] QA started
[14:33:48] QA passed: 8/8
[14:33:49] DevOps done
[14:33:50] DONE — output/bookstore-api/  ($0.43, 1m 49s)
```

---

## Part B — Web Dashboard

### Pages

| Route | Purpose |
|---|---|
| `/` | Home — input form + recent runs |
| `/build/:run_id` | Live build view (the showcase) |
| `/runs` | Past runs list |
| `/runs/:run_id` | Read-only view of a completed run |
| `/settings` | LLM provider config |

### `/build/:run_id` — The Showcase Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  AgentForge                                       Cost: $0.18  ⚙️    │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─ Agent Graph ──────────────────────┐ ┌─ Active: Architect ─────┐ │
│  │                                      │ │                          │ │
│  │       ●━━━━━━━━━━━●━━━━━━━━━━●     │ │ Streaming output...     │ │
│  │       PM         PdM       Arch   ◀━━│ │                          │ │
│  │                              │       │ │ Choosing FastAPI...      │ │
│  │                  ┌──────────┴──┐    │ │                          │ │
│  │                  ▼              ▼   │ │ The system needs to      │ │
│  │                  ●              ●   │ │ handle 12 endpoints...   │ │
│  │                FE Dev        BE Dev │ │                          │ │
│  │                  └──────┬──────┘    │ │                          │ │
│  │                         ▼            │ └─────────────────────────┘ │
│  │                         ●            │                              │
│  │                         QA           │ ┌─ Artifacts ──────────────┐│
│  │                         │             │ │ ▶ PRD                     ││
│  │                         ▼             │ │ ▶ Architecture (active)   ││
│  │                         ●             │ │ ▶ Code Files (locked)     ││
│  │                       DevOps          │ │ ▶ Test Report (locked)    ││
│  │                                       │ │ ▶ DevOps (locked)         ││
│  └────────────────────────────────────┘ └─────────────────────────────┘│
│                                                                       │
│  ┌─ Event Stream ──────────────────────────────────────────────────┐│
│  │ 14:32:18 ▸ Product Manager done (4.2s, $0.04, 3,200 tokens)    ││
│  │ 14:32:18 ▸ Project Manager → routed to Architect                ││
│  │ 14:32:19 ▸ Architect started                                    ││
│  │ 14:32:21 ▸ Architect → web_search("FastAPI vs Flask 2025")     ││
│  └──────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────┘
```

### Components

#### `<GraphView />`
- Built with `@xyflow/react` (reactflow)
- Nodes are custom `<AgentNode />` components
- Node states: `idle` (gray), `active` (pulsing), `done` (green check), `failed` (red X)
- Edges animate when traversed (`animated: true` flag)
- Layout is fixed — it's a viz, not an editor

#### `<AgentNode />`
```tsx
function AgentNode({ data }: NodeProps) {
  return (
    <div className={cn(
      "rounded-lg border-2 p-3 min-w-[140px] bg-white shadow",
      data.state === 'active' && 'border-blue-500 animate-pulse',
      data.state === 'done' && 'border-green-500',
      data.state === 'failed' && 'border-red-500',
    )}>
      <div className="flex items-center gap-2">
        <Icon name={data.icon} />
        <span className="font-medium">{data.label}</span>
      </div>
      {data.tokens && (
        <div className="text-xs text-gray-500 mt-1">
          {data.tokens.toLocaleString()} tokens
        </div>
      )}
    </div>
  );
}
```

#### `<ArtifactPanel />`
Tabs for each artifact type. Code files use Monaco editor (read-only, syntax highlighting). PRD/Architecture rendered as Markdown. Test Report as a custom view with expandable failed cases.

#### `<EventLog />`
Virtualized list (only render visible items) — important because long builds emit thousands of events. Filter by agent or event type.

#### `<CostMeter />`
Live updating bar showing token usage and USD cost. Shows breakdown by agent on hover.

### WebSocket Protocol

Server → Client messages (JSON):

```typescript
type ServerEvent =
  | { type: "node_start"; agent: AgentRole; timestamp: string }
  | { type: "node_end"; agent: AgentRole; duration_ms: number; cost_usd: number }
  | { type: "llm_token"; agent: AgentRole; token: string }
  | { type: "tool_call"; agent: AgentRole; tool: string; args: any }
  | { type: "tool_result"; agent: AgentRole; tool: string; ok: boolean }
  | { type: "artifact_update"; artifact: "prd" | "architecture" | "..."; data: any }
  | { type: "phase_change"; phase: Phase }
  | { type: "error"; message: string }
  | { type: "done"; output_dir: string; total_cost_usd: number };
```

Client → Server:

```typescript
type ClientEvent =
  | { type: "subscribe"; run_id: string }
  | { type: "interrupt_response"; data: any }    // for HIL
  | { type: "abort" };
```

### Styling

- Tailwind for utility CSS
- Color scheme: dark mode default (looks better in demo videos)
- Font: `JetBrains Mono` for code, `Inter` for UI (or `Geist` family)
- Animations subtle; pulsing borders on active nodes are the only "loud" thing

### State Management

`zustand` store mirrors the build state:

```ts
interface BuildStore {
  runId: string | null;
  phase: Phase;
  agents: Record<AgentRole, AgentStatus>;
  artifacts: {
    prd?: PRD;
    architecture?: ArchitectureDoc;
    codeFiles: Record<string, FileBundle>;
    testReport?: TestReport;
    devopsFiles?: DevOpsBundle;
  };
  events: Event[];
  cost: number;
  tokens: number;
  
  startBuild: (description: string) => void;
  applyEvent: (event: ServerEvent) => void;
  abort: () => void;
}
```

### Settings Page

Simple form:
- LLM provider (radio: anthropic / openai / ollama)
- Model name (select with curated options)
- API key (masked input, stored in browser localStorage AND sent to server for the session)
- Profile preset (dropdown: balanced / quality / cheap / local)

Settings persist to localStorage; backend uses session-scoped keys for security (never logged).

---

## Part C — Streaming Pipeline (shared)

Both CLI and web dashboard consume the same event stream from LangGraph:

```python
# agentforge/observability/streaming.py
async def stream_events(graph, initial_state, config):
    """Convert raw astream_events into typed AgentForge events."""
    async for event in graph.astream_events(initial_state, config=config, version="v2"):
        kind = event["event"]
        if kind == "on_chain_start" and event["name"] in NODE_NAMES:
            yield NodeStartEvent(agent=event["name"], timestamp=now())
        elif kind == "on_chain_end" and event["name"] in NODE_NAMES:
            yield NodeEndEvent(...)
        elif kind == "on_chat_model_stream":
            yield TokenEvent(agent=current_agent, token=event["data"]["chunk"].content)
        elif kind == "on_tool_start":
            yield ToolCallEvent(...)
        # ...
```

The CLI subscribes via async iteration. The dashboard publishes to its WebSocket.

---

## Part D — Demo Mode

For interview safety, `--cached <scenario>` replays a pre-recorded successful run:

```bash
agentforge build "..." --cached todo_app
# Plays back events at realistic speed without making any API calls
```

Cached runs live in `examples/cached_runs/*.jsonl` — one event per line, with timestamp deltas preserved.

This is the magic feature for live demos. **Always have a backup cached run in case the live LLM flakes during an interview.**
