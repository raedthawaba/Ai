"""
Multi-Agent System v3 — نظام الوكلاء المتعددين
==============================================

يقوم بـ:
- تعريف أنواع وكلاء مختلفة
- تخصيص المهام للوكلاء المناسبين
- تنسيق عمل الوكلاء
- التعاون والتفاوض بين الوكلاء
- تجميع النتائج
- معالجة الصراعات
- التعلم من التعاون

أنواع الوكلاء:
- Analyst: محلّل البيانات والمعلومات
- Executor: منفّذ المهام
- Reviewer: مراجع النتائج
- Optimizer: محسّن الأداء
- Coordinator: منسّق العمل
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from hajeen_platform.core.llm import LLMManager
from hajeen_platform.brain.task_decomposer_v3 import Task, TaskStatus, TaskPriority

logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """أنواع الوكلاء."""
    ANALYST = "analyst"              # محلّل
    EXECUTOR = "executor"            # منفّذ
    REVIEWER = "reviewer"            # مراجع
    OPTIMIZER = "optimizer"          # محسّن
    COORDINATOR = "coordinator"      # منسّق


class AgentCapability(str, Enum):
    """قدرات الوكلاء."""
    ANALYSIS = "analysis"
    EXECUTION = "execution"
    REVIEW = "review"
    OPTIMIZATION = "optimization"
    COORDINATION = "coordination"
    CODE_GENERATION = "code_generation"
    DATA_PROCESSING = "data_processing"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    DECISION_MAKING = "decision_making"


class MessageType(str, Enum):
    """أنواع الرسائل بين الوكلاء."""
    TASK_ASSIGNMENT = "task_assignment"
    RESULT_SUBMISSION = "result_submission"
    QUERY = "query"
    FEEDBACK = "feedback"
    NEGOTIATION = "negotiation"
    CONFLICT_RESOLUTION = "conflict_resolution"
    COORDINATION = "coordination"


@dataclass
class AgentMessage:
    """رسالة بين الوكلاء."""
    message_id: str
    from_agent_id: str
    to_agent_id: str
    message_type: MessageType
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    processed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "from_agent_id": self.from_agent_id,
            "to_agent_id": self.to_agent_id,
            "message_type": self.message_type.value,
            "content": self.content,
            "created_at": self.created_at,
            "processed_at": self.processed_at,
        }


@dataclass
class Agent:
    """وكيل ذكي."""
    agent_id: str
    name: str
    agent_type: AgentType
    capabilities: List[AgentCapability]
    description: str
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2048
    status: str = "idle"
    current_task_id: Optional[str] = None
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "agent_type": self.agent_type.value,
            "capabilities": [c.value for c in self.capabilities],
            "description": self.description,
            "model": self.model,
            "status": self.status,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "total_execution_time_ms": round(self.total_execution_time_ms, 2),
        }

    @property
    def success_rate(self) -> float:
        """معدل النجاح."""
        total = self.completed_tasks + self.failed_tasks
        if total == 0:
            return 0.0
        return self.completed_tasks / total

    @property
    def avg_execution_time_ms(self) -> float:
        """متوسط وقت التنفيذ."""
        if self.completed_tasks == 0:
            return 0.0
        return self.total_execution_time_ms / self.completed_tasks


@dataclass
class AgentTeam:
    """فريق من الوكلاء."""
    team_id: str
    name: str
    agents: Dict[str, Agent]
    coordinator_agent_id: str
    message_queue: List[AgentMessage] = field(default_factory=list)
    collaboration_history: List[Dict[str, Any]] = field(default_factory=list)
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "team_id": self.team_id,
            "name": self.name,
            "agent_count": len(self.agents),
            "agents": {aid: a.to_dict() for aid, a in self.agents.items()},
            "coordinator_agent_id": self.coordinator_agent_id,
            "total_tasks_completed": self.total_tasks_completed,
            "total_tasks_failed": self.total_tasks_failed,
        }


@dataclass
class CollaborationResult:
    """نتيجة التعاون بين الوكلاء."""
    collaboration_id: str
    team_id: str
    task_id: str
    assigned_agents: List[str]
    results_by_agent: Dict[str, str]
    final_result: str
    quality_score: float
    execution_time_ms: float
    messages_exchanged: int
    conflicts_resolved: int
    confidence: float
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "collaboration_id": self.collaboration_id,
            "team_id": self.team_id,
            "task_id": self.task_id,
            "assigned_agents": self.assigned_agents,
            "final_result": self.final_result,
            "quality_score": round(self.quality_score, 3),
            "execution_time_ms": round(self.execution_time_ms, 2),
            "messages_exchanged": self.messages_exchanged,
            "conflicts_resolved": self.conflicts_resolved,
            "confidence": round(self.confidence, 3),
        }


class MultiAgentSystemV3:
    """
    نظام الوكلاء المتعددين v3.
    
    يستخدم:
    - LLM لكل وكيل
    - نظام رسائل للتواصل
    - منسّق مركزي
    """

    def __init__(self, llm_manager: LLMManager) -> None:
        self.llm_manager = llm_manager
        self._teams: Dict[str, AgentTeam] = {}
        self._agents: Dict[str, Agent] = {}
        self._collaborations: Dict[str, CollaborationResult] = {}
        self._collaboration_history: List[CollaborationResult] = []
        logger.info("MultiAgentSystemV3: initialized")

    async def create_team(
        self,
        team_name: str,
        agent_types: List[AgentType],
    ) -> AgentTeam:
        """إنشاء فريق من الوكلاء."""
        team_id = str(uuid.uuid4())
        agents = {}
        coordinator_agent_id = None
        
        try:
            # إنشاء الوكلاء
            for agent_type in agent_types:
                agent = await self._create_agent(agent_type)
                agents[agent.agent_id] = agent
                self._agents[agent.agent_id] = agent
                
                # الوكيل الأول من نوع COORDINATOR يصبح منسّقاً
                if agent_type == AgentType.COORDINATOR and coordinator_agent_id is None:
                    coordinator_agent_id = agent.agent_id
            
            # إذا لم يكن هناك منسّق، إنشاء واحد
            if coordinator_agent_id is None:
                coordinator = await self._create_agent(AgentType.COORDINATOR)
                agents[coordinator.agent_id] = coordinator
                self._agents[coordinator.agent_id] = coordinator
                coordinator_agent_id = coordinator.agent_id
            
            # إنشاء الفريق
            team = AgentTeam(
                team_id=team_id,
                name=team_name,
                agents=agents,
                coordinator_agent_id=coordinator_agent_id,
            )
            
            self._teams[team_id] = team
            
            logger.info(
                "multi_agent_system_v3: created team %s with %d agents",
                team_name, len(agents)
            )
            
            return team
        
        except Exception as e:
            logger.error("multi_agent_system_v3: error creating team: %s", e, exc_info=True)
            raise

    async def _create_agent(self, agent_type: AgentType) -> Agent:
        """إنشاء وكيل."""
        agent_id = str(uuid.uuid4())
        
        # تحديد الخصائص بناءً على النوع
        if agent_type == AgentType.ANALYST:
            name = "محلّل البيانات"
            capabilities = [
                AgentCapability.ANALYSIS,
                AgentCapability.KNOWLEDGE_RETRIEVAL,
                AgentCapability.DATA_PROCESSING,
            ]
            description = "متخصص في تحليل البيانات والمعلومات"
        elif agent_type == AgentType.EXECUTOR:
            name = "منفّذ المهام"
            capabilities = [
                AgentCapability.EXECUTION,
                AgentCapability.CODE_GENERATION,
                AgentCapability.DECISION_MAKING,
            ]
            description = "متخصص في تنفيذ المهام والعمليات"
        elif agent_type == AgentType.REVIEWER:
            name = "مراجع النتائج"
            capabilities = [
                AgentCapability.REVIEW,
                AgentCapability.ANALYSIS,
                AgentCapability.DECISION_MAKING,
            ]
            description = "متخصص في مراجعة وتقييم النتائج"
        elif agent_type == AgentType.OPTIMIZER:
            name = "محسّن الأداء"
            capabilities = [
                AgentCapability.OPTIMIZATION,
                AgentCapability.ANALYSIS,
                AgentCapability.DECISION_MAKING,
            ]
            description = "متخصص في تحسين الأداء والكفاءة"
        else:  # COORDINATOR
            name = "منسّق الفريق"
            capabilities = [
                AgentCapability.COORDINATION,
                AgentCapability.DECISION_MAKING,
                AgentCapability.ANALYSIS,
            ]
            description = "متخصص في تنسيق عمل الفريق"
        
        agent = Agent(
            agent_id=agent_id,
            name=name,
            agent_type=agent_type,
            capabilities=capabilities,
            description=description,
        )
        
        return agent

    async def collaborate(
        self,
        team_id: str,
        task: Task,
        context: Optional[Dict[str, Any]] = None,
    ) -> CollaborationResult:
        """
        تعاون الوكلاء لإنجاز مهمة.
        
        الخطوات:
        1. اختيار الوكلاء المناسبين
        2. توزيع المهام
        3. تنفيذ المهام بالتوازي
        4. جمع النتائج
        5. معالجة الصراعات
        6. تجميع النتيجة النهائية
        """
        collaboration_id = str(uuid.uuid4())
        t0 = time.perf_counter()
        
        try:
            team = self._teams.get(team_id)
            if not team:
                raise ValueError(f"Team {team_id} not found")
            
            # ── Step 1: اختيار الوكلاء المناسبين ──────────────────
            selected_agents = await self._select_suitable_agents(team, task)
            
            # ── Step 2: توزيع المهام ──────────────────────────────
            agent_tasks = await self._distribute_tasks(
                selected_agents, task, context
            )
            
            # ── Step 3: تنفيذ المهام بالتوازي ────────────────────
            results_by_agent = await self._execute_agent_tasks(
                team, agent_tasks
            )
            
            # ── Step 4: جمع النتائج ────────────────────────────────
            collected_results = await self._collect_results(
                results_by_agent, selected_agents
            )
            
            # ── Step 5: معالجة الصراعات ──────────────────────────
            conflicts_resolved = await self._resolve_conflicts(
                collected_results, team
            )
            
            # ── Step 6: تجميع النتيجة النهائية ────────────────────
            final_result = await self._aggregate_results(
                collected_results, team, task
            )
            
            # ── Step 7: حساب الجودة والثقة ──────────────────────
            quality_score = await self._evaluate_collaboration_quality(
                final_result, task
            )
            confidence = await self._calculate_collaboration_confidence(
                selected_agents, quality_score
            )
            
            execution_time_ms = (time.perf_counter() - t0) * 1000
            
            # ── Step 8: بناء النتيجة النهائية ────────────────────
            result = CollaborationResult(
                collaboration_id=collaboration_id,
                team_id=team_id,
                task_id=task.task_id,
                assigned_agents=[a.agent_id for a in selected_agents],
                results_by_agent=results_by_agent,
                final_result=final_result,
                quality_score=quality_score,
                execution_time_ms=execution_time_ms,
                messages_exchanged=len(team.message_queue),
                conflicts_resolved=conflicts_resolved,
                confidence=confidence,
                reasoning=f"تعاون {len(selected_agents)} وكلاء لإنجاز المهمة",
            )
            
            # تحديث الإحصائيات
            team.total_tasks_completed += 1
            for agent in selected_agents:
                agent.completed_tasks += 1
                agent.total_execution_time_ms += execution_time_ms
            
            # تخزين مؤقت
            self._collaborations[collaboration_id] = result
            self._collaboration_history.append(result)
            
            logger.info(
                "multi_agent_system_v3: collaboration completed agents=%d quality=%.3f time=%.1f",
                len(selected_agents), quality_score, execution_time_ms
            )
            
            return result
        
        except Exception as e:
            logger.error("multi_agent_system_v3: error during collaboration: %s", e, exc_info=True)
            
            execution_time_ms = (time.perf_counter() - t0) * 1000
            
            return CollaborationResult(
                collaboration_id=collaboration_id,
                team_id=team_id,
                task_id=task.task_id,
                assigned_agents=[],
                results_by_agent={},
                final_result="",
                quality_score=0.0,
                execution_time_ms=execution_time_ms,
                messages_exchanged=0,
                conflicts_resolved=0,
                confidence=0.0,
                reasoning=f"فشل التعاون: {str(e)}",
                metadata={"error": str(e)},
            )

    async def _select_suitable_agents(
        self,
        team: AgentTeam,
        task: Task,
    ) -> List[Agent]:
        """اختيار الوكلاء المناسبين."""
        suitable = []
        
        # اختيار منسّق دائماً
        coordinator = team.agents[team.coordinator_agent_id]
        suitable.append(coordinator)
        
        # اختيار وكلاء إضافيين بناءً على نوع المهمة
        if task.priority == TaskPriority.CRITICAL:
            # للمهام الحرجة، اختيار مراجع
            reviewers = [a for a in team.agents.values() if a.agent_type == AgentType.REVIEWER]
            if reviewers:
                suitable.append(reviewers[0])
        
        # اختيار منفّذ
        executors = [a for a in team.agents.values() if a.agent_type == AgentType.EXECUTOR]
        if executors:
            suitable.append(executors[0])
        
        return suitable

    async def _distribute_tasks(
        self,
        agents: List[Agent],
        task: Task,
        context: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        """توزيع المهام على الوكلاء."""
        agent_tasks = {}
        
        for agent in agents:
            # إنشاء مهمة مخصصة لكل وكيل
            task_description = f"""أنت {agent.name}.

