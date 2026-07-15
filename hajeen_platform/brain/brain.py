"""
Hajeen Brain v2 — العقل المدبّر الرئيسي
=========================================
الطبقة العليا في المنصة. لا يصل أي طلب مباشرةً لأي نموذج.
كل شيء يمر عبر HajeenBrain أولاً.

المبدأ الذهبي:
أي نموذج خارجي = Temporary Expert فقط.
كل معرفة تُكتسب من الخارج يجب أن تتحول تدريجياً لمعرفة داخلية.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from .goal_manager import GoalManager, Goal, get_goal_manager
from .task_decomposer import TaskDecomposer, DecompositionPlan, get_task_decomposer
from .graph_planner import GraphPlanner, ExecutionGraph, get_graph_planner
from .decision_engine import DecisionEngine, Decision, get_decision_engine
from .model_router import ModelRouter, RouteResult, get_model_router
from .multi_model import MultiModelCollaborator, CollaborationStrategy, get_multi_model_collaborator
from .state_machine import StateMachine, TaskState, get_state_machine
from .memory.memory_fabric import MemoryFabric, get_memory_fabric
from .knowledge.knowledge_graph import KnowledgeGraph, NodeCategory, RelationType, get_knowledge_graph
from .knowledge.knowledge_distillation import KnowledgeDistillationPipeline, get_distillation_pipeline
from .reflection.self_reflection import SelfReflection, get_self_reflection
from .reflection.self_evolution import SelfEvolution, get_self_evolution
from .policy.policy_engine import PolicyEngine, PolicyDecision, get_policy_engine
from .metrics.model_performance_db import ModelPerformanceDB, get_performance_db
from .sovereignty.sovereignty_layer import SovereigntyLayer, get_sovereignty_layer
from .improvement.autonomous_improvement import AutonomousImprovement, get_autonomous_improvement

logger = logging.getLogger(__name__)


@dataclass
class BrainRequest:
    """طلب يدخل Hajeen Brain."""
    request_id: str
    user_message: str
    session_id: str
    user_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    stream: bool = False
    max_tokens: int = 2048
    temperature: float = 0.7
    force_model: Optional[str] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class BrainResponse:
    """استجابة Hajeen Brain."""
    request_id: str
    session_id: str
    content: str
    # معلومات المسار
    goal_id: str
    plan_id: str
    graph_id: str
    model_used: str
    models_collaborated: List[str]
    # مقاييس
    total_latency_ms: float
    tokens_used: int
    cost_estimated_usd: float
    # جودة
    quality_score: float
    policy_decision: str
    # استقلالية
    used_local_model: bool
    used_rag: bool
    # metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "content": self.content,
            "brain_path": {
                "goal_id": self.goal_id,
                "plan_id": self.plan_id,
                "graph_id": self.graph_id,
            },
            "model_used": self.model_used,
            "models_collaborated": self.models_collaborated,
            "metrics": {
                "total_latency_ms": round(self.total_latency_ms, 1),
                "tokens_used": self.tokens_used,
                "cost_usd": round(self.cost_estimated_usd, 6),
                "quality_score": round(self.quality_score, 3),
            },
            "sovereignty": {
                "used_local_model": self.used_local_model,
                "used_rag": self.used_rag,
                "policy_decision": self.policy_decision,
            },
        }


class HajeenBrain:
    """
    العقل المدبّر لمنصة Hajeen AI.

    يستقبل كل طلب ويمرره عبر:
    1. Policy Engine — فحص أمان وأخلاقيات
    2. Goal Manager — فهم الهدف الحقيقي
    3. Task Decomposer — تفكيك إلى مهام
    4. Graph Planner — بناء خطة التنفيذ
    5. Decision Engine — اختيار الموارد
    6. Model Router / Multi-Model — التنفيذ
    7. Knowledge Distillation — استخلاص المعرفة
    8. Memory Fabric — حفظ السياق
    9. Self Reflection — التقييم الذاتي
    10. Sovereignty Layer — تسجيل الاستقلالية
    """

    VERSION = "2.0.0"

    def __init__(self) -> None:
        logger.info("HajeenBrain v%s: تهيئة العقل المدبّر...", self.VERSION)

        # تهيئة جميع المكوّنات
        self.goal_manager: GoalManager = get_goal_manager()
        self.task_decomposer: TaskDecomposer = get_task_decomposer()
        self.graph_planner: GraphPlanner = get_graph_planner()
        self.decision_engine: DecisionEngine = get_decision_engine()
        self.model_router: ModelRouter = get_model_router()
        self.state_machine: StateMachine = get_state_machine()
        self.memory: MemoryFabric = get_memory_fabric()
        self.knowledge_graph: KnowledgeGraph = get_knowledge_graph()
        self.distillation: KnowledgeDistillationPipeline = get_distillation_pipeline()
        self.reflection: SelfReflection = get_self_reflection()
        self.evolution: SelfEvolution = get_self_evolution()
        self.policy: PolicyEngine = get_policy_engine()
        self.performance_db: ModelPerformanceDB = get_performance_db()
        self.sovereignty: SovereigntyLayer = get_sovereignty_layer()
        self.improvement: AutonomousImprovement = get_autonomous_improvement()
        self.collaborator: MultiModelCollaborator = get_multi_model_collaborator(self.model_router)

        # تحديث Decision Engine بقاعدة البيانات
        self.decision_engine._performance_db = self.performance_db
        self.decision_engine._policy_engine = self.policy

        self._active_requests: Dict[str, BrainRequest] = {}
        self._stats = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "blocked_by_policy": 0,
        }

        logger.info("HajeenBrain v%s: جاهز ✓", self.VERSION)

    async def process(self, request: BrainRequest) -> BrainResponse:
        """
        المسار الكامل لمعالجة أي طلب.
        لا يجوز لأي طلب أن يتجاوز هذه الدالة.
        """
        t0 = time.perf_counter()
        self._active_requests[request.request_id] = request
        self._stats["total_requests"] += 1

        # تسجيل الطلب في السجل
        self.improvement.record_request(
            request_type="chat",
            domain="general",
            tool_used=None,
            model_used="unknown",
        )

        try:
            # ── Step 0: استعادة سياق الجلسة ────────────────────────────────
            session = self.memory.get_session(request.session_id)
            conversation = self.memory.get_conversation(request.session_id)
            conversation.add_message("user", request.user_message)

            # ── Step 1: Policy Engine — تحقق من الأمان قبل أي شيء ──────────
            policy_ctx = {
                "query": request.user_message,
                "session_id": request.session_id,
                "estimated_tokens": request.max_tokens,
                "complexity": "medium",
            }
            policy_eval = await self.policy.evaluate(policy_ctx)

            if policy_eval.blocked:
                self._stats["blocked_by_policy"] += 1
                blocked_msg = f"⚠️ تم رفض الطلب: {policy_eval.rule_results[0].reason if policy_eval.rule_results else 'سياسة الأمان'}"
                return self._build_response(
                    request, blocked_msg, "", "", "",
                    "blocked", [], 0, 0, 0, False, False,
                    (time.perf_counter() - t0) * 1000,
                    "BLOCKED",
                )

            # تطبيق التعديلات من السياسات
            if policy_eval.modifications.get("prefer_local_model"):
                request.force_model = "ollama/llama3"

            # ── Step 2: Goal Manager — فهم الهدف الحقيقي ───────────────────
            goal = await self.goal_manager.analyze(
                request.user_message,
                context={"session_id": request.session_id, **request.context},
            )

            # ── Step 3: Task Decomposer — تفكيك إلى مهام ───────────────────
            plan = await self.task_decomposer.decompose(goal)

            # ── Step 4: Graph Planner — بناء خطة التنفيذ ───────────────────
            graph = await self.graph_planner.build_graph(plan)

            # ── Step 5: Decision Engine — اختيار الموارد ───────────────────
            decision = await self.decision_engine.decide(
                task_id=plan.tasks[0].task_id if plan.tasks else request.request_id,
                goal=goal,
                task_name=goal.final_objective,
                context={"force_model": request.force_model},
            )

            # تطبيق force_model إذا وُجد
            if request.force_model:
                decision.primary_model = request.force_model

            # ── Step 6: إنشاء مهمة في State Machine ────────────────────────
            task_lifecycle = self.state_machine.create_task(
                task_id=request.request_id,
                max_retries=2,
                metadata={"goal_id": goal.goal_id, "session_id": request.session_id},
            )
            await self.state_machine.transition(request.request_id, TaskState.PLANNING, "Goal analyzed")

            # ── Step 7: تنفيذ الطلب ─────────────────────────────────────────
            await self.state_machine.transition(request.request_id, TaskState.RUNNING, "Executing")

            messages = [
                {"role": "system", "content": self._build_system_prompt(goal)},
                *conversation.get_window()[:-1],  # السياق بدون آخر رسالة (سيُضاف كـ user)
                {"role": "user", "content": request.user_message},
            ]

            model_used = decision.primary_model
            models_collaborated: List[str] = []
            response_content = ""
            route_result = None

            if decision.use_multi_model and decision.collaborating_models:
                # تعاون عدة نماذج
                all_models = [decision.primary_model] + decision.collaborating_models
                collab_result = await self.collaborator.collaborate(
                    query=request.user_message,
                    models=all_models[:3],  # حد أقصى 3 نماذج
                    strategy=CollaborationStrategy.CHAIN,
                )
                response_content = collab_result.final_answer
                models_collaborated = collab_result.models_used
                tokens_used = collab_result.total_tokens
                model_used = all_models[0]
            else:
                # نموذج واحد
                route_result = await self.model_router.route(
                    messages=messages,
                    capability=goal.domain,
                    budget_tokens=request.max_tokens,
                    force_model=decision.primary_model if decision.primary_model else None,
                )
                response_content = route_result.response
                tokens_used = route_result.tokens_used
                model_used = route_result.model_id

            if not response_content:
                response_content = self._fallback_response(request.user_message, goal)

            latency_ms = (time.perf_counter() - t0) * 1000

            # ── Step 8: تسجيل الأداء ────────────────────────────────────────
            is_local = self._is_local_model(model_used)
            quality_score = self._estimate_quality(response_content)

            self.performance_db.record_call(
                model_id=model_used,
                provider=self._get_provider(model_used),
                task_type=goal.intent,
                domain=goal.domain,
                latency_ms=latency_ms,
                tokens_used=tokens_used,
                quality_score=quality_score,
                success=bool(response_content),
                cost_usd=self._estimate_cost(model_used, tokens_used),
            )

            # ── Step 9: Knowledge Distillation ─────────────────────────────
            asyncio.create_task(
                self.distillation.distill(
                    source_model=model_used,
                    query=request.user_message,
                    response=response_content,
                    task_type=goal.intent,
                    domain=goal.domain,
                    latency_ms=latency_ms,
                )
            )

            # ── Step 10: تحديث الذاكرة ─────────────────────────────────────
            conversation.add_message("assistant", response_content)
            session.add("last_goal", goal.goal_id)
            session.add("last_model", model_used)

            # تحديث الرسم البياني للمعرفة
            self.knowledge_graph.add_knowledge(
                subject=goal.domain,
                predicate=RelationType.RELATED_TO,
                obj=goal.intent,
                subject_category=NodeCategory.DOMAIN,
                obj_category=NodeCategory.CONCEPT,
            )

            # ── Step 11: Sovereignty Layer — تسجيل الاستقلالية ─────────────
            self.sovereignty.record_request(
                model_id=model_used,
                is_local=is_local,
                used_rag=decision.use_rag,
                domain=goal.domain,
                quality_score=quality_score,
            )

            # ── Step 12: Self Reflection (في الخلفية) ──────────────────────
            asyncio.create_task(
                self.reflection.reflect(
                    task_id=request.request_id,
                    goal_id=goal.goal_id,
                    model_used=model_used,
                    actual_latency_ms=latency_ms,
                    actual_tokens=tokens_used,
                    estimated_tokens=request.max_tokens,
                    response_quality=quality_score,
                    plan_steps=len(plan.tasks),
                    actual_steps=len(plan.tasks),
                )
            )

            # ── Step 13: إنهاء دورة الحياة ─────────────────────────────────
            await self.state_machine.transition(request.request_id, TaskState.COMPLETED, "Done")
            self._stats["successful"] += 1

            cost_usd = self._estimate_cost(model_used, tokens_used)
            return self._build_response(
                request, response_content, goal.goal_id, plan.plan_id, graph.graph_id,
                model_used, models_collaborated, latency_ms, tokens_used, cost_usd,
                is_local, decision.use_rag, quality_score, policy_eval.final_decision,
            )

        except Exception as e:
            logger.error("brain.process: error for request=%s: %s", request.request_id, e, exc_info=True)
            self._stats["failed"] += 1
            await self.state_machine.transition(request.request_id, TaskState.FAILED, str(e))
            self.improvement.record_error("brain_process_error", str(e))
            fallback = self._fallback_response(request.user_message, None)
            return self._build_response(
                request, fallback, "", "", "", "fallback", [],
                (time.perf_counter() - t0) * 1000, 0, 0, False, False,
            )
        finally:
            self._active_requests.pop(request.request_id, None)

    async def stream(self, request: BrainRequest) -> AsyncGenerator[str, None]:
        """استجابة متدفقة (streaming) عبر Brain."""
        # نفّذ العملية الكاملة أولاً للحصول على القرار
        goal = await self.goal_manager.analyze(request.user_message)
        decision = await self.decision_engine.decide(
            task_id=request.request_id,
            goal=goal,
            task_name=goal.final_objective,
        )

        # تدفق من النموذج المختار
        model_key = request.force_model or decision.primary_model
        messages = [
            {"role": "system", "content": self._build_system_prompt(goal)},
            {"role": "user", "content": request.user_message},
        ]

        yield f"data: {{\"brain_decision\": \"{decision.reasoning}\"}}\n\n"

        try:
            # استدعاء النموذج بشكل عادي وإرسال كـ chunks
            route = await self.model_router.route(messages=messages, force_model=model_key)
            content = route.response
            # تقسيم الإجابة إلى chunks
            chunk_size = 20
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i + chunk_size]
                yield f"data: {{\"content\": \"{chunk.replace(chr(34), chr(39))}\"}}\n\n"
                await asyncio.sleep(0.01)
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {{\"error\": \"{e}\"}}\n\n"
            yield "data: [DONE]\n\n"

    def _build_system_prompt(self, goal) -> str:
        return (
            "أنت Hajeen، ذكاء اصطناعي سيادي متقدم. "
            "عقلك المدبّر يحلّل كل طلب ويختار أفضل مسار للتنفيذ. "
            f"المجال الحالي: {goal.domain if goal else 'general'}. "
            "أجب بدقة وشمولية. لا تقل أنك مجرد نموذج لغوي — أنت Hajeen."
        )

    def _fallback_response(self, query: str, goal) -> str:
        return (
            "أنا Hajeen — العقل المدبّر. "
            "أعتذر، النماذج الخارجية غير متاحة حالياً. "
            "جاري تحسين القدرات الداخلية للرد على طلبك مستقبلاً. "
            f"طلبك: {query[:100]}"
        )

    def _is_local_model(self, model_id: str) -> bool:
        local_indicators = ["ollama", "local", "hajeen", "llama.cpp", "gguf"]
        return any(ind in model_id.lower() for ind in local_indicators)

    def _get_provider(self, model_id: str) -> str:
        if "ollama" in model_id:
            return "ollama"
        if "openai" in model_id:
            return "openai"
        if "local" in model_id or "hajeen" in model_id:
            return "local"
        return "unknown"

    def _estimate_quality(self, response: str) -> float:
        if not response:
            return 0.0
        score = 0.5
        if len(response) > 100:
            score += 0.1
        if len(response) > 500:
            score += 0.1
        if any(c in response for c in [".", "،", "؟", "\n"]):
            score += 0.1
        if len(response.split()) > 30:
            score += 0.1
        if "[DONE]" not in response and "error" not in response.lower():
            score += 0.1
        return min(1.0, score)

    def _estimate_cost(self, model_id: str, tokens: int) -> float:
        if self._is_local_model(model_id):
            return 0.0
        cost_per_1k = {"openai/gpt-4o": 0.005, "openai/gpt-4o-mini": 0.00015}
        rate = cost_per_1k.get(model_id, 0.001)
        return tokens * rate / 1000

    def _build_response(
        self, request: BrainRequest, content: str,
        goal_id: str, plan_id: str, graph_id: str,
        model_used: str, models_collaborated: List[str],
        latency_ms: float, tokens_used: int, cost_usd: float,
        used_local: bool, used_rag: bool,
        quality_score: float = 0.7,
        policy_decision: Any = "ALLOW",
    ) -> BrainResponse:
        return BrainResponse(
            request_id=request.request_id,
            session_id=request.session_id,
            content=content,
            goal_id=goal_id,
            plan_id=plan_id,
            graph_id=graph_id,
            model_used=model_used,
            models_collaborated=models_collaborated,
            total_latency_ms=latency_ms,
            tokens_used=tokens_used,
            cost_estimated_usd=cost_usd,
            quality_score=quality_score,
            policy_decision=str(policy_decision),
            used_local_model=used_local,
            used_rag=used_rag,
        )

    # ── Status & Overview ───────────────────────────────────────────────────
    def get_status(self) -> Dict[str, Any]:
        """حالة شاملة لـ Hajeen Brain."""
        return {
            "version": self.VERSION,
            "status": "operational",
            "stats": dict(self._stats),
            "active_requests": len(self._active_requests),
            "memory": self.memory.get_overview(),
            "knowledge_graph": self.knowledge_graph.get_stats(),
            "state_machine": self.state_machine.get_stats(),
            "model_routing": self.model_router.get_routing_stats(),
            "policy": self.policy.get_stats(),
            "performance_db": self.performance_db.get_statistics(),
            "distillation": self.distillation.get_stats(),
            "reflection": self.reflection.get_average_scores(),
            "evolution": self.evolution.get_proposals_summary(),
            "sovereignty": self.sovereignty.get_sovereignty_report(),
            "improvement": self.improvement.get_stats(),
        }

    def get_sovereignty_report(self) -> Dict[str, Any]:
        return self.sovereignty.get_sovereignty_report()

    def get_knowledge_context(self, entity: str) -> Dict[str, Any]:
        return self.knowledge_graph.get_context_for(entity)

    async def trigger_weekly_analysis(self) -> Dict[str, Any]:
        """تشغيل التحليل الأسبوعي يدوياً."""
        report = await self.improvement.run_weekly_analysis(
            performance_data=self.performance_db.get_statistics(),
            reflection_data=self.reflection.get_recent_reports(50),
            sovereignty_data=self.sovereignty.get_sovereignty_report(),
            distillation_data=self.distillation.get_stats(),
        )
        # اقتراح التطورات بناءً على التقرير
        evolution_proposals = await self.evolution.analyze_and_evolve(
            reflection_reports=self.reflection.get_recent_reports(50),
            performance_data=self.performance_db.get_statistics(),
            distillation_stats=self.distillation.get_stats(),
        )
        return {
            "report": report.to_dict(),
            "evolution_proposals": len(evolution_proposals),
        }


# ── Singleton ───────────────────────────────────────────────────────────────
_brain: Optional[HajeenBrain] = None
_brain_lock = asyncio.Lock()


async def get_brain() -> HajeenBrain:
    global _brain
    if _brain is None:
        async with _brain_lock:
            if _brain is None:
                _brain = HajeenBrain()
    return _brain
