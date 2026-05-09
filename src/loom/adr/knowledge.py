"""Curated knowledge base for ADR generation.

Contains alternatives, positives, and negatives for common (layer, technology)
pairs. This enables rich ADR content without additional LLM calls.
"""

from typing import TypedDict


class TechKnowledge(TypedDict):
    """Knowledge entry for a technology choice."""

    alternatives: list[tuple[str, str]]  # (name, reason why not chosen)
    positives: list[str]
    negatives: list[str]
    docs_url: str | None


# Keyed by (layer, technology) - case-insensitive matching
ADR_KNOWLEDGE: dict[tuple[str, str], TechKnowledge] = {
    # Backend frameworks
    ("backend", "fastapi"): {
        "alternatives": [
            (
                "Flask",
                "simpler and more familiar, but lacks native async support and "
                "requires extra plumbing for OpenAPI docs and request validation.",
            ),
            (
                "Express.js",
                "would split the language between frontend and backend; "
                "not justified for an API-only project.",
            ),
            (
                "Django REST Framework",
                "more batteries-included but heavier; overkill for most APIs "
                "without complex admin or ORM requirements.",
            ),
        ],
        "positives": [
            "Native Pydantic integration matches our data validation strategy.",
            "Auto-generated OpenAPI docs at `/docs` simplify API testing.",
            "Async-first design supports future scaling without rework.",
            "Excellent type hints and IDE autocomplete support.",
        ],
        "negatives": [
            "Slightly steeper learning curve for contributors unfamiliar with async.",
            "Smaller middleware ecosystem compared to Express or Django.",
        ],
        "docs_url": "https://fastapi.tiangolo.com",
    },
    ("backend", "flask"): {
        "alternatives": [
            (
                "FastAPI",
                "better async support and built-in validation, but adds complexity "
                "not needed for simple synchronous APIs.",
            ),
            (
                "Django",
                "more full-featured but heavy for a simple API without admin needs.",
            ),
        ],
        "positives": [
            "Simple and well-documented with extensive ecosystem.",
            "Low learning curve for new contributors.",
            "Flexible architecture allows gradual complexity.",
        ],
        "negatives": [
            "No native async support; may need migration for high concurrency.",
            "OpenAPI docs require additional extensions (Flask-RESTX, apispec).",
        ],
        "docs_url": "https://flask.palletsprojects.com",
    },
    ("backend", "express"): {
        "alternatives": [
            (
                "FastAPI",
                "would provide better type safety but requires Python; "
                "JavaScript stack preferred for this project.",
            ),
            (
                "NestJS",
                "more structured but adds TypeScript and decorator complexity.",
            ),
        ],
        "positives": [
            "Ubiquitous JavaScript knowledge; easy to hire.",
            "Massive middleware ecosystem for common tasks.",
            "Minimal, unopinionated design allows flexibility.",
        ],
        "negatives": [
            "No built-in validation; requires express-validator or Joi.",
            "Callback-heavy patterns can lead to complex code without discipline.",
        ],
        "docs_url": "https://expressjs.com",
    },
    ("backend", "express.js"): {  # Alias
        "alternatives": [
            (
                "FastAPI",
                "would provide better type safety but requires Python; "
                "JavaScript stack preferred for this project.",
            ),
            (
                "NestJS",
                "more structured but adds TypeScript and decorator complexity.",
            ),
        ],
        "positives": [
            "Ubiquitous JavaScript knowledge; easy to hire.",
            "Massive middleware ecosystem for common tasks.",
            "Minimal, unopinionated design allows flexibility.",
        ],
        "negatives": [
            "No built-in validation; requires express-validator or Joi.",
            "Callback-heavy patterns can lead to complex code without discipline.",
        ],
        "docs_url": "https://expressjs.com",
    },
    # Frontend frameworks
    ("frontend", "react"): {
        "alternatives": [
            (
                "Vue 3",
                "gentler learning curve but smaller ecosystem for complex SPAs.",
            ),
            (
                "Svelte",
                "better performance but smaller community and fewer UI libraries.",
            ),
            (
                "Vanilla JS",
                "no framework overhead but manual DOM management doesn't scale.",
            ),
        ],
        "positives": [
            "Largest ecosystem of UI component libraries.",
            "Industry standard; extensive documentation and tutorials.",
            "Strong TypeScript integration with excellent tooling.",
        ],
        "negatives": [
            "JSX can feel unfamiliar to backend developers.",
            "Many ways to structure state management; requires discipline.",
        ],
        "docs_url": "https://react.dev",
    },
    ("frontend", "react+vite"): {
        "alternatives": [
            (
                "Create React App",
                "simpler setup but slower builds and less flexible configuration.",
            ),
            (
                "Next.js",
                "better for SEO-critical apps but adds server complexity not needed here.",
            ),
            (
                "Vue 3 + Vite",
                "viable alternative but React's larger ecosystem preferred.",
            ),
        ],
        "positives": [
            "Vite provides instant HMR and fast production builds.",
            "React's ecosystem offers mature UI libraries (shadcn, MUI, etc.).",
            "TypeScript support is first-class in both tools.",
        ],
        "negatives": [
            "Requires more configuration than opinionated meta-frameworks.",
            "No built-in SSR; needs additional setup if SEO becomes important.",
        ],
        "docs_url": "https://vitejs.dev",
    },
    ("frontend", "vue"): {
        "alternatives": [
            (
                "React",
                "larger ecosystem but steeper learning curve for this team's background.",
            ),
            (
                "Svelte",
                "even simpler but smaller community and component library selection.",
            ),
        ],
        "positives": [
            "Gentle learning curve with excellent documentation.",
            "Single-file components keep template/script/style together.",
            "Composition API provides React-like flexibility when needed.",
        ],
        "negatives": [
            "Smaller ecosystem of enterprise-grade UI libraries vs React.",
            "Some advanced patterns require understanding Vue's reactivity system.",
        ],
        "docs_url": "https://vuejs.org",
    },
    ("frontend", "vue 3"): {  # Alias
        "alternatives": [
            (
                "React",
                "larger ecosystem but steeper learning curve for this team's background.",
            ),
            (
                "Svelte",
                "even simpler but smaller community and component library selection.",
            ),
        ],
        "positives": [
            "Gentle learning curve with excellent documentation.",
            "Single-file components keep template/script/style together.",
            "Composition API provides React-like flexibility when needed.",
        ],
        "negatives": [
            "Smaller ecosystem of enterprise-grade UI libraries vs React.",
            "Some advanced patterns require understanding Vue's reactivity system.",
        ],
        "docs_url": "https://vuejs.org",
    },
    ("frontend", "vanilla"): {
        "alternatives": [
            (
                "React",
                "would add complexity not justified for a simple interface.",
            ),
            (
                "Alpine.js",
                "lightweight reactivity but still a dependency to maintain.",
            ),
        ],
        "positives": [
            "Zero dependencies; smallest possible bundle size.",
            "No build step needed; simple deployment.",
            "Full control over DOM manipulation.",
        ],
        "negatives": [
            "Manual state management becomes unwieldy as app grows.",
            "No component reuse patterns without custom solutions.",
        ],
        "docs_url": None,
    },
    # Databases
    ("database", "sqlite"): {
        "alternatives": [
            (
                "PostgreSQL",
                "more powerful but requires separate server setup not justified "
                "for single-user or low-traffic applications.",
            ),
            (
                "MySQL",
                "similar complexity to Postgres without the advanced features.",
            ),
            (
                "In-memory dict",
                "simplest but loses data on restart.",
            ),
        ],
        "positives": [
            "Zero configuration; database is a single file.",
            "Perfect for prototypes, demos, and single-user apps.",
            "Full SQL support with transactions.",
        ],
        "negatives": [
            "No concurrent write support; not suitable for multi-user production.",
            "No built-in replication or clustering.",
        ],
        "docs_url": "https://www.sqlite.org/docs.html",
    },
    ("database", "postgres"): {
        "alternatives": [
            (
                "SQLite",
                "simpler but can't handle concurrent writes or multi-user production.",
            ),
            (
                "MySQL",
                "viable but Postgres has better JSON support and extensibility.",
            ),
            (
                "MongoDB",
                "flexible schemas but loses relational integrity guarantees.",
            ),
        ],
        "positives": [
            "Industry standard for production applications.",
            "Excellent JSON support for semi-structured data.",
            "Strong ecosystem of extensions (PostGIS, pg_vector, etc.).",
        ],
        "negatives": [
            "Requires server setup and connection management.",
            "More complex local development than SQLite.",
        ],
        "docs_url": "https://www.postgresql.org/docs/",
    },
    ("database", "postgresql"): {  # Alias
        "alternatives": [
            (
                "SQLite",
                "simpler but can't handle concurrent writes or multi-user production.",
            ),
            (
                "MySQL",
                "viable but Postgres has better JSON support and extensibility.",
            ),
            (
                "MongoDB",
                "flexible schemas but loses relational integrity guarantees.",
            ),
        ],
        "positives": [
            "Industry standard for production applications.",
            "Excellent JSON support for semi-structured data.",
            "Strong ecosystem of extensions (PostGIS, pg_vector, etc.).",
        ],
        "negatives": [
            "Requires server setup and connection management.",
            "More complex local development than SQLite.",
        ],
        "docs_url": "https://www.postgresql.org/docs/",
    },
    ("database", "in-memory"): {
        "alternatives": [
            (
                "SQLite",
                "persists data but adds file I/O complexity.",
            ),
            (
                "Redis",
                "production-ready but requires separate server.",
            ),
        ],
        "positives": [
            "Simplest possible storage for demos and prototypes.",
            "No external dependencies or configuration.",
            "Fast reads and writes with no I/O overhead.",
        ],
        "negatives": [
            "All data lost on restart.",
            "No query language; manual data filtering required.",
        ],
        "docs_url": None,
    },
    # Auth approaches
    ("auth", "jwt"): {
        "alternatives": [
            (
                "Session cookies",
                "simpler but requires server-side session storage.",
            ),
            (
                "OAuth 2.0 only",
                "secure but requires third-party provider setup.",
            ),
            (
                "No auth",
                "simplest but not suitable for user-specific data.",
            ),
        ],
        "positives": [
            "Stateless; no server-side session storage needed.",
            "Works well with SPAs and mobile clients.",
            "Standard claims format for user identity.",
        ],
        "negatives": [
            "Tokens can't be revoked without additional infrastructure.",
            "Must handle token refresh logic on client.",
        ],
        "docs_url": "https://jwt.io/introduction",
    },
    ("auth", "session"): {
        "alternatives": [
            (
                "JWT",
                "stateless but harder to revoke and requires refresh logic.",
            ),
            (
                "OAuth 2.0",
                "better for third-party integrations but complex for simple apps.",
            ),
        ],
        "positives": [
            "Simple to implement and understand.",
            "Easy to revoke by deleting server-side session.",
            "Built-in support in most web frameworks.",
        ],
        "negatives": [
            "Requires server-side session storage (memory, Redis, DB).",
            "Harder to use with mobile apps and cross-domain APIs.",
        ],
        "docs_url": None,
    },
    ("auth", "session cookies"): {  # Alias
        "alternatives": [
            (
                "JWT",
                "stateless but harder to revoke and requires refresh logic.",
            ),
            (
                "OAuth 2.0",
                "better for third-party integrations but complex for simple apps.",
            ),
        ],
        "positives": [
            "Simple to implement and understand.",
            "Easy to revoke by deleting server-side session.",
            "Built-in support in most web frameworks.",
        ],
        "negatives": [
            "Requires server-side session storage (memory, Redis, DB).",
            "Harder to use with mobile apps and cross-domain APIs.",
        ],
        "docs_url": None,
    },
    ("auth", "none"): {
        "alternatives": [
            (
                "JWT",
                "would add auth but not needed for public/demo application.",
            ),
            (
                "Basic Auth",
                "simple but sends credentials with every request.",
            ),
        ],
        "positives": [
            "Simplest possible implementation.",
            "No user management overhead.",
            "Appropriate for public APIs or demos.",
        ],
        "negatives": [
            "No user-specific data or access control.",
            "Not suitable for production with sensitive data.",
        ],
        "docs_url": None,
    },
    # Testing frameworks
    ("testing", "pytest"): {
        "alternatives": [
            (
                "unittest",
                "built-in but more verbose and less feature-rich.",
            ),
            (
                "nose2",
                "dated; pytest has become the Python standard.",
            ),
        ],
        "positives": [
            "De facto standard for Python testing.",
            "Rich plugin ecosystem (pytest-cov, pytest-asyncio, etc.).",
            "Concise assertion syntax and excellent fixtures.",
        ],
        "negatives": [
            "Magic fixture injection can confuse newcomers.",
            "Some advanced features have learning curve.",
        ],
        "docs_url": "https://docs.pytest.org",
    },
    ("testing", "jest"): {
        "alternatives": [
            (
                "Vitest",
                "faster but younger ecosystem.",
            ),
            (
                "Mocha + Chai",
                "more flexible but requires more configuration.",
            ),
        ],
        "positives": [
            "Built-in mocking, snapshots, and coverage.",
            "Excellent integration with React Testing Library.",
            "Parallel test execution out of the box.",
        ],
        "negatives": [
            "Can be slow on large test suites.",
            "Configuration can become complex for non-standard setups.",
        ],
        "docs_url": "https://jestjs.io",
    },
    ("testing", "vitest"): {
        "alternatives": [
            (
                "Jest",
                "more mature but slower; Vite projects benefit from native Vitest.",
            ),
            (
                "Mocha",
                "flexible but requires manual setup for common features.",
            ),
        ],
        "positives": [
            "Blazing fast with Vite's native ESM support.",
            "Jest-compatible API for easy migration.",
            "Built-in TypeScript support without configuration.",
        ],
        "negatives": [
            "Younger ecosystem; fewer plugins than Jest.",
            "Some Jest features still being implemented.",
        ],
        "docs_url": "https://vitest.dev",
    },
}


def get_knowledge(layer: str, technology: str) -> TechKnowledge | None:
    """Get knowledge for a (layer, technology) pair.

    Args:
        layer: The tech layer (backend, frontend, database, auth, testing)
        technology: The technology name (case-insensitive)

    Returns:
        TechKnowledge if found, None otherwise
    """
    key = (layer.lower(), technology.lower())
    return ADR_KNOWLEDGE.get(key)


def has_knowledge(layer: str, technology: str) -> bool:
    """Check if we have curated knowledge for a tech choice."""
    return get_knowledge(layer, technology) is not None
