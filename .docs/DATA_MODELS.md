# DATA_MODELS — Pydantic Schemas

This is the **source of truth** for inter-agent contracts. Every field defined here is exactly what flows between nodes. If an agent's output doesn't match these schemas, the parser fails and the agent retries.

> Goes in `loom/state/models.py`.

---

## 1. Enums

```python
from enum import Enum

class Phase(str, Enum):
    INIT = "init"
    REQUIREMENTS = "requirements"
    DESIGN = "design"
    DEVELOPMENT = "development"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    DONE = "done"
    FAILED = "failed"

class AgentRole(str, Enum):
    PRODUCT_MANAGER = "product_manager"
    ARCHITECT = "architect"
    FRONTEND_DEV = "frontend_dev"
    BACKEND_DEV = "backend_dev"
    QA = "qa_engineer"
    DEVOPS = "devops_engineer"
    SUPERVISOR = "project_manager"

class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"

class ProjectType(str, Enum):
    REST_API = "rest_api"
    FULLSTACK_WEB = "fullstack_web"
    CLI_TOOL = "cli_tool"
    STATIC_SITE = "static_site"
    MICROSERVICE = "microservice"
```

## 2. PRD Models

```python
from pydantic import BaseModel, Field

class UserStory(BaseModel):
    id: str = Field(..., pattern=r"^US-\d{3}$")
    role: str
    goal: str
    benefit: str
    acceptance_criteria: list[str] = Field(..., min_length=1)
    priority: Priority

class DataEntity(BaseModel):
    name: str
    description: str
    fields: dict[str, str]  # field_name -> type (e.g. "string", "int", "datetime")

class PRD(BaseModel):
    project_name: str
    project_slug: str = Field(..., pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=40)
    project_type: ProjectType
    one_liner: str = Field(..., max_length=200)
    target_users: list[str]
    user_stories: list[UserStory] = Field(..., min_length=1)
    data_entities: list[DataEntity]
    must_have_features: list[str]
    nice_to_have_features: list[str] = []
    out_of_scope: list[str] = []
    success_metrics: list[str]
    assumptions: list[str] = []
```

## 3. Architecture Models

```python
class TechChoice(BaseModel):
    layer: Literal["frontend", "backend", "database", "auth", "deployment", "testing", "other"]
    technology: str
    version: str
    rationale: str

class APIEndpoint(BaseModel):
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    path: str
    description: str
    request_schema: dict | None = None
    response_schema: dict
    auth_required: bool = False
    user_story_ids: list[str] = []  # links back to PRD

class Component(BaseModel):
    name: str
    type: Literal["service", "module", "page", "ui_component", "middleware"]
    location: Literal["frontend", "backend"]
    responsibility: str
    depends_on: list[str] = []

class ArchitectureDoc(BaseModel):
    stack: list[TechChoice] = Field(..., min_length=1)
    api_endpoints: list[APIEndpoint]
    components: list[Component]
    data_models: list[DataEntity]
    folder_structure: dict[str, str]
    component_diagram_mermaid: str
    deployment_diagram_mermaid: str
    notes: str = ""
```

## 4. Code Models

```python
class CodeFile(BaseModel):
    path: str            # relative to project root
    content: str
    language: str        # "python", "javascript", "typescript", "html", "css", "json", "yaml"

class FileBundle(BaseModel):
    files: list[CodeFile]
    entry_point: str
    install_commands: list[str]
    run_commands: list[str]
    notes: str = ""
```

## 5. QA Models

```python
class TestCase(BaseModel):
    name: str
    file: str
    passed: bool
    duration_ms: float
    error_message: str | None = None

class TestReport(BaseModel):
    total: int
    passed: int
    failed: int
    skipped: int = 0
    duration_ms: float
    cases: list[TestCase]
    coverage_percent: float | None = None
    raw_output: str   # truncate to 10k chars before storing

    @property
    def all_passed(self) -> bool:
        return self.failed == 0 and self.total > 0

class QAFeedback(BaseModel):
    target_agent: Literal["frontend_dev", "backend_dev", "both"]
    failed_tests: list[TestCase]
    suspected_files: list[str]
    suggested_fixes: list[str]
    raw_error_excerpt: str = Field(..., max_length=4000)
```

