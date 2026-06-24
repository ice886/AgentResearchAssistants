"""CLI 入口：python -m agent_research run/resume。"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from typing import Any

from .config import get_settings
from .harness.blackboard import Blackboard
from .harness.budget import BudgetController
from .harness.checkpoint import CheckpointGate
from .harness.enums import RoleName, Verdict
from .harness.messagebus import MessageBus
from .harness.models import CodeArtifact, Decision, PaperDraft
from .harness.orchestrator import Orchestrator
from .harness.sandbox import SandboxManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent_research")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="开始一次新的研究实验")
    run_p.add_argument("--idea", required=True, help="研究想法描述")
    run_p.add_argument("--run-id", default=None, help="指定 run_id（默认自动生成）")
    run_p.add_argument("--auto", action="store_true", help="全自动模式（跳过检查点）")

    resume_p = sub.add_parser("resume", help="从已有 run_id 恢复")
    resume_p.add_argument("--run-id", required=True)
    resume_p.add_argument("--auto", action="store_true")

    args = parser.parse_args()

    if args.cmd == "run":
        _cmd_run(args.idea, args.run_id, auto=args.auto)
    elif args.cmd == "resume":
        _cmd_resume(args.run_id, auto=args.auto)


def _cmd_run(idea: str, run_id: str | None, *, auto: bool) -> None:
    run_id = run_id or str(uuid.uuid4())[:8]
    settings = get_settings()
    paths = settings.run_paths(run_id)
    paths.ensure()
    log.info("run_id=%s  idea=%s", run_id, idea)

    bb = Blackboard(paths)
    _run_pipeline(bb, idea=idea, run_id=run_id, auto=auto)


def _cmd_resume(run_id: str, *, auto: bool) -> None:
    settings = get_settings()
    paths = settings.run_paths(run_id)
    if not paths.blackboard_json.exists():
        log.error("run_id=%s 不存在，请先用 run 命令创建", run_id)
        sys.exit(1)

    log.info("resume run_id=%s", run_id)
    bb = Blackboard.restore(paths)
    _run_pipeline(bb, idea="", run_id=run_id, auto=auto)


def _run_pipeline(
    bb: Blackboard, *, idea: str, run_id: str, auto: bool
) -> None:
    # lazy import 避免在无 API key 时也强制加载 anthropic
    from .agents.base import RoleAgent
    from .agents.sdk_adapter import AnthropicSDKClient
    from .harness.tools.builtin import bootstrap_registry
    from .workflow.nodes import build_research_pipeline

    settings = get_settings()
    sdk = AnthropicSDKClient(settings)
    sandbox = SandboxManager(settings)
    registry = bootstrap_registry(sandbox)

    def _agent(role: RoleName) -> RoleAgent:
        return RoleAgent(role, sdk, registry=registry, settings=settings)

    bus = MessageBus()
    budget = BudgetController(settings.limits.token_budget)

    graph = build_research_pipeline(
        phd=_agent(RoleName.PHD),
        postdoc=_agent(RoleName.POSTDOC),
        ml_engineer=_agent(RoleName.ML_ENGINEER),
        reviewer=_agent(RoleName.REVIEWER),
        sandbox=sandbox,
        blackboard=bb,
        bus=bus,
        idea=idea,
    )

    if auto:
        gate = CheckpointGate(enabled=False)
    else:
        gate = CheckpointGate(enabled=True, decision_fn=_interactive_gate)

    orch = Orchestrator(bb, gate)
    result = orch.run(graph)

    paths = settings.run_paths(run_id)
    _save_budget(budget, paths)
    _export_artifacts(bb, paths)

    if result.aborted:
        log.warning("运行被中止（REJECT 决议）")
    else:
        log.info(
            "完成 run_id=%s  phases=%s  decisions=%d  budget_spent=%d",
            run_id,
            result.completed_nodes,
            len(result.decisions),
            budget.spent(),
        )


def _interactive_gate(checkpoint_id: str) -> Decision:
    print(f"\n=== 检查点: {checkpoint_id} ===")
    print("请输入决议 [approve/edit/reject]（直接回车 = approve）: ",
          end="", flush=True)
    choice = input().strip().lower()
    verdict_map = {
        "approve": Verdict.APPROVE,
        "edit": Verdict.APPROVE,
        "reject": Verdict.REJECT,
    }
    verdict = verdict_map.get(choice, Verdict.APPROVE)
    note = None
    if verdict == Verdict.APPROVE and choice == "edit":
        note = input("备注（可选）: ").strip() or None
    return Decision(checkpoint_id=checkpoint_id, verdict=verdict, human_note=note)


def _save_budget(budget: BudgetController, paths: Any) -> None:
    try:
        paths.budget_json.write_text(
            json.dumps(budget.report().model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _export_artifacts(bb: Blackboard, paths: Any) -> None:
    """把 Blackboard 里的文件制品导出到 runs/<run_id>/ 子目录。"""
    try:
        if bb.exists("code.main"):
            paths.code_dir.mkdir(exist_ok=True)
            art = bb.get("code.main")
            assert isinstance(art.payload, CodeArtifact)
            for fname, content in art.payload.files.items():
                (paths.code_dir / fname).write_text(content, encoding="utf-8")
            log.info("exported code.main → %s", paths.code_dir)
    except Exception as exc:
        log.warning("export code failed: %s", exc)

    try:
        if bb.exists("paper.main"):
            paths.paper_dir.mkdir(exist_ok=True)
            art = bb.get("paper.main")
            assert isinstance(art.payload, PaperDraft)
            for k, v in art.payload.sections.items():
                (paths.paper_dir / f"{k}.tex").write_text(v, encoding="utf-8")
            log.info("exported paper.main → %s", paths.paper_dir)
    except Exception as exc:
        log.warning("export paper failed: %s", exc)


if __name__ == "__main__":
    main()
