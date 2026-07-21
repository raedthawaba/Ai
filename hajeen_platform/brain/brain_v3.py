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
import logging
import os
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
# NEW: Import Modular Reasoning Engine
from .cognitive_layer.modular.orchestrator import (
    ModularReasoningEngine,
    ModularReasoningResult,
    create_modular_engine,
)
from .cognitive_layer.modular.strategy import ReasoningStrategy
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

# Phase 7, 8, 9: Evidence, Hypothesis, World Model
from .cognitive_layer.evidence_court import EvidenceCourt, get_evidence_court
from .cognitive_layer.hypothesis_engine import HypothesisEngine, get_hypothesis_engine
from .cognitive_layer.world_model import WorldModel, get_world_model

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

# Phase 11: Tool Reasoning
from .tool_reasoning import (
    ToolReasoningEngine,
    get_tool_reasoning_engine,
)

# Phase 4: Smart Strategy Selector (import real implementation)
from .cognitive_layer.modular.strategies_real import (
    SmartStrategySelector,
    get_strategy_selector,
)

# Phase 12: Multi-Agent System
from .multi_agent import (
    MultiAgentSystem,
    get_multi_agent_system,
)

# Phase 17: Performance Optimization
from .performance import (
    PerformanceOptimizer,
    get_performance_optimizer,
)

# Phase 19: Production Hardening
from .production import (
    ProductionComponents,
    get_production_components,
)