## 6. DevOps Models

```python
class DevOpsBundle(BaseModel):
    dockerfile_backend: str | None = None
    dockerfile_frontend: str | None = None
    docker_compose: str
    github_actions_ci: str
    readme_run_instructions: str
    env_example: str
    other_files: dict[str, str] = {}  # path -> content for anything else
```

## 7. Audit & Cost Models

```python
from datetime import datetime

class Event(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    type: Literal[
        "phase_transition",
        "agent_start",
        "agent_end",
        "tool_call",
        "tool_result",
        "error",
        "retry",
        "interrupt",
    ]
    agent: AgentRole | None = None
    phase: Phase | None = None
    payload: dict = {}

class CostEntry(BaseModel):
    agent: AgentRole
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
```

## 8. Sandbox Execution Models

```python
class ExecutionResult(BaseModel):
    exit_code: int
    stdout: str          # truncate to 50k chars
    stderr: str          # truncate to 50k chars
    duration_ms: float
    timed_out: bool
    files_written: list[str] = []
```

## 9. The Master AgentState

```python
from typing import Annotated
from operator import add
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

def merge_dicts(a: dict, b: dict) -> dict:
    """Reducer: merge two dicts, b takes precedence on key conflicts."""
    return {**a, **b}

class AgentState(BaseModel):
    # Input
    description: str
    config: dict = {}                # CLI flags, model overrides, etc.

    # Routing
    phase: Phase = Phase.INIT
    retry_count: int = 0
    interactive: bool = False

    # Artifacts (one writer each, except code_files)
    prd: PRD | None = None
    architecture: ArchitectureDoc | None = None
    code_files: Annotated[dict[str, FileBundle], merge_dicts] = {}
        # keys: "frontend", "backend"
    test_report: TestReport | None = None
    qa_feedback: QAFeedback | None = None
    devops_files: DevOpsBundle | None = None

    # Logs
    messages: Annotated[list[BaseMessage], add_messages] = []
    events: Annotated[list[Event], add] = []
    costs: Annotated[list[CostEntry], add] = []

    # Final output
    output_dir: str | None = None    # where files were written
    error: str | None = None         # set if graph failed

    class Config:
        arbitrary_types_allowed = True
```

## 10. Configuration Model

```python
class LLMConfig(BaseModel):
    provider: Literal["anthropic", "openai", "ollama"]
    model: str
    temperature: float = 0.2
    max_tokens: int = 4096
    api_key: str | None = None       # falls back to env

class LoomConfig(BaseModel):
    """Loaded from CLI flags + env + config file."""
    llm_default: LLMConfig
    llm_overrides: dict[AgentRole, LLMConfig] = {}
    output_dir: str = "./output"
    max_retries: int = 2
    sandbox_timeout_seconds: int = 90
    sandbox_memory_mb: int = 512
    use_docker_sandbox: bool = True
    interactive: bool = False
    use_llm_supervisor: bool = False
    enable_langsmith: bool = False
    cost_budget_usd: float | None = None  # hard cap
```

## 11. Schema Validation Rules

| Field | Rule | Why |
|---|---|---|
| `PRD.project_slug` | regex kebab-case ≤40 chars | Used as folder name |
| `UserStory.id` | regex `US-\d{3}` | Links from architecture & tests |
| `APIEndpoint.path` | starts with `/` | URL safety |
| `CodeFile.path` | no `..`, no leading `/` | Sandbox safety — no escape |
| `CodeFile.content` | non-empty | No placeholder files |
| `TestReport.total` | == `passed + failed + skipped` | Consistency |

Add Pydantic `field_validator`s to enforce all of these.

## 12. Schema Evolution

When adding fields:
1. Add as `Optional` with sensible default first
2. Update the relevant prompt to mention it
3. Run a few builds to confirm LLMs populate it
4. Tighten to required in a follow-up

Never break a field's name or type without versioning the state.
