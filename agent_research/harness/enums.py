"""系统级枚举。

抽出供 ``models`` 与 ``config`` 共用，避免 ``config`` 反向依赖较重的 schema 模块。
全部为 ``str, Enum``，序列化为字符串值，便于 JSON 往返与外部可读。
"""

from __future__ import annotations

from enum import StrEnum


class RoleName(StrEnum):
    """对标论文角色的 agent 角色名。"""

    PROFESSOR = "Professor"
    POSTDOC = "Postdoc"
    PHD = "PhD"
    ML_ENGINEER = "MLEngineer"
    SW_ENGINEER = "SWEngineer"
    REVIEWER = "Reviewer"


class Namespace(StrEnum):
    """Blackboard 制品命名空间（artifact id 的前缀）。"""

    IDEA = "idea"
    LIT_REVIEW = "lit_review"
    PLAN = "plan"
    DATASET = "dataset"
    CODE = "code"
    RUNS = "runs"
    FIGURES = "figures"
    PAPER = "paper"
    REVIEWS = "reviews"
    DECISIONS = "decisions"


class Intent(StrEnum):
    """MessageBus 消息意图。"""

    PROPOSE = "propose"
    CRITIQUE = "critique"
    APPROVE = "approve"
    REQUEST_REVISION = "request_revision"
    HANDOFF = "handoff"
    REPORT = "report"


class Verdict(StrEnum):
    """检查点人工决议。"""

    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"


class RunStatus(StrEnum):
    """单次实验运行状态。"""

    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    OOM = "oom"