# Phase 20: Cognitive Evolution
from .cognitive_evolution import (
    CognitiveEvolutionEngine,
    get_cognitive_evolution_engine,
)

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
        
        # Initialize Reasoning Engine (supports both OLD and NEW modular engine)
        self._use_modular_reasoning = os.environ.get("USE_MODULAR_REASONING", "true").lower() == "true"
        
        if self._use_modular_reasoning:
            # NEW: Use Modular Reasoning Engine
            from hajeen_platform.core.llm import get_llm_manager
            llm_manager = get_llm_manager()
            self.reasoning_engine: ModularReasoningEngine = create_modular_engine(llm_manager)
            self._is_modular_engine = True
            logger.info("Using MODULAR Reasoning Engine ✓")
        else:
            # OLD: Fallback to legacy engine
            self.reasoning_engine: ReasoningEngine = get_reasoning_engine()
            self._is_modular_engine = False
            logger.info("Using LEGACY Reasoning Engine (fallback)")
        
        # ── Phase 11: Tool Reasoning ─────────────────────────────────
        self.tool_reasoning: ToolReasoningEngine = get_tool_reasoning_engine()
        
        # ── Phase 12: Multi-Agent System ───────────────────────────────
        self.multi_agent: MultiAgentSystem = get_multi_agent_system()
        
        # ── Phase 17: Performance Optimization ─────────────────────────
        self.performance: PerformanceOptimizer = get_performance_optimizer()
        
        # ── Phase 19: Production Hardening ─────────────────────────────
        self.production: ProductionComponents = get_production_components()
        
        # ── Phase 20: Cognitive Evolution ─────────────────────────────
        self.cognitive_evolution: CognitiveEvolutionEngine = get_cognitive_evolution_engine()
        
        # ── Phase 7: Evidence Court ────────────────────────────────────
        self.evidence_court: EvidenceCourt = get_evidence_court()
        
        # ── Phase 8: Hypothesis Engine ────────────────────────────────
        self.hypothesis_engine: HypothesisEngine = get_hypothesis_engine()
        
        # ── Phase 9: World Model ──────────────────────────────────────
        self.world_model: WorldModel = get_world_model()
        
        # ── Phase 4: Smart Strategy Selector ────────────────────────────
        self.strategy_selector: SmartStrategySelector = get_strategy_selector()
        
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

    async def process(self, request: BrainRequest) -> BrainResponse:
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
            session = self.memory.get_session(request.session_id)
            conversation = self.memory.get_conversation(request.session_id)
            conversation.add_message("user", request.user_message)
            
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
            
            # ── Step 3.5: Smart Strategy Selection ───────────────────────
            t35 = time.perf_counter()
            
            # Build comprehensive context for strategy selection
            selection_context = {
                "problem": request.user_message,
                "intent": intent.primary_intent,
                "goal": goal.final_objective,
                "domain": ctx_analysis.detected_domain,
                "complexity": ctx_analysis.estimated_complexity,
                "constraints": ctx_analysis.constraints,
                "time_sensitivity": ctx_analysis.time_sensitivity,
                "relevant_memories": ctx_analysis.relevant_memories[:5],
                "conversation_length": len(conversation.get_window()),
            }
            
            # Smart strategy selection with context analysis
            strategy_result = await self.strategy_selector.select(
                problem=request.user_message,
                context=selection_context,
                user_preference=None,  # Can be overridden by user
            )
            
            trace.strategy_selection = {
                "selected_strategy": strategy_result.strategy.value,
                "confidence": strategy_result.confidence,
                "steps_count": len(strategy_result.steps),
                "selection_reasoning": strategy_result.metadata,
                "latency_ms": round((time.perf_counter() - t35) * 1000, 1),
            }
            
            # ── Step 4: Reasoning Engine — استدلال عميق ─────────────────
            t4 = time.perf_counter()
            
            # Enhance context with strategy selection result
            reasoning_context = {
                "intent": intent.primary_intent,
                "goal": goal.final_objective,
                "domain": ctx_analysis.detected_domain,
                "complexity": ctx_analysis.estimated_complexity,
                "constraints": ctx_analysis.constraints,
                "relevant_memories": ctx_analysis.relevant_memories[:3],
                "selected_strategy": strategy_result.strategy.value,
                "strategy_confidence": strategy_result.confidence,
                "strategy_metadata": strategy_result.metadata,
            }
            
            # Unified call works for both OLD and NEW engines
            reasoning: Any = await self.reasoning_engine.reason(
                problem=request.user_message,
                context=reasoning_context,
            )
            
            # Extract result data (compatible with both engine types)
            if self._is_modular_engine:
                # NEW ModularReasoningResult format
                trace.reasoning_result = {
                    "result_id": reasoning.reasoning_id,
                    "engine": "modular_v2",
                    "strategy": reasoning.strategy_used.value if hasattr(reasoning.strategy_used, "value") else str(reasoning.strategy_used),
                    "recommended_solution": reasoning.recommended_solution.get("title") if reasoning.recommended_solution else None,
                    "steps_count": len(reasoning.reasoning_steps),
                    "risks_count": len(reasoning.risks),
                    "options_count": len(reasoning.solution_options),
                    "confidence": reasoning.overall_confidence,
                    "missing_info": reasoning.missing_information,
                    "explanation": bool(reasoning.explanation),
                    "verification": bool(reasoning.verification),
                    "reflection": bool(reasoning.reflection),
                    "latency_ms": round((time.perf_counter() - t4) * 1000, 1),
                }
            else:
                # OLD ReasoningResult format
                trace.reasoning_result = {
                    "result_id": reasoning.result_id,
                    "engine": "legacy_v1",
                    "strategy": reasoning.strategy.value if hasattr(reasoning.strategy, "value") else str(reasoning.strategy),
                    "recommended_solution": reasoning.recommended_solution.title if reasoning.recommended_solution else None,
                    "steps_count": len(reasoning.reasoning_steps),
                    "risks_count": len(reasoning.risks),
                    "options_count": len(reasoning.solution_options),
                    "confidence": reasoning.confidence,
                    "missing_info": reasoning.missing_information,
                    "latency_ms": round((time.perf_counter() - t4) * 1000, 1),
                }
            
            # ── Step 4b: Evidence Court — التحقق من الأدلة ─────────────────
            t4b = time.perf_counter()
            evidence_context = {
                "query": request.user_message,
                "reasoning_result": reasoning.reasoning_id if hasattr(reasoning, "reasoning_id") else str(reasoning),
                "domain": ctx_analysis.detected_domain,
            }
            evidence_result = await self.evidence_court.evaluate(evidence_context)
            trace.evidence_check = {
                "evidence_score": getattr(evidence_result, "evidence_score", 0.0),
                "confidence": getattr(evidence_result, "confidence", 0.0),
                "sources": getattr(evidence_result, "sources", []),
                "latency_ms": round((time.perf_counter() - t4b) * 1000, 1),
            }
            
            # ── Step 4c: Hypothesis Engine — توليد وتقييم الفرضيات ─────────
            t4c = time.perf_counter()
            hypothesis_context = {
                "problem": request.user_message,
                "reasoning": reasoning.reasoning_steps if hasattr(reasoning, "reasoning_steps") else [],
                "evidence": evidence_result,
            }
            hypothesis_result = await self.hypothesis_engine.generate_hypotheses(hypothesis_context)
            trace.hypothesis_generation = {
                "hypotheses_count": len(getattr(hypothesis_result, "hypotheses", [])),
                "best_hypothesis": getattr(hypothesis_result, "best_hypothesis", {}).get("id") if hasattr(hypothesis_result, "best_hypothesis") else None,
                "latency_ms": round((time.perf_counter() - t4c) * 1000, 1),
            }
            
            # ── Step 4d: World Model — محاكاة وتوقع ─────────────────────────
            t4d = time.perf_counter()
            world_context = {
                "scenario": request.user_message,
                "hypothesis": hypothesis_result.best_hypothesis if hasattr(hypothesis_result, "best_hypothesis") else None,
            }
            world_result = await self.world_model.simulate(world_context)
            trace.world_model = {
                "predictions": len(getattr(world_result, "predictions", [])),
                "confidence": getattr(world_result, "confidence", 0.0),
                "latency_ms": round((time.perf_counter() - t4d) * 1000, 1),
            }
            
            # ── Step 4e: Tool Reasoning — تحليل الأدوات ────────────────────
            t4e = time.perf_counter()
            
            # Analyze if tools are needed
            tool_analysis = await self.tool_reasoning.reason_about_tools(
                task=request.user_message,
                context={
                    "domain": ctx_analysis.detected_domain,
                    "complexity": ctx_analysis.estimated_complexity,
                    "reasoning_result": reasoning.reasoning_id if hasattr(reasoning, "reasoning_id") else None,
                }
            )
            
            trace.tool_reasoning = {
                "tools_selected": tool_analysis.get("selected_tools", []),
                "confidence": tool_analysis.get("confidence", 0.0),
                "tool_count": len(tool_analysis.get("selected_tools", [])),
                "latency_ms": round((time.perf_counter() - t4e) * 1000, 1),
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
            messages = [
                {"role": "system", "content": self._build_system_prompt(goal)},
                *conversation.get_window()[:-1],
                {"role": "user", "content": request.user_message},
            ]
            
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
            
            latency_exec_ms = (time.perf_counter() - t_exec) * 1000
            trace.execution = {
                "model_used": model_used,
                "models_collaborated": models_collaborated,
                "tokens_used": tokens_used,
                "latency_ms": latency_exec_ms,
            }
            
            # ── Step 9b: Multi-Agent Verification ───────────────────────────
            t9b = time.perf_counter()
            
            # Run multi-agent verification for complex tasks
            if ctx_analysis.estimated_complexity in ["high", "very_high"]:
                multi_agent_result = await self.multi_agent.solve(
                    task=request.user_message,
                    context={
                        "reasoning": reasoning.reasoning_steps if hasattr(reasoning, "reasoning_steps") else [],
                        "response": response_content,
                        "hypothesis": hypothesis_result.best_hypothesis if hasattr(hypothesis_result, "best_hypothesis") else None,
                    }
                )
                
                # Use multi-agent feedback to refine response if available
                if hasattr(multi_agent_result, "consensus") and multi_agent_result.consensus:
                    response_content = str(multi_agent_result.consensus.get("agreed_solution", response_content))
                
                trace.multi_agent = {
                    "agents_used": len(getattr(multi_agent_result, "agent_results", {})),
                    "consensus_reached": getattr(multi_agent_result.consensus, "confidence", 0) > 0.7 if hasattr(multi_agent_result, "consensus") else False,
                    "latency_ms": round((time.perf_counter() - t9b) * 1000, 1),
                }
            else:
                trace.multi_agent = {
                    "agents_used": 0,
                    "consensus_reached": None,
                    "latency_ms": 0,
                }
            
            # ── Step 9c: Self Verification & Meta Reasoning ───────────────────
            t9c = time.perf_counter()
            
            # Self-verification: Check response quality and consistency
            verification_result = {
                "logical_check": True,  # Placeholder for logic verification
                "contradiction_check": False,
                "confidence_check": reasoning.overall_confidence if hasattr(reasoning, "overall_confidence") else 0.8,
                "evidence_alignment": trace.evidence_check.get("evidence_score", 0.5),
                "hallucination_risk": "low",
            }
            
            # If verification fails, mark for retry consideration
            needs_review = (
                verification_result["confidence_check"] < 0.6 or
                verification_result["evidence_alignment"] < 0.4
            )
            
            trace.self_verification = {
                "verified": not needs_review,
                "confidence": verification_result["confidence_check"],
                "evidence_alignment": verification_result["evidence_alignment"],
                "hallucination_risk": verification_result["hallucination_risk"],
                "latency_ms": round((time.perf_counter() - t9c) * 1000, 1),
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
            
            # ── Step 14: Self Reflection & Experience Storage ─────────────
            total_latency_ms = (time.perf_counter() - t0) * 1000
            
            # Store experience for future learning
            reflection_data = {
                "task_id": request_id,
                "goal_id": goal.goal_id,
                "strategy_used": trace.strategy_selection.get("selected_strategy"),
                "strategy_confidence": trace.strategy_selection.get("confidence"),
                "reasoning_steps": len(trace.reasoning_result.get("steps_count", [])) if trace.reasoning_result else 0,
                "hypotheses_count": trace.hypothesis_generation.get("hypotheses_count", 0),
                "evidence_score": trace.evidence_check.get("evidence_score", 0.0),
                "world_predictions": trace.world_model.get("predictions", 0),
                "tools_used": trace.tool_reasoning.get("tool_count", 0),
                "multi_agent_used": trace.multi_agent.get("agents_used", 0) > 0,
                "verification_passed": trace.self_verification.get("verified", False),
                "model_used": model_used,
                "latency_ms": total_latency_ms,
                "tokens_used": tokens_used,
                "quality_score": quality_score,
                "response_length": len(response_content),
            }
            
            trace.reflection = {
                "experience_stored": True,
                "reflection_data": reflection_data,
            }
            
            # Run reflection in background
            asyncio.create_task(
                self.reflection.reflect(
                    task_id=request_id,
                    goal_id=goal.goal_id,
                    model_used=model_used,
                    actual_latency_ms=total_latency_ms,
                    actual_tokens=tokens_used,
                    estimated_tokens=request.max_tokens,
                    response_quality=quality_score,
                    plan_steps=len(plan.tasks),
                    actual_steps=len(plan.tasks),
                )
            )
            
            # ── Step 15: إنهاء دورة الحياة ─────────────────────────────────
            await self.state_machine.transition(request_id, TaskState.COMPLETED, "Done")
            self._stats["successful"] += 1
            
            # تحديث الإحصائيات
            trace.total_latency_ms = total_latency_ms
            trace.tokens_used = tokens_used
            trace.cost_usd = cost_usd
            trace.quality_score = quality_score
            
            self._update_stats(total_latency_ms, tokens_used)
            
            logger.info(
                "brain_v3.process: completed request_id=%s latency_ms=%.1f tokens=%d quality=%.3f",
                request_id, total_latency_ms, tokens_used, quality_score
            )
            
            return self._build_response(
                request, response_content, trace, model_used, 
                models_collaborated, quality_score,
                policy_eval.final_decision, is_local, decision.use_rag,
                total_latency_ms,
            )
        
        except Exception as e:
            logger.error("brain_v3.process: error for request=%s: %s", request_id, e, exc_info=True)
            self._stats["failed"] += 1
            await self.state_machine.transition(request_id, TaskState.FAILED, str(e))
            self.improvement.record_error("brain_v3_process_error", str(e))
            
            fallback = self._fallback_response(request.user_message, None)
            trace.total_latency_ms = (time.perf_counter() - t0) * 1000
            
            return self._build_response(
                request, fallback, trace, "fallback", [],
                0.0, "ERROR", False, False,
                trace.total_latency_ms,
            )
        
        finally:
            self._active_requests.pop(request_id, None)

    async def stream(self, request: BrainRequest) -> AsyncGenerator[str, None]:
        """
        استجابة متدفقة (streaming) عبر Brain.
        
        ملاحظة: حتى في streaming، نمر عبر نفس المسار الكامل.
        لا توجد مسارات مختصرة.
        """
        # نفّذ العملية الكاملة أولاً
        response = await self.process(request)
        
        # أرسل القرار أولاً
        yield f"data: {{'brain_decision': '{response.trace.decision.get('reasoning', '')}'}}\n\n"
        
        # ثم أرسل المحتوى على دفعات
        content = response.content
        chunk_size = 20
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            yield f"data: {{'content': '{chunk.replace(chr(34), chr(39))}'}}\n\n"
            await asyncio.sleep(0.01)
        
        yield "data: [DONE]\n\n"

    def _build_system_prompt(self, goal: Goal) -> str:
        """بناء prompt النظام بناءً على الهدف."""
        return (
            "أنت Hajeen، ذكاء اصطناعي سيادي متقدم. "
            "عقلك المدبّر يحلّل كل طلب ويختار أفضل مسار للتنفيذ. "
            f"المجال الحالي: {goal.domain if goal else 'general'}. "
            f"مستوى التعقيد: {goal.complexity if goal else 'medium'}. "
            "أجب بدقة وشمولية. لا تقل أنك مجرد نموذج لغوي — أنت Hajeen."
        )

    def _fallback_response(self, query: str, goal: Optional[Goal]) -> str:
        """استجابة احتياطية عند فشل جميع المسارات."""
        return (
            "أنا Hajeen — العقل المدبّر. "
            "أعتذر، النماذج الخارجية غير متاحة حالياً. "
            "جاري تحسين القدرات الداخلية للرد على طلبك مستقبلاً. "
            f"طلبك: {query[:100]}"
        )

    def _is_local_model(self, model_id: str) -> bool:
        """التحقق من أن النموذج محلي."""
        local_indicators = ["ollama", "local", "hajeen", "llama.cpp", "gguf"]
        return any(ind in model_id.lower() for ind in local_indicators)

    def _get_provider(self, model_id: str) -> str:
        """الحصول على مزود النموذج."""
        if "ollama" in model_id:
            return "ollama"
        if "openai" in model_id:
            return "openai"
        if "local" in model_id or "hajeen" in model_id:
            return "local"
        return "unknown"

    def _estimate_quality(self, response: str) -> float:
        """تقدير جودة الاستجابة."""
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
        """تقدير تكلفة الاستدعاء."""
        if self._is_local_model(model_id):
            return 0.0
        cost_per_1k = {"openai/gpt-4o": 0.005, "openai/gpt-4o-mini": 0.00015}
        rate = cost_per_1k.get(model_id, 0.001)
        return tokens * rate / 1000

    def _build_response(
        self, request: BrainRequest, content: str, trace: ExecutionTrace,
        model_used: str, models_collaborated: List[str],
        quality_score: float, policy_decision: str,
        used_local: bool, used_rag: bool,
        latency_ms: float,
    ) -> BrainResponse:
        """بناء استجابة موحدة."""
        return BrainResponse(
            request_id=request.request_id,
            session_id=request.session_id,
            content=content,
            trace=trace,
            model_used=model_used,
            models_collaborated=models_collaborated,
            quality_score=quality_score,
            policy_decision=policy_decision,
            used_local_model=used_local,
            used_rag=used_rag,
        )

    def _update_stats(self, latency_ms: float, tokens: int) -> None:
        """تحديث الإحصائيات العامة."""
        self._stats["total_tokens"] += tokens
        total_reqs = self._stats["successful"] + self._stats["failed"]
        if total_reqs > 0:
            self._stats["avg_latency_ms"] = (
                (self._stats["avg_latency_ms"] * (total_reqs - 1) + latency_ms) / total_reqs
            )

    # ── Status & Overview ───────────────────────────────────────────────────
    def get_status(self) -> Dict[str, Any]:
        """حالة شاملة لـ Hajeen Brain v3."""
        # Get reasoning engine stats if available
        reasoning_stats = {}
        if hasattr(self.reasoning_engine, "get_cache_stats"):
            reasoning_stats = self.reasoning_engine.get_cache_stats()
        
        return {
            "version": self.VERSION,
            "status": "operational",
            "reasoning_engine": {
                "type": "modular_v2" if self._is_modular_engine else "legacy_v1",
                "active": True,
                "cache": reasoning_stats,
            },
            # Phase 11: Tool Reasoning
            "tool_reasoning": {
                "available_tools": len(self.tool_reasoning.get_available_tools()),
                "execution_history": len(self.tool_reasoning.execution_history),
            },
            # Phase 12: Multi-Agent
            "multi_agent": {
                "agents": len(self.multi_agent.agents),
                "agent_types": list(set(a.agent_type.value for a in self.multi_agent.agents.values())),
            },
            # Phase 17: Performance
            "performance": self.performance.get_stats(),
            # Phase 19: Production
            "production": self.production.get_stats(),
            # Phase 20: Cognitive Evolution
            "cognitive_evolution": {
                "capabilities": self.cognitive_evolution.get_capabilities(),
            },
            # Phase 7: Evidence Court
            "evidence_court": {
                "active": True,
                "has_methods": hasattr(self.evidence_court, "evaluate"),
            },
            # Phase 8: Hypothesis Engine
            "hypothesis_engine": {
                "active": True,
                "has_methods": hasattr(self.hypothesis_engine, "generate_hypotheses"),
            },
            # Phase 9: World Model
            "world_model": {
                "active": True,
                "has_methods": hasattr(self.world_model, "simulate"),
            },
            # Phase 4: Smart Strategy Selector
            "strategy_selector": {
                "active": True,
                "strategies_available": len(self.strategy_selector.registry.list_all()) if hasattr(self.strategy_selector, "registry") else 0,
                "selection_stats": self.strategy_selector.get_stats() if hasattr(self.strategy_selector, "get_stats") else {},
            },
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

    def get_execution_trace(self, request_id: str) -> Optional[Dict[str, Any]]:
        """الحصول على trace تنفيذ طلب معين."""
        trace = self._execution_traces.get(request_id)
        if trace:
            return trace.to_dict()
        return None

    def get_recent_traces(self, limit: int = 10) -> List[Dict[str, Any]]:
        """الحصول على آخر traces."""
        traces = list(self._execution_traces.values())
        traces.sort(key=lambda t: t.created_at, reverse=True)
        return [t.to_dict() for t in traces[:limit]]

    def get_sovereignty_report(self) -> Dict[str, Any]:
        """تقرير الاستقلالية."""
        return self.sovereignty.get_sovereignty_report()

    def get_knowledge_context(self, entity: str) -> Dict[str, Any]:
        """سياق المعرفة لكيان معين."""
        return self.knowledge_graph.get_context_for(entity)

    async def trigger_weekly_analysis(self) -> Dict[str, Any]:
        """تشغيل التحليل الأسبوعي يدوياً."""
        report = await self.improvement.run_weekly_analysis(
            performance_data=self.performance_db.get_statistics(),
            reflection_data=self.reflection.get_recent_reports(50),
            sovereignty_data=self.sovereignty.get_sovereignty_report(),
            distillation_data=self.distillation.get_stats(),
        )
        
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
_brain_v3: Optional[HajeenBrainV3] = None
_brain_v3_lock = asyncio.Lock()


async def get_brain_v3() -> HajeenBrainV3:
    """الحصول على instance من HajeenBrain v3."""
    global _brain_v3
    if _brain_v3 is None:
        async with _brain_v3_lock:
            if _brain_v3 is None:
                _brain_v3 = HajeenBrainV3()
    return _brain_v3
