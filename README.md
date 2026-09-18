# Loom

[![CI](https://github.com/rihaans/Loom/actions/workflows/ci.yml/badge.svg)](https://github.com/rihaans/Loom/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A team of AI agents that scaffold a project together — writing the code,
**reviewing each other's work**, testing it in a sandbox, and containerising it.

Built on [LangGraph](https://langchain-ai.github.io/langgraph/) as a stateful
graph: agents exchange typed Pydantic artifacts, a Code Reviewer critiques the
build and hands work back to the developers or up to the architect, and the
whole loop is bounded so it always terminates.

<p align="center">
  <img src="docs/screenshots/terminal.png" alt="Loom chat REPL" width="760">
</p>

## Install

```bash
pip install loom-build          # the command is `loom`
```

You need Python 3.11+ and one LLM provider:

```bash
ollama pull llama3.1:8b                # free, local
export ANTHROPIC_API_KEY="sk-ant-..."  # best quality
export OPENAI_API_KEY="sk-..."
```

Docker is optional but **required for tests to actually run**. Without it Loom
still builds, and reports the result as unverified rather than claiming tests
passed:

```bash
loom sandbox build              # one-time, ~2 min
loom doctor                     # check everything is wired up
```

## Use

```bash
loom                            # chat: scope the project with the PM, then build
loom build "a CLI that converts markdown to PDF"
loom plan "..."                 # cost and architecture preview, no code generated
```

A build lands in `./output/<project-slug>/` with source, tests, a Dockerfile,
`docker-compose.yml`, GitHub Actions CI, and architectural decision records.

Re-running a build reuses cached artifacts, so iterating is cheap — an identical
rebuild measured 177.3s → 10.8s with every stage reused.

```bash
loom build "..." --require-sandbox   # fail rather than leave code untested
loom build "..." --no-cache          # regenerate every stage
loom cache status                    # what the cache is holding
```

## Documentation

- [Usage](docs/usage.md) — every command, slash commands, configuration, output layout
- [Architecture](docs/architecture.md) — the agents, the graph, state, memory, sandbox
- [Decision records](docs/adrs/) — why the key design choices were made
- [Contributing](CONTRIBUTING.md) — development setup and conventions
- [Changelog](CHANGELOG.md)

## Status

Alpha, and honest about it. The pipeline runs end to end and the output is a
complete, structured project — but read what it generates before trusting it,
and run with Docker so the tests actually execute. Quality tracks the model you
point it at: a 7B local model produces something structurally complete with
rough edges; a frontier model does considerably better.

Known limitations are listed in the [changelog](CHANGELOG.md) and
[usage guide](docs/usage.md).

## License

MIT
