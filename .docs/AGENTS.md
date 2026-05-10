# AGENTS — Per-Agent Specifications

Every agent follows this pattern:

```python
agent = (
    ChatPromptTemplate.from_messages([
        ("system", AGENT_SYSTEM_PROMPT),
        MessagesPlaceholder("history", optional=True),
        ("human", "{input}"),
    ])
    | get_llm_for_role(AgentRole.X)
    | output_parser_for(OutputModel)
)
```

Then it's wrapped in a node function that adapts state ↔ agent I/O.

---

## 1. Project Manager (Supervisor)

| Property | Value |
|---|---|
| **Role** | Routing only — NOT an LLM agent |
| **LLM** | None (pure Python) |
| **Reads** | `phase`, all artifacts, `retry_count` |
| **Writes** | `phase`, `events` |
| **Tools** | None |
| **Output** | Updated state with new `phase` |

### Why no LLM here?

Routing is deterministic given state. Saving the LLM call for every transition saves ~40% of total tokens and eliminates a class of routing bugs. **An LLM-based supervisor is opt-in** for users who want to learn that pattern (see §8).

### Node function

```python
def project_manager_node(state: AgentState) -> dict:
    next_phase = decide_next_phase(state)
    return {
        "phase": next_phase,
        "events": [Event(type="phase_transition", phase=next_phase)],
    }
```

---

## 2. Product Manager

| Property | Value |
|---|---|
| **Role** | Translate user description → structured PRD |
| **LLM** | Smart model (Claude Sonnet recommended) |
| **Reads** | `description` |
| **Writes** | `prd`, `messages`, `costs` |
| **Tools** | None |
| **Output** | `PRD` Pydantic model |

### Output schema

```python
class UserStory(BaseModel):
    id: str               # "US-001"
    role: str             # "registered user"
    goal: str             # "log in with email"
    benefit: str          # "so I can access my data"
    acceptance_criteria: list[str]
    priority: Literal["P0", "P1", "P2"]

class DataEntity(BaseModel):
    name: str
    fields: dict[str, str]   # field_name -> type
    description: str

class PRD(BaseModel):
    project_name: str
    project_slug: str        # kebab-case, used as folder name
    one_liner: str
    target_users: list[str]
    user_stories: list[UserStory]
    data_entities: list[DataEntity]
    must_have_features: list[str]
    nice_to_have_features: list[str]
    out_of_scope: list[str]
    success_metrics: list[str]
```

System prompt → see `PROMPTS.md § Product Manager`.

---

## 3. Architect

| Property | Value |
|---|---|
| **Role** | Choose tech stack, design system, define API contracts |
| **LLM** | Smart model (Claude Sonnet recommended) |
| **Reads** | `description`, `prd` |
| **Writes** | `architecture`, `messages`, `costs` |
| **Tools** | `web_search` (optional), `read_documentation` |
| **Output** | `ArchitectureDoc` Pydantic model |

### Output schema

```python
class TechChoice(BaseModel):
    layer: Literal["frontend", "backend", "database", "auth", "deployment", "testing"]
    technology: str
    version: str
    rationale: str

class APIEndpoint(BaseModel):
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    path: str
    request_schema: dict | None
    response_schema: dict
    auth_required: bool
    description: str

class Component(BaseModel):
    name: str
    type: Literal["service", "module", "page", "component"]
    responsibility: str
    depends_on: list[str]

class ArchitectureDoc(BaseModel):
    stack: list[TechChoice]
    api_endpoints: list[APIEndpoint]
    components: list[Component]
    data_models: list[DataEntity]
    folder_structure: dict[str, str]
    component_diagram_mermaid: str
    deployment_diagram_mermaid: str
```

### Stack selection guidance baked into the prompt

```
Backend candidates:    FastAPI, Express.js, Flask
Frontend candidates:   React+Vite, Vue 3, vanilla HTML+JS
Database candidates:   SQLite (default), Postgres, in-memory dict
Auth candidates:       JWT (jose/pyjwt), session cookies, none
Testing:               pytest+httpx, jest+supertest, vitest
```

System prompt → `PROMPTS.md § Architect`.

---

## 4. Frontend Developer

| Property | Value |
|---|---|
| **Role** | Implement frontend code per architecture |
| **LLM** | Code-strong model (Claude Sonnet 4.5) |
| **Reads** | `prd`, `architecture`, `qa_feedback?` |
| **Writes** | `code_files["frontend"]`, `messages`, `costs` |
| **Tools** | None |
| **Output** | `FileBundle` |

### Output schema

```python
class CodeFile(BaseModel):
    path: str                # relative to project root
    content: str
    language: str

class FileBundle(BaseModel):
    files: list[CodeFile]
    entry_point: str
    install_commands: list[str]
    run_commands: list[str]
```

