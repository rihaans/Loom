# Usage

Full command, configuration and output reference. For a quick start see the [README](../README.md).

---

## Usage

### Chat REPL (recommended)

```bash
loom
```

You'll see a big LOOM banner and a `You ▸` prompt. Type your idea, then have a conversation with the PM:

```
You ▸ build me a personal finance tracker

📋  Product Manager
Got it — a few questions:
  • Single-user or multi-user (with login)?
  • Manual entry only, or should it import bank CSVs?
  • Categories, tags, both, or neither?

You ▸ single user, manual entry, simple categories

📋  Product Manager
Perfect — I have what I need. <READY_TO_DRAFT>

You ▸ yes
```

After "yes", PM drafts the PRD, the panel renders, and the Architect proposes a stack. Type "yes" again and the build pipeline runs autonomously.

### One-shot build (for CI / scripts)

```bash
loom build "A Flask API for expense tracking with monthly summaries"

# Refuse to finish unless tests actually ran in a sandbox
loom build "..." --require-sandbox

# Refuse to write into an output directory that already has files
loom build "..." --no-overwrite
```

No conversation — the PM and Architect produce their artifacts in a single LLM call each, and the build proceeds straight through.

### Plan-only (cost preview without spending tokens on code)

```bash
loom plan "your idea here"
```

Returns estimated cost, duration, file count, and a draft architecture — without running devs/QA/DevOps.

### Resume an interrupted session

```bash
loom history                 # list past chat sessions
loom history show <id>       # replay a transcript
loom resume <thread_id>      # resume from the last checkpoint
```

### Iterating cheaply

Every agent's output is cached against a hash of its inputs, so re-running a
build reuses work instead of paying for it again. On a local 7B model an
identical rebuild went from **177.3s to 10.8s** with all 8 stages reused,
producing byte-identical output.

```bash
loom cache status           # entries, size, location (~/.loom/artifacts)
loom cache clear            # drop everything
loom build "..." --no-cache # ignore the cache and regenerate every stage
```

One thing legitimately causes misses: memory. It injects past builds into the
architect's prompt and every build adds to it, so the prompt genuinely differs
each run and the cache correctly misses. Use `--no-memory` for reproducible,
cache-friendly runs.

### Capping spend

```toml
[cost]
budget_usd = 1.00           # hard stop; checked before each expensive agent
warn_threshold_usd = 0.50
```

The build stops cleanly when the cap is reached, keeping whatever was produced
and reporting what was spent.

### Other commands

```bash
loom version              # show installed version
loom doctor               # diagnose setup
loom estimate "..."       # rough cost estimate
loom config show          # show resolved config
loom config init          # create loom.toml from template
loom sandbox info         # Docker sandbox status
loom sandbox build        # build the sandbox image
loom memory status        # vector store stats
loom memory list          # list past builds in memory
loom memory search "..."  # semantic search over past builds
loom cache status         # artifact cache stats
loom cache clear          # empty the artifact cache
loom ui                   # launch the web dashboard
```

### The web dashboard

`loom ui` serves a live view of a build: the agent graph including the Code
Reviewer's `revise` / `escalate` edges, progress, cost and artifacts.

<p align="center">
  <img src="screenshots/home.png" alt="Dashboard home" width="720"><br><br>
  <img src="screenshots/build.png" alt="Live build graph" width="720"><br><br>
  <img src="screenshots/runs.png" alt="Build history" width="720">
</p>


---

## The Chat REPL

The chat REPL is what makes Loom feel like a teammate rather than a one-shot generator. Behind the scenes it:

1. Compiles the LangGraph state machine in **interactive mode** (`interrupt_after` PM and Architect)
2. Runs the graph until it pauses
3. Reads your input via `prompt_toolkit` (with arrow-key history, Ctrl-C to abort, Ctrl-D to exit)
4. Pushes your input into graph state via `update_state`
5. Resumes the graph until the next pause
6. Renders new agent messages with a **typewriter effect** and shows a **spinner** while the LLM is thinking

### Affirmative shortcuts

The PM has a turn cap (8 turns max) and uses a `<READY_TO_DRAFT>` sentinel to signal when it has enough info. To advance, you can:

