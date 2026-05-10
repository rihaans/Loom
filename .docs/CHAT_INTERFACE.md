# CHAT_INTERFACE — Conversational REPL

> **Status:** Phase 9 feature. The new primary entry point: `loom` (no args) opens an interactive chat where the user collaborates with each agent.

This is the UX pivot that makes Loom feel like a teammate instead of a black-box build pipeline. Typing `loom` opens a styled terminal interface — like Claude Code or `gh copilot` — where you describe an idea, the Product Manager asks clarifying questions, you negotiate the architecture, and you watch the build happen.

`loom build "..."` continues to work for CI/scripting. The chat REPL is additive, not a replacement.

---

## 1. Why This Exists

The current `loom build "todo app"` is one-shot. The Architect picks a stack you didn't ask for; the Product Manager guesses at requirements you didn't state. If the result is wrong, you re-run from scratch.

The chat REPL solves three problems at once:

| Problem with `loom build` | Solved by chat REPL |
|---|---|
| User can't iterate on requirements before code is written | PM asks questions; you answer; PRD is co-authored |
| Stack choice is opaque and uncorrectable mid-build | Architect proposes; you can say "use Postgres instead"; iterates |
| No demo moment beyond watching a progress bar | The conversation IS the demo. Every interaction is screen-recordable. |

It also makes Loom **feel finished** in a way the imperative CLI doesn't. Recruiters watching the Loom video will see a tool they immediately understand, because they've used Claude Code, Cursor, Aider — they know this UX shape.

## 2. What It Looks Like

```
$ loom

  ╭───────────────────────────────────────────────────────╮
  │   Loom — your AI software team                        │
  │   v0.1.0 · anthropic/claude-sonnet-4-5 (auto)         │
  │                                                        │
  │   Type your idea, or /help for commands.              │
  │   Ctrl+C to abort the current step. Ctrl+D to exit.   │
  ╰───────────────────────────────────────────────────────╯

  You ▸ build me an expense tracker

  📋 Product Manager · @pm
  Happy to help! A couple of questions to scope this:

   • Personal use only, or shared with a partner / household?
   • Just text entry of expenses, or do you want receipt
     photo uploads?
   • Reporting: monthly summaries, category breakdowns, CSV
     export — which of these matter?

  You ▸ personal, just text entry, monthly summary and CSV export sounds great

  📋 Product Manager
  Got it. Anything about recurring expenses (rent, subscriptions)
  or do you just want one-off entries?

  You ▸ just one-offs

  📋 Product Manager
  Perfect. I think I have enough to draft a PRD. Want me to
  write it up? (yes / more questions)

  You ▸ yes

  📋 Product Manager
  ⠋ drafting...

  📋 Product Manager
  Here's the PRD:

  ┌─ PRD: expense-tracker ──────────────────────────────┐
  │ A personal CLI/web app to track day-to-day expenses │
  │ with monthly summaries and CSV export.              │
  │                                                      │
  │ P0 features:                                         │
  │   • Add expense (amount, category, date, note)      │
  │   • List expenses, filter by month                  │
  │   • Monthly total + per-category breakdown          │
  │   • Export current view to CSV                      │
  │                                                      │
  │ Data: Expense (id, amount, category, date, note)    │
  │ Out of scope: auth, receipts, recurring, multi-user │
  └──────────────────────────────────────────────────────┘

  Look good? (yes / edit / restart)

  You ▸ add a delete-expense feature too

  📋 Product Manager
  Adding it. Updated PRD:
  [updated PRD with delete in P0]
  Look good? (yes / edit / restart)

  You ▸ yes

  ✓ PRD locked.

  🏗 Architect · @architect
  ⠋ designing...

  🏗 Architect
  My recommendation:

   Stack:    FastAPI + SQLite + Jinja templates
   Why:      Single-user → no auth needed. SQLite keeps it
             zero-deploy. Jinja avoids the JS build step.
   Endpoints: 6 (POST/GET/DELETE /expenses, GET /summary,
             GET /export.csv, GET /)

  Sound good? (yes / change / different stack)

  You ▸ can we use Postgres instead

  🏗 Architect
  Switching to Postgres. Adds a docker-compose service for
  the DB but otherwise no change to the design.

  Sound good? (yes / change)

  You ▸ yes

  ✓ Architecture locked.

  💻 Frontend Dev   ⚙️  Backend Dev   ─ working in parallel
  ⠋ frontend (templates + CSS)   ⠋ backend (5 files)

  ✓ Backend done · 7 files
  ✓ Frontend done · 3 files

  🧪 QA · @qa
  ⠋ writing tests... running in Docker...

  🧪 QA
  ✓ 9 / 9 tests passing.

  🚀 DevOps
  ✓ Dockerfile, docker-compose.yml, .github/workflows/ci.yml

  ┌─────────────────────────────────────────────────────┐
  │ ✅ Build complete: ./output/expense-tracker/        │
  │                                                      │
  │ Run with:                                            │
  │   cd output/expense-tracker                          │
  │   docker compose up                                  │
  │                                                      │
  │ Cost: $0.42 · Time: 3m 12s · 8,400 tokens           │
  └─────────────────────────────────────────────────────┘

  You ▸ /quit
  Bye 👋
```

