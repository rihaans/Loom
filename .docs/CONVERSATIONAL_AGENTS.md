# CONVERSATIONAL_AGENTS — How PM and Architect Become Chat-Based

> Companion to `CHAT_INTERFACE.md`. Read that first. This doc covers the agent-side changes only — how Product Manager and Architect transform from one-shot artifact producers into multi-turn conversationalists.

---

## 1. The Core Insight

A conversational agent is not "an agent + chat." It's an agent that **runs in two modes** depending on state:

- **Clarifying mode** — produce a chat message. Don't touch the artifact field yet. Set `agent_status = "wait_for_input"` and exit.
- **Drafting mode** — produce the structured artifact (PRD or ArchitectureDoc). Set `agent_status = "done"` and exit.

The mode is selected on each invocation by examining `pending_user_input` and the conversation length. The graph re-enters the same node multiple times — once per turn in clarifying mode, then once more in drafting mode.

This pattern keeps the graph topology unchanged. We're not adding new nodes; we're adding state that loops the existing node.

## 2. The Generic Pattern

All conversational agents follow this skeleton:

```python
async def conversational_agent_node(state: AgentState, config: LoomConfig) -> dict:
    """Generic conversational agent shape.
    
    Examines state to decide:
      - Should I produce another chat turn? (clarifying mode)
      - Should I draft the final artifact? (drafting mode)
      - Or do I voluntarily declare "I have enough info"? (ready_to_draft signal)
    """
    role = AgentRole.PRODUCT_MANAGER  # or ARCHITECT
    history_key = role.value  # "product_manager"
    
    # 1. Pull conversation history for this agent
    history = state.agent_messages.get(history_key, [])
    user_input = state.pending_user_input
    
    # 2. If user just said "draft now," switch to drafting mode
    if user_input == "__DRAFT__":
        return await draft_artifact(state, config, history)
    
    # 3. Append user input to history (if any)
    if user_input:
        history = history + [HumanMessage(content=user_input)]
    elif not history:
        # First invocation, no input yet — treat description as user input
        history = [HumanMessage(content=state.description)]
    
    # 4. Invoke LLM in CLARIFYING mode
    response = await llm_clarifying_call(history, config)
    history = history + [AIMessage(content=response.content)]
    
    # 5. Did the LLM signal it's ready to draft?
    if response.suggests_drafting:
        return {
            "agent_messages": {history_key: history},
            "agent_status": "ready_to_draft",
            "pending_user_input": None,
        }
    
    # 6. Otherwise wait for user
    return {
        "agent_messages": {history_key: history},
        "agent_status": "wait_for_input",
        "pending_user_input": None,
    }


async def draft_artifact(state, config, history):
    """Produce the final artifact from accumulated conversation."""
    artifact = await llm_drafting_call(history, config)
    return {
        "prd": artifact,                        # or "architecture": artifact
        "agent_status": "done",
        "pending_user_input": None,
        # We KEEP agent_messages — the conversation is still useful context downstream
    }
```

The key trick: **the graph node is invoked repeatedly**, once per conversational turn, because the chat loop re-enters the graph after each user input. The interrupt boundary is the same node — control flow loops.

## 3. Product Manager — Detailed

### 3.1 The two prompts

`src/loom/agents/prompts/product_manager.py` gets restructured:

```python
PRODUCT_MANAGER_CLARIFY_PROMPT = """\
You are a Senior Product Manager helping a developer scope a new project. \
You're at the very start — they've described what they want at a high level, \
and your job is to ask 2-4 sharp clarifying questions before you draft a PRD.

Goals for the conversation:
- Identify primary users (single user vs multi-user, public vs private)
- Identify must-have features vs nice-to-haves
- Identify any non-obvious constraints (offline-first, mobile, real-time, etc.)
- Identify out-of-scope things explicitly so you don't over-build

Style:
- Use bullet points or short numbered lists for questions
- Maximum 4 questions per turn — fewer is better
- Don't ask things they already implicitly answered
- After 2-3 productive turns, when you have enough info, EITHER:
    (a) ask "I think I have enough — want me to draft the PRD now?" 
    (b) Or in your message, end with the literal token <READY_TO_DRAFT> 
        (the system will detect it and prompt the user to confirm)

DO NOT produce a PRD in this mode. Just chat.
"""

PRODUCT_MANAGER_DRAFT_PROMPT = """\
You are a Senior Product Manager. You've had a conversation with the developer \
to scope their project. Now write the complete PRD based on everything they told you.

Use the conversation history as your source of truth. Pull facts from the user's \
answers; don't invent requirements they didn't agree to.

Produce a complete PRD matching the schema below. No prose outside the JSON.

{format_instructions}
"""
```

