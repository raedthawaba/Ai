from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    goal: str = ""
    memory: Dict[str, Any] = field(default_factory=dict)
    tool_results: List[Dict] = field(default_factory=list)
    iterations: int = 0
    max_iterations: int = 10
    start_time: float = field(default_factory=time.time)

    def is_exhausted(self) -> bool:
        return self.iterations >= self.max_iterations

    def elapsed(self) -> float:
        return time.time() - self.start_time


@dataclass
class AgentStep:
    step_id: str = field(default_factory=lambda: str(uuid4()))
    action: str = ""
    observation: str = ""
    tool_used: Optional[str] = None
    tool_args: Dict = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class AgentResult:
    success: bool
    output: str
    steps: List[AgentStep] = field(default_factory=list)
    context: Optional[AgentContext] = None
    error: Optional[str] = None
    total_duration_ms: float = 0.0


class BaseAgent(ABC):
    """Abstract base class for all agent types."""

    def __init__(
        self,
        name: str,
        description: str = "",
        max_iterations: int = 10,
        llm: Optional[Any] = None,
    ) -> None:
        self.name = name
        self.description = description
        self.max_iterations = max_iterations
        self._llm = llm
        self._tools: Dict[str, Any] = {}
        logger.info("Agent '%s' initialized", name)

    def register_tool(self, name: str, fn: Any, description: str = "") -> None:
        self._tools[name] = {"fn": fn, "description": description}
        logger.debug("Tool registered: %s on agent %s", name, self.name)

    async def run(self, goal: str, context: Optional[AgentContext] = None) -> AgentResult:
        ctx = context or AgentContext(goal=goal, max_iterations=self.max_iterations)
        start = time.perf_counter()
        try:
            result = await self._execute(ctx)
            result.total_duration_ms = round((time.perf_counter() - start) * 1000, 2)
            return result
        except Exception as exc:
            logger.error("Agent '%s' error: %s", self.name, exc)
            return AgentResult(
                success=False,
                output="",
                error=str(exc),
                total_duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )

    @abstractmethod
    async def _execute(self, context: AgentContext) -> AgentResult:
        """Implement agent logic here."""

    async def _call_tool(self, name: str, **kwargs: Any) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError(f"Tool '{name}' not found on agent '{self.name}'")
        fn = tool["fn"]
        if asyncio.iscoroutinefunction(fn):
            return await fn(**kwargs)
        return fn(**kwargs)

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
