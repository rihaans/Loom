# TESTING_STRATEGY — How We Test Loom

Testing an LLM-powered system has a fundamental tension: real LLM calls are expensive, slow, and non-deterministic. Mocked LLM calls miss real behavior. We solve this with **layered tests**.

---

## 1. Test Layers

```
┌─────────────────────────────────────────────────────┐
│  E2E with real LLMs (slow, opt-in, costs $)         │  ← runs nightly
├─────────────────────────────────────────────────────┤
│  Integration with mocked LLMs                       │  ← runs in CI
├─────────────────────────────────────────────────────┤
│  Unit tests of pure functions                       │  ← runs in CI, fast
└─────────────────────────────────────────────────────┘
```

| Layer | Speed | Determinism | Cost | When |
|---|---|---|---|---|
| Unit | < 1s | 100% | $0 | Every commit |
| Integration | 5-30s | 100% (mocked) | $0 | Every commit |
| E2E | 2-10 min | ~80% (LLM variance) | $0.50-3 / run | Nightly + manual |

## 2. Unit Tests — `tests/unit/`

Test pure functions only. No LLM calls, no Docker, no network.

| File | What |
|---|---|
| `test_state.py` | Pydantic schemas validate correctly; reducers merge properly |
| `test_routing.py` | `decide_next_phase()` returns correct phase for each state |
| `test_prompts.py` | Prompts render with expected variables; no f-string errors |
| `test_llm_factory.py` | `get_llm_for_role()` returns the right LLM type for each config |
| `test_output_parsers.py` | Parsing succeeds on good JSON, fails cleanly on bad |
| `test_slugify.py` | Project slugs are kebab-case and safe |
| `test_cost.py` | Token → USD calculation matches provider price tables |

### Example

```python
# tests/unit/test_routing.py
def test_decide_next_phase_initial():
    state = AgentState(description="x")
    assert decide_next_phase(state) == Phase.REQUIREMENTS

def test_decide_next_phase_after_prd():
    state = AgentState(description="x", prd=sample_prd())
    assert decide_next_phase(state) == Phase.DESIGN

def test_decide_next_phase_qa_failed_under_retry_cap():
    state = AgentState(
        description="x", prd=sample_prd(), architecture=sample_arch(),
        code_files={"frontend": sample_files(), "backend": sample_files()},
        test_report=failed_test_report(),
        retry_count=1,
    )
    assert decide_next_phase(state) == Phase.DEVELOPMENT  # retry

def test_decide_next_phase_qa_failed_at_retry_cap():
    state = AgentState(
        description="x", prd=sample_prd(), architecture=sample_arch(),
        code_files={"frontend": sample_files(), "backend": sample_files()},
        test_report=failed_test_report(),
        retry_count=2,
    )
    assert decide_next_phase(state) == Phase.DEPLOYMENT  # advance anyway
```

## 3. Integration Tests — `tests/integration/`

Run the full graph with mocked LLMs.

### Mocking strategy

LangChain provides `FakeListChatModel` — returns canned responses in order. We seed it with realistic outputs:

```python
# tests/fixtures/mock_llm.py
from langchain_core.language_models.fake_chat_models import FakeListChatModel

def mock_pm_response() -> str:
    return json.dumps({
        "project_name": "Todo App",
        "project_slug": "todo-app",
        "project_type": "fullstack_web",
        "one_liner": "A simple todo list with auth",
        "user_stories": [{
            "id": "US-001",
            "role": "user", "goal": "create a todo", "benefit": "track tasks",
            "acceptance_criteria": ["Form accepts text", "Saves to backend"],
            "priority": "P0",
        }],
        "data_entities": [{"name": "Todo", "fields": {"title": "string", "done": "bool"}, "description": "..."}],
        "must_have_features": ["auth", "CRUD"],
        # ... full PRD ...
    })

@pytest.fixture
def fake_llm_full_pipeline():
    return FakeListChatModel(responses=[
        mock_pm_response(),
        mock_architect_response(),
        mock_frontend_response(),
        mock_backend_response(),
        mock_qa_response(),       # passing tests
        mock_devops_response(),
    ])
```

Then patch the LLM factory:

```python
@pytest.fixture
def patched_llm(fake_llm_full_pipeline, monkeypatch):
    monkeypatch.setattr(
        "loom.llm.factory.get_llm_for_role",
        lambda role, config: fake_llm_full_pipeline,
    )
```

### Tests

