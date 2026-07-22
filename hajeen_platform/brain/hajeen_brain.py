"""
HajeenBrain - Production Entry Point
=====================================

This is the official single entry point for the Hajeen AI Brain system.

Usage:
    from hajeen_platform.brain.hajeen_brain import HajeenBrain
    
    brain = HajeenBrain()
    response = await brain.process(request)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, AsyncGenerator

# Contracts
from .contracts import (
    BrainRequest,
    BrainResponse,
    ReasoningResult,
    PlanningResult,
    DecisionResult,
    ExecutionResult,
    ExecutionMetadata,
    ResponseStatus,
    RequestType,
)

# Engine imports
from .cognitive_layer.intent_analyzer import IntentAnalyzer, Intent, get_intent_analyzer
from .cognitive_layer.context_analyzer import ContextAnalyzer, get_context_analyzer
from .cognitive_layer.reasoning_engine import ReasoningEngine, get_reasoning_engine
from .planning_engine import get_planning_engine
from .task_decomposer import TaskDecomposer, get_task_decomposer
from .graph_planner import GraphPlanner, get_graph_planner
from .decision_engine import DecisionEngineV2, get_decision_engine
from .model_router import ModelRouter, get_model_router
from .memory.memory_fabric import MemoryFabric, get_memory_fabric
from .knowledge.knowledge_graph import KnowledgeGraph, get_knowledge_graph
from .knowledge.knowledge_distillation import KnowledgeDistillationPipeline as KnowledgeDistillation
from .policy.policy_engine import PolicyEngine, get_policy_engine
from .reflection.self_reflection import SelfReflection
from .reflection.self_evolution import SelfEvolution
from .improvement.autonomous_improvement import AutonomousImprovement
from .sovereignty.sovereignty_layer import SovereigntyLayer
from .state_machine import StateMachine, TaskState
from .metrics.model_performance_db import ModelPerformanceDB
from .goal_manager import GoalManager, get_goal_manager


@dataclass
class HajeenBrain:
    """
    HajeenBrain - Official Production Entry Point
    
    This class provides a unified interface to the Hajeen AI Brain system.
    All requests should go through this class.
    
    Architecture:
        Policy → Intent → Context → Reasoning → Planning → Decision → Execution → Learning
    """
    
    # Configuration
    config: Dict[str, Any] = field(default_factory=dict)
    
    # Engine instances (lazy loaded)
    _intent_analyzer: Optional[IntentAnalyzer] = None
    _context_analyzer: Optional[ContextAnalyzer] = None
    _reasoning_engine: Optional[ReasoningEngine] = None
    _planning_engine: Optional[Any] = None
    _task_decomposer: Optional[TaskDecomposer] = None
    _graph_planner: Optional[GraphPlanner] = None
    _decision_engine: Optional[DecisionEngineV2] = None
    _model_router: Optional[ModelRouter] = None
    _memory: Optional[MemoryFabric] = None
    _knowledge_graph: Optional[KnowledgeGraph] = None
    _policy_engine: Optional[PolicyEngine] = None
    _goal_manager: Optional[GoalManager] = None
    
    # Supporting components
    _state_machine: Optional[StateMachine] = None
    _performance_db: Optional[ModelPerformanceDB] = None
    _knowledge_distillation: Optional[KnowledgeDistillation] = None
    _self_reflection: Optional[SelfReflection] = None
    _self_evolution: Optional[SelfEvolution] = None
    _autonomous_improvement: Optional[AutonomousImprovement] = None
    _sovereignty: Optional[SovereigntyLayer] = None
    
    # State
    _initialized: bool = False
    
    @property
    def intent_analyzer(self) -> IntentAnalyzer:
        """Get Intent Analyzer instance"""
        if self._intent_analyzer is None:
            self._intent_analyzer = get_intent_analyzer()
        return self._intent_analyzer
    
    @property
    def context_analyzer(self) -> ContextAnalyzer:
        """Get Context Analyzer instance"""
        if self._context_analyzer is None:
            self._context_analyzer = get_context_analyzer(memory_fabric=self.memory)
        return self._context_analyzer
    
    @property
    def reasoning_engine(self) -> ReasoningEngine:
        """Get Reasoning Engine instance"""
        if self._reasoning_engine is None:
            self._reasoning_engine = get_reasoning_engine()
        return self._reasoning_engine
    
    @property
    def planning_engine(self):
        """Get Planning Engine instance"""
        if self._planning_engine is None:
            self._planning_engine = get_planning_engine()
        return self._planning_engine
    
    @property
    def task_decomposer(self) -> TaskDecomposer:
        """Get Task Decomposer instance"""
        if self._task_decomposer is None:
            self._task_decomposer = get_task_decomposer()
        return self._task_decomposer
    
    @property
    def graph_planner(self) -> GraphPlanner:
        """Get Graph Planner instance"""
        if self._graph_planner is None:
            self._graph_planner = get_graph_planner()
        return self._graph_planner
    
    @property
    def decision_engine(self) -> DecisionEngineV2:
        """Get Decision Engine instance"""
        if self._decision_engine is None:
            self._decision_engine = get_decision_engine()
        return self._decision_engine
    
    @property
    def model_router(self) -> ModelRouter:
        """Get Model Router instance"""
        if self._model_router is None:
            self._model_router = get_model_router()
        return self._model_router
    
    @property
    def memory(self) -> MemoryFabric:
        """Get Memory Fabric instance"""
        if self._memory is None:
            self._memory = get_memory_fabric()
        return self._memory
    
    @property
    def knowledge_graph(self) -> KnowledgeGraph:
        """Get Knowledge Graph instance"""
        if self._knowledge_graph is None:
            self._knowledge_graph = get_knowledge_graph()
        return self._knowledge_graph
    
    @property
    def policy_engine(self) -> PolicyEngine:
        """Get Policy Engine instance"""
        if self._policy_engine is None:
            self._policy_engine = get_policy_engine()
        return self._policy_engine
    
    @property
    def goal_manager(self) -> GoalManager:
        """Get Goal Manager instance"""
        if self._goal_manager is None:
            self._goal_manager = get_goal_manager()
        return self._goal_manager
    
    @property
    def state_machine(self) -> StateMachine:
        """Get State Machine instance"""
        if self._state_machine is None:
            self._state_machine = StateMachine()
        return self._state_machine
    
    @property
    def performance_db(self) -> ModelPerformanceDB:
        """Get Performance DB instance"""
        if self._performance_db is None:
            self._performance_db = ModelPerformanceDB()
        return self._performance_db
    
    async def initialize(self) -> None:
        """Initialize the brain system"""
        if self._initialized:
            return
        
        # Initialize supporting components
        self._knowledge_distillation = KnowledgeDistillation(
            knowledge_graph=self.knowledge_graph
        )
        self._self_reflection = SelfReflection()
        self._self_evolution = SelfEvolution()
        self._autonomous_improvement = AutonomousImprovement(
            performance_db=self.performance_db
        )
        self._sovereignty = SovereigntyLayer()
        
        self._initialized = True
    
    async def process(self, request: BrainRequest) -> BrainResponse:
        """
        Process a user request through the full pipeline.
        
        Pipeline:
            1. Policy Check
            2. Intent Analysis
            3. Context Analysis
            4. Reasoning
            5. Planning
            6. Decision
            7. Execution
            8. Learning
        
        Args:
            request: BrainRequest with user message and context
            
        Returns:
            BrainResponse with the generated response
        """
        start_time = time.perf_counter()
        request_id = str(uuid.uuid4())
        
        # Initialize if needed
        if not self._initialized:
            await self.initialize()
        
        # Response placeholder
        response_content = ""
        errors = []
        warnings = []
        metadata = {}
        
        try:
            # ── Step 1: Policy Check ────────────────────────────────────────
            t_policy = time.perf_counter()
            policy_result = await self.policy_engine.evaluate(request)
            
            if not policy_result.allowed:
                return BrainResponse(
                    content=policy_result.message or "Request not allowed by policy",
                    session_id=request.session_id,
                    status=ResponseStatus.FAILED,
                    errors=[policy_result.message] if policy_result.message else ["Policy violation"],
                )
            
            # ── Step 2: Intent Analysis ──────────────────────────────────────
            t_intent = time.perf_counter()
            intent: Intent = await self.intent_analyzer.analyze(
                user_message=request.user_message,
                context={"session_id": request.session_id}
            )
            metadata["intent_analysis"] = {
                "intent": intent.primary_intent,
                "confidence": intent.confidence,
                "category": intent.category.value if hasattr(intent.category, 'value') else str(intent.category),
            }
            
            # ── Step 3: Context Analysis ───────────────────────────────────────
            t_context = time.perf_counter()
            session = self.memory.get_session(request.session_id)
            conversation = self.memory.get_conversation(request.session_id)
            
            ctx_analysis = await self.context_analyzer.analyze(
                message=request.user_message,
                session=session,
                conversation=conversation,
            )
            metadata["context_analysis"] = {
                "domain": ctx_analysis.detected_domain,
                "complexity": ctx_analysis.estimated_complexity,
            }
            
            # ── Step 4: Reasoning ─────────────────────────────────────────────
            t_reasoning = time.perf_counter()
            reasoning: ReasoningResult = await self.reasoning_engine.reason(
                problem=request.user_message,
                context={
                    "intent": intent.primary_intent,
                    "domain": ctx_analysis.detected_domain,
                    "complexity": ctx_analysis.estimated_complexity,
                },
            )
            metadata["reasoning"] = {
                "strategy": reasoning.strategy.value if hasattr(reasoning.strategy, 'value') else str(reasoning.strategy),
                "confidence": reasoning.confidence,
                "steps_count": len(reasoning.reasoning_steps),
            }
            
            # ── Step 5: Planning ──────────────────────────────────────────────
            t_planning = time.perf_counter()
            
            # Create goal from intent
            goal = await self.goal_manager.analyze(request.user_message)
            
            # Decompose to tasks
            plan = await self.task_decomposer.decompose(goal)
            
            # Build execution graph
            graph = await self.graph_planner.build_graph(plan)
            
            metadata["planning"] = {
                "goal_id": goal.goal_id,
                "tasks": len(plan.tasks),
                "graph_nodes": len(graph.nodes),
            }
            
            # ── Step 6: Decision ───────────────────────────────────────────────
            t_decision = time.perf_counter()
            decision = await self.decision_engine.decide(
                task_id=plan.tasks[0].task_id if plan.tasks else request_id,
                goal=goal,
                task_name=goal.final_objective,
                context={"force_model": request.force_model},
            )
            metadata["decision"] = {
                "model": decision.primary_model,
                "confidence": decision.confidence,
            }
            
            # Apply force_model if provided
            if request.force_model:
                decision.primary_model = request.force_model
            
            # ── Step 7: Execution ─────────────────────────────────────────────
            t_execution = time.perf_counter()
            
            # Route to model
            route_result = await self.model_router.route(
                prompt=request.user_message,
                context={
                    "intent": intent.primary_intent,
                    "domain": ctx_analysis.detected_domain,
                    "preferred_model": decision.primary_model,
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature,
                }
            )
            
            response_content = route_result.content
            metadata["execution"] = {
                "model_used": route_result.model,
                "latency_ms": (time.perf_counter() - t_execution) * 1000,
            }
            
            # ── Step 8: Memory Update ─────────────────────────────────────────
            conversation.add_message(
                role="user",
                content=request.user_message
            )
            conversation.add_message(
                role="assistant",
                content=response_content
            )
            
            # ── Step 9: Knowledge Distillation ───────────────────────────────
            asyncio.create_task(
                self._knowledge_distillation.distill(
                    user_message=request.user_message,
                    response=response_content,
                    intent=intent.primary_intent,
                )
            )
            
            # ── Step 10: Sovereignty Record ─────────────────────────────────
            asyncio.create_task(
                self._sovereignty.record_request(
                    request_id=request_id,
                    intent=intent.primary_intent,
                    domain=ctx_analysis.detected_domain,
                    model=decision.primary_model,
                )
            )
            
        except Exception as e:
            errors.append(str(e))
            response_content = f"Error processing request: {str(e)}"
        
        # Calculate total latency
        total_latency = (time.perf_counter() - start_time) * 1000
        
        # Build response
        response = BrainResponse(
            content=response_content,
            session_id=request.session_id,
            status=ResponseStatus.SUCCESS if not errors else ResponseStatus.PARTIAL,
            execution_metadata=ExecutionMetadata(
                total_latency_ms=total_latency,
                engine_latencies={
                    "policy": (t_intent - t_policy) * 1000,
                    "intent": (t_context - t_intent) * 1000,
                    "context": (t_reasoning - t_context) * 1000,
                    "reasoning": (t_planning - t_reasoning) * 1000,
                    "planning": (t_decision - t_planning) * 1000,
                    "decision": (t_execution - t_decision) * 1000,
                    "execution": total_latency - (t_execution - start_time) * 1000,
                },
            ),
            intent=intent.primary_intent if 'intent' in dir() else None,
            confidence=metadata.get("reasoning", {}).get("confidence", 0.0),
            errors=errors,
            warnings=warnings,
            extra_data=metadata,
        )
        
        return response
    
    async def process_stream(
        self, 
        request: BrainRequest
    ) -> AsyncGenerator[str, None]:
        """
        Process a request with streaming response.
        
        Args:
            request: BrainRequest
            
        Yields:
            str: Chunks of the response
        """
        # For now, process normally and yield chunks
        response = await self.process(request)
        
        # Simple chunking (in production, this would stream from the model)
        chunk_size = 50
        for i in range(0, len(response.content), chunk_size):
            yield response.content[i:i + chunk_size]
    
    async def cleanup(self) -> None:
        """Cleanup resources"""
        # Future: cleanup database connections, close threads, etc.
        self._initialized = False


# Global singleton instance
_hajeen_brain: Optional[HajeenBrain] = None


def get_hajeen_brain() -> HajeenBrain:
    """Get the global HajeenBrain instance"""
    global _hajeen_brain
    if _hajeen_brain is None:
        _hajeen_brain = HajeenBrain()
    return _hajeen_brain
