
"""
Hajeen Brain v3 — العقل المدبّر المركزي المُحسّن
================================================

إعادة تصميم شاملة للعقل المركزي:
1. لا توجد مسارات مختصرة (shortcuts) — كل طلب يمر عبر الطبقة الإدراكية الكاملة
2. استدلال عميق في كل خطوة — لا قواعد ثابتة أو مطابقة كلمات مفتاحية
3. تدفق موحد — سواء كان streaming أو batch، كل الطلبات تتبع نفس المسار
4. مراقبة ذاتية مستمرة — كل قرار يُسجل ويُقيّم
5. تطور مستمر — النظام يتعلم من كل طلب ويحسّن نفسه

المبدأ الذهبي:
أي نموذج خارجي = Temporary Expert فقط.
كل معرفة تُكتسب من الخارج يجب أن تتحول تدريجياً لمعرفة داخلية.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional

from .cognitive_layer.context_analyzer import (
    ContextAnalysis,
    ContextAnalyzer,
    get_context_analyzer,
)
from .cognitive_layer.intent_analyzer import Intent, IntentAnalyzer, get_intent_analyzer
from .cognitive_layer.reasoning_engine import (
    ReasoningEngine,
    ReasoningResult,
    get_reasoning_engine,
)
from .decision_engine import DecisionEngine, get_decision_engine
from .goal_manager import Goal, GoalManager, get_goal_manager
from .graph_planner import GraphPlanner, get_graph_planner
from .improvement.autonomous_improvement import (
    AutonomousImprovement,
    get_autonomous_improvement,
)
from .knowledge.knowledge_distillation import (
    KnowledgeDistillationPipeline,
    get_distillation_pipeline,
)
from .knowledge.knowledge_graph import (
    KnowledgeGraph,
    NodeCategory,
    RelationType,
    get_knowledge_graph,
)
from .memory.memory_fabric import MemoryFabric, get_memory_fabric
from .metrics.model_performance_db import ModelPerformanceDB, get_performance_db
from .model_router import ModelRouter, get_model_router
from .multi_model import (
    CollaborationStrategy,
    MultiModelCollaborator,
    get_multi_model_collaborator,
)
from .policy.policy_engine import PolicyEngine, get_policy_engine
from .reflection.self_evolution import SelfEvolution, get_self_evolution
from .reflection.self_reflection import SelfReflection, get_self_reflection
from .sovereignty.sovereignty_layer import SovereigntyLayer, get_sovereignty_layer
from .state_machine import StateMachine, TaskState, get_state_machine
from .task_decomposer import TaskDecomposer, get_task_decomposer

logger = logging.getLogger(__name__)


class RequestType(str, Enum):
    """أنواع الطلبات المختلفة."""
    CHAT = "chat"
    REASONING = "reasoning"
    ANALYSIS = "analysis"
    GENERATION = "generation"
    TRAINING = "training"


@dataclass
class BrainRequest:
    """طلب يدخل Hajeen Brain v3."""
    request_id: str
    user_message: str
    session_id: str
    user_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    stream: bool = False
    max_tokens: int = 2048
    temperature: float = 0.7
    force_model: Optional[str] = None
    request_type: RequestType = RequestType.CHAT
    created_at: float = field(default_factory=time.time)


@dataclass
class ExecutionTrace:
    """تتبع تنفيذ الطلب عبر جميع الطبقات."""
    request_id: str
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # الطبقات التي مرّ عليها الطلب
    policy_evaluation: Dict[str, Any] = field(default_factory=dict)
    intent_analysis: Dict[str, Any] = field(default_factory=dict)
    goal_analysis: Dict[str, Any] = field(default_factory=dict)
    context_analysis: Dict[str, Any] = field(default_factory=dict)
    reasoning_result: Dict[str, Any] = field(default_factory=dict)
    decomposition: Dict[str, Any] = field(default_factory=dict)
    planning: Dict[str, Any] = field(default_factory=dict)
    decision: Dict[str, Any] = field(default_factory=dict)
    execution: Dict[str, Any] = field(default_factory=dict)
    reflection: Dict[str, Any] = field(default_factory=dict)
    
    # المقاييس
    total_latency_ms: float = 0.0
    tokens_used: int = 0
    cost_usd: float = 0.0
    quality_score: float = 0.0
    
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "layers": {
                "policy": self.policy_evaluation,
                "intent": self.intent_analysis,
                "goal": self.goal_analysis,
                "context": self.context_analysis,
                "reasoning": self.reasoning_result,
                "decomposition": self.decomposition,
                "planning": self.planning,
                "decision": self.decision,
                "execution": self.execution,
                "reflection": self.reflection,
            },
            "metrics": {
                "total_latency_ms": round(self.total_latency_ms, 1),
                "tokens_used": self.tokens_used,
                "cost_usd": round(self.cost_usd, 6),
                "quality_score": round(self.quality_score, 3),
            },
            "created_at": self.created_at,
        }


@dataclass
class BrainResponse:
    """استجابة Hajeen Brain v3."""
    request_id: str
    session_id: str
    content: str
    
    # المسار والقرارات
    trace: ExecutionTrace
    
    # النموذج والتعاون
    model_used: str
    models_collaborated: List[str]
    
    # الجودة والأداء
    quality_score: float
    policy_decision: str
    
    # الاستقلالية
    used_local_model: bool
    used_rag: bool
    
    # البيانات الوصفية
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "content": self.content,
            "trace": self.trace.to_dict(),
            "model_used": self.model_used,
            "models_collaborated": self.models_collaborated,
            "quality_score": round(self.quality_score, 3),
            "policy_decision": self.policy_decision,
            "sovereignty": {
                "used_local_model": self.used_local_model,
                "used_rag": self.used_rag,
            },
        }


class HajeenBrainV3:
    """
    العقل المدبّر المركزي v3 — لا توجد مسارات مختصرة.

    كل طلب يمر عبر:
    1. Policy Engine — فحص أمان وأخلاقيات
    2. Intent Analyzer — فهم النية الحقيقية (استدلالي)
    3. Goal Analyzer — تحويل إلى أهداف (استدلالي)
    4. Context Analyzer — تحليل السياق والذاكرة
    5. Reasoning Engine — استدلال عميق
    6. Task Decomposer — تفكيك إلى مهام
    7. Graph Planner — بناء خطة التنفيذ
    8. Decision Engine — اختيار الموارد
    9. Model Router / Multi-Model — التنفيذ
    10. Knowledge Distillation — استخلاص المعرفة
    11. Self Reflection — التقييم الذاتي
    12. Sovereignty Layer — تسجيل الاستقلالية

    لا توجد استثناءات أو مسارات مختصرة.
    """

    VERSION = "3.0.0"
    
    def __init__(self) -> None:
        logger.info("HajeenBrain v%s: تهيئة العقل المدبّر المركزي...", self.VERSION)
        
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

        # ── المكوّنات المعرفية (Cognitive Layer) ────────────────────────
        self.intent_analyzer: IntentAnalyzer = get_intent_analyzer()
        self.context_analyzer: ContextAnalyzer = get_context_analyzer(
            memory_fabric=self.memory
        )
        self.reasoning_engine: ReasoningEngine = get_reasoning_engine()
        
        # تحديث Decision Engine
        self.decision_engine._performance_db = self.performance_db
        self.decision_engine._policy_engine = self.policy
        
        # إحصائيات عامة
        self._active_requests: Dict[str, BrainRequest] = {}
        self._execution_traces: Dict[str, ExecutionTrace] = {}
        self._stats = {
            "total_requests": 0,
            "successful": 0,
            "failed": 0,
            "blocked_by_policy": 0,
            "avg_latency_ms": 0.0,
            "total_tokens": 0,
        }
        
        logger.info("HajeenBrain v%s: جاهز ✓", self.VERSION)

    async def stream(self, request: BrainRequest) -> AsyncGenerator[str, None]:
        """
        المسار الموحد لمعالجة أي طلب متدفق.
        """
        request.stream = True # Ensure stream is true for this method
        async for chunk in self._process_internal(request):
            yield chunk

    async def process(self, request: BrainRequest) -> BrainResponse:
        """
        المسار الموحد لمعالجة أي طلب غير متدفق.
        """
        request.stream = False # Ensure stream is false for this method
        result = await self._process_internal(request)
        if isinstance(result, AsyncGenerator):
            # Consume the generator to get the full response
            full_content = ""
            async for chunk in result:
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        import ast
                        data_dict = ast.literal_eval(data_str)
                        if "content" in data_dict:
                            full_content += data_dict["content"]
                    except Exception as e:
                        logger.debug("Failed to parse stream chunk during non-streaming process: %s", e)
                        full_content += data_str # Fallback
            # Reconstruct BrainResponse from the trace and full_content
            trace = self._execution_traces.get(request.request_id, ExecutionTrace(request_id=request.request_id))
            return BrainResponse(
                request_id=request.request_id,
                session_id=request.session_id,
                content=full_content,
                trace=trace,
                model_used=trace.execution.get("model_used", "unknown"),
                models_collaborated=trace.execution.get("models_collaborated", []),
                quality_score=trace.quality_score,
                policy_decision=trace.policy_evaluation.get("decision", "unknown"),
                used_local_model=trace.execution.get("used_local_model", False),
                used_rag=trace.execution.get("used_rag", False),
                metadata=request.context,
            )
        return result # Should be BrainResponse if not streaming


    async def _process_internal(self, request: BrainRequest) -> BrainResponse | AsyncGenerator[str, None]:
        """
        المسار الموحد لمعالجة أي طلب.
        لا يجوز لأي طلب أن يتجاوز هذه الدالة أو يأخذ مسار مختصر.
        """
        t0 = time.perf_counter()
        request_id = request.request_id
        self._active_requests[request_id] = request
        
        # إنشاء trace لتتبع الطلب
        trace = ExecutionTrace(request_id=request_id)
        self._execution_traces[request_id] = trace
        
        self._stats["total_requests"] += 1
        
        try:
            logger.info("brain_v3.process: request_id=%s user_message=%s", 
                       request_id, request.user_message[:50])
            
            # ── Step 0: استعادة سياق الجلسة ────────────────────────────────
            # Get or create session and conversation memory
            session = self.memory.get_session(request.session_id)
            conversation = self.memory.get_conversation(request.session_id)
            conversation.add_message("user", request.user_message)

            # If a system prompt is provided in the request context, add it to the conversation memory
            if request.context.get("system_prompt"):
                conversation.add_message("system", request.context["system_prompt"]) # Add system prompt to conversation history
            
            # ── Step 1: Policy Engine — تحقق من الأمان قبل أي شيء ──────────
            t1 = time.perf_counter()
            policy_ctx = {
                "query": request.user_message,
                "session_id": request.session_id,
                "estimated_tokens": request.max_tokens,
                "request_type": request.request_type.value,
            }
            policy_eval = await self.policy.evaluate(policy_ctx)
            trace.policy_evaluation = {
                "blocked": policy_eval.blocked,
                "decision": policy_eval.final_decision,
                "latency_ms": (time.perf_counter() - t1) * 1000,
            }
            
            if policy_eval.blocked:
                self._stats["blocked_by_policy"] += 1
                blocked_msg = f"⚠️ تم رفض الطلب: {policy_eval.rule_results[0].reason if policy_eval.rule_results else 'سياسة الأمان'}"
                logger.warning("brain_v3.process: request blocked by policy: %s", request_id)
                return self._build_response(
                    request, blocked_msg, trace, "blocked", [], 0.0, 
                    policy_eval.final_decision, False, False,
                    (time.perf_counter() - t0) * 1000,
                )
            
            # ── Step 2: Intent Analyzer — فهم النية الحقيقية (استدلالي) ─────
            t2 = time.perf_counter()
            intent: Intent = await self.intent_analyzer.analyze(
                user_message=request.user_message,
                context={"session_id": request.session_id, **request.context},
            )
            trace.intent_analysis = {
                "intent_id": intent.intent_id,
                "category": intent.category.value if hasattr(intent.category, "value") else str(intent.category),
                "primary_intent": intent.primary_intent,
                "secondary_intents": intent.secondary_intents,
                "implicit_requirements": intent.implicit_requirements,
                "confidence": intent.confidence,
                "reasoning": intent.reasoning,
                "latency_ms": round((time.perf_counter() - t2) * 1000, 1),
            }

            # ── Goal Analysis ──────────────────────────────────────────────
            t2b = time.perf_counter()
            goal = await self.goal_manager.analyze(
                request.user_message,
                context={
                    "session_id": request.session_id,
                    "intent": intent.primary_intent,
                    **request.context,
                },
            )
            trace.goal_analysis = {
                "goal_id": goal.goal_id,
                "final_objective": goal.final_objective,
                "complexity": goal.complexity,
                "domain": goal.domain,
                "latency_ms": round((time.perf_counter() - t2b) * 1000, 1),
            }
            
            # ── Step 3: Context Analyzer — تحليل السياق والذاكرة ──────────
            t3 = time.perf_counter()
            ctx_analysis: ContextAnalysis = await self.context_analyzer.analyze(
                user_message=request.user_message,
                session_id=request.session_id,
                user_id=request.user_id,
                additional_context={
                    "intent": intent.primary_intent,
                    "goal": goal.final_objective,
                    **request.context,
                },
            )
            trace.context_analysis = {
                "analysis_id": ctx_analysis.analysis_id,
                "detected_domain": ctx_analysis.detected_domain,
                "domain_expertise": ctx_analysis.domain_expertise_level,
                "estimated_complexity": ctx_analysis.estimated_complexity,
                "relevant_memories_count": len(ctx_analysis.relevant_memories),
                "constraints": ctx_analysis.constraints,
                "priorities": ctx_analysis.priorities,
                "time_sensitivity": ctx_analysis.time_sensitivity,
                "conversation_length": len(conversation.get_window()),
                "confidence": ctx_analysis.confidence,
                "latency_ms": round((time.perf_counter() - t3) * 1000, 1),
            }
            
            # ── Step 4: Reasoning Engine — استدلال عميق ─────────────────
            t4 = time.perf_counter()
            reasoning: ReasoningResult = await self.reasoning_engine.reason(
                problem=request.user_message,
                context={
                    "intent": intent.primary_intent,
                    "goal": goal.final_objective,
                    "domain": ctx_analysis.detected_domain,
                    "complexity": ctx_analysis.estimated_complexity,
                    "constraints": ctx_analysis.constraints,
                    "relevant_memories": ctx_analysis.relevant_memories[:3],
                },
            )
            trace.reasoning_result = {
                "result_id": reasoning.result_id,
                "strategy": reasoning.strategy.value if hasattr(reasoning.strategy, "value") else str(reasoning.strategy),
                "recommended_solution": reasoning.recommended_solution.title if reasoning.recommended_solution else None,
                "steps_count": len(reasoning.reasoning_steps),
                "risks_count": len(reasoning.risks),
                "options_count": len(reasoning.solution_options),
                "confidence": reasoning.confidence,
                "missing_info": reasoning.missing_information,
                "latency_ms": round((time.perf_counter() - t4) * 1000, 1),
            }
            
            # ── Step 5: Task Decomposer — تفكيك إلى مهام ───────────────────
            t5 = time.perf_counter()
            plan = await self.task_decomposer.decompose(goal)
            trace.decomposition = {
                "plan_id": plan.plan_id,
                "task_count": len(plan.tasks),
                "latency_ms": (time.perf_counter() - t5) * 1000,
            }
            
            # ── Step 6: Graph Planner — بناء خطة التنفيذ ───────────────────
            t6 = time.perf_counter()
            graph = await self.graph_planner.build_graph(plan)
            trace.planning = {
                "graph_id": graph.graph_id,
                "node_count": len(graph.nodes),
                "edge_count": len(graph.edges),
                "latency_ms": (time.perf_counter() - t6) * 1000,
            }
            
            # ── Step 7: Decision Engine — اختيار الموارد ───────────────────
            t7 = time.perf_counter()
            decision = await self.decision_engine.decide(
                task_id=plan.tasks[0].task_id if plan.tasks else request_id,
                goal=goal,
                task_name=goal.final_objective,
                context={"force_model": request.force_model},
            )
            
            # تطبيق force_model إذا وُجد
            if request.force_model:
                decision.primary_model = request.force_model
            
            trace.decision = {
                "primary_model": decision.primary_model,
                "use_multi_model": decision.use_multi_model,
                "use_rag": decision.use_rag,
                "reasoning": decision.reasoning,
                "latency_ms": (time.perf_counter() - t7) * 1000,
            }
            
            # ── Step 8: إنشاء مهمة في State Machine ────────────────────────
            task_lifecycle = self.state_machine.create_task(
                task_id=request_id,
                max_retries=2,
                metadata={"goal_id": goal.goal_id, "session_id": request.session_id},
            )
            await self.state_machine.transition(request_id, TaskState.PLANNING, "Goal analyzed")
            
            # ── Step 9: تنفيذ الطلب ─────────────────────────────────────────
            await self.state_machine.transition(request_id, TaskState.RUNNING, "Executing")
            
            t_exec = time.perf_counter()
            
            # Prepare messages for the model router
            messages = conversation.get_window() # Get recent conversation history
            if request.context.get("system_prompt"): # Add system prompt if provided
                messages.insert(0, {"role": "system", "content": request.context["system_prompt"]})
            else:
                messages.insert(0, {"role": "system", "content": self._build_system_prompt(goal)})

            model_used = decision.primary_model
            models_collaborated: List[str] = []
            response_content = ""
            tokens_used = 0
            
            if decision.use_multi_model and decision.collaborating_models:
                # تعاون عدة نماذج
                all_models = [decision.primary_model] + decision.collaborating_models
                collab_result = await self.collaborator.collaborate(
                    query=request.user_message,
                    models=all_models[:3],
                    strategy=CollaborationStrategy.CHAIN,
                )
                response_content = collab_result.final_answer
                models_collaborated = collab_result.models_used
                tokens_used = collab_result.total_tokens
                model_used = all_models[0]
            else:
                # نموذج واحد عبر ModelRouter
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
            
            latency_exec_ms = (time.perf_counter() - t_exec) * 1000
            trace.execution = {
                "model_used": model_used,
                "models_collaborated": models_collaborated,
                "tokens_used": tokens_used,
                "latency_ms": latency_exec_ms,
            }
            
            # ── Step 10: تسجيل الأداء ────────────────────────────────────────
            is_local = self._is_local_model(model_used)
            quality_score = self._estimate_quality(response_content)
            cost_usd = self._estimate_cost(model_used, tokens_used)
            
            self.performance_db.record_call(
                model_id=model_used,
                provider=self._get_provider(model_used),
                task_type=goal.intent,
                domain=goal.domain,
                latency_ms=latency_exec_ms,
                tokens_used=tokens_used,
                quality_score=quality_score,
                success=bool(response_content),
                cost_usd=cost_usd,
            )
            
            # ── Step 11: Knowledge Distillation ─────────────────────────────
            asyncio.create_task(
                self.distillation.distill(
                    source_model=model_used,
                    query=request.user_message,
                    response=response_content,
                    task_type=goal.intent,
                    domain=goal.domain,
                    latency_ms=latency_exec_ms,
                )
            )
            
            # ── Step 12: تحديث الذاكرة ─────────────────────────────────────
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
            
            # ── Step 13: Sovereignty Layer — تسجيل الاستقلالية ─────────────
            self.sovereignty.record_request(
                model_id=model_used,
                is_local=is_local,
                used_rag=decision.use_rag,
                domain=goal.domain,
                quality_score=quality_score,
            )
            
            # ── Step 14: Self Reflection (في الخلفية) ────────────────────
            total_latency_ms = (time.perf_counter() - t0) * 1000
            trace.reflection = {
                "pending": True,
                "scheduled": True,
            }
            
            asyncio.create_task(
                self.reflection.reflect(
                    task_id=request_id,
                    goal_id=goal.goal_id,
                    model_used=model_used,
                    actual_latency_ms=total_latency_ms,
                    actual_tokens=tokens_used,
                    estimated_tokens=request.max_tokens,
                    response_quality=quality_score,
                    policy_decision=policy_eval.final_decision,
                )
            )
            
            # ── Step 15: Autonomous Improvement (في الخلفية) ──────────────
            asyncio.create_task(
                self.improvement.process_feedback(
                    request_id=request_id,
                    model_used=model_used,
                    quality_score=quality_score,
                    latency_ms=total_latency_ms,
                    tokens_used=tokens_used,
                    success=True,
                )
            )
            
            # تحديث حالة المهمة
            await self.state_machine.transition(request_id, TaskState.COMPLETED, "Execution finished")
            
            # تحديث الإحصائيات
            self._stats["successful"] += 1
            self._stats["avg_latency_ms"] = (
                (self._stats["avg_latency_ms"] * (self._stats["total_requests"] - 1)) + total_latency_ms
            ) / self._stats["total_requests"]
            self._stats["total_tokens"] += tokens_used
            
            # إرجاع الاستجابة
            return self._build_response(
                request, response_content, trace, quality_score, models_collaborated,
                quality_score, decision.primary_model, is_local, decision.use_rag,
                total_latency_ms,
            )

        except Exception as e:
            logger.error("brain_v3.process: خطأ في المعالجة لـ %s: %s", request_id, e, exc_info=True)
            self._stats["failed"] += 1
            await self.state_machine.transition(request_id, TaskState.FAILED, f"Error: {e}")
            
            # إذا كان هناك خطأ، نُرجع استجابة خطأ
            error_msg = f"حدث خطأ أثناء معالجة طلبك: {e}"
            return self._build_response(
                request, error_msg, trace, "error", [], 0.0, 
                "error", False, False,
                (time.perf_counter() - t0) * 1000,
            )
        finally:
            del self._active_requests[request_id]

    def _build_system_prompt(self, goal: Goal) -> str:
        """
        يبني الـ system prompt بناءً على الهدف.
        """
        base_prompt = "أنت مساعد ذكاء اصطناعي مفيد ودقيق."
        if goal.final_objective:
            base_prompt += f" هدفك الأساسي هو: {goal.final_objective}."
        if goal.domain:
            base_prompt += f" أنت متخصص في مجال {goal.domain}."
        return base_prompt

    def _fallback_response(self, user_message: str, goal: Goal) -> str:
        """
        استجابة احتياطية في حال فشل التوليد.
        """
        return f"عذراً، لم أتمكن من توليد استجابة كاملة لطلبك: \"{user_message}\". يرجى المحاولة مرة أخرى أو إعادة صياغة طلبك. (الهدف: {goal.final_objective})"

    def _estimate_quality(self, response_content: str) -> float:
        """
        تقدير جودة الاستجابة (placeholder).
        """
        return 0.75 # قيمة افتراضية

    def _estimate_cost(self, model_id: str, tokens: int) -> float:
        """
        تقدير التكلفة (placeholder).
        """
        # مثال بسيط: 0.001 دولار لكل 1000 توكن
        return (tokens / 1000) * 0.001

    def _is_local_model(self, model_id: str) -> bool:
        """
        التحقق مما إذا كان النموذج محلياً (placeholder).
        """
        return "ollama" in model_id.lower() or "local" in model_id.lower()

    def _get_provider(self, model_id: str) -> str:
        """
        الحصول على مزود النموذج (placeholder).
        """
        if "ollama" in model_id.lower():
            return "Ollama"
        if "gpt" in model_id.lower():
            return "OpenAI"
        return "Unknown"

    def _build_response(
        self, 
        request: BrainRequest, 
        content: str, 
        trace: ExecutionTrace, 
        quality_score_str: str, # Changed type to str to match 