```python
# tests/integration/test_graph_linear.py
async def test_full_pipeline_happy_path(patched_llm, tmp_path):
    config = LoomConfig(output_dir=str(tmp_path), use_docker_sandbox=False)
    result = await build("a todo app", config=config)
    
    assert result.phase == Phase.DONE
    assert result.prd is not None
    assert result.architecture is not None
    assert "frontend" in result.code_files
    assert "backend" in result.code_files
    assert result.test_report.all_passed
    assert result.devops_files is not None
    assert (tmp_path / "todo-app" / "README.md").exists()


async def test_qa_retry_loop(patched_llm_with_failing_then_passing_qa, tmp_path):
    """First QA run fails → dev agents retry → second QA passes."""
    config = LoomConfig(output_dir=str(tmp_path), use_docker_sandbox=False)
    result = await build("a todo app", config=config)
    
    assert result.retry_count == 1
    assert result.test_report.all_passed
    assert count_calls(patched_llm, "frontend_dev") == 2


async def test_parallel_dev_execution(patched_llm):
    """Frontend and Backend run via Send API and merge correctly."""
    state = AgentState(
        description="x", phase=Phase.DEVELOPMENT,
        prd=sample_prd(), architecture=sample_arch(),
    )
    graph = build_graph(test_config())
    final = await graph.ainvoke(state)
    
    assert "frontend" in final.code_files
    assert "backend" in final.code_files


async def test_interrupt_after_pm(patched_llm, tmp_path):
    """With interactive=True, graph interrupts after PM."""
    config = LoomConfig(interactive=True, output_dir=str(tmp_path))
    graph = build_graph(config)
    
    initial = AgentState(description="todo app", interactive=True)
    thread_id = "test-thread"
    cfg = {"configurable": {"thread_id": thread_id}}
    
    async for _ in graph.astream(initial, config=cfg):
        pass
    
    state_snapshot = graph.get_state(cfg)
    assert state_snapshot.next == ("architect",)  # paused before architect
    assert state_snapshot.values.prd is not None
```

## 4. Sandbox Tests — `tests/integration/test_sandbox_real.py`

Marked `@pytest.mark.docker` and skipped in unit-only CI.

```python
@pytest.mark.docker
def test_sandbox_runs_pytest():
    runner = SandboxRunner(timeout_seconds=30)
    result = runner.run(
        files={
            "test_x.py": "def test_pass(): assert 1 + 1 == 2",
        },
        command="pytest -v",
    )
    assert result.exit_code == 0
    assert "1 passed" in result.stdout
```

## 5. E2E Tests — `tests/e2e/`

Real LLM calls. Marked `@pytest.mark.e2e`. Skipped unless `RUN_E2E=1`.

```python
@pytest.mark.e2e
@pytest.mark.parametrize("scenario", ["todo_app", "url_shortener", "csv_to_json"])
async def test_demo_scenario(scenario):
    description = load_scenario(scenario)
    config = LoomConfig(
        llm_default=LLMConfig(provider="anthropic", model="claude-sonnet-4-5"),
    )
    result = await build(description, config=config)
    
    assert result.phase == Phase.DONE
    assert result.test_report.all_passed or result.retry_count == 2
    
    output_dir = Path(result.output_dir)
    assert (output_dir / "Dockerfile").exists() or (output_dir / "docker-compose.yml").exists()
```

## 6. Snapshot Tests for Prompts

```python
# tests/unit/test_prompt_snapshots.py
def test_pm_prompt_snapshot(snapshot):
    """Catch unintentional prompt changes."""
    rendered = build_pm_prompt({"description": "a todo app"})
    snapshot.assert_match(rendered, "pm_prompt.txt")
```

Updated only via deliberate `pytest --snapshot-update`.

## 7. Property-Based Tests (hypothesis)

For state reducers and parsers:

```python
from hypothesis import given, strategies as st

@given(
    a=st.dictionaries(st.text(), st.integers()),
    b=st.dictionaries(st.text(), st.integers()),
)
def test_merge_dicts_idempotent(a, b):
    result1 = merge_dicts(merge_dicts(a, b), b)
    result2 = merge_dicts(a, b)
    assert result1 == result2
```

## 8. CI Configuration

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install ruff mypy
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy src/loom

  test-unit-integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit tests/integration -v --cov=loom

  test-sandbox:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: docker build -f docker/sandbox.Dockerfile -t loom-sandbox:latest .
      - run: pip install -e ".[dev]"
      - run: pytest tests/integration/test_sandbox_real.py -v -m docker

  e2e:
    if: github.event_name == 'schedule' || contains(github.event.head_commit.message, '[e2e]')
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: pip install -e ".[dev]"
      - env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          RUN_E2E: "1"
        run: pytest tests/e2e -v -m e2e
```

## 9. Coverage Targets

| Module | Coverage target |
|---|---|
| `state/`, `graph/routing.py` | 100% (pure logic) |
| `agents/` (node functions) | 90% |
| `tools/sandbox_exec.py` | 80% |
| `cli/` | 70% |
| `server/` | 70% |
| `frontend/` | smoke-test only (Playwright optional) |

## 10. Manual QA Checklist

Before each release:

- [ ] `loom build "todo app"` succeeds with Anthropic
- [ ] `loom build "todo app"` succeeds with OpenAI
- [ ] `loom build "todo app"` succeeds with Ollama qwen2.5-coder:7b
- [ ] `loom build "..." --interactive` pauses correctly
- [ ] `loom ui` opens dashboard, build runs end-to-end
- [ ] Generated project has working `docker compose up`
- [ ] Generated project's tests pass
- [ ] Cached demo replays without API calls
- [ ] `loom resume <thread_id>` works after Ctrl+C
- [ ] Cost tracker matches actual API usage within 5%
