# ARCHITECTURE — System Design

## 1. Layers

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          INTERFACE LAYER                                │
│   ┌──────────────────┐   ┌─────────────────┐   ┌─────────────────────┐│
│   │ CLI (rich+typer) │   │  Web Dashboard   │   │  Python SDK          ││
│   │ textual UI       │   │  FastAPI + React │   │  agentforge.build() ││
│   └────────┬─────────┘   └────────┬─────────┘   └──────────┬──────────┘│
└────────────┼─────────────────────────┼─────────────────────┼────────────┘
             └─────────────────────────┴─────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       ORCHESTRATION LAYER (LangGraph)                   │
│                                                                         │
│   StateGraph[AgentState]                                                │
│   ├── Nodes: project_manager, product_manager, architect,               │
│   │          frontend_dev, backend_dev, qa_engineer, devops_engineer    │
│   ├── Edges: conditional routing via supervisor                         │
│   ├── Parallel: Send API (frontend ⊕ backend)                           │
│   ├── Subgraph: dev↔QA retry loop                                       │
│   ├── Interrupts: human-in-loop checkpoints                             │
│   └── Checkpointer: SQLite (dev) / Postgres (prod)                      │
│                                                                         │
│   ┌───────────────┐  ┌──────────────┐  ┌──────────────────┐            │
│   │ State Manager │  │ Cost Tracker │  │  Event Streamer   │            │
│   │ (Pydantic)    │  │ (per agent)  │  │ (WebSocket pump)  │            │
│   └───────────────┘  └──────────────┘  └──────────────────┘            │
└─────────────────────────────────────────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            AGENT LAYER                                  │
│                                                                         │
│   Each agent = Runnable composed of:                                    │
│     ChatPromptTemplate → ChatModel → StructuredOutputParser             │
│                                                                         │
│   AGENT      LLM CHOICE              TOOLS              OUTPUT          │
│   PM         (deterministic)         None              Phase            │
│   PdM        Claude Sonnet (smart)   None              PRD              │
│   Architect  Claude Sonnet (smart)   web_search        Architecture     │
│   Frontend   Claude Sonnet (code)    None              FileBundle       │
│   Backend    Claude Sonnet (code)    None              FileBundle       │
│   QA         Claude Sonnet (code)    sandbox_exec      TestReport       │
│   DevOps     Claude Haiku (cheap)    None              DevOpsBundle     │
└─────────────────────────────────────────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            TOOL LAYER                                   │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐│
│   │ FileWriter   │  │ SandboxExec  │  │SchemaValidator│ │ WebSearch  ││
│   │ (workspace)  │  │ (Docker)     │  │ (pydantic)    │ │ (Tavily)   ││
│   └──────────────┘  └──────────────┘  └──────────────┘  └────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      INFRASTRUCTURE LAYER                               │
│   ┌────────────────┐  ┌────────────────┐  ┌──────────────────────────┐ │
│   │ LLM Providers  │  │ Docker Engine  │  │ SQLite (checkpoints +    │ │
│   │ Anthropic/OAI  │  │ (sandbox)      │  │ run history)             │ │
│   │ Ollama (local) │  │                │  │                          │ │
│   └────────────────┘  └────────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2. Request Lifecycle (CLI invocation)

```
1. User → CLI:  agentforge build "..."
2. CLI parses → builds initial AgentState (description, config)
3. CLI invokes graph.astream_events(state) for streaming
4. LangGraph routes through supervisor:
     project_manager → product_manager → project_manager → architect → ...
5. Each agent:
     a. Reads relevant fields from state
     b. Composes prompt from template + state
     c. Invokes LLM (with retry on parse failure)
     d. Parses structured output
     e. Returns state update (LangGraph reducer merges)
6. QA phase:
     a. Writes generated code to ./output/<slug>/
     b. Spins up Docker sandbox, mounts code, runs tests
     c. Captures stdout/stderr/exit code
     d. If fail and retries left: conditional edge → back to dev agents
7. DevOps phase: writes Dockerfile, docker-compose.yml, .github/workflows/
8. Final state returned → CLI prints summary, location, run instructions
```

## 3. Communication Pattern — Artifact Passing

Agents do NOT exchange free-form chat. They communicate by reading and writing **typed artifacts** in shared state:

```
User input (str)
    │
    ▼
PRD (Pydantic)              ← Product Manager produces
    │
    ▼
ArchitectureDoc (Pydantic)  ← Architect produces, reads PRD
    │
    ▼
{frontend: FileBundle, backend: FileBundle}  ← Devs produce in parallel
    │
    ▼
TestReport (Pydantic)       ← QA produces, reads code + PRD
    │
    ▼
DevOpsBundle (Pydantic)     ← DevOps produces, reads everything
```

