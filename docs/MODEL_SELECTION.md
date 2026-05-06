# MODEL_SELECTION — Which LLM for Which Agent

A core feature of AgentForge is **provider-agnostic, per-agent LLM configuration**. Each agent has different requirements: PM needs reasoning, devs need code skill, DevOps needs neither.

---

## TL;DR Recommendation Table

| Agent | Best (Quality) | Best (Cost) | Best (Local) | Why |
|---|---|---|---|---|
| Project Manager | n/a (deterministic) | n/a | n/a | Pure Python, no LLM |
| Product Manager | **Claude Sonnet 4.5** | GPT-4o-mini | Llama 3.1 70B | Reasoning + structured output |
| Architect | **Claude Sonnet 4.5** | Claude Haiku 3.5 | Qwen2.5-coder 32B | System design judgment |
| Frontend Dev | **Claude Sonnet 4.5** | DeepSeek-V3 | Qwen2.5-coder 32B | Code generation quality |
| Backend Dev | **Claude Sonnet 4.5** | DeepSeek-V3 | Qwen2.5-coder 32B | Code generation quality |
| QA Engineer | **Claude Sonnet 4.5** | GPT-4o-mini | Qwen2.5-coder 14B | Test writing + error analysis |
| DevOps | Claude Haiku 3.5 | GPT-4o-mini | Llama 3.1 8B | Templated, cheap is fine |

**Default config** (no API keys): All agents → `qwen2.5-coder:7b` via Ollama.

**Recommended config** (with budget): All agents → `claude-sonnet-4-5` except DevOps → `claude-haiku-3-5`.

---

## Provider Notes

### Anthropic (recommended)

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

- **Strengths**: Best at structured output, follows long prompts, code quality
- **Models**:
  - `claude-sonnet-4-5` — flagship, best for everything
  - `claude-haiku-3-5` — 5x cheaper, fine for DevOps and simple PM tasks
  - `claude-opus-4-7` — overkill for this project; use only if you want maximum quality

### OpenAI

```bash
export OPENAI_API_KEY="sk-..."
```

- **Strengths**: Mature SDK, structured output mode, broad knowledge
- **Models**:
  - `gpt-4o` — strong all-rounder, slightly behind Sonnet on code
  - `gpt-4o-mini` — very cheap, surprisingly good for routing/DevOps
  - `o1-mini` — reasoning-heavy, good for Architect but slow & pricey

### Ollama (local, free)

```bash
# Install: https://ollama.ai
ollama pull qwen2.5-coder:7b   # ~4.7 GB, runs on 8GB RAM
ollama pull qwen2.5-coder:32b  # ~20 GB, needs 32GB RAM, much better
ollama pull llama3.1:8b        # general reasoning
```

- **Strengths**: Free, private, no rate limits
- **Limitations**: Smaller models miss subtle prompt instructions, slower inference, weaker JSON adherence
- **Pro tip**: Use JSON mode (`format="json"`) and lower temperature (0.0) for structured output

### DeepSeek (cheap, very good code)

```bash
export DEEPSEEK_API_KEY="..."
```

- **Strengths**: Code quality near Sonnet at ~10x cheaper
- **Limitations**: Slower than US providers, occasional latency spikes
- Use via `langchain-openai` with `base_url="https://api.deepseek.com"`

---

## Per-Agent LLM Configuration

```toml
# In ~/.agentforge/config.toml or agentforge.toml in project root

[llm.default]
provider = "anthropic"
model = "claude-sonnet-4-5"
temperature = 0.2

# Override per agent
[llm.devops_engineer]
provider = "anthropic"
model = "claude-haiku-3-5"
temperature = 0.0

[llm.product_manager]
temperature = 0.3   # slight creativity for PRD writing
```

Or via environment:

```bash
export AGENTFORGE_LLM_DEFAULT="anthropic:claude-sonnet-4-5"
export AGENTFORGE_LLM_DEVOPS="anthropic:claude-haiku-3-5"
```

Or via CLI flags:

```bash
agentforge build "..." \
  --llm anthropic:claude-sonnet-4-5 \
  --llm-devops anthropic:claude-haiku-3-5
```

---

## Cost Estimates per Build

For "todo app with auth + CRUD" (a typical demo):

| Configuration | Total tokens | Cost |
|---|---|---|
| All Claude Sonnet 4.5 | ~80k | ~$0.50 |
| Sonnet for code, Haiku for rest | ~80k | ~$0.20 |
| All GPT-4o-mini | ~80k | ~$0.04 |
| All Ollama qwen2.5-coder:7b | ~80k | $0 (own electricity) |
| All Ollama qwen2.5-coder:32b | ~80k | $0 |

For "fullstack book review site":

| Configuration | Total tokens | Cost |
|---|---|---|
| All Claude Sonnet 4.5 | ~200k | ~$1.30 |
| Mixed (recommended) | ~200k | ~$0.55 |

---

## Quality vs Cost Map

```
Quality
  ▲
  │   Claude Opus
  │      ●
  │
  │           Claude Sonnet 4.5    ← recommended
  │              ●
  │                       GPT-4o
  │                         ●
  │
  │                                    Qwen-32B (local)
  │                                         ●
  │                  Claude Haiku
  │                      ●            DeepSeek-V3
  │                                       ●
  │                              GPT-4o-mini
  │                                  ●
  │              Qwen-7B (local)
  │                  ●
  │
  └──────────────────────────────────────────────► Cheaper →
```

---

## Implementation: The LLM Factory

```python
# agentforge/llm/factory.py
def get_llm_for_role(role: AgentRole, config: AgentForgeConfig) -> BaseChatModel:
    """Returns a configured LLM for an agent role, falling back through:
    1. Per-role override
    2. Default config
    3. Auto-detect from env (Anthropic > OpenAI > Ollama)
    """
    role_config = config.llm_overrides.get(role) or config.llm_default
    
    if role_config.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=role_config.model,
            temperature=role_config.temperature,
            max_tokens=role_config.max_tokens,
            api_key=role_config.api_key or os.getenv("ANTHROPIC_API_KEY"),
        )
    elif role_config.provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=role_config.model,
            temperature=role_config.temperature,
            max_tokens=role_config.max_tokens,
            api_key=role_config.api_key or os.getenv("OPENAI_API_KEY"),
        )
    elif role_config.provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=role_config.model,
            temperature=role_config.temperature,
            base_url=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            format="json",  # critical for structured output with smaller models
        )
    else:
        raise ValueError(f"Unknown provider: {role_config.provider}")


def auto_detect_default() -> LLMConfig:
    """If user provides no config, pick best available."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return LLMConfig(provider="anthropic", model="claude-sonnet-4-5")
    if os.getenv("OPENAI_API_KEY"):
        return LLMConfig(provider="openai", model="gpt-4o-mini")
    return LLMConfig(provider="ollama", model="qwen2.5-coder:7b", temperature=0.0)
```

---

## Tips for Smaller Local Models

When using Ollama models < 30B params:
- Malformed JSON → set `format="json"`, temperature 0.0
- Skipped instructions → use shorter, more direct prompts (variants in `prompts/local.py`)
- Hallucinated APIs → constrain stack choices more aggressively
- Slow responses → reduce `max_tokens`, batch size

The `agentforge.toml` ships with a `[profile.local]` preset:

```toml
[profile.local]
[profile.local.llm.default]
provider = "ollama"
model = "qwen2.5-coder:7b"
temperature = 0.0
max_tokens = 2048

prompt_variant = "concise"

[profile.local.retry]
max_parse_attempts = 5
```

Activate with: `agentforge build "..." --profile local`