المهمة الرئيسية: {task.title}
الوصف: {task.description}

قدّم مساهمتك بناءً على تخصصك."""
            
            agent_tasks[agent.agent_id] = task_description
        
        return agent_tasks

    async def _execute_agent_tasks(
        self,
        team: AgentTeam,
        agent_tasks: Dict[str, str],
    ) -> Dict[str, str]:
        """تنفيذ مهام الوكلاء بالتوازي."""
        results = {}
        
        async def execute_agent_task(agent_id: str, task_description: str):
            try:
                agent = team.agents[agent_id]
                
                response = await self.llm_manager.generate(
                    prompt=task_description,
                    model=agent.model,
                    temperature=agent.temperature,
                    max_tokens=agent.max_tokens,
                )
                
                results[agent_id] = response
            except Exception as e:
                logger.warning("multi_agent_system_v3: agent %s failed: %s", agent_id, e)
                results[agent_id] = f"فشل: {str(e)}"
        
        # تنفيذ بالتوازي
        tasks = [
            execute_agent_task(agent_id, task_desc)
            for agent_id, task_desc in agent_tasks.items()
        ]
        await asyncio.gather(*tasks)
        
        return results

    async def _collect_results(
        self,
        results_by_agent: Dict[str, str],
        agents: List[Agent],
    ) -> Dict[str, Any]:
        """جمع النتائج."""
        return {
            "results": results_by_agent,
            "agent_count": len(agents),
            "timestamp": time.time(),
        }

    async def _resolve_conflicts(
        self,
        collected_results: Dict[str, Any],
        team: AgentTeam,
    ) -> int:
        """معالجة الصراعات."""
        # في هذه النسخة، نفترض عدم وجود صراعات
        return 0

    async def _aggregate_results(
        self,
        collected_results: Dict[str, Any],
        team: AgentTeam,
        task: Task,
    ) -> str:
        """تجميع النتائج النهائية."""
        results_text = "\n".join([
            f"- {result}" for result in collected_results["results"].values()
        ])
        
        prompt = f"""جمّع النتائج التالية من الوكلاء:

