# Loom — Autonomous Software Development Team

> A multi-agent system built with **LangChain + LangGraph** that simulates a full software development team. Give it a project description → it produces a working, tested, containerized MVP.

This repository ships as a **portfolio project** demonstrating advanced LangGraph patterns: stateful supervisor graphs, parallel fan-out via the `Send` API, conditional routing, interrupts for human-in-the-loop, persistent checkpointing, and tool-using agents that produce executable code validated in a Docker sandbox.

---

## 📖 For Claude Code: Read This First

You are implementing this project. The documentation in `.docs/` is your **single source of truth**.

1. **`.docs/README.md`** — start here, has the doc map
2. **`.docs/PROGRESS.md`** — your live task tracker; update as you complete tasks
3. **`.docs/IMPLEMENTATION_PLAN.md`** — phase-by-phase build plan with review gates
4. Then read the spec docs referenced from the doc map, in order

### How to work

- **Phase-gated.** Stop at every phase boundary and ask the user to review.
- **Checkbox-driven.** Mark `[ ]` → `[x]` in `PROGRESS.md` as you complete tasks.
- **Document deviations.** If you change a design decision while implementing, update the relevant spec doc *and* note it in `PROGRESS.md` under "Notes / Issues / Decisions."
- **No silent shortcuts.** If you skip a feature, mark it explicitly. If a test fails, do not delete it.

---

## What the System Does (User-Facing)

### `loom` — Chat REPL (the primary entry point)

```
$ loom

  ╭─ Loom — your AI software team ────────────────────────╮
  │ Type your idea, or /help for commands.                 │
  ╰────────────────────────────────────────────────────────╯

  You ▸ build me an expense tracker

  📋 Product Manager
  Happy to help! A couple of questions:
    • Personal use, or shared with a partner?
    • Receipt photo uploads, or just text entry?
    • Reporting needs — monthly / category / CSV?

  You ▸ personal, just text, monthly + CSV

  📋 Product Manager
  ⠋ drafting PRD...
```

You converse with each agent in turn. PM clarifies requirements, Architect proposes a stack, then the full pipeline runs (parallel devs → QA in Docker → DevOps → ADRs).

### `loom build "..."` — One-shot (for CI / scripts)

```bash
loom build "A Flask API for a personal expense tracker with categories,
                  monthly summaries, and CSV export"

[12:04:31] 🎯 Project Manager: Starting build pipeline
[12:04:48] ✓ PRD complete (5 user stories, 3 entities)
[12:05:02] ✓ Architecture complete
[12:05:03] 💻 Frontend Dev   ─┐
[12:05:03] ⚙️  Backend Dev    ─┴─ running in parallel
[12:06:22] ✓ Tests: 14/14 passing
[12:06:31] ✓ Done. Output: ./output/expense-tracker/
              Tokens used: 47,832  |  Cost: $0.00 (Ollama)
```

The user can then `cd output/expense-tracker && docker-compose up` and the app runs.

---

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/loom
cd loom
pip install -e ".[dev]"

# Free path: install Ollama, pull a model
ollama pull qwen2.5-coder:7b

# Or use Claude/GPT
export ANTHROPIC_API_KEY="sk-..."

# Start a chat session (primary interface)
loom

# Or run non-interactively
loom build "your project idea here"
```

## Status

🚧 In active development — Phases 0–8.7 complete (259 tests passing). Phase 9 (Chat REPL) is next. See `.docs/PROGRESS.md`.

## License

MIT
