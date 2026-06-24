"""RoleAgent 单测：模型选择、prompt、工具白名单与 SDK adapter 调用。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from agent_research.agents import AgentResult, AgentTask, RoleAgent, SDKInvocation
from agent_research.config import ModelConfig, Settings
from agent_research.harness.enums import RoleName
from agent_research.harness.tools import ToolRegistry, ToolSpec


class FakeSDK:
    def __init__(self, result: AgentResult | Mapping[str, Any] | None = None) -> None:
        self.invocations: list[SDKInvocation] = []
        self.result = result or AgentResult(content="ok", output={"done": True})

    def run(self, invocation: SDKInvocation) -> AgentResult | Mapping[str, Any]:
        self.invocations.append(invocation)
        return self.result


def _noop(_payload: Mapping[str, Any]) -> dict[str, bool]:
    return {"ok": True}


def test_role_agent_injects_role_model_prompt_and_authorized_tools():
    registry = ToolRegistry()
    registry.register(ToolSpec("lit_search", "search", _noop), {RoleName.PHD})
    registry.register(ToolSpec("run_code", "run", _noop), {RoleName.ML_ENGINEER})
    sdk = FakeSDK()
    settings = Settings(
        models=ModelConfig(
            default_model="claude-default",
            per_role={RoleName.PHD: "claude-phd"},
        )
    )
    agent = RoleAgent(RoleName.PHD, sdk, registry=registry, settings=settings)

    result = agent.run(AgentTask(goal="summarize papers", input_refs=["idea.main"]))

    assert result.output == {"done": True}
    assert agent.model == "claude-phd"
    assert agent.tool_names == ("lit_search",)
    invocation = sdk.invocations[0]
    assert invocation.role == RoleName.PHD
    assert invocation.model == "claude-phd"
    assert "PhD" in invocation.system_prompt
    assert "Blackboard" in invocation.system_prompt
    assert "run_code" in invocation.system_prompt
    assert [tool.name for tool in invocation.tools] == ["lit_search"]
    assert invocation.task.goal == "summarize papers"


def test_default_prompts_encode_role_specific_research_discipline():
    reviewer = RoleAgent(RoleName.REVIEWER, FakeSDK())
    ml_engineer = RoleAgent(RoleName.ML_ENGINEER, FakeSDK())

    assert "Quality" in reviewer.system_prompt
    assert "Originality" in reviewer.system_prompt
    assert "Confidence" in reviewer.system_prompt
    assert "SandboxManager" in ml_engineer.system_prompt
    assert "stdout/stderr" in ml_engineer.system_prompt


def test_role_agent_normalizes_mapping_result_from_sdk():
    sdk = FakeSDK({"content": "mapped", "output": {"x": 1}, "tool_calls": ["t"]})
    agent = RoleAgent(RoleName.REVIEWER, sdk, system_prompt="review prompt")

    result = agent.run(AgentTask(goal="review"))

    assert result.content == "mapped"
    assert result.output == {"x": 1}
    assert result.tool_calls == ["t"]
    assert sdk.invocations[0].system_prompt == "review prompt"


def test_role_agent_can_receive_extra_tools_for_adapter_specific_tools():
    tool = ToolSpec("sdk_native", "native", _noop)
    sdk = FakeSDK()
    agent = RoleAgent(RoleName.PROFESSOR, sdk, extra_tools=(tool,))

    agent.run(AgentTask(goal="advise"))

    assert agent.tool_names == ("sdk_native",)
    assert [t.name for t in sdk.invocations[0].tools] == ["sdk_native"]