- Type `/done`, `/yes`, `/y`, `/skip`, `/draft` (slash commands)
- Or just type plain `yes`, `ok`, `sure`, `done`, `go`, `looks good`, `lgtm`, `perfect`, `do it`, etc. — Loom detects these as draft triggers automatically

Long prose like *"yes but also add auth"* is **not** treated as affirmative — it's passed through as conversation.

### Visual experience

- **Big LOOM banner** at session start with a champagne gold-foil wordmark
- **Per-agent speaker bars** — a champagne `◇` and the agent's name (monochrome, name-only; state is carried by muted sage/amber/rose, not by a rainbow of hues)
- **Thinking spinner** between your input and the agent's reply: `⠋ PM is thinking…`
- **Typewriter rendering** of agent responses (~240 chars/sec)
- **Rounded panel artifacts** for PRDs and architecture summaries
- **Live progress** during parallel dev execution

For accessibility / CI:

```bash
loom --plain    # disable colors, animations, and rich rendering
```

---

## Slash Commands

Typing `/` pops a command menu; `/help`, `/status` and `/cost` render as panels.

<p align="center">
  <img src="screenshots/commands.png" alt="Slash command menu and panels" width="680">
</p>

While in a chat session, type any of these:

| Command | Aliases | What |
|---|---|---|
| `/help` | `/?`, `/h` | Show this list |
| `/done` | `/yes`, `/y`, `/draft` | Tell the current agent to commit (e.g. draft the PRD) |
| `/skip` | | Accept the current proposal as-is |
| `/quit` | `/q`, `/exit` | Exit the session (transcript saved) |
| `/restart` | `/reset` | Discard current build, start over |
| `/back` | `/undo` | Restore the previous checkpoint (one step back) |
| `/show <type>` | | Render an artifact: `prd`, `architecture`, `code`, `tests` |
| `/save [name]` | | Save the current chat transcript |
| `/model <id>` | | Show / switch active LLM |
| `/cost` | `/tokens` | Show running token + dollar cost |

Anything else you type is sent to the active agent as a message.

---

## Output Layout

A successful build produces a complete, runnable project under `./output/<project-slug>/`:

```
output/markdown-to-pdf/
├── src/
│   ├── main.py              ← entry point
│   ├── converter.py
│   └── styles/
├── tests/
│   ├── test_converter.py
│   └── test_cli.py
├── docs/
│   └── adrs/
│       ├── 0000-index.md
│       ├── 0001-python-cli.md
│       └── 0002-weasyprint.md
├── Dockerfile
├── docker-compose.yml
├── .github/
│   └── workflows/
│       └── ci.yml
├── requirements.txt
└── README.md                ← run instructions
```

To run the generated project:

```bash
cd output/markdown-to-pdf
docker-compose up
# or follow the generated README's instructions
```

---

## Configuration

Loom resolves configuration from (highest to lowest priority):

1. CLI flags (`--model`, `--no-memory`, etc.)
2. Environment variables (`ANTHROPIC_API_KEY`, `LOOM_*`)
3. `./loom.toml` (project-local)
4. `~/.loom/config.toml` (user-global)
5. Sensible defaults

Generate a starter config:

```bash
loom config init
```

A minimal `loom.toml`:

```toml
[llm.default]
provider = "anthropic"
model = "claude-sonnet-4-5"
temperature = 0.2
max_tokens = 4096

[build]
output_dir = "./output"
max_retries = 2
interactive = false

[sandbox]
use_docker = true
timeout_seconds = 90
memory_mb = 512

[chat]
no_streaming = false
plain = false
```

See [`loom.example.toml`](../loom.example.toml) for the full schema and per-agent overrides.

### Per-agent LLM overrides

You can pin specific agents to specific models — useful for cost optimization (cheap model for chat, expensive for drafting):

```toml
[llm.product_manager]
provider = "anthropic"
model = "claude-haiku-3-5"      # cheap for clarifying turns

[llm.backend_dev]
provider = "anthropic"
model = "claude-sonnet-4-5"     # quality for code generation

[llm.devops_engineer]
provider = "ollama"
model = "qwen2.5-coder:7b"      # mostly templated, free is fine
```

---