The whole thing is one continuous chat. Each agent appears as a "speaker," produces output, hands off to the next. The user has full control via natural language and slash commands.

## 3. Architecture

### 3.1 The two-actor model

The REPL has two actors: the **chat loop** (controller) and the **graph** (worker).

```
┌─────────────────────────────────────────────────────────────────┐
│                     ChatSession (controller)                    │
│                                                                 │
│   while not done:                                               │
│     1. Read user input (with prompt_toolkit)                    │
│     2. Parse: slash command or message?                         │
│     3. If slash: handle locally                                 │
│     4. If message: route to current agent                       │
│     5. Run graph forward to next interrupt                      │
│     6. Render agent output                                      │
│     7. Loop                                                     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼ (drives via interrupts)
┌─────────────────────────────────────────────────────────────────┐
│             LangGraph (existing, with new interrupts)           │
│                                                                 │
│   product_manager (CONVERSATIONAL — multi-turn)                 │
│        │ interrupt after each turn until user says "draft"      │
│        ▼                                                        │
│   memory_retrieve                                                │
│        │                                                        │
│        ▼                                                        │
│   architect (LIGHT-CONVERSATIONAL — propose / negotiate)        │
│        │ interrupt for accept-or-change                         │
│        ▼                                                        │
│   developers + QA + DevOps (ONE-SHOT, with progress events)     │
│        │                                                        │
│        ▼                                                        │
│   memory_persist → END                                          │
└─────────────────────────────────────────────────────────────────┘
```

The chat loop is in charge. The graph is a function it calls repeatedly, advancing one interrupt at a time. The graph already supports interrupts (Phase 5); we're just adding more interrupt points and a multi-turn input pattern for PM and Architect.

### 3.2 Why this architecture and not "agents call back into the chat"

An alternative is making each agent a coroutine that yields user-input requests. This is what tools like AutoGen do. We don't, because:

- LangGraph's interrupt model already gives us pause-and-resume for free.
- The chat loop has a clean place to handle slash commands without polluting agent code.
- Existing one-shot agents (Devs, QA, DevOps) need zero changes.
- Streaming events (token-by-token) still flow through `astream_events` exactly as today.

The only architectural cost is one new state field — see § 4.

## 4. State Changes

### 4.1 New field on `AgentState`

```python
# In src/loom/state/models.py

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(BaseModel):
    # ... existing fields ...
    
    # NEW: per-agent conversation history (for conversational agents only)
    # Keys: AgentRole values that are conversational (PM, Architect)
    # Values: list of LangChain BaseMessage (Human / AI alternating)
    agent_messages: Annotated[
        dict[str, list[BaseMessage]],
        merge_messages_dict
    ] = Field(default_factory=dict)
    
    # NEW: signals from the chat loop into the graph
    # When the user types something, this carries it to the active agent
    pending_user_input: str | None = None
    
    # NEW: signals from the agent back to the chat loop
    # "wait_for_input" → conversational agent wants another turn
    # "ready_to_draft" → agent thinks it has enough; wants user confirmation
    # "drafting" → agent is producing the artifact (one-shot mode now)
    # "done" → agent's artifact is in state; move to next agent
    agent_status: str | None = None
```

