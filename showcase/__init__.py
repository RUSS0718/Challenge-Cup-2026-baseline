"""Product-side entry points for the explicit ``showcase_mvp`` profile.

The package is intentionally separate from the root ``user_agent`` module.
Importing the official profile therefore never loads this package or its
future product-only dependencies.
"""

from .graph import (
    AgentDecision,
    GraphDependencyError,
    LangGraphExecutionLoop,
    LoopBudget,
    ToolExecutionResult,
)
from .profile import OFFICIAL_PROFILE, SHOWCASE_PROFILE, ProfileBoundaryError
from .run_service import (
    AgentAdapter,
    AgentResult,
    FakeAgentAdapter,
    RunNotFoundError,
    RunRequest,
    RunService,
    RunValidationError,
)
from .storage import PersistenceError, SQLiteStore
from .tools import PythonMathTool, ToolRegistry, ToolSpec

__all__ = [
    "AgentAdapter",
    "AgentDecision",
    "AgentResult",
    "FakeAgentAdapter",
    "GraphDependencyError",
    "LangGraphExecutionLoop",
    "LoopBudget",
    "OFFICIAL_PROFILE",
    "ProfileBoundaryError",
    "PersistenceError",
    "RunNotFoundError",
    "RunRequest",
    "RunService",
    "RunValidationError",
    "SHOWCASE_PROFILE",
    "SQLiteStore",
    "ToolExecutionResult",
    "ToolRegistry",
    "ToolSpec",
    "PythonMathTool",
]
