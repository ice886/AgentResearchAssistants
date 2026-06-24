"""AnthropicSDKClient：SDKAgentClient 协议的真实实现，接 anthropic Python SDK。

职责：
- 将 SDKInvocation（role/model/system/tools/task）翻译为 anthropic.messages.create 调用
- 处理 tool_use 循环直到 end_turn（最多 max_tool_iters 轮）
- 将 SDK 响应规范化为 AgentResult
- API key 从 Settings 读取（SecretStr，不写入日志）
"""

from __future__ import annotations

import json
from typing import Any

import anthropic

from ..agents.base import AgentResult, AgentTask, SDKInvocation
from ..config import Settings, get_settings


class AnthropicSDKClient:
    """调用真实 Claude API 的 SDKAgentClient 实现。"""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        max_tool_iters: int = 5,
    ) -> None:
        self._settings = settings or get_settings()
        self.max_tool_iters = max_tool_iters
        self._client: anthropic.Anthropic | None = None

    def run(self, invocation: SDKInvocation) -> AgentResult:
        client = self._get_client()
        tools = _build_tool_defs(invocation)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": _build_user_content(invocation.task)}
        ]

        # 中转站通常不支持 thinking 参数，原生 Anthropic API 才支持
        use_thinking = self._settings.anthropic_base_url is None

        # 跨轮次记录最后一次工具调用的 input（tool_use 发生在中间轮，end_turn 在最后轮）
        last_tool_input: dict[str, Any] = {}
        last_tool_name: str = ""

        for _ in range(self.max_tool_iters + 1):
            kwargs: dict[str, Any] = {
                "model": invocation.model,
                "max_tokens": 8192,
                "system": invocation.system_prompt,
                "messages": messages,
            }
            if use_thinking:
                kwargs["thinking"] = {"type": "adaptive"}
            if tools:
                kwargs["tools"] = tools

            with client.messages.stream(**kwargs) as stream:
                response = stream.get_final_message()

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason == "tool_use":
                # 记录这轮的 tool_use input（可能被 end_turn 轮覆盖，保留最后一次）
                for block in response.content:
                    if block.type == "tool_use":
                        last_tool_input = dict(block.input) if block.input else {}
                        last_tool_name = block.name
                tool_results = _execute_tools(response, invocation)
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                break

        return _to_agent_result(response, last_tool_input, last_tool_name)

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            key = self._settings.anthropic_api_key
            api_key = key.get_secret_value() if key else None
            base_url = self._settings.anthropic_base_url
            if base_url:
                self._client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
            else:
                self._client = anthropic.Anthropic(api_key=api_key)
        return self._client


def _build_tool_defs(invocation: SDKInvocation) -> list[dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": dict(t.input_schema) if t.input_schema else {
                "type": "object"
            },
        }
        for t in invocation.tools
    ]


def _build_user_content(task: AgentTask) -> str:
    parts = [task.goal]
    if task.instructions:
        parts.append(task.instructions)
    if task.context:
        parts.append(
            f"Context:\n{json.dumps(dict(task.context), ensure_ascii=False, indent=2)}"
        )
    if task.input_refs:
        parts.append(f"Input refs: {task.input_refs}")
    return "\n\n".join(parts)


def _execute_tools(
    response: anthropic.types.Message,
    invocation: SDKInvocation,
) -> list[dict[str, Any]]:
    tool_map = {t.name: t for t in invocation.tools}
    results: list[dict[str, Any]] = []
    for block in response.content:
        if block.type != "tool_use":
            continue
        tool = tool_map.get(block.name)
        if tool is None:
            content = f"Error: unknown tool {block.name!r}"
            is_error = True
        else:
            try:
                raw = tool.handler(block.input)
                content = json.dumps(raw) if not isinstance(raw, str) else raw
                is_error = False
            except Exception as exc:
                content = f"Error: {exc}"
                is_error = True
        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": content,
            "is_error": is_error,
        })
    return results


def _to_agent_result(
    response: anthropic.types.Message,
    last_tool_input: dict[str, Any] | None = None,
    last_tool_name: str = "",
) -> AgentResult:
    text_parts: list[str] = []
    tool_calls: list[str] = []
    final_tool_input: dict[str, Any] = {}

    # 先看最后一轮 response 里有没有 tool_use（有些 model 在 end_turn 前还会调工具）
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(block.name)
            final_tool_input = dict(block.input) if block.input else {}

    content = "\n".join(text_parts)

    # 优先用跨轮次捕获的 tool_input（关键修复：tool_use 在中间轮，end_turn 在最后轮）
    accumulated_tool_input = last_tool_input or {}
    if accumulated_tool_input and not final_tool_input:
        final_tool_input = accumulated_tool_input
        if last_tool_name and last_tool_name not in tool_calls:
            tool_calls.append(last_tool_name)

    # 确定 output：工具输入 > 文本 JSON > 空
    if final_tool_input:
        output = final_tool_input
    elif content.strip().startswith("{"):
        try:
            output = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            output = {}
    else:
        output = {}

    return AgentResult(
        content=content,
        output=output,
        tool_calls=tool_calls,
        raw=response,
    )