### 4.2 The new reducer

```python
# In src/loom/state/reducers.py

def merge_messages_dict(
    a: dict[str, list[BaseMessage]] | None,
    b: dict[str, list[BaseMessage]] | None,
) -> dict[str, list[BaseMessage]]:
    """Merge two per-agent message dicts. Inner lists are appended."""
    a = a or {}
    b = b or {}
    out = dict(a)
    for agent_key, new_msgs in b.items():
        out[agent_key] = out.get(agent_key, []) + new_msgs
    return out
```

This allows `agent_messages["product_manager"]` to grow over multiple PM turns without losing history.

### 4.3 Why store messages on AgentState rather than in ChatSession only

Three reasons:

1. **Checkpointing for free.** `loom resume <thread_id>` already works because LangGraph persists `AgentState`. Putting chat history there means resume restores conversation context too.
2. **Memory system can use it later.** When we want to memorize "what kinds of clarifying questions led to good PRDs," the data is already in state.
3. **Web dashboard can render it.** The dashboard reads `AgentState`; it can show the conversation alongside the graph viz.

## 5. The ChatSession Class

```python
# src/loom/cli/chat/session.py

class ChatSession:
    """Owns the REPL loop. Drives the graph via interrupts."""
    
    def __init__(self, config: LoomConfig):
        self.config = config
        self.thread_id = str(uuid.uuid4())
        self.checkpointer = MemorySaver()  # or SqliteSaver for persistence
        self.graph = compile_graph(
            config,
            checkpointer=self.checkpointer,
            interrupt_before=[
                "memory_retrieve",   # after PM finishes, pause for Architect input
                "frontend_dev",      # after Architect finishes
                "memory_persist",    # at end, before persisting
            ],
        )
        self.renderer = ChatRenderer(config)
        self.command_parser = SlashCommandParser()
        self.session_active = True
    
    async def run(self, initial_input: str | None = None) -> BuildResult:
        """The main REPL loop."""
        self.renderer.render_banner()
        
        # Bootstrap
        first_input = initial_input or self.read_user_input()
        if not first_input or self.is_quit(first_input):
            return None
        
        state = AgentState(description=first_input, interactive=True)
        cfg = {"configurable": {"thread_id": self.thread_id}}
        
        while self.session_active:
            # Run the graph forward until it pauses (interrupt or terminal node)
            final_state = await self.run_graph_step(state, cfg)
            
            # Examine where we paused
            snapshot = self.graph.get_state(cfg)
            
            if not snapshot.next:  # Graph hit END
                self.renderer.render_completion(final_state)
                return final_state
            
            # Determine which agent is paused and what it wants
            paused_at = snapshot.next[0]
            agent_status = final_state.get("agent_status")
            
            if agent_status == "wait_for_input":
                # Conversational agent wants another turn
                user_msg = self.read_user_input()
                if self.handle_slash_command(user_msg, cfg):
                    continue   # slash command was handled; loop
                # Inject user message back into state
                self.graph.update_state(
                    cfg,
                    {"pending_user_input": user_msg, "agent_status": None},
                )
                state = None  # signal "resume from checkpoint"
            
            elif agent_status == "ready_to_draft":
                # Agent thinks it's done; ask user
                user_msg = self.read_user_input(
                    prompt="(yes to draft / keep talking / /done to force)"
                )
                if user_msg.lower() in ("yes", "y", "draft", "/done"):
                    self.graph.update_state(
                        cfg,
                        {"pending_user_input": "__DRAFT__", "agent_status": None},
                    )
                else:
                    # User wants another conversational turn
                    self.graph.update_state(
                        cfg,
                        {"pending_user_input": user_msg, "agent_status": None},
                    )
                state = None
            
            else:
                # Generic interrupt point (e.g. "review architecture")
                self.handle_review_gate(paused_at, final_state, cfg)
                state = None
    
    async def run_graph_step(self, state, cfg):
        """Run the graph until next interrupt, streaming events to renderer."""
        events = self.graph.astream_events(state, config=cfg, version="v2")
        async for event in events:
            self.renderer.dispatch_event(event)
        return self.graph.get_state(cfg).values
```

