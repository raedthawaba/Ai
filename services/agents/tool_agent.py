from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base_agent import AgentContext, AgentResult, AgentStep, BaseAgent

logger = logging.getLogger(__name__)

_TOOL_SELECT_PROMPT = """You are an AI that selects the right tool for a task.
Available tools: {tools}
Task: {task}
Output JSON: {{"tool": "tool_name", "args": {{"key": "value"}}}}
JSON:"""


class ToolAgent(BaseAgent):
    """LLM-driven agent that autonomously selects and calls tools."""

    def __init__(self, llm: Optional[Any] = None, **kwargs: Any) -> None:
        super().__init__(name="tool", description="Autonomous tool-calling agent", llm=llm, **kwargs)

    async def _execute(self, context: AgentContext) -> AgentResult:
        steps: List[AgentStep] = []
        accumulated_output: List[str] = []

        while not context.is_exhausted():
            context.iterations += 1
            tool_name, args = await self._select_tool(context.goal, context)

            if tool_name is None or tool_name == "finish":
                break

            step = await self._run_tool(tool_name, args, context)
            steps.append(step)
            context.tool_results.append(step.to_dict() if hasattr(step, "to_dict") else {"result": step.result})

            if step.result:
                accumulated_output.append(str(step.result))

            if step.error:
                break

        output = "\n".join(accumulated_output) if accumulated_output else f"Completed: {context.goal}"
        return AgentResult(success=True, output=output, steps=steps, context=context)

    async def _select_tool(
        self, task: str, context: AgentContext
    ) -> Tuple[Optional[str], Dict]:
        if not self._tools:
            return None, {}

        if self._llm is not None:
            try:
                from core.inference_engine import InferenceConfig
                tools_desc = json.dumps(
                    {k: v.get("description", "") for k, v in self._tools.items()}
                )
                prompt = _TOOL_SELECT_PROMPT.format(tools=tools_desc, task=task)
                text = await self._llm.agenerate(
                    prompt, config=InferenceConfig(max_new_tokens=128, temperature=0.1)
                )
                parsed = json.loads(text.strip())
                return parsed.get("tool"), parsed.get("args", {})
            except Exception as exc:
                logger.debug("LLM tool selection failed: %s", exc)

        first_tool = next(iter(self._tools))
        return first_tool, {}

    async def _run_tool(
        self, tool_name: str, args: Dict, context: AgentContext
    ) -> AgentStep:
        try:
            result = await self._call_tool(tool_name, **args)
            return AgentStep(
                action=f"call_tool:{tool_name}",
                tool_used=tool_name,
                tool_args=args,
                result=result,
                observation=f"Tool '{tool_name}' returned successfully",
            )
        except Exception as exc:
            logger.error("Tool '%s' failed: %s", tool_name, exc)
            return AgentStep(
                action=f"call_tool:{tool_name}",
                tool_used=tool_name,
                tool_args=args,
                error=str(exc),
                observation=f"Tool '{tool_name}' failed",
            )