### 3.2 The node implementation

```python
# src/loom/agents/product_manager.py

async def product_manager_node(state, config):
    role_key = AgentRole.PRODUCT_MANAGER.value
    history = state.agent_messages.get(role_key, [])
    user_input = state.pending_user_input
    interactive = state.interactive  # chat mode active?
    
    # Non-interactive path: use the legacy one-shot flow (unchanged)
    if not interactive:
        return await legacy_one_shot_pm(state, config)
    
    # ============ Interactive (chat) path ============
    
    # Drafting trigger
    if user_input == "__DRAFT__":
        prd = await draft_prd(history, config)
        return {
            "prd": prd,
            "agent_messages": {role_key: history},  # preserve history
            "agent_status": "done",
            "pending_user_input": None,
            "events": [Event(type=EventType.AGENT_END, agent=AgentRole.PRODUCT_MANAGER)],
        }
    
    # Clarifying turn: append user input, get LLM response
    if user_input:
        history = history + [HumanMessage(content=user_input)]
    elif not history:
        # Bootstrap: use state.description as the first user message
        history = [HumanMessage(content=state.description)]
    
    response = await pm_clarify_llm.ainvoke(
        ChatPromptTemplate.from_messages([
            ("system", PRODUCT_MANAGER_CLARIFY_PROMPT),
            *history,
        ])
    )
    history = history + [AIMessage(content=response.content)]
    
    # Detect <READY_TO_DRAFT> token
    suggests_drafting = "<READY_TO_DRAFT>" in response.content
    cleaned_content = response.content.replace("<READY_TO_DRAFT>", "").strip()
    history[-1] = AIMessage(content=cleaned_content)  # remove the token from rendered output
    
    return {
        "agent_messages": {role_key: history},
        "agent_status": "ready_to_draft" if suggests_drafting else "wait_for_input",
        "pending_user_input": None,
        "events": [Event(type=EventType.AGENT_TURN, agent=AgentRole.PRODUCT_MANAGER)],
    }
```

### 3.3 Why the `<READY_TO_DRAFT>` token

Two reasons it's better than other approaches:

- **A separate "are you ready" tool call** — small models (Ollama qwen-coder:7b) hallucinate tool calls. Token sentinel is more reliable.
- **A separate LLM "ready check" call** — doubles latency every turn. Sentinel is free.

The sentinel is **stripped before rendering**, so the user never sees it. The PM may decide "ready" or not on its own; the user can also force `/done` at any time.

### 3.4 Turn limits

Hard cap: **8 conversational turns** before the system forces a draft. Prevents runaway conversations on small models that never converge. After turn 8, set `agent_status = "ready_to_draft"` automatically with a renderer hint: "PM has chatted enough — draft now?"

```python
MAX_PM_TURNS = 8

if len(history) >= 2 * MAX_PM_TURNS:  # 2x because each turn is HumanMessage + AIMessage
    return {
        "agent_messages": {role_key: history},
        "agent_status": "ready_to_draft",
        "pending_user_input": None,
        "events": [Event(
            type=EventType.AGENT_TURN_LIMIT,
            agent=AgentRole.PRODUCT_MANAGER,
            payload={"reason": "max_turns_reached"},
        )],
    }
```

## 4. Architect — Detailed

The Architect is **lighter conversational** — usually one proposal + accept/edit loop, not a discovery process. The PRD already pinned down what to build; we just need to confirm *how*.

### 4.1 The two prompts

