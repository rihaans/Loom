# ADR 0002 — Code Reviewer agent (generator–critic loop)

- Status: Accepted
- Date: 2026-06
- Deciders: Loom maintainers

## Context

Originally the only inter-agent feedback was the QA → dev retry: code was
generated, then tested, and failing tests bounced back to the developers. But
tests can't catch what they don't cover — missing requirements, frontend/backend
contract mismatches, insecure defaults, references to symbols that don't exist.
The developers also silently accepted whatever the architect produced; the
"negotiation" the README implied didn't exist in the graph.

We considered a free-form **agent mesh** (any agent can talk to any agent,
autonomously). We rejected it: it's non-deterministic, expensive (agents looping
in conversation), hard to debug, and hard to test. For code generation the work
is mostly a pipeline. We wanted *structured, bounded* interaction where it adds
value, not a free-for-all.

## Decision

Add a **Code Reviewer** agent between the developers and QA — the critic in a
generator–critic loop. It reviews the whole build (frontend + backend together)
against the PRD and architecture and emits a typed `ReviewReport`
(`approved`, `summary`, `issues[]`, `target_agent`, `escalate_to_architect`).

The reviewer is a **hub** that hands off dynamically:

- **approve** (no critical/major issues) → QA
- **code defect** → back to the targeted developer(s) with the issues as
  revision instructions
- **architectural root cause** → *upstream* to the Architect, which revises the
  design (it already consumes `architecture_feedback`) and re-fans to the devs
- **review budget exhausted** → proceed to QA anyway (never deadlock)

The loop is bounded by `max_review_iterations` (default 1) so it always
terminates. A reviewer LLM failure degrades gracefully: log and proceed to QA,
never sink an otherwise-good build.

See [src/loom/agents/reviewer.py](../../src/loom/agents/reviewer.py).

## Consequences

- A genuine agent-to-agent feedback loop that catches defects tests miss.
- The architect↔dev "negotiation" is now real: design problems route upstream.
- Deterministic and testable — the budget guarantees termination, and the loop
  is exercised end-to-end through the compiled graph in
  [tests/integration/test_review_loop.py](../../tests/integration/test_review_loop.py).

## Alternatives considered

- **Full agent mesh.** Rejected (see Context): non-deterministic and costly.
- **Reviewer routes only to devs.** Rejected: architectural defects can't be
  fixed by the devs; they need the architect. Hence the escalation edge.
