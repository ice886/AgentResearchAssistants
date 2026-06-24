"""内置工具：按角色注册 run_code 与 retrieve_papers 到 ToolRegistry。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..enums import RoleName
from ..sandbox import SandboxManager
from .arxiv import search_arxiv
from .registry import (
    ToolRegistry,
    ToolSpec,
    make_run_code_tool,
)

_RUN_CODE_ROLES = frozenset({RoleName.ML_ENGINEER, RoleName.SW_ENGINEER})
_RETRIEVE_ROLES = frozenset({RoleName.PHD, RoleName.POSTDOC, RoleName.PROFESSOR})


def bootstrap_registry(sandbox: SandboxManager) -> ToolRegistry:
    """构建并返回预注册内置工具的 ToolRegistry。"""
    registry = ToolRegistry()
    registry.register(make_run_code_tool(sandbox), allowed_roles=_RUN_CODE_ROLES)
    registry.register(_make_retrieve_papers_tool(), allowed_roles=_RETRIEVE_ROLES)
    return registry


def _make_retrieve_papers_tool() -> ToolSpec:
    def _handler(payload: Mapping[str, Any]) -> Any:
        query = str(payload.get("query", ""))
        max_results = int(payload.get("max_results", 5))
        entries = search_arxiv(query, max_results=max_results)
        return [e.model_dump() for e in entries]

    return ToolSpec(
        name="retrieve_papers",
        description="通过 arXiv 检索相关论文，返回文献条目列表。",
        handler=_handler,
        input_schema={
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "检索关键词"},
                "max_results": {"type": "integer", "default": 5},
            },
        },
        metadata={"category": "retrieval"},
    )