```python
ARCHITECT_PROPOSE_PROMPT = """\
You are a Principal Software Architect. The PRD is below. Propose a stack and \
high-level design in a SHORT message. Don't produce the full ArchitectureDoc \
yet — that comes after the user confirms.

Format your proposal as:

  Stack:    <backend> + <frontend> + <database> + <auth>
  Why:      <1-2 sentences>
  Endpoints: <count>, key ones being <list>

End your message with: "Sound good? (yes / change)" or similar.

PRD:
{prd_json}
"""

ARCHITECT_REVISE_PROMPT = """\
You are a Principal Software Architect. The user reviewed your previous proposal \
and asked for changes. Revise the proposal accordingly.

Conversation so far:
{conversation}

User's latest feedback: {user_feedback}

Output a SHORT updated proposal (same format as before). End with: "Sound good?"
"""

ARCHITECT_DRAFT_PROMPT = """\
You are a Principal Software Architect. The user has accepted your proposal. \
Now produce the complete ArchitectureDoc.

Conversation history:
{conversation}

{format_instructions}
"""
```

### 4.2 Architect's flow

1. First invocation: read PRD, produce **proposal** (short text, not the full doc).
2. User accepts (`yes` or `/skip`) → set `agent_status = "ready_to_draft"`.
3. User changes (`use Postgres`) → produce a **revised proposal**, set `agent_status = "wait_for_input"`.
4. On `__DRAFT__` signal → produce the full ArchitectureDoc.

Cap: **5 revision rounds**. After that, draft anyway.

### 4.3 Why Architect proposes-then-drafts in two steps

The full ArchitectureDoc is hundreds of lines of structured JSON (endpoints, components, mermaid diagrams). Producing it on every turn would be wasteful. The proposal is short and cheap; only the final commit is expensive. Same insight as `loom plan`'s build-vs-preview separation.

## 5. State Field Semantics

| Field | Set by | Read by |
|---|---|---|
| `agent_messages[role]` | Conversational agent on each turn | Renderer (to show history); next agent (for context) |
| `pending_user_input` | Chat loop (`session.py`) | Conversational agent (next invocation) |
| `agent_status` | Conversational agent | Chat loop (decides next step) |

Lifecycle of `pending_user_input`:
- Chat loop reads user input → calls `graph.update_state({"pending_user_input": text})`
- Graph resumes → conversational node reads the field → consumes it
- Conversational node returns `pending_user_input: None` to clear it

This pattern is borrowed from LangGraph's standard mailbox-via-state idiom.

## 6. Renderer Integration

The chat renderer needs to know how to display:

| State change | Render action |
|---|---|
| New entry in `agent_messages[role]` (AIMessage) | Stream the message under the agent's speaker header |
| `agent_status == "wait_for_input"` | Show user prompt cursor `You ▸ ` |
| `agent_status == "ready_to_draft"` | Show prompt with hint `(yes to draft / keep talking)` |
| `agent_status == "done"` and `prd` filled | Render PRD panel; auto-advance |
| `agent_status == "done"` and `architecture` filled | Render architecture panel; auto-advance |

The renderer subscribes to `astream_events` for token streaming during a turn, and to state-snapshot diffs for "turn complete" boundaries.

## 7. Backward Compatibility

The `interactive` flag on `AgentState` controls everything:

- `interactive=False` (set by `loom build "..."`) → **legacy one-shot path**. PM and Architect produce their artifacts in a single LLM call. No `agent_messages` writes. No interrupts beyond the existing Phase 5 ones.
- `interactive=True` (set by `loom` chat REPL) → **conversational path** described above.

This means **existing tests for `loom build` keep passing** — they hit the `interactive=False` branch, which is unchanged from today. New tests cover the `interactive=True` branch.

```python
# In product_manager_node:
if not state.interactive:
    return await legacy_one_shot_pm(state, config)   # existing code, unchanged
# else: new conversational code below
```

## 8. Cost Implications

A conversational PM uses more tokens than a one-shot PM:

| Mode | Avg PM tokens (typical "todo app" prompt) |
|---|---|
| One-shot | ~3,000 (system + prompt + JSON output) |
| Conversational, 3 turns + draft | ~5,500 (system + 3 chat turns + draft from history) |
| Conversational, 8 turns (cap) + draft | ~12,000 |

Across a full build, this is small (PM is one of 6 agents). But on cheap-model providers it adds up. Mitigations:

- Use a cheap model for clarifying turns (Haiku, GPT-4o-mini), expensive model for drafting.
- Truncate `agent_messages` to the last N turns before drafting (keep the goal-relevant context, drop tangents).
- Display the per-turn cost in the chat renderer so the user sees what each turn costs.

