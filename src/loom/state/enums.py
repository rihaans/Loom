"""Enums for AgentForge state management."""

from enum import StrEnum


class Phase(StrEnum):
    """Build pipeline phases."""

    INIT = "init"
    REQUIREMENTS = "requirements"
    DESIGN = "design"
    DEVELOPMENT = "development"
    REVIEW = "review"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    DONE = "done"
    FAILED = "failed"


class AgentRole(StrEnum):
    """Agent roles in the build pipeline."""

    PRODUCT_MANAGER = "product_manager"
    ARCHITECT = "architect"
    FRONTEND_DEV = "frontend_dev"
    BACKEND_DEV = "backend_dev"
    CODE_REVIEWER = "code_reviewer"
    QA = "qa_engineer"
    DEVOPS = "devops_engineer"
    SUPERVISOR = "project_manager"


class Priority(StrEnum):
    """User story priority levels."""

    P0 = "P0"  # Must have for MVP
    P1 = "P1"  # Should have
    P2 = "P2"  # Nice to have


class ProjectType(StrEnum):
    """Types of projects that can be generated."""

    REST_API = "rest_api"
    FULLSTACK_WEB = "fullstack_web"
    CLI_TOOL = "cli_tool"
    STATIC_SITE = "static_site"
    MICROSERVICE = "microservice"


class EventType(StrEnum):
    """Types of events emitted during build."""

    PHASE_TRANSITION = "phase_transition"
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_TURN = "agent_turn"
    AGENT_TURN_LIMIT = "agent_turn_limit"
    CHAT_INPUT = "chat_input"
    CHAT_COMMAND = "chat_command"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    RETRY = "retry"
    INTERRUPT = "interrupt"


class TechLayer(StrEnum):
    """Technology stack layers."""

    FRONTEND = "frontend"
    BACKEND = "backend"
    DATABASE = "database"
    AUTH = "auth"
    DEPLOYMENT = "deployment"
    TESTING = "testing"
    OTHER = "other"


class ComponentType(StrEnum):
    """Types of software components."""

    SERVICE = "service"
    MODULE = "module"
    PAGE = "page"
    UI_COMPONENT = "ui_component"
    MIDDLEWARE = "middleware"


class ComponentLocation(StrEnum):
    """Where a component lives."""

    FRONTEND = "frontend"
    BACKEND = "backend"


class HttpMethod(StrEnum):
    """HTTP methods for API endpoints."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class TargetAgent(StrEnum):
    """Target agents for QA feedback."""

    FRONTEND_DEV = "frontend_dev"
    BACKEND_DEV = "backend_dev"
    BOTH = "both"


class ReviewSeverity(StrEnum):
    """Severity of an issue raised by the Code Reviewer."""

    CRITICAL = "critical"  # Will not run / security hole / data loss — must fix
    MAJOR = "major"  # Wrong behaviour or missing requirement — should fix
    MINOR = "minor"  # Style / polish — non-blocking
