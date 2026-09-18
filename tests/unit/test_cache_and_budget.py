"""Tests for the artifact cache and cost-budget enforcement.

Both exist to make Loom cheap enough to iterate with: the cache stops you
paying twice for the same artifact, the budget stops a runaway build.
"""

from pathlib import Path

import pytest

from loom.cache import ArtifactCache, cache_key
from loom.config.models import LoomConfig
from loom.cost import BudgetExceededError, check_budget, spent_so_far
from loom.state.enums import AgentRole
from loom.state.models import CostEntry, DevOpsBundle


@pytest.fixture
def cache(tmp_path: Path) -> ArtifactCache:
    return ArtifactCache(cache_dir=tmp_path / "artifacts")


def _bundle(compose: str = "services: {}") -> DevOpsBundle:
    return DevOpsBundle(docker_compose=compose)


def _key(**over: object) -> str:
    base: dict[str, object] = {
        "agent": "devops_engineer",
        "system_prompt": "sys",
        "human_template": "tmpl {x}",
        "prompt_input": {"x": "1"},
        "model_id": "ChatOllama:qwen2.5-coder:7b",
        "output_model": "DevOpsBundle",
    }
    base.update(over)
    return cache_key(**base)  # type: ignore[arg-type]


class TestCacheKey:
    def test_is_deterministic(self) -> None:
        assert _key() == _key()

    def test_dict_ordering_does_not_matter(self) -> None:
        a = _key(prompt_input={"x": "1", "y": "2"})
        b = _key(prompt_input={"y": "2", "x": "1"})
        assert a == b, "key must not depend on dict insertion order"

    @pytest.mark.parametrize(
        "field,value",
        [
            ("agent", "architect"),
            ("system_prompt", "different"),
            ("human_template", "different {x}"),
            ("prompt_input", {"x": "2"}),
            ("model_id", "ChatAnthropic:claude-opus-5"),
            ("output_model", "PRD"),
        ],
    )
    def test_any_input_change_changes_the_key(self, field: str, value: object) -> None:
        assert _key(**{field: value}) != _key()

    def test_different_models_never_share_an_entry(self) -> None:
        """A cheap model's output must not be served for an expensive one."""
        assert _key(model_id="ollama:small") != _key(model_id="anthropic:big")


class TestArtifactCache:
    def test_miss_on_empty_cache(self, cache: ArtifactCache) -> None:
        assert cache.get(_key(), DevOpsBundle) is None
        assert cache.stats.misses == 1

    def test_roundtrip(self, cache: ArtifactCache) -> None:
        k = _key()
        cache.put(k, _bundle("services: {web: {}}"), agent="devops_engineer")
        got = cache.get(k, DevOpsBundle, agent="devops_engineer")
        assert got is not None
        assert got.docker_compose == "services: {web: {}}"
        assert cache.stats.hits == 1

    def test_survives_a_new_instance(self, tmp_path: Path) -> None:
        d = tmp_path / "artifacts"
        ArtifactCache(cache_dir=d).put(_key(), _bundle(), agent="devops_engineer")
        assert ArtifactCache(cache_dir=d).get(_key(), DevOpsBundle) is not None

    def test_disabled_cache_never_hits(self, tmp_path: Path) -> None:
        c = ArtifactCache(cache_dir=tmp_path / "a", enabled=False)
        c.put(_key(), _bundle())
        assert c.get(_key(), DevOpsBundle) is None

    def test_corrupt_entry_is_a_miss_not_a_crash(self, cache: ArtifactCache) -> None:
        k = _key()
        cache.put(k, _bundle())
        path = cache._path(k)
        path.write_text("{ not json", encoding="utf-8")
        assert cache.get(k, DevOpsBundle) is None
        assert not path.exists(), "unusable entry should be removed"

    def test_clear_and_count(self, cache: ArtifactCache) -> None:
        cache.put(_key(), _bundle())
        cache.put(_key(agent="architect"), _bundle())
        assert cache.entry_count() == 2
        assert cache.clear() == 2
        assert cache.entry_count() == 0


