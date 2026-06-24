"""提交类工具：agent 调用这些工具来强制提交结构化输出。

handler 把 input dict 原样返回，sdk_adapter 捕获 tool_use.input 作为 output。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .registry import ToolSpec


def make_submit_code_tool() -> ToolSpec:
    """ML Engineer 提交改进后的实验代码。"""

    def _handler(payload: Mapping[str, Any]) -> Any:
        return dict(payload)

    return ToolSpec(
        name="submit_code",
        description=(
            "Submit improved ML experiment code. "
            "Call this when you have written better code to improve the score metric. "
            "The code must print a JSON line {\"score\": <float>} at the end of stdout."
        ),
        handler=_handler,
        input_schema={
            "type": "object",
            "required": ["code"],
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Complete Python code. "
                        "Must print {\"score\": <float>} on the last line."
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what changed and why.",
                },
            },
        },
        metadata={"category": "submission"},
    )


def make_submit_review_tool() -> ToolSpec:
    """Reviewer 提交论文评分。"""

    def _handler(payload: Mapping[str, Any]) -> Any:
        dims = {
            "quality": float(payload.get("quality", 0.0)),
            "clarity": float(payload.get("clarity", 0.0)),
            "originality": float(payload.get("originality", 0.0)),
            "significance": float(payload.get("significance", 0.0)),
        }
        return {"dims": dims, "comments": str(payload.get("comments", ""))}

    return ToolSpec(
        name="submit_review",
        description=(
            "Submit your structured review scores for the paper draft. "
            "Rate each dimension 0.0–1.0. Call this after reading the paper."
        ),
        handler=_handler,
        input_schema={
            "type": "object",
            "required": ["quality", "clarity", "originality", "significance"],
            "properties": {
                "quality": {
                    "type": "number",
                    "description": "Technical correctness and soundness (0.0–1.0)",
                },
                "clarity": {
                    "type": "number",
                    "description": "Writing clarity and organization (0.0–1.0)",
                },
                "originality": {
                    "type": "number",
                    "description": "Novelty of contribution (0.0–1.0)",
                },
                "significance": {
                    "type": "number",
                    "description": "Impact and importance (0.0–1.0)",
                },
                "comments": {
                    "type": "string",
                    "description": "Detailed review comments and suggestions.",
                },
            },
        },
        metadata={"category": "submission"},
    )


def make_submit_lit_entries_tool() -> ToolSpec:
    """PhD 提交文献综述条目。"""

    def _handler(payload: Mapping[str, Any]) -> Any:
        return dict(payload)

    return ToolSpec(
        name="submit_lit_entries",
        description=(
            "Submit the list of relevant papers found for the literature review. "
            "Call this after searching and reading relevant papers."
        ),
        handler=_handler,
        input_schema={
            "type": "object",
            "required": ["entries"],
            "properties": {
                "entries": {
                    "type": "array",
                    "description": "List of paper entries.",
                    "items": {
                        "type": "object",
                        "required": [
                            "arxiv_id", "title", "summary",
                            "relevance", "citation_key",
                        ],
                        "properties": {
                            "arxiv_id": {"type": "string"},
                            "title": {"type": "string"},
                            "summary": {"type": "string"},
                            "relevance": {
                                "type": "number",
                                "description": "Relevance score 0.0–1.0",
                            },
                            "citation_key": {"type": "string"},
                        },
                    },
                },
            },
        },
        metadata={"category": "submission"},
    )


def make_submit_plan_tool() -> ToolSpec:
    """PhD 提交实验计划。"""

    def _handler(payload: Mapping[str, Any]) -> Any:
        return dict(payload)

    return ToolSpec(
        name="submit_plan",
        description=(
            "Submit the finalized experiment plan. "
            "Call this when the plan has converged and is ready to execute."
        ),
        handler=_handler,
        input_schema={
            "type": "object",
            "required": ["hypotheses", "methodology", "metrics", "success_criteria"],
            "properties": {
                "hypotheses": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of research hypotheses to test.",
                },
                "methodology": {
                    "type": "string",
                    "description": "Experimental methodology description.",
                },
                "metrics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Evaluation metrics to use.",
                },
                "success_criteria": {
                    "type": "string",
                    "description": "What constitutes a successful experiment.",
                },
            },
        },
        metadata={"category": "submission"},
    )


def make_submit_paper_tool() -> ToolSpec:
    """PhD/Author 提交论文草稿各节。"""

    def _handler(payload: Mapping[str, Any]) -> Any:
        return dict(payload)

    return ToolSpec(
        name="submit_paper",
        description=(
            "Submit the complete LaTeX paper draft with all sections. "
            "Call this when you have written the full paper."
        ),
        handler=_handler,
        input_schema={
            "type": "object",
            "required": ["sections"],
            "properties": {
                "sections": {
                    "type": "object",
                    "description": (
                        "Dict of section_name -> LaTeX content. "
                        "Required keys: introduction, methodology, "
                        "experiments, conclusion. "
                        "Optional: abstract, related_work."
                    ),
                    "additionalProperties": {"type": "string"},
                },
                "bib_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Bibliography citation keys used.",
                },
            },
        },
        metadata={"category": "submission"},
    )