Every artifact is validated by Pydantic at the boundary. If an LLM returns malformed output, parsing fails → retry with error context. **No agent can corrupt downstream agents' inputs.**

## 4. State Management

The shared state is a single Pydantic model (`AgentState`) passed by reference through the graph. LangGraph handles merging via field-level reducers:

| Field | Reducer | Why |
|---|---|---|
| `messages` | `add_messages` | Append-only log of all LLM messages |
| `prd` | last-write-wins | Single producer (PM) |
| `architecture` | last-write-wins | Single producer (Architect) |
| `code_files` | dict-merge | Frontend + Backend both write, different keys |
| `test_report` | last-write-wins | Single producer (QA) |
| `devops_files` | dict-merge | DevOps writes multiple files |
| `phase` | last-write-wins | Supervisor controls |
| `retry_count` | increment | Bounded counter |
| `costs` | append | Each agent contributes |
| `events` | append | Audit trail |

See `DATA_MODELS.md` for the full schema.

## 5. Error Handling Strategy

```
Agent execution
       │
       ▼
LLM API error? (rate limit, 5xx)  →  Exponential backoff (tenacity), 3 attempts
       │
       ▼
Output parse error? (bad JSON)    →  Retry with error in next prompt
       │
       ▼
QA: tests failed?                 →  Conditional edge → dev agents with feedback
       │                              (bounded by retry cap)
       ▼
Mark step success → return to supervisor
```

Unrecoverable errors → graph terminates with partial state, CLI shows what completed and where it failed.

## 6. Concurrency & Parallelism

LangGraph's `Send` API enables true parallel execution:

```python
def route_to_developers(state: AgentState) -> list[Send]:
    return [
        Send("frontend_dev", state),
        Send("backend_dev", state),
    ]
```

LangGraph runs them concurrently and waits for both before continuing. Their outputs merge via the dict-merge reducer on `code_files`.

## 7. Sandbox Architecture (Code Execution)

```
QA Agent
   │
   ▼
sandbox_exec tool
   │
   ▼
SandboxRunner.run(files, command)
   │
   ▼
1. Create temp dir on host
2. Write all generated files into it
3. docker run --rm \
       --network=none \
       --memory=512m \
       --cpus=1 \
       --read-only --tmpfs /tmp \
       -v <tempdir>:/workspace:ro \
       -w /workspace \
       agentforge-sandbox:python   # pre-built image with python+pytest+node
       <command>
4. Capture stdout, stderr, exit_code, duration
5. Return ExecutionResult Pydantic model
```

Details in `SANDBOX.md`.

## 8. Web Dashboard Architecture

```
┌──────────────────┐      WebSocket       ┌──────────────────────┐
│  React frontend  │ ◄──────────────────► │  FastAPI server      │
│  - Graph viz     │  (event stream)      │  - /api/build (POST) │
│    (reactflow)   │                      │  - /ws/{run_id}      │
│  - Side panels   │      REST            │  - /api/runs         │
│  - Cost meter    │ ────────────────────►│                      │
│                  │                      │  Spawns LangGraph    │
│                  │ ◄────────────────────│  in async task,      │
│                  │      JSON            │  pumps astream_events│
│                  │                      │  to WebSocket        │
└──────────────────┘                      └──────────────────────┘
```

The dashboard subscribes to LangGraph's `astream_events` and pushes them through a WebSocket. The React frontend reflects state changes in real time.

## 9. Configuration & Secrets

```
agentforge/config.py loads (in priority order):
  1. CLI flags (--llm, --output-dir, etc.)
  2. Env vars (ANTHROPIC_API_KEY, OPENAI_API_KEY, OLLAMA_HOST, ...)
  3. ~/.agentforge/config.toml (user defaults)
  4. ./agentforge.toml (project defaults)
  5. Built-in defaults
```

No secrets are ever logged or committed. The `.env.example` file documents required vars without values.

## 10. Observability

Every agent invocation logs (via `structlog`):
- agent name, phase, timestamp
- input state digest (no PII), output state digest
- token usage (input + output), cost
- duration, retry count
- LLM provider + model used

Optional LangSmith integration via `LANGCHAIN_API_KEY` env var enables full tracing.

## 11. Why These Choices

| Decision | Reason |
|---|---|
| LangGraph over LangChain agents | Need cyclic graphs (retry loop), parallelism (Send), and durable state |
| Pydantic everywhere | Catches LLM output errors at boundaries, enables IDE autocomplete |
| Docker sandbox | Generated code is untrusted by definition |
| Provider-agnostic LLMs | Demo on Ollama (free), production on Claude (best quality) |
| Subgraph for QA loop | Keeps the main graph readable; reusable pattern |
| Supervisor pattern | Centralizes routing logic; easy to debug |
| Structured artifacts not chat | Eliminates ambiguity, enables validation |
