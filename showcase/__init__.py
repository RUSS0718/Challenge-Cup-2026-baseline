"""Product-side entry points for the explicit ``showcase_mvp`` profile.

The package is intentionally separate from the root ``user_agent`` module.
Importing the official profile therefore never loads this package or its
future product-only dependencies.
"""

from .profile import OFFICIAL_PROFILE, SHOWCASE_PROFILE, ProfileBoundaryError
from .storage import PersistenceError, SQLiteStore
from .run_service import (
    AgentAdapter,
    AgentResult,
    FakeAgentAdapter,
    RunNotFoundError,
    RunRequest,
    RunService,
    RunValidationError,
)

__all__ = [
    "AgentAdapter",
    "AgentResult",
    "FakeAgentAdapter",
    "OFFICIAL_PROFILE",
    "ProfileBoundaryError",
    "PersistenceError",
    "RunNotFoundError",
    "RunRequest",
    "RunService",
    "RunValidationError",
    "SHOWCASE_PROFILE",
    "SQLiteStore",
]
