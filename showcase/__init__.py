"""Product-side entry points for the explicit ``showcase_mvp`` profile.

The package is intentionally separate from the root ``user_agent`` module.
Importing the official profile therefore never loads this package or its
future product-only dependencies.
"""

from .adapters import (
    AdapterError,
    DeepAgentsAdapter,
    InternAgentAdapter,
    InternChatModel,
    InternModelAdapter,
    ModelResponse,
    ToolRequest,
)
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
from .vision import ImageAsset, VisionAdapter, VisionInputError, VisionResult

__all__ = [
    "AgentAdapter",
    "AgentDecision",
    "AdapterError",
    "AgentResult",
    "FakeAgentAdapter",
    "GraphDependencyError",
    "DeepAgentsAdapter",
    "InternAgentAdapter",
    "InternChatModel",
    "InternModelAdapter",
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
    "ToolRequest",
    "ModelResponse",
    "ToolRegistry",
    "ToolSpec",
    "PythonMathTool",
    "ImageAsset",
    "VisionAdapter",
    "VisionInputError",
    "VisionResult",
]
