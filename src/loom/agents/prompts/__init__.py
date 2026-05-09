"""System prompts for all agents."""

from loom.agents.prompts.architect import (
    ARCHITECT_HUMAN_TEMPLATE,
    ARCHITECT_SYSTEM_PROMPT,
)
from loom.agents.prompts.backend_dev import (
    BACKEND_DEV_HUMAN_TEMPLATE,
    BACKEND_DEV_SYSTEM_PROMPT,
)
from loom.agents.prompts.devops_engineer import (
    DEVOPS_ENGINEER_HUMAN_TEMPLATE,
    DEVOPS_ENGINEER_SYSTEM_PROMPT,
)
from loom.agents.prompts.frontend_dev import (
    FRONTEND_DEV_HUMAN_TEMPLATE,
    FRONTEND_DEV_SYSTEM_PROMPT,
)
from loom.agents.prompts.product_manager import (
    PRODUCT_MANAGER_HUMAN_TEMPLATE,
    PRODUCT_MANAGER_SYSTEM_PROMPT,
)
from loom.agents.prompts.qa_engineer import (
    QA_ENGINEER_HUMAN_TEMPLATE,
    QA_ENGINEER_SYSTEM_PROMPT,
)

__all__ = [
    # Architect
    "ARCHITECT_HUMAN_TEMPLATE",
    "ARCHITECT_SYSTEM_PROMPT",
    # Backend Developer
    "BACKEND_DEV_HUMAN_TEMPLATE",
    "BACKEND_DEV_SYSTEM_PROMPT",
    # DevOps Engineer
    "DEVOPS_ENGINEER_HUMAN_TEMPLATE",
    "DEVOPS_ENGINEER_SYSTEM_PROMPT",
    # Frontend Developer
    "FRONTEND_DEV_HUMAN_TEMPLATE",
    "FRONTEND_DEV_SYSTEM_PROMPT",
    # Product Manager
    "PRODUCT_MANAGER_HUMAN_TEMPLATE",
    "PRODUCT_MANAGER_SYSTEM_PROMPT",
    # QA Engineer
    "QA_ENGINEER_HUMAN_TEMPLATE",
    "QA_ENGINEER_SYSTEM_PROMPT",
]
