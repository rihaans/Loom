# DEMO_SCENARIOS — Five Showcase Builds

These are the demo projects shipped in `examples/`. Each has been verified to produce a working MVP. The Loom video should walk through at least three of them.

For each scenario:
- **Input**: the exact prompt to type
- **Expected stack**: what the architect should pick
- **Expected output**: file count, runnable commands
- **Demo notes**: what to highlight

---

## Scenario 1 — Todo App with Auth (the classic)

**Input:**
```
A todo list web app where users can sign up, log in, create todos, mark them
as done, and delete them. Each user only sees their own todos. Use a clean,
minimal design.
```

**Expected stack:** FastAPI + React+Vite + SQLite + JWT

**Expected output:**
- `backend/`: ~10 files (main.py, models.py, routes/auth.py, routes/todos.py, db.py, schemas.py, security.py, deps.py, requirements.txt)
- `frontend/`: ~12 files (App.jsx, pages/Login.jsx, pages/Signup.jsx, pages/Todos.jsx, components/TodoItem.jsx, api.js, package.json, vite.config.js, index.html, index.css)
- `tests/`: ~6 test files
- `docker-compose.yml`, `Dockerfile.backend`, `Dockerfile.frontend`
- `.github/workflows/ci.yml`

**Run:** `docker compose up` → http://localhost:5173

**Demo highlights:**
- Show parallel execution of frontend + backend
- Highlight the JWT flow in generated auth code
- Run `docker compose up`, hit signup, log in, add todos — all live

**Why it works:** Classic CRUD with auth is well-represented in LLM training data, and the Pydantic schemas constrain output to runnable code.

---

## Scenario 2 — URL Shortener with Analytics

**Input:**
```
A URL shortener service. Anyone can submit a long URL and get back a short
code. When someone visits the short link, they're redirected, and a click is
logged. Provide an analytics endpoint that returns click counts and timestamps
for any short code.
```

**Expected stack:** FastAPI + vanilla HTML+JS + SQLite (no auth needed)

**Expected output:**
- `backend/`: ~6 files
- `frontend/`: ~3 files (index.html, main.js, style.css) — the architect should choose simple HTML for this
- `tests/`: ~3 test files

**Run:** `docker compose up` → http://localhost:8000

**Demo highlights:**
- Architect chose vanilla HTML over React — show this decision in the architecture doc
- Demonstrate the QA agent's tests catching a bug in the redirect logic on first run, retrying
- Hit the analytics endpoint with curl during the demo

---

## Scenario 3 — Book Review Site (more complex)

**Input:**
```
A book review website. Books have title, author, ISBN, and cover image URL.
Users can sign up and post reviews with a 1-5 star rating and a text comment.
Users can browse all books and see the average rating per book. Search books
by title or author.
```

**Expected stack:** FastAPI + React+Vite + SQLite + JWT

**Expected output:**
- More complex schemas (Books, Users, Reviews with relationships)
- Search endpoint with query parameters
- Aggregation logic (average rating)
- Frontend has multiple pages: list, detail, search results, login

**Run:** `docker compose up` → http://localhost:5173

**Demo highlights:**
- Show how the data model from PRD flows into both backend models and frontend types
- Highlight the search logic
- This is the "wow they actually built it" scenario — the most complex one

---

## Scenario 4 — CSV to JSON CLI Tool

**Input:**
```
A command-line tool written in Python that converts CSV files to JSON. It
should support reading from a file path or stdin, optional schema validation
via a JSON Schema file, pretty-print output, and a --records flag to wrap
output as an array of records (default) or a single object keyed by row index.
```

**Expected stack:** Python + Typer + jsonschema (no frontend, no DB)

**Expected output:**
- `csv_to_json/`: cli.py, converter.py, validator.py
- `tests/`: ~4 test files with sample CSVs and expected outputs
- `pyproject.toml`, `Dockerfile`
- No `docker-compose.yml` (single-binary tool)

**Run:** `pip install . && csv-to-json input.csv`

**Demo highlights:**
- Show the architect skipping the frontend entirely
- Show the QA agent piping test input via subprocess and asserting on stdout
- Run the actual tool on a sample CSV during the demo

---

## Scenario 5 — Kanban Board (most complex, optional)

**Input:**
```
A kanban board web app like Trello but minimal. Boards contain columns,
columns contain cards. Users can create boards, add columns, drag cards
between columns, and edit card titles and descriptions. No auth needed —
boards are accessed via shareable URLs containing a UUID.
```

**Expected stack:** FastAPI + React+Vite + SQLite

**Expected output:**
- Backend with 3 nested resources (boards/columns/cards)
- Frontend with drag-and-drop (library: react-dnd or @dnd-kit)
- WebSocket support for real-time updates (architect may or may not include this)

**Demo highlights:**
- The drag-and-drop is impressive in a demo
- May fail QA the first time and demonstrate the retry loop in action

**Risk:** This scenario tests the limits — drag-and-drop is hard for LLMs to generate correctly. If the architect chooses something simpler (click-to-move with arrow buttons), that's fine. **Use this scenario only after the others reliably work.**

---

## Cached Run Strategy

For the Loom video and live demos, every scenario has a `cached_runs/<scenario>.jsonl` file produced by:

```bash
loom build "$(cat examples/01_todo_app.md)" --record-run > cached_runs/todo_app.jsonl
```

The cached run is a JSONL of all events with their original timestamps. Replay:

```bash
loom demo todo_app
# Plays back at original speed, no API calls, no Docker — just visual
```

This is the **interview safety net**. If the LLM is slow or flaky on the day, switch to cached.

---

## Recording the Loom

Suggested 3-minute structure:

| Time | Content |
|---|---|
| 0:00-0:20 | "Loom — six AI agents that build software. Watch this." |
| 0:20-0:30 | Show CLI: `loom build "todo app with auth"` |
| 0:30-0:50 | Show TUI lighting up — PM, Architect, parallel devs, QA, DevOps |
| 0:50-1:10 | Switch to web dashboard mid-build, show graph + streaming output |
| 1:10-1:30 | Show generated `output/todo-app/` directory |
| 1:30-1:50 | `cd output/todo-app && docker compose up` — show app running |
| 1:50-2:20 | Sign up, log in, add a todo, watch it persist — works! |
| 2:20-2:40 | Show the QA retry loop on a different scenario (URL shortener) |
| 2:40-3:00 | Wrap: "Built on LangChain + LangGraph. Repo link in description." |

Keep cuts tight. Energy matters more than completeness.

---

## Test These Before Recording

A scenario only goes in the demo if it passes this checklist:

- [ ] Build completes without manual intervention
- [ ] All generated tests pass on first or second QA run
- [ ] `docker compose up` starts without errors
- [ ] User can complete the primary user story (e.g. signup → add todo → log out → log in → see todo)
- [ ] No leaked secrets, no broken imports, no missing files
- [ ] Reproducible — running the same prompt twice produces working code both times (allow some variation in choices)

If a scenario fails this checklist after 3 tries, drop it from the demo set. **Reliability over breadth.**
