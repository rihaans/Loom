# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Unverified test runs are no longer reported as passing.** When no sandbox
  is available, nothing is executed — the QA agent now marks its report
  `is_stub`, `all_passed` returns False, no coverage figure is invented, and
  the CLI prints an explicit warning. Previously a Docker-less machine got a
  green "5/5 passed, 85% coverage" that measured nothing.
- **Current Anthropic models are priced correctly.** `claude-opus-5`,
  `claude-sonnet-5`, and `claude-haiku-4-5` previously matched no pricing entry
  and reported `$0.00`. Prefix matching also billed `claude-opus-4-8` at Opus
  4.5's $15/$75 instead of $5/$25. Lookup is now exact-match with dated-snapshot
  normalisation, and unknown models report "unknown" rather than zero.
- **A missing LLM provider fails immediately with an actionable message.**
  Previously a run with no API key silently fell back to Ollama and died with
  three rounds of "All connection attempts failed".
- **`typer.Exit` is no longer swallowed** by the `build` command's exception
  handler, which printed a spurious `Error: 1` after every failed build.
- **`loom ui` works from a pip install.** The dashboard is now shipped inside
  the wheel and located via the package, not by walking up from `__file__`.
- CI is green again: resolved 9 `ruff check` violations and 1 formatting
  failure that would have failed every run.

### Performance

- **Artifact cache (new).** Each agent's output is cached against a hash of the
  prompts, rendered inputs, model and schema, so re-running a build reuses work
  instead of paying for it again.
  Measured end-to-end through the CLI on a local 7B model: an identical
  rebuild went from **177.3s to 10.8s with 8/8 stages reused (16.4x)**,
  producing **byte-identical project trees**. Parse retries share one cache
  entry with their first attempt, so a retry does not poison the rerun -
  before that fix the same build reused only 7 of 11 stages and produced
  different output. On by default; `--no-cache` to bypass, `loom cache
  status` / `loom cache clear` to inspect. Leave memory off (`--no-memory`)
  for reproducible runs: memory intentionally changes the architect's prompt
  each time, so it correctly invalidates the cache.
- **The reviewer no longer re-reads code it already reviewed.** On a revise
  iteration only the bundle the reviewer handed back is sent in full; the
  unchanged one is listed as a file index. The review prompt is dominated by the
  code dump and the reviewer is the node that repeats, so this is the largest
  avoidable cost in the loop: measured **40-56% off the dump** on a targeted
  re-review. Every file is still accounted for in the file count.
- **Stopped sending the JSON schema when the model is already bound to it.**
  Native structured output constrains the model to the schema, so repeating it
  in the prompt was dead weight. Measured saving: **~2,777 tokens per clean
  build, ~4,178 with a review loop** - 44-70% off each agent's prompt overhead.
  The text-parser fallback still gets the full schema, because it needs it.

### Added

- **The cost budget is now enforced.** `cost_budget_usd` has been configurable
  since the beginning but nothing ever read it - a $1 cap could not stop a $50
  build. It is now checked before each expensive agent, stopping the run with
  what was spent and what the cap was.

- `--require-sandbox` on `loom build` — fail rather than produce unverified results.
- `--no-overwrite` on `loom build` — refuse to write into a non-empty output directory.
- `BuildResult.tests_verified` and `BuildResult.cost_status` so API consumers can
  tell a real result from an unmeasured one.
- Durable dashboard run history in `~/.loom/runs.db`; the build list now survives
  a server restart.
- `CONTRIBUTING.md` and this changelog.

### Changed

- Default Anthropic model is now `claude-sonnet-5` (was `claude-sonnet-4-5`).
- PyPI distribution name is `loom-build`; the installed command remains `loom`.
- Documented minimum Python is 3.11, matching what `pyproject.toml` has always required.

## [0.1.0] - 2026-07-24

Initial development release: multi-agent pipeline (PM → Architect → parallel
devs → Code Reviewer → QA → DevOps), chat REPL, web dashboard, Docker sandbox,
vector memory, ADR generation.
