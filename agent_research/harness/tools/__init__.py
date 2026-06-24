"""工具注册与按角色授权。"""

from .builtin import bootstrap_registry
from .registry import (
    ToolAuthorizationError,
    ToolRegistry,
    ToolRegistryError,
    ToolSpec,
    ToolValidationError,
    make_run_code_tool,
)
from .submission import (
    make_submit_code_tool,
    make_submit_lit_entries_tool,
    make_submit_paper_tool,
    make_submit_plan_tool,
    make_submit_review_tool,
)

__all__ = [
    "ToolAuthorizationError",
    "ToolRegistry",
    "ToolRegistryError",
    "ToolSpec",
    "ToolValidationError",
    "bootstrap_registry",
    "make_run_code_tool",
    "make_submit_code_tool",
    "make_submit_lit_entries_tool",
    "make_submit_paper_tool",
    "make_submit_plan_tool",
    "make_submit_review_tool",
]
