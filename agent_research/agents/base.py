"""RoleAgent：角色化 SDK subagent 的轻量封装。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from agent_research.config import Settings, get_settings
from agent_research.harness.enums import RoleName
from agent_research.harness.tools import ToolRegistry, ToolSpec

from .prompts import prompt_for


class AgentTask(BaseModel):
    """交给 RoleAgent 的结构化任务。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    goal: str
    input_refs: list[str] = Field(default_factory=list)
    context: Mapping[str, Any] = Field(default_factory=dict)
    output_schema: Mapping[str, Any] | None = None
    instructions: str | None = None


class AgentResult(BaseModel):
    """RoleAgent 返回的结构化结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    output: Mapping[str, Any] = Field(default_factory=dict)
    tool_calls: list[str] = Field(default_factory=list)
    raw: Any = None


@dataclass(frozen=True)
class SDKInvocation:
    """传给底层 SDK adapter 的完整 subagent 调用请求。"""

    role: RoleName
    model: str
    system_prompt: str
    tools: tuple[ToolSpec, ...]
    task: AgentTask


@runtime_checkable
class SDKAgentClient(Protocol):
    """Claude Agent SDK adapter 的最小协议。"""

    def run(self, invocation: SDKInvocation) -> AgentResult | Mapping[str, Any]:
        """执行一次角色化 subagent 调用。"""


class RoleAgent:
    """按角色绑定 prompt、模型与工具白名单的 SDK subagent 封装。"""

    def __init__(
        self,
        role: RoleName,
        sdk: SDKAgentClient,
        *,
        registry: ToolRegistry | None = None,
        settings: Settings | None = None,
        system_prompt: str | None = None,
        extra_tools: Sequence[ToolSpec] = (),
    ) -> None:
        self.role = role
        self._sdk = sdk
        self._registry = registry or ToolRegistry()
        self._settings = settings or get_settings()
        self.system_prompt = system_prompt or prompt_for(role)
        self._extra_tools = tuple(extra_tools)

    @property
    def model(self) -> str:
        return self._settings.models.for_role(self.role)

    @property
    def tools(self) -> tuple[ToolSpec, ...]:
        return (*self._registry.tools_for(self.role), *self._extra_tools)

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(tool.name for tool in self.tools)

    def run(self, task: AgentTask) -> AgentResult:
        """执行任务，并把 SDK adapter 输出规范化为 AgentResult。"""
        invocation = SDKInvocation(
            role=self.role,
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            task=task,
        )
        result = self._sdk.run(invocation)
        if isinstance(result, AgentResult):
            return result
        return AgentResult.model_validate(result)
