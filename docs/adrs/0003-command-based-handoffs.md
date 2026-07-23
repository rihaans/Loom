# ADR 0003 — `Command`-based dynamic handoffs for the review loop

- Status: Accepted
- Date: 2026-06
- Deciders: Loom maintainers

## Context

The graph's control flow used static `add_conditional_edges` + standalone
routing functions that return the name of the next node. That works for a fixed
pipeline, but the Code Reviewer (ADR 0002) needs a node that *decides its own
next hop at runtime* — and that hop can be a plain node (`qa_engineer`,
`architect`) or a parallel fan-out to specific developers via the `Send` API.

## Decision

The Code Reviewer node returns a LangGraph **`Command`** instead of a state dict:

```python
return Command(goto="qa_engineer", update={...})                       # approve
return Command(goto=[Send("backend_dev", payload)], update={...})       # revise
return Command(goto="architect", update={...})                          # escalate
```

`Command(goto=..., update=...)` is the modern LangGraph idiom (the same primitive
behind `langgraph-supervisor` / swarm handoffs): the node both writes state and
chooses where execution goes next, including dynamic `Send` fan-out. No
conditional edge is declared for the reviewer — its destinations are decided in
code.

The deterministic policy functions (`route_after_qa`, etc.) are kept as-is for
the fixed pipeline edges; we only moved the *dynamic* hop to `Command`.

## Consequences

- The review/retry/escalate loop is expressed where the decision is made, not in
  a separate routing table — easier to read and to extend.
- Demonstrates current LangGraph patterns (post conditional-edge era).
- Verified to loop and terminate through the real compiled graph in
  [tests/integration/test_review_loop.py](../../tests/integration/test_review_loop.py).

## Alternatives considered

- **Conditional edges only.** Rejected: can't fan out to `Send` *and* pick a
  plain node from one decision point without awkward indirection.
- **Migrate all routing to `Command`.** Deferred: the linear pipeline edges are
  fine as static edges; only the reviewer needs dynamic handoff today.