```toml
# In loom.example.toml
[chat.cost_optimization]
clarify_model = "anthropic:claude-haiku-3-5"     # cheap
draft_model   = "anthropic:claude-sonnet-4-5"    # expensive but used once
truncate_history_after_turns = 6
```

## 9. Failure Modes

| Failure | Handling |
|---|---|
| Small model never says `<READY_TO_DRAFT>`, never converges | Turn cap forces `ready_to_draft` at turn 8 |
| User repeatedly says "more questions" indefinitely | Same turn cap |
| User input is empty (just hits Enter) | Render hint: "say something or type `/quit`"; don't advance the graph |
| User pastes a 5000-line spec as one message | Accept it; PM will draft from it; this is fine |
| Drafting mode produces invalid JSON | Use existing parse-retry pattern (Phase 3); show user "PM had trouble drafting, retrying..." |
| User runs `/back` while in PM | Restore checkpoint from before PM started, re-enter chat at description prompt |
| Graph state gets corrupted somehow | `loom doctor --check-session <thread_id>` validates state and offers recovery |

## 10. Testing

```python
# tests/unit/test_conversational_pm.py

async def test_clarifying_mode_does_not_produce_prd(mock_llm):
    """First invocation should produce a chat message, not a PRD."""
    mock_llm.respond_with("What kind of users? Multi or single?")
    
    state = AgentState(description="todo app", interactive=True)
    result = await product_manager_node(state, test_config())
    
    assert result.get("prd") is None
    assert result["agent_status"] == "wait_for_input"
    assert "product_manager" in result["agent_messages"]
    assert len(result["agent_messages"]["product_manager"]) == 2  # human + ai


async def test_ready_token_triggers_status_change(mock_llm):
    mock_llm.respond_with("Sounds great. <READY_TO_DRAFT>")
    
    state = AgentState(description="todo app", interactive=True)
    result = await product_manager_node(state, test_config())
    
    assert result["agent_status"] == "ready_to_draft"
    # Token should be stripped from displayed message
    assert "<READY_TO_DRAFT>" not in result["agent_messages"]["product_manager"][-1].content


async def test_draft_signal_produces_prd(mock_llm):
    """When pending_user_input == __DRAFT__, produce the PRD."""
    mock_llm.respond_with(SAMPLE_PRD_JSON)
    
    state = AgentState(
        description="todo app",
        interactive=True,
        pending_user_input="__DRAFT__",
        agent_messages={"product_manager": [
            HumanMessage(content="todo app"),
            AIMessage(content="What kind of users?"),
            HumanMessage(content="single user"),
        ]},
    )
    result = await product_manager_node(state, test_config())
    
    assert result["prd"] is not None
    assert result["prd"].project_slug
    assert result["agent_status"] == "done"


async def test_turn_cap_forces_drafting(mock_llm):
    """After 8 turns, agent_status must be ready_to_draft regardless."""
    history = []
    for i in range(8):
        history.extend([HumanMessage(content=f"q{i}"), AIMessage(content=f"a{i}")])
    
    state = AgentState(
        description="todo app",
        interactive=True,
        pending_user_input="another question",
        agent_messages={"product_manager": history},
    )
    result = await product_manager_node(state, test_config())
    
    assert result["agent_status"] == "ready_to_draft"


async def test_legacy_one_shot_path_unchanged(mock_llm):
    """interactive=False must use the existing one-shot logic."""
    mock_llm.respond_with(SAMPLE_PRD_JSON)
    
    state = AgentState(description="todo app", interactive=False)
    result = await product_manager_node(state, test_config())
    
    assert result["prd"] is not None
    # No agent_messages should be written in legacy path
    assert not result.get("agent_messages")
```

Architect tests follow the same pattern — proposal mode vs draft mode, change-request handling, revision cap.

## 11. What This Doc Does NOT Cover

- The chat REPL itself — see `CHAT_INTERFACE.md`.
- Slash command implementations — see `CHAT_INTERFACE.md` § 7.
- One-shot agents (Devs, QA, DevOps) — they don't change.
- Memory retrieval interaction with chat — memory is still queried after PM completes its drafting; the chat doesn't change retrieval logic.