class TestBudgetEnforcement:
    def _state(self, *costs: float) -> dict[str, object]:
        return {
            "costs": [
                CostEntry(
                    agent=AgentRole.BACKEND_DEV,
                    model="claude-sonnet-5",
                    input_tokens=100,
                    output_tokens=100,
                    cost_usd=c,
                )
                for c in costs
            ]
        }

    def test_no_budget_means_no_limit(self) -> None:
        cfg = LoomConfig()
        assert cfg.cost_budget_usd is None
        assert check_budget(self._state(99.0), cfg, "backend dev") is None

    def test_under_budget_proceeds(self) -> None:
        cfg = LoomConfig(cost_budget_usd=1.00)
        assert check_budget(self._state(0.25, 0.25), cfg, "backend dev") is None

    def test_at_or_over_budget_stops(self) -> None:
        cfg = LoomConfig(cost_budget_usd=1.00)
        msg = check_budget(self._state(0.60, 0.50), cfg, "backend dev")
        assert msg is not None
        assert "budget" in msg.lower()
        assert "1.00" in msg and "backend dev" in msg

    def test_spent_so_far_sums_entries(self) -> None:
        assert spent_so_far(self._state(0.1, 0.2, 0.3)) == pytest.approx(0.6)

    def test_error_message_is_actionable(self) -> None:
        e = BudgetExceededError(spent=2.5, budget=1.0, next_agent="reviewer")
        text = str(e)
        assert "2.5" in text and "1.00" in text
        assert "loom.toml" in text or "LOOM_COST_BUDGET" in text


def _key_with_scope(prompt_input: dict[str, object], agent: str = "backend_dev") -> str:
    """Compute a cache key the way build_agent_chain does, honouring the scope."""
    from loom.agents.base import CACHE_SCOPE_KEY

    scope = prompt_input.get(CACHE_SCOPE_KEY)
    basis = scope if isinstance(scope, dict) else prompt_input
    return cache_key(
        agent=agent,
        system_prompt="sys",
        human_template="tmpl",
        prompt_input={k: v for k, v in basis.items() if k != CACHE_SCOPE_KEY},
        model_id="m",
        output_model="FileBundle",
    )


class TestRetryScopeSharesOneCacheEntry:
    """A parse retry must not create a second, unreachable cache entry.

    Retry feedback is appended to the prompt, so without a canonical scope the
    artifact gets cached under the *retried* prompt. A rerun starts from
    attempt 1, misses, regenerates, and that miss cascades to every downstream
    agent - which is what made repeat builds expensive.
    """

    def test_retry_attempts_share_a_key(self) -> None:
        from loom.agents.base import CACHE_SCOPE_KEY

        attempt1: dict[str, object] = {"prd_json": "PRD", "architecture_json": "ARCH"}
        attempt1[CACHE_SCOPE_KEY] = {**attempt1, "architecture_json": "ARCH"}

        attempt2: dict[str, object] = {
            "prd_json": "PRD",
            "architecture_json": "ARCH\n\nPARSE ERROR: missing field",
        }
        attempt2[CACHE_SCOPE_KEY] = {**attempt2, "architecture_json": "ARCH"}

        assert _key_with_scope(attempt1) == _key_with_scope(attempt2), (
            "a retry must reuse the first attempt's cache entry"
        )

    def test_a_genuinely_different_request_still_differs(self) -> None:
        """The scope must not collapse distinct requests together."""
        from loom.agents.base import CACHE_SCOPE_KEY

        def keyed(arch: str) -> str:
            pi: dict[str, object] = {"prd_json": "PRD", "architecture_json": arch}
            pi[CACHE_SCOPE_KEY] = {**pi, "architecture_json": arch}
            return _key_with_scope(pi)

        assert keyed("ARCH-A") != keyed("ARCH-B")

    def test_without_a_scope_the_full_input_is_used(self) -> None:
        a: dict[str, object] = {"prd_json": "PRD", "architecture_json": "ARCH"}
        b: dict[str, object] = {"prd_json": "PRD", "architecture_json": "ARCH+feedback"}
        assert _key_with_scope(a) != _key_with_scope(b)


class TestCacheScopeNeverReachesThePrompt:
    """The reserved key is internal and must not be rendered into a prompt."""

    def test_reserved_key_is_stripped(self) -> None:
        from langchain_core.language_models.fake_chat_models import FakeListChatModel

        from loom.agents.base import CACHE_SCOPE_KEY, build_agent_chain
        from loom.state.models import DevOpsBundle

        llm = FakeListChatModel(responses=['{"docker_compose": "x"}'])
        chain, parser = build_agent_chain(
            system_prompt="sys",
            human_template="build {architecture_json}",
            output_model=DevOpsBundle,
            llm=llm,
            use_structured_output=False,
            agent_name="devops_engineer",
        )
        pi: dict[str, object] = {
            "architecture_json": "ARCH",
            "format_instructions": parser.get_format_instructions(),
        }
        pi[CACHE_SCOPE_KEY] = dict(pi)
        # Rendering would raise if the reserved key leaked into the template.
        result = chain.invoke(pi)
        assert isinstance(result, DevOpsBundle)