This is pseudo-code; production version will be more careful with error handling. But the shape is: **chat loop → graph step → render → read input → repeat.**

## 6. Conversational Agents — How PM and Architect Change

Detailed in `CONVERSATIONAL_AGENTS.md`. Summary:

- PM gets two prompt modes: **clarifying mode** (asks questions, doesn't draft) and **drafting mode** (produces full PRD from accumulated conversation).
- The PM node, on each invocation, decides which mode based on:
  - `pending_user_input == "__DRAFT__"` → drafting mode
  - Otherwise → clarifying mode (set `agent_status = "wait_for_input"` after each LLM call)
  - PM may also voluntarily set `agent_status = "ready_to_draft"` when its prompt judges enough info is gathered.
- Architect is similar but lighter — usually one proposal + accept/edit, not a multi-turn discovery process.
- Devs / QA / DevOps are unchanged — one-shot, no chat.

## 7. Slash Commands

The minimal set, designed to be discoverable and forgettable:

| Command | Effect |
|---|---|
| `/help` | Show this list |
| `/quit`, `/exit`, `/q` | Exit the session (with save prompt) |
| `/done` | Force the current conversational agent to draft now |
| `/restart` | Restart the current agent's conversation |
| `/back` | Rewind to the previous agent (uses checkpointer) |
| `/show <prd \| arch \| code \| tests \| events>` | Re-display an artifact |
| `/save [name]` | Save session checkpoint with a label |
| `/skip` | Accept current proposal without changes (same as typing "yes") |
| `/model <model>` | Switch the active LLM (mid-session) |
| `/cost` | Show current cost + token usage |

Implementation in `src/loom/cli/chat/commands.py`. Each is a small function:

```python
def cmd_show(args: list[str], session: ChatSession) -> bool:
    """Show an artifact."""
    if not args:
        session.renderer.render_error("Usage: /show <prd | arch | code | tests | events>")
        return True
    target = args[0]
    state = session.graph.get_state(session.cfg).values
    
    if target == "prd" and state.get("prd"):
        session.renderer.render_prd(state["prd"])
    elif target == "arch" and state.get("architecture"):
        session.renderer.render_architecture(state["architecture"])
    # ... etc
    return True   # command handled; don't pass to agent
```

Slash command parsing is **first** — anything starting with `/` is a command, never sent to the agent.

## 8. Rendering

Built on `rich.console.Console`, not Textual. Rationale:

- Textual is a full TUI app — overkill for a chat REPL where the layout is just sequential messages
- `rich` gives us markdown, syntax highlighting, panels, and tables, all flowing top-to-bottom like a normal terminal
- Easier to record and screenshot for demos
- Easier to copy-paste from the terminal (Textual screens trap input)

Components in `src/loom/cli/chat/renderer.py`:

```python
class ChatRenderer:
    def render_banner(self) -> None:
        """One-time welcome panel at session start."""
    
    def render_user_message(self, text: str) -> None:
        """`You ▸ <text>` in the user color."""
    
    def render_agent_speaker(self, agent: AgentRole) -> None:
        """`📋 Product Manager · @pm` header line."""
    
    def render_agent_message(self, agent: AgentRole, markdown: str) -> None:
        """Body text from the agent. Markdown rendered."""
    
    def render_agent_thinking(self, agent: AgentRole) -> None:
        """⠋ thinking spinner, replaced when content streams."""
    
    def render_artifact_panel(self, title: str, fields: dict) -> None:
        """Boxed summary (PRD, Architecture)."""
    
    def render_progress_parallel(self, slots: list[dict]) -> None:
        """Two-column layout for parallel devs."""
    
    def render_completion(self, state: AgentState) -> None:
        """Final summary panel with cost, time, output dir."""
    
    def render_error(self, message: str) -> None:
        """Red error panel."""
    
    def dispatch_event(self, event: dict) -> None:
        """Route a LangGraph stream event to the right render method."""
```

Color scheme: muted by default, agents have role colors (PM = green, Architect = cyan, Devs = blue/yellow, QA = magenta, DevOps = orange). Background stays terminal-default — no fancy theming. Recordable on any terminal.

## 9. Streaming Tokens

When the LLM is generating, we want to stream tokens so the user sees output appearing word-by-word — same UX as Claude Code, ChatGPT, etc.

Already supported via `astream_events` from Phase 7. The chat renderer subscribes:

```python
# In dispatch_event:
if event["event"] == "on_chat_model_stream":
    chunk = event["data"]["chunk"].content
    # Append to current agent's message buffer; flush partial render
    self.current_agent_buffer += chunk
    self.live.update(Markdown(self.current_agent_buffer))
```

`rich.live.Live` lets us update one region of the terminal as content grows. When the agent finishes, we finalize the message and move on.

For token-by-token display to look smooth, set the LLM temperature low and use a model that streams quickly (Sonnet, Haiku, Ollama qwen-coder all stream well; Ollama on slow hardware will look choppy — that's fine).

## 10. Error Handling and Recovery

Conversation errors are different from build errors. Categories:

| Error | Chat REPL response |
|---|---|
| LLM API failure (rate limit, network) | Show "⚠ network error, retrying..." then retry via tenacity. Don't lose conversation context. |
| LLM produces invalid JSON in drafting mode | Same retry-with-error pattern as today — the agent gets one more shot before reporting failure to the user. |
| User Ctrl-C during streaming | Cancel the current LLM call, return to prompt. State unchanged. |
| User Ctrl-C while user is typing | Cancel the input; return to prompt. State unchanged. |
| User Ctrl-D | Save checkpoint and exit. Print resume command. |
| Sandbox unavailable for QA | Tell the user inline ("⚠ Docker not running, skipping test execution"). Don't crash the chat. |
| Slash command unknown | "Unknown command. Type `/help` for the list." Don't pass to agent. |

Critical invariant: **the chat loop should never crash mid-session**. Any uncaught exception is shown as a panel error, the session continues, and the user can `/save` and exit cleanly.

## 11. The `loom build "..."` Command Stays

Existing CLI semantics unchanged:

```bash
loom build "todo app"               # one-shot, non-interactive (CI / scripts)
loom build "todo app" --interactive # prompts at each phase gate (Phase 5 feature)
loom                                # NEW: chat REPL
loom plan "todo app"                # plan-only preview (Phase 8.6 feature)
```

The chat REPL becomes the **default and recommended** flow for humans. `loom build` is preserved for automation. We'll mark it as such in `loom --help` output.

## 12. Configuration

```toml
# Add to loom.example.toml

[chat]
enabled = true                          # default: true
default_model = "anthropic:claude-sonnet-4-5"  # falls back to global default
streaming = true                        # token-by-token display
markdown_in_messages = true             # render markdown in agent output
remember_history = true                 # save chat to ~/.loom/chats/<thread_id>.jsonl
prompt_style = "▸"                      # the user input prompt character

[chat.colors]
user = "white"
pm = "green"
architect = "cyan"
frontend_dev = "blue"
backend_dev = "yellow"
qa = "magenta"
devops = "orange3"
error = "red"
```

CLI flag overrides:
- `--no-streaming` — render full message after generation completes (useful for slow Ollama)
- `--plain` — skip colors and markdown (for CI logs / accessibility)
- `--model <model>` — start with a specific LLM

## 13. Persistence and Resume

Every chat session has a `thread_id`. With the SQLite checkpointer enabled, the entire conversation + state is recoverable:

```bash
loom                          # start fresh session, get thread_id printed at end
loom resume <thread_id>       # continue an interrupted session
loom history                  # list recent sessions
loom history show <id>        # print the chat transcript
```

`loom resume` is already a Phase 5 feature; it works for the chat REPL automatically because chat history lives in `AgentState.agent_messages`.

## 14. Testing Strategy

Test layers:

| Layer | Test type | Goal |
|---|---|---|
| Slash command parser | unit | `/show prd` parses to `("show", ["prd"])` |
| ChatRenderer | unit (snapshot) | Markdown rendering is stable |
| Conversational PM | unit (mocked LLM) | Multi-turn conversation produces valid PRD; clarifying mode doesn't draft |
| ChatSession state machine | unit (mocked graph) | Each `agent_status` → correct next step |
| Full chat flow | integration | Mocked LLM, scripted user input, assert final state matches expected |
| Real LLM chat | manual / e2e | Tagged `@pytest.mark.e2e`, runs against Ollama |

Key new test fixtures:
- `MockUserInput` — feeds scripted user inputs into ChatSession's input reader
- `ChatTranscript` — records every render call so tests can assert on output

```python
# Example integration test
async def test_full_chat_flow_happy_path(mock_user_input, mock_llm):
    mock_user_input.queue([
        "an expense tracker",          # initial idea
        "personal, just text entry",   # answer to PM question
        "yes",                         # accept PRD
        "yes",                         # accept architecture
        "/quit",
    ])
    session = ChatSession(test_config())
    result = await session.run()
    
    assert result.prd is not None
    assert result.prd.project_slug == "expense-tracker"
    assert "anthropic" not in result.prd.must_have_features  # didn't leak metadata
    assert result.test_report.all_passed
```

## 15. What Goes Where (File Layout)

```
src/loom/cli/
├── chat/                              ← NEW MODULE
│   ├── __init__.py
│   ├── session.py                     ← ChatSession class (the REPL controller)
│   ├── renderer.py                    ← ChatRenderer (rich-based output)
│   ├── input.py                       ← user input loop (prompt_toolkit)
│   ├── commands.py                    ← slash command handlers
│   └── transcript.py                  ← optional persistence to ~/.loom/chats/
├── app.py                             ← MODIFIED: `loom` (no args) → ChatSession.run()
└── tui.py                             ← unchanged (still used for `loom build` progress)
```

```
src/loom/agents/
├── product_manager.py                 ← MODIFIED: two-mode (clarify / draft)
├── architect.py                       ← MODIFIED: lighter conversational
└── prompts/
    ├── product_manager.py             ← MODIFIED: split into CLARIFY_PROMPT and DRAFT_PROMPT
    └── architect.py                   ← MODIFIED: similar split
```

```
src/loom/state/
├── models.py                          ← MODIFIED: add agent_messages, pending_user_input, agent_status
└── reducers.py                        ← MODIFIED: add merge_messages_dict
```

```
src/loom/graph/
└── builder.py                         ← MODIFIED: new interrupt points for chat mode
```

Tests:

```
tests/unit/
├── test_chat_session.py               ← NEW
├── test_chat_renderer.py              ← NEW (snapshot-based)
├── test_chat_commands.py              ← NEW (slash command parser)
└── test_conversational_pm.py          ← NEW
tests/integration/
└── test_chat_flow.py                  ← NEW (mocked LLM, scripted user input)
```

## 16. Implementation Checklist

Phase 9 tasks (mirrors `IMPLEMENTATION_PLAN.md § Phase 9`):

### 9.1 Foundations

- [ ] Add `agent_messages`, `pending_user_input`, `agent_status` to `AgentState`
- [ ] Implement `merge_messages_dict` reducer in `state/reducers.py`
- [ ] Update `AgentState` round-trip tests for the new fields

### 9.2 Conversational PM (single agent first — phase gate)

- [ ] Split `agents/prompts/product_manager.py` into two modes (`CLARIFY`, `DRAFT`)
- [ ] Modify `agents/product_manager.py` to inspect `pending_user_input` and switch modes
- [ ] Set `agent_status = "wait_for_input"` after clarifying turn
- [ ] Set `agent_status = "ready_to_draft"` if PM voluntarily decides
- [ ] On `pending_user_input == "__DRAFT__"`, run drafting mode
- [ ] Unit tests: clarifying mode doesn't produce PRD; drafting mode does; multi-turn conversation accumulates correctly

**🛑 Phase gate 9.2.** Verify PM works end-to-end via direct graph invocation before building the chat loop.

### 9.3 Conversational Architect

- [ ] Same pattern as PM but with lighter prompt (one proposal + change-request loop)
- [ ] Unit tests

### 9.4 ChatSession + REPL loop

- [ ] `src/loom/cli/chat/input.py` — prompt_toolkit-based input reader with history
- [ ] `src/loom/cli/chat/renderer.py` — rich-based renderer
- [ ] `src/loom/cli/chat/commands.py` — slash command parser and handlers
- [ ] `src/loom/cli/chat/session.py` — ChatSession class with run() loop
- [ ] Wire `loom` (no args) in `cli/app.py` to ChatSession.run()
- [ ] Wire streaming events from `astream_events` to renderer

### 9.5 Persistence

- [ ] `src/loom/cli/chat/transcript.py` — JSONL transcripts in `~/.loom/chats/`
- [ ] `loom history` and `loom history show` CLI commands
- [ ] Verify `loom resume <thread_id>` works for chat sessions

### 9.6 Tests

- [ ] Unit: slash command parser, renderer (snapshot), conversational PM, ChatSession state machine
- [ ] Integration: full chat flow with mocked LLM and scripted user input
- [ ] Manual e2e: real Ollama session producing a working MVP via chat
- [ ] Snapshot test for the welcome banner
- [ ] CI: ensure `loom build "..."` continues to pass all existing tests

### 9.7 Polish

- [ ] Error panels for common failure modes (Docker, Ollama, API key missing)
- [ ] `--no-streaming` flag for slow Ollama
- [ ] `--plain` flag for CI / accessibility
- [ ] Update `loom doctor` to validate chat-mode prerequisites
- [ ] Update README with the chat REPL as the primary example
- [ ] Record demo video showing the full chat flow

## 17. Demo Script

The 90-second demo for the Loom video:

| Time | Content |
|---|---|
| 0:00 | Terminal opens. Type `loom`. Banner appears. |
| 0:05 | "build me a habit tracker" |
| 0:08 | PM asks 2-3 clarifying questions (streaming, fast) |
| 0:25 | User answers all in one message: "single user, daily, with streaks and a chart" |
| 0:30 | PM drafts PRD (panel renders) |
| 0:40 | User: "yes" |
| 0:42 | Architect proposes Flask + SQLite |
| 0:50 | User: "use Postgres instead" |
| 0:55 | Architect confirms |
| 1:00 | Frontend + Backend in parallel (split-screen progress) |
| 1:30 | QA runs tests in Docker — all pass |
| 1:40 | DevOps writes Dockerfile + CI |
| 1:50 | Final panel: project location + run command + cost |
| 1:55 | `cd output/habit-tracker && docker compose up` |
| 2:00 | App is running in browser. Add a habit. Mark it done. Done. |

That's the demo. The chat is the story; the working app is the punchline.

## 18. What This Doc Does NOT Cover (Future Work)

- **Voice input** — speech-to-text for the chat REPL. Cool, out of scope for v1.
- **Multi-project sessions** — running two builds in parallel from one chat. Out of scope.
- **Web dashboard chat mode** — the dashboard could embed a chat panel. Phase 10.
- **Agent-to-agent visible chat** — show PM "consulting" Architect. Theatrical, not implementable cleanly with the current graph.
- **Context window management for long conversations** — if PM chats for 30 turns, prompts get huge. Strategy: summarize after N turns, store summary in state, drop old messages. v2.