{results_text}

المهمة الأصلية: {task.title}

قدّم نتيجة نهائية موحدة."""
        
        try:
            final_result = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.5,
                max_tokens=1024,
            )
            return final_result
        except Exception as e:
            logger.warning("multi_agent_system_v3: failed to aggregate: %s", e)
            return results_text

    async def _evaluate_collaboration_quality(
        self,
        result: str,
        task: Task,
    ) -> float:
        """تقييم جودة التعاون."""
        if not result:
            return 0.0
        
        score = 0.5
        
        # الطول
        if len(result) > 200:
            score += 0.2
        
        # البنية
        if "\n" in result:
            score += 0.15
        
        # الكمية
        if len(result.split()) > 50:
            score += 0.15
        
        return min(1.0, score)

    async def _calculate_collaboration_confidence(
        self,
        agents: List[Agent],
        quality_score: float,
    ) -> float:
        """حساب ثقة التعاون."""
        # متوسط معدل نجاح الوكلاء
        success_rates = [a.success_rate for a in agents]
        avg_success = sum(success_rates) / len(success_rates) if success_rates else 0.5
        
        # دمج مع درجة الجودة
        return (avg_success + quality_score) / 2

    def get_collaboration(self, collaboration_id: str) -> Optional[CollaborationResult]:
        """الحصول على نتيجة تعاون محفوظة."""
        return self._collaborations.get(collaboration_id)

    def get_recent_collaborations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """آخر نتائج التعاون."""
        recent = self._collaboration_history[-limit:]
        return [c.to_dict() for c in recent]

    def get_team_stats(self, team_id: str) -> Dict[str, Any]:
        """إحصائيات الفريق."""
        team = self._teams.get(team_id)
        if not team:
            return {}
        
        return {
            "team_id": team_id,
            "team_name": team.name,
            "agent_count": len(team.agents),
            "total_tasks_completed": team.total_tasks_completed,
            "total_tasks_failed": team.total_tasks_failed,
            "agents": {aid: a.to_dict() for aid, a in team.agents.items()},
        }

    def get_system_stats(self) -> Dict[str, Any]:
        """إحصائيات النظام."""
        if not self._collaboration_history:
            return {"total_collaborations": 0}
        
        total = len(self._collaboration_history)
        avg_agents = sum(len(c.assigned_agents) for c in self._collaboration_history) / total
        avg_quality = sum(c.quality_score for c in self._collaboration_history) / total
        avg_confidence = sum(c.confidence for c in self._collaboration_history) / total
        
        return {
            "total_collaborations": total,
            "total_teams": len(self._teams),
            "total_agents": len(self._agents),
            "avg_agents_per_collaboration": round(avg_agents, 1),
            "avg_quality_score": round(avg_quality, 3),
            "avg_confidence": round(avg_confidence, 3),
        }


# Singleton
_multi_agent_system_v3: Optional[MultiAgentSystemV3] = None


def get_multi_agent_system_v3(
    llm_manager: Optional[LLMManager] = None,
) -> MultiAgentSystemV3:
    """الحصول على instance من MultiAgentSystemV3."""
    global _multi_agent_system_v3
    if _multi_agent_system_v3 is None:
        if llm_manager is None:
            from hajeen_platform.core.llm import get_llm_manager
            llm_manager = get_llm_manager()
        _multi_agent_system_v3 = MultiAgentSystemV3(llm_manager)
    return _multi_agent_system_v3
