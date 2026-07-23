# ADR 0001 — Native structured output instead of text JSON parsing

- Status: Accepted
- Date: 2026-06
- Deciders: Loom maintainers

## Context

Every generation agent (Architect, Frontend/Backend Dev, DevOps, Code Reviewer)
must return a typed Pydantic artifact. The original implementation used the
pre-2024 LangChain idiom:

```python
chain = prompt | llm | PydanticOutputParser(pydantic_object=Model)
```

The model was asked, in free text, to emit JSON matching a schema printed into
the prompt via `get_format_instructions()`. We then regex/JSON-parsed the reply.
This is brittle:

- The model can wrap JSON in prose, code fences, or trailing commentary.
- Each agent carried a hand-rolled 3-attempt retry loop that fed parse errors
  back into the prompt to coax valid JSON.
- It wastes tokens re-printing the schema and the retries.

## Decision

Bind the schema to the model **natively** via `llm.with_structured_output(Model)`,
which uses provider tool/JSON mode (Anthropic tool calling, OpenAI JSON/function
mode, recent Ollama JSON mode) to constrain the output to the schema.

`build_agent_chain` ([src/loom/agents/base.py](../../src/loom/agents/base.py))
prefers the native path and **falls back** to the legacy parser chain when a
provider doesn't implement `with_structured_output` (`_bind_structured_output`
returns `None`). The `PydanticOutputParser` is still returned from
`build_agent_chain` so format-instructions and the fallback path are unchanged.

## Consequences

- Far fewer parse failures; the retry loops become a safety net rather than the
  primary mechanism.
- No interface change for callers or tests: `build_agent_chain` still returns
  `(chain, parser)` and `chain.ainvoke(input)` still yields a validated model.
- The fallback keeps the full provider matrix working, including older local
  models without tool calling.

## Alternatives considered

- **Keep text parsing.** Rejected: brittle and the reason for the retry cruft.
- **Drop the parser entirely.** Rejected: it still provides format instructions
  for weaker models and a graceful fallback for unsupported providers.