### Behavior on retry

If `qa_feedback` is set, the prompt includes failed test output and instructs surgical fixes rather than rewrites.

System prompt → `PROMPTS.md § Frontend Developer`.

---

## 5. Backend Developer

Mirrors Frontend Dev but writes to `code_files["backend"]`. Same schema. Different prompt focused on:
- API endpoint implementation matching `architecture.api_endpoints`
- Database schema matching `architecture.data_models`
- Error handling, validation, status codes
- A working `main.py` / `app.js` that boots the server

System prompt → `PROMPTS.md § Backend Developer`.

---

## 6. QA Engineer

| Property | Value |
|---|---|
| **Role** | Write tests, execute them, report results |
| **LLM** | Code-strong model |
| **Reads** | `prd`, `architecture`, `code_files` |
| **Writes** | `test_report`, `qa_feedback`, `messages`, `costs` |
| **Tools** | `sandbox_exec` — runs code in Docker |
| **Output** | `TestReport` Pydantic model |

### Two-phase execution

1. **Generate tests** (LLM call): Produce test files and a run command.
2. **Execute** (tool call): Materialize all files (app + tests) in temp dir, run in Docker sandbox, capture output.
3. **Analyze** (LLM call, optional): If tests fail, produce structured `qa_feedback` for dev agents.

### Output schema

```python
class TestCase(BaseModel):
    name: str
    file: str
    passed: bool
    duration_ms: float
    error_message: str | None

class TestReport(BaseModel):
    total: int
    passed: int
    failed: int
    skipped: int
    duration_ms: float
    cases: list[TestCase]
    coverage_percent: float | None
    raw_output: str

class QAFeedback(BaseModel):
    target_agent: Literal["frontend_dev", "backend_dev", "both"]
    failed_tests: list[TestCase]
    suspected_files: list[str]
    suggested_fixes: list[str]
```

System prompt → `PROMPTS.md § QA Engineer`.

---

## 7. DevOps Engineer

| Property | Value |
|---|---|
| **Role** | Containerization + CI/CD |
| **LLM** | Cheap model (Claude Haiku, GPT-4o-mini) |
| **Reads** | `architecture`, `code_files` |
| **Writes** | `devops_files`, `messages`, `costs` |
| **Tools** | None |
| **Output** | `DevOpsBundle` |

### Output schema

```python
class DevOpsBundle(BaseModel):
    dockerfile_backend: str | None
    dockerfile_frontend: str | None
    docker_compose: str
    github_actions_ci: str
    readme_run_instructions: str
    env_example: str
```

System prompt → `PROMPTS.md § DevOps Engineer`.

---

## 8. Advanced Pattern (Optional): LLM-Based Supervisor

For users who want to learn the supervisor pattern with an LLM in the loop:

```python
class SupervisorDecision(BaseModel):
    next_phase: Phase
    reasoning: str
    blockers: list[str]

supervisor_chain = (
    ChatPromptTemplate.from_messages([
        ("system", SUPERVISOR_SYSTEM_PROMPT),
        ("human", "Current state summary: {state_summary}\nWhat next?"),
    ])
    | smart_llm
    | PydanticOutputParser(SupervisorDecision)
)
```

This adds ~$0.10 per build but makes the system more flexible for novel project types. Gated behind `--llm-supervisor` flag.

---

## 9. Tool Specifications

### `sandbox_exec`

```python
@tool
def sandbox_exec(
    files: dict[str, str],
    command: str,
    language: Literal["python", "node"] = "python",
    timeout_seconds: int = 60,
) -> ExecutionResult:
    """Execute code in an isolated Docker sandbox."""
```

Returns:
```python
class ExecutionResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool
```

Implementation in `SANDBOX.md`.

### `web_search` (optional, for Architect)

Wraps Tavily API. Used for "what's the current best-practice for X". Limited to 3 calls per build to control cost.

### `file_writer` (internal, post-graph)

Not an LLM tool — used by the runtime after graph completion to materialize all `code_files` and `devops_files` to disk.

---

## 10. Behavior Contracts

Every agent MUST:
- Return only valid JSON matching its schema (enforced by Pydantic parser)
- Emit descriptive event entries via `events: [Event(...)]`
- Report tokens via `costs: [CostEntry(...)]`
- Tolerate missing optional inputs (e.g. `qa_feedback` is None on first dev pass)

Every agent MUST NOT:
- Modify state fields outside its declared writes
- Make tool calls outside its declared tool list
- Call other agents directly (orchestration is the supervisor's job)
- Produce free-form prose where structured output is expected
