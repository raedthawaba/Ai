"""Agent Service — Phase 5 — تنظيم الـ agents مع tool execution وmemory."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_TOOL = "waiting_tool"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ToolCall:
    tool_name: str
    arguments: Dict
    call_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class AgentStep:
    step_id: str
    thought: str
    action: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    observation: str = ""
    is_final: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentTrace:
    agent_id: str
    session_id: str
    query: str
    steps: List[AgentStep] = field(default_factory=list)
    final_answer: Optional[str] = None
    status: AgentStatus = AgentStatus.IDLE
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    total_tokens: int = 0

    @property
    def duration_ms(self) -> float:
        if self.finished_at:
            return round((self.finished_at - self.started_at) * 1000, 2)
        return round((time.time() - self.started_at) * 1000, 2)

    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "query": self.query,
            "status": self.status.value,
            "final_answer": self.final_answer,
            "steps": len(self.steps),
            "duration_ms": self.duration_ms,
        }


class ToolRegistry:
    """سجل الأدوات المتاحة للـ agents."""

    def __init__(self) -> None:
        self._tools: Dict[str, Callable] = {}
        self._descriptions: Dict[str, str] = {}

    def register(
        self,
        name: str,
        fn: Callable,
        description: str = "",
    ) -> None:
        self._tools[name] = fn
        self._descriptions[name] = description
        logger.debug("ToolRegistry: registered '%s'", name)

    def list_tools(self) -> List[Dict]:
        return [
            {"name": name, "description": desc}
            for name, desc in self._descriptions.items()
        ]

    async def execute(self, call: ToolCall) -> ToolCall:
        fn = self._tools.get(call.tool_name)
        if fn is None:
            call.error = f"أداة غير معروفة: {call.tool_name}"
            return call

        t0 = time.perf_counter()
        try:
            if asyncio.iscoroutinefunction(fn):
                call.result = await fn(**call.arguments)
            else:
                loop = asyncio.get_event_loop()
                call.result = await loop.run_in_executor(
                    None, lambda: fn(**call.arguments)
                )
        except Exception as exc:
            call.error = str(exc)
            logger.error("Tool '%s' failed: %s", call.tool_name, exc)
        finally:
            call.duration_ms = round((time.perf_counter() - t0) * 1000, 2)

        return call


class AgentMemory:
    """ذاكرة الـ agent — short-term + long-term."""

    def __init__(self, max_short_term: int = 20) -> None:
        self._short_term: List[Dict] = []
        self._long_term: Dict[str, Any] = {}
        self._max = max_short_term

    def add_message(self, role: str, content: str) -> None:
        self._short_term.append({"role": role, "content": content})
        if len(self._short_term) > self._max:
            self._short_term = self._short_term[-self._max:]

    def get_history(self) -> List[Dict]:
        return list(self._short_term)

    def store(self, key: str, value: Any) -> None:
        self._long_term[key] = value

    def recall(self, key: str) -> Optional[Any]:
        return self._long_term.get(key)

    def clear_short_term(self) -> None:
        self._short_term.clear()

    def summary(self) -> Dict:
        return {
            "short_term_messages": len(self._short_term),
            "long_term_keys": len(self._long_term),
        }


class AgentService:
    """
    خدمة الـ agent الرئيسية مع:
    - agent orchestration
    - tool execution framework
    - memory layer
    - async execution
    - failure isolation
    - state management
    - multi-turn support
    - tracing كامل
    - retry handling
    - cancellation support
    """

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        llm_manager: Optional[Any] = None,
        max_steps: int = 10,
        step_timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._tools = tool_registry or ToolRegistry()
        self._llm = llm_manager
        self._max_steps = max_steps
        self._step_timeout = step_timeout
        self._max_retries = max_retries
        self._active_agents: Dict[str, AgentTrace] = {}
        self._sessions: Dict[str, AgentMemory] = {}
        self._register_default_tools()
        logger.info("AgentService initialized: max_steps=%d", max_steps)

    def _register_default_tools(self) -> None:
        self._tools.register(
            "search",
            self._tool_search,
            "بحث عن معلومات في قاعدة البيانات",
        )
        self._tools.register(
            "summarize",
            self._tool_summarize,
            "تلخيص نص",
        )
        self._tools.register(
            "calculate",
            self._tool_calculate,
            "حساب تعبير رياضي",
        )

    # ─── Execution ────────────────────────────────────────────────────────────

    async def run(
        self,
        query: str,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> AgentTrace:
        """تشغيل agent كامل على استعلام."""
        agent_id = agent_id or str(uuid.uuid4())[:12]
        session_id = session_id or str(uuid.uuid4())[:12]

        trace = AgentTrace(
            agent_id=agent_id,
            session_id=session_id,
            query=query,
            status=AgentStatus.RUNNING,
        )
        self._active_agents[agent_id] = trace

        # استرجاع أو إنشاء memory للجلسة
        memory = self._sessions.setdefault(session_id, AgentMemory())
        memory.add_message("user", query)

        try:
            await self._execute_loop(trace, memory)
        except asyncio.CancelledError:
            trace.status = AgentStatus.CANCELLED
            logger.warning("Agent '%s' cancelled", agent_id)
        except Exception as exc:
            trace.status = AgentStatus.FAILED
            logger.error("Agent '%s' failed: %s", agent_id, exc)
        finally:
            trace.finished_at = time.time()
            self._active_agents.pop(agent_id, None)

        if trace.final_answer:
            memory.add_message("assistant", trace.final_answer)

        logger.info(
            "Agent '%s': status=%s steps=%d duration=%.0fms",
            agent_id, trace.status.value, len(trace.steps), trace.duration_ms,
        )
        return trace

    async def _execute_loop(
        self,
        trace: AgentTrace,
        memory: AgentMemory,
    ) -> None:
        for step_num in range(self._max_steps):
            step = AgentStep(step_id=f"step_{step_num + 1}", thought="")

            # بناء الـ prompt
            history = memory.get_history()
            tools = self._tools.list_tools()
            thought = await self._think(trace.query, history, tools, step_num)
            step.thought = thought

            # تحليل الـ action
            tool_calls = self._parse_tool_calls(thought)
            if tool_calls:
                step.action = tool_calls[0].tool_name
                trace.status = AgentStatus.WAITING_TOOL

                # تنفيذ الأدوات
                for call in tool_calls:
                    try:
                        executed = await asyncio.wait_for(
                            self._tools.execute(call),
                            timeout=self._step_timeout,
                        )
                        step.tool_calls.append(executed)
                        step.observation += f"[{call.tool_name}]: {executed.result or executed.error}\n"
                    except asyncio.TimeoutError:
                        call.error = f"timeout بعد {self._step_timeout}s"
                        step.tool_calls.append(call)

                trace.status = AgentStatus.RUNNING
            else:
                # لا أدوات — هذه الإجابة النهائية
                step.is_final = True
                trace.final_answer = thought
                step.observation = "إجابة نهائية"

            trace.steps.append(step)

            if step.is_final:
                trace.status = AgentStatus.COMPLETED
                break
        else:
            # تجاوز الحد الأقصى للخطوات
            trace.status = AgentStatus.COMPLETED
            trace.final_answer = trace.steps[-1].thought if trace.steps else "لم أتمكن من الإجابة"

    async def _think(
        self,
        query: str,
        history: List[Dict],
        tools: List[Dict],
        step: int,
    ) -> str:
        """يولّد الـ thought المناسب للخطوة الحالية."""
        if self._llm is not None:
            try:
                from core.prompts.prompt_builder import PromptBuilder
                builder = PromptBuilder(system_persona="agent")
                prompt = builder.build_agent_step(query, history, tools, step)
                return await self._llm.agenerate(prompt)
            except Exception as exc:
                logger.warning("LLM thought generation failed: %s", exc)

        # Fallback rule-based
        if step == 0:
            return f"سأجيب على: {query}"
        return f"الإجابة: بناءً على المعلومات المتاحة حول '{query}'"

    def _parse_tool_calls(self, thought: str) -> List[ToolCall]:
        """تحليل الـ tool calls من نص الـ thought."""
        # في النظام الإنتاجي يُستخدم JSON parsing أو regex
        # هنا نُنفّذ منطق بسيط للكشف
        tool_names = [t["name"] for t in self._tools.list_tools()]
        for name in tool_names:
            if f"use_tool:{name}" in thought.lower() or f"[tool:{name}]" in thought:
                return [ToolCall(tool_name=name, arguments={"query": thought[:200]})]
        return []

    # ─── State Management ─────────────────────────────────────────────────────

    def cancel_agent(self, agent_id: str) -> bool:
        trace = self._active_agents.get(agent_id)
        if trace:
            trace.status = AgentStatus.CANCELLED
            return True
        return False

    def get_session_memory(self, session_id: str) -> Optional[AgentMemory]:
        return self._sessions.get(session_id)

    def clear_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def active_count(self) -> int:
        return len(self._active_agents)

    # ─── Built-in Tools ───────────────────────────────────────────────────────

    async def _tool_search(self, query: str = "") -> str:
        return f"نتائج البحث عن: {query}"

    async def _tool_summarize(self, text: str = "") -> str:
        words = text.split()
        return " ".join(words[:50]) + ("..." if len(words) > 50 else "")

    async def _tool_calculate(self, expression: str = "") -> str:
        try:
            allowed = set("0123456789+-*/()., ")
            if any(c not in allowed for c in expression):
                return "تعبير غير آمن"
            return str(eval(expression))  # noqa: S307 — مُقيَّد بالأحرف المسموحة
        except Exception as exc:
            return f"خطأ: {exc}"

    def health(self) -> Dict:
        return {
            "status": "ok",
            "active_agents": self.active_count(),
            "registered_tools": len(self._tools._tools),
            "active_sessions": len(self._sessions),
        }
