"""三阶段 ResearchPipeline：lit_review → plan → experiment → paper + 四个检查点。

每个 phase handler 是零参数 callable，由 build_research_pipeline 工厂注入依赖后返回。
各阶段 agent 通过 extra_tools 注入对应"提交工具"，强制结构化输出。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from ..agents.base import AgentTask, RoleAgent
from ..harness.blackboard import Blackboard
from ..harness.enums import RoleName
from ..harness.messagebus import MessageBus, approve_on_intent
from ..harness.models import (
    Artifact,
    ExperimentPlan,
    LitEntry,
    LitReview,
)
from ..harness.sandbox import SandboxManager
from ..harness.solver.mle import MLESolver
from ..harness.solver.paper import PaperSolver
from ..harness.tools.submission import (
    make_submit_code_tool,
    make_submit_lit_entries_tool,
    make_submit_paper_tool,
    make_submit_plan_tool,
    make_submit_review_tool,
)
from .pipeline import Node, StateGraph

log = logging.getLogger(__name__)


def build_research_pipeline(
    *,
    phd: RoleAgent,
    postdoc: RoleAgent,
    ml_engineer: RoleAgent,
    reviewer: RoleAgent,
    sandbox: SandboxManager,
    blackboard: Blackboard,
    bus: MessageBus,
    idea: str = "",
) -> StateGraph:
    """返回三阶段四检查点的 StateGraph，handler 已完全注入依赖。"""
    return StateGraph([
        Node("lit_review", handler=_lit_review_handler(phd, blackboard, idea)),
        Node("cp1", is_checkpoint=True),
        Node("plan", handler=_plan_handler(phd, postdoc, bus, blackboard, idea)),
        Node("cp2", is_checkpoint=True),
        Node("experiment", handler=_experiment_handler(
            ml_engineer, sandbox, blackboard, idea
        )),
        Node("cp3", is_checkpoint=True),
        Node("paper", handler=_paper_handler(phd, reviewer, blackboard, idea)),
        Node("cp4", is_checkpoint=True),
    ])


# ─── phase handlers ───────────────────────────────────────────────────────────


def _lit_review_handler(
    phd: RoleAgent, bb: Blackboard, idea: str
) -> Callable[[], None]:
    def _run() -> None:
        # 注入提交工具，强制 agent 返回结构化文献列表
        phd_with_tool = _with_extra_tools(phd, [make_submit_lit_entries_tool()])
        result = phd_with_tool.run(AgentTask(
            goal=(
                f"Search and summarize relevant academic papers for: {idea}\n\n"
                "Find 3-5 highly relevant papers. For each paper provide: "
                "arxiv_id, title, summary (2-3 sentences), "
                "relevance score (0.0-1.0), citation_key.\n"
                "You MUST call the submit_lit_entries tool to submit your findings."
            ),
        ))
        entries: list[LitEntry] = []
        raw_entries = result.output.get("entries") if result.output else []
        if isinstance(raw_entries, list):
            for e in raw_entries[:10]:
                if isinstance(e, dict):
                    try:
                        entries.append(LitEntry.model_validate(e))
                    except Exception:
                        pass

        log.info("[lit_review] parsed %d entries", len(entries))
        art = Artifact(
            id="lit_review.main",
            created_by=RoleName.PHD,
            payload=LitReview(entries=entries),
        )
        version = (
            bb.history("lit_review.main")[-1] if bb.exists("lit_review.main") else 0
        )
        bb.set(art, expected_version=version)

    return _run


def _plan_handler(
    phd: RoleAgent, postdoc: RoleAgent, bus: MessageBus, bb: Blackboard, idea: str
) -> Callable[[], None]:
    def _run() -> None:
        # PhD 在 dialogue 结束后提交计划
        phd_with_tool = _with_extra_tools(phd, [make_submit_plan_tool()])

        # 先做计划磋商（最多8轮）
        transcript = bus.dialogue(
            [phd_with_tool, postdoc],
            topic=f"experiment plan for: {idea}",
            max_turns=8,
            converge_fn=approve_on_intent,
        )

        # 让 PhD 提交最终计划
        context: dict[str, object] = {
            "idea": idea,
            "dialogue_summary": [
                {"role": str(m.from_role), "intent": str(m.intent)}
                for m in transcript.messages[-4:]
            ],
        }
        result = phd_with_tool.run(AgentTask(
            goal=(
                f"Based on the experiment plan discussion, submit the finalized plan "
                f"for: {idea}\n"
                "You MUST call the submit_plan tool with hypotheses, methodology, "
                "metrics, and success_criteria."
            ),
            context=context,
        ))

        plan_data = result.output
        if plan_data:
            try:
                plan_art = Artifact(
                    id="plan.main",
                    created_by=RoleName.PHD,
                    payload=ExperimentPlan(
                        hypotheses=plan_data.get("hypotheses", []),
                        methodology=str(plan_data.get("methodology", "")),
                        metrics=plan_data.get("metrics", []),
                        success_criteria=str(plan_data.get("success_criteria", "")),
                    ),
                )
                version = bb.history("plan.main")[-1] if bb.exists("plan.main") else 0
                bb.set(plan_art, expected_version=version)
                log.info("[plan] saved ExperimentPlan to blackboard")
            except Exception as exc:
                log.warning("[plan] failed to save plan: %s", exc)

    return _run


def _experiment_handler(
    ml_engineer: RoleAgent, sandbox: SandboxManager, bb: Blackboard, idea: str
) -> Callable[[], None]:
    def _run() -> None:
        # 从 Blackboard 读取计划作为上下文
        plan_context = ""
        if bb.exists("plan.main"):
            plan = bb.get("plan.main")
            plan_context = (
                f"\nExperiment plan:\n{plan.payload.model_dump_json(indent=2)}"
            )

        # 注入提交工具
        eng_with_tool = _with_extra_tools(ml_engineer, [make_submit_code_tool()])

        # 构造初始 baseline 代码，包含研究背景
        initial_code = (
            f"# Research idea: {idea}\n"
            "# TODO: implement actual experiment\n"
            "# The code MUST print {\"score\": <float>} on the last line\n"
            "import json\n"
            "score = 0.0  # replace with actual metric\n"
            "print(json.dumps({'score': score}))\n"
        )

        solver = MLESolver(
            eng_with_tool, sandbox, bb,
            max_iters=5, score_threshold=0.8,
        )
        # 在 solver goal 里注入 idea 和 plan
        solver._propose_goal = (  # type: ignore[attr-defined]
            f"Improve ML experiment code for: {idea}.{plan_context}\n"
            "Write complete Python code that trains/evaluates a model and prints "
            '{"score": <float>} on the last line. '
            "You MUST call the submit_code tool with your improved code."
        )
        result = solver.solve(initial_code)
        log.info(
            "[experiment] solver finished: iters=%d converged=%s score=%s",
            result.iters, result.converged, result.best_score,
        )

    return _run


def _paper_handler(
    phd: RoleAgent, reviewer: RoleAgent, bb: Blackboard, idea: str
) -> Callable[[], None]:
    def _run() -> None:
        # 从 Blackboard 收集上下文
        context_parts: list[str] = [f"Research idea: {idea}"]
        if bb.exists("lit_review.main"):
            lit = bb.get("lit_review.main")
            context_parts.append(
                f"Literature review:\n{lit.payload.model_dump_json(indent=2)}"
            )
        if bb.exists("plan.main"):
            plan = bb.get("plan.main")
            context_parts.append(
                f"Experiment plan:\n{plan.payload.model_dump_json(indent=2)}"
            )
        if bb.exists("runs.history"):
            runs = bb.get("runs.history")
            # 只取最后3条记录避免 context 太长
            records = runs.payload.records[-3:]  # type: ignore[union-attr]
            context_parts.append(
                "Experiment results:\n"
                + json.dumps([r.model_dump() for r in records], indent=2)
            )
        if bb.exists("code.main"):
            code_art = bb.get("code.main")
            files = code_art.payload.files  # type: ignore[union-attr]
            main_code = files.get("main.py", "")[:2000]
            context_parts.append(f"Final experiment code:\n```python\n{main_code}\n```")

        full_context = "\n\n".join(context_parts)

        # 注入提交工具
        phd_with_tool = _with_extra_tools(phd, [make_submit_paper_tool()])
        reviewer_with_tool = _with_extra_tools(reviewer, [make_submit_review_tool()])

        initial_latex = (
            "\\documentclass{article}\n"
            "\\usepackage[utf8]{inputenc}\n"
            "\\usepackage{amsmath}\n"
            "\\usepackage{booktabs}\n\n"
            "\\begin{document}\n\n"
            "\\section{Introduction}\n"
            f"% Research idea: {idea}\n"
            "\\section{Methodology}\n"
            "\\section{Experiments}\n"
            "\\section{Conclusion}\n\n"
            "\\end{document}"
        )

        solver = PaperSolver(
            phd_with_tool, reviewer_with_tool, bb,
            max_iters=3, score_threshold=0.75,
        )
        solver._propose_goal = (  # type: ignore[attr-defined]
            f"Write a complete LaTeX paper for: {idea}\n\n"
            f"{full_context}\n\n"
            "Write sections: abstract, introduction, methodology, experiments, "
            "conclusion, and references. Use proper LaTeX formatting. "
            "You MUST call the submit_paper tool with a 'sections' dict "
            "(keys: abstract, introduction, methodology, experiments, conclusion) "
            "and 'bib_refs' list."
        )
        solver._evaluate_goal = (  # type: ignore[attr-defined]
            "Review this paper draft carefully. Score it on quality, clarity, "
            "originality, and significance (each 0.0-1.0). Provide detailed comments. "
            "You MUST call the submit_review tool with your scores."
        )
        result = solver.solve(initial_latex)
        log.info(
            "[paper] solver finished: iters=%d converged=%s score=%s",
            result.iters, result.converged, result.best_score,
        )

    return _run


# ─── helpers ──────────────────────────────────────────────────────────────────


def _with_extra_tools(
    agent: RoleAgent, extra: list[Any]
) -> RoleAgent:
    """返回带有额外工具的新 RoleAgent 实例（不修改原 agent）。"""
    from ..agents.base import RoleAgent as _RoleAgent
    combined = list(agent._extra_tools) + list(extra)
    return _RoleAgent(
        agent.role,
        agent._sdk,
        registry=agent._registry,
        settings=agent._settings,
        system_prompt=agent.system_prompt,
        extra_tools=combined,
    )
