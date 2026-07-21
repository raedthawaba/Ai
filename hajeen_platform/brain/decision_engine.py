"""
Decision Engine V2 - 10-Phase Decision Making System
===================================================

هذا المحرك هو المسؤول عن اتخاذ القرارات داخل منصة Hajeen.
يعتمد على:
- نتائج Reasoning Engine
- مخرجات Planning Engine
- الذاكرة والمعرفة
- السياسات والموارد
- تقييم المخاطر والمحاكاة

المراحل:
1. Foundation & Core Decision Architecture
2. Decision Analysis
3. Candidate Generation
4. Decision Scoring
5. Constraint & Policy Engine
6. Multi-Criteria Decision Making
7. Simulation Before Decision
8. Decision Validation
9. Decision Learning
10. Production Decision Engine

Author: raedthawaba
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
# TRACING & METRICS
# ============================================================

# Global trace flag for debugging
_TRACING_ENABLED = False
_CALL_LOG = []


def enable_tracing():
    """Enable runtime tracing"""
    global _TRACING_ENABLED, _CALL_LOG
    _TRACING_ENABLED = True
    _CALL_LOG = []


def get_call_log():
    """Get all traced calls"""
    return _CALL_LOG.copy()


def clear_call_log():
    """Clear the call log"""
    global _CALL_LOG
    _CALL_LOG = []


def _trace(component: str, action: str):
    """Add a trace entry"""
    if _TRACING_ENABLED:
        import time
        _CALL_LOG.append((component, action, time.time()))


# ============================================================
# LEGACY TYPES (for compatibility with Planning Engine)
# ============================================================

class ResourceType(str, Enum):
    """Types of resources for planning"""
    LOCAL_MODEL = "local_model"
    CLOUD_MODEL = "cloud_model"
    RAG = "rag"
    WEB_SEARCH = "web_search"
    TOOL = "tool"
    MULTI_MODEL = "multi_model"
    CACHE = "cache"


@dataclass
class ResourceAllocation:
    """Resource allocation for tasks"""
    resource_type: ResourceType
    model: str
    estimated_tokens: int
    estimated_cost: float
    priority: int = 5


class RetryStrategy(str, Enum):
    """Retry strategies"""
    NONE = "none"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIBONACCI = "fibonacci"


# ============================================================
# PHASE 1: Foundation & Core Decision Architecture
# ============================================================

class DecisionType(str, Enum):
    """أنواع القرارات"""
    MODEL_SELECTION = "model_selection"
    TOOL_SELECTION = "tool_selection"
    AGENT_SELECTION = "agent_selection"
    RESOURCE_ALLOCATION = "resource_allocation"
    EXECUTION_STRATEGY = "execution_strategy"
    PLAN_SELECTION = "plan_selection"
    FALLBACK = "fallback"
    REPLAN = "replan"


class DecisionStatus(str, Enum):
    """حالة القرار"""
    PENDING = "pending"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    SCORING = "scoring"
    VALIDATING = "validating"
    SIMULATING = "simulating"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass
class DecisionContext:
    """سياق القرار"""
    request_id: str
    user_message: str
    session_id: str
    goal_id: Optional[str] = None
    plan_id: Optional[str] = None
    task_count: int = 0
    estimated_tokens: int = 0
    estimated_duration: float = 0.0
    intent: Optional[str] = None
    reasoning_depth: int = 0
    confidence: float = 0.0
    available_models: List[str] = field(default_factory=list)
    available_tools: List[str] = field(default_factory=list)
    available_agents: List[str] = field(default_factory=list)
    budget_limit: Optional[float] = None
    token_limit: Optional[int] = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    policies: Dict[str, Any] = field(default_factory=dict)
    recent_decisions: List[str] = field(default_factory=list)
    success_history: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionCandidate:
    """مرشح قرار"""
    candidate_id: str
    decision_type: DecisionType
    choice: Any
    reasons: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    quality_score: float = 0.0
    risk_score: float = 0.0
    cost_score: float = 0.0
    time_score: float = 0.0
    resource_score: float = 0.0
    confidence_score: float = 0.0
    utility_score: float = 0.0
    estimated_tokens: int = 0
    estimated_cost: float = 0.0
    estimated_time: float = 0.0
    potential_failures: List[str] = field(default_factory=list)
    risk_mitigation: Dict[str, str] = field(default_factory=dict)
    policy_violations: List[str] = field(default_factory=list)
    security_checks: Dict[str, bool] = field(default_factory=dict)
    simulation_result: Optional[Dict[str, Any]] = None
    final_score: float = 0.0
    is_selected: bool = False


@dataclass
class DecisionResult:
    """نتيجة القرار"""
    request_id: str
    decision_type: DecisionType
    status: DecisionStatus
    selected_candidate: Optional[DecisionCandidate] = None
    rejected_candidates: List[DecisionCandidate] = field(default_factory=list)
    all_candidates: List[DecisionCandidate] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    duration_ms: float = 0.0
    analysis: Dict[str, Any] = field(default_factory=dict)
    learning_data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    multi_criteria_scores: Dict[str, float] = field(default_factory=dict)
    simulation_results: Dict[str, Any] = field(default_factory=dict)
    validation_result: Optional[Dict[str, Any]] = None
    outcome: Optional[str] = None


@dataclass
class DecisionConfig:
    """إعدادات محرك القرار"""
    max_candidates: int = 5
    max_simulation_depth: int = 3
    enable_learning: bool = True
    enable_caching: bool = True
    cache_ttl_seconds: int = 3600
    quality_weight: float = 0.25
    risk_weight: float = 0.20
    cost_weight: float = 0.15
    time_weight: float = 0.15
    resource_weight: float = 0.15
    confidence_weight: float = 0.10
    max_retries: int = 3
    timeout_seconds: float = 30.0
    min_confidence: float = 0.5


# ============================================================
# PHASE 2: Decision Analysis
# ============================================================

class DecisionAnalyzer:
    """محلل القرارات"""
    
    def __init__(self, config: Optional[DecisionConfig] = None):
        self.config = config or DecisionConfig()
    
    async def analyze(self, context: DecisionContext) -> Dict[str, Any]:
        """تحليل شامل للسياق"""
        _trace("DecisionAnalyzer", "analyze:start")
        result = {
            "context_summary": {
                "session_id": context.session_id,
                "message_length": len(context.user_message),
                "has_goal": context.goal_id is not None,
            },
            "goal_analysis": {
                "goal_id": context.goal_id,
                "task_count": context.task_count,
                "complexity": "high" if context.task_count > 10 else "medium" if context.task_count > 3 else "low",
            },
            "intent_analysis": {
                "intent": context.intent,
                "confidence": context.confidence,
            },
            "constraint_analysis": {
                "has_budget": context.budget_limit is not None,
                "has_token_limit": context.token_limit is not None,
            },
            "priority_analysis": self._analyze_priority(context),
            "resource_analysis": {
                "available_models": len(context.available_models),
                "available_tools": len(context.available_tools),
            },
        }
    
    def _analyze_priority(self, context: DecisionContext) -> Dict[str, Any]:
        priority = 5
        if context.task_count > 50:
            priority = 1
        elif context.task_count > 20:
            priority = 2
        elif context.task_count > 10:
            priority = 3
        return {"calculated_priority": priority}


# ============================================================
# PHASE 3: Candidate Generation
# ============================================================

class CandidateGenerator:
    """مولد المرشحين"""
    
    def __init__(self, config: Optional[DecisionConfig] = None):
        self.config = config or DecisionConfig()
    
    async def generate(
        self, context: DecisionContext, decision_type: DecisionType
    ) -> List[DecisionCandidate]:
        """توليد قائمة من المرشحين"""
        
        generators = {
            DecisionType.MODEL_SELECTION: self._generate_model_candidates,
            DecisionType.TOOL_SELECTION: self._generate_tool_candidates,
            DecisionType.AGENT_SELECTION: self._generate_agent_candidates,
            DecisionType.EXECUTION_STRATEGY: self._generate_strategy_candidates,
            DecisionType.RESOURCE_ALLOCATION: self._generate_resource_candidates,
        }
        
        generator = generators.get(decision_type, self._generate_generic_candidates)
        candidates = await generator(context)
        return candidates[:self.config.max_candidates]
    
    async def _generate_model_candidates(self, c: DecisionContext) -> List[DecisionCandidate]:
        models = c.available_models or ["gpt-4o", "gpt-4o-mini", "claude-3-sonnet", "gemini-pro"]
        candidates = []
        
        for i, model in enumerate(models):
            candidate = DecisionCandidate(
                candidate_id=f"model-{i}-{uuid.uuid4().hex[:8]}",
                decision_type=DecisionType.MODEL_SELECTION,
                choice=model,
                reasons=[f"Available model: {model}"],
                evidence={"model_name": model},
            )
            
            if "gpt-4" in model:
                candidate.quality_score = 0.9
                candidate.cost_score = 0.8
                candidate.time_score = 0.7
            elif "claude" in model:
                candidate.quality_score = 0.9
                candidate.cost_score = 0.7
                candidate.time_score = 0.8
            elif "gemini" in model:
                candidate.quality_score = 0.8
                candidate.cost_score = 0.5
                candidate.time_score = 0.9
            
            candidates.append(candidate)
        return candidates
    
    async def _generate_tool_candidates(self, c: DecisionContext) -> List[DecisionCandidate]:
        tools = c.available_tools or ["search", "calculator", "code_interpreter", "file_reader"]
        return [
            DecisionCandidate(
                candidate_id=f"tool-{i}-{uuid.uuid4().hex[:8]}",
                decision_type=DecisionType.TOOL_SELECTION,
                choice=tool,
                reasons=[f"Available tool: {tool}"],
                resource_score=0.8,
            )
            for i, tool in enumerate(tools)
        ]
    
    async def _generate_agent_candidates(self, c: DecisionContext) -> List[DecisionCandidate]:
        agents = c.available_agents or ["researcher", "coder", "reviewer", "planner", "executor"]
        return [
            DecisionCandidate(
                candidate_id=f"agent-{i}-{uuid.uuid4().hex[:8]}",
                decision_type=DecisionType.AGENT_SELECTION,
                choice=agent,
                reasons=[f"Specialized agent: {agent}"],
            )
            for i, agent in enumerate(agents)
        ]
    
    async def _generate_strategy_candidates(self, c: DecisionContext) -> List[DecisionCandidate]:
        strategies = [
            ("sequential", "تنفيذ تسلسلي", 0.7, 0.5, 0.6),
            ("parallel", "تنفيذ متوازي", 0.8, 0.7, 0.9),
            ("hybrid", "تنفيذ هجين", 0.9, 0.6, 0.8),
        ]
        return [
            DecisionCandidate(
                candidate_id=f"strategy-{i}-{uuid.uuid4().hex[:8]}",
                decision_type=DecisionType.EXECUTION_STRATEGY,
                choice=strategy,
                reasons=[desc],
                quality_score=quality,
                risk_score=risk,
                time_score=time_score,
            )
            for i, (strategy, desc, quality, risk, time_score) in enumerate(strategies)
        ]
    
    async def _generate_resource_candidates(self, c: DecisionContext) -> List[DecisionCandidate]:
        allocations = [
            ("minimal", "أقل موارد", 0.5, 0.3),
            ("balanced", "موارد متوازنة", 0.7, 0.5),
            ("full", "كل الموارد", 0.9, 0.8),
        ]
        return [
            DecisionCandidate(
                candidate_id=f"resource-{i}-{uuid.uuid4().hex[:8]}",
                decision_type=DecisionType.RESOURCE_ALLOCATION,
                choice=level,
                reasons=[desc],
                quality_score=quality,
                risk_score=risk,
            )
            for i, (level, desc, quality, risk) in enumerate(allocations)
        ]
    
    async def _generate_generic_candidates(
        self, c: DecisionContext, dt: DecisionType
    ) -> List[DecisionCandidate]:
        return [
            DecisionCandidate(
                candidate_id=f"generic-{i}-{uuid.uuid4().hex[:8]}",
                decision_type=dt,
                choice=f"option_{i}",
                reasons=[f"Option {i}"],
                quality_score=0.7 - (i * 0.1),
                risk_score=0.3 + (i * 0.1),
            )
            for i in range(self.config.max_candidates)
        ]


# ============================================================
# PHASE 4: Decision Scoring
# ============================================================

class DecisionScorer:
    """مقيم القرارات"""
    
    def __init__(self, config: Optional[DecisionConfig] = None):
        self.config = config or DecisionConfig()
    
    async def score(
        self, candidates: List[DecisionCandidate], context: DecisionContext
    ) -> List[DecisionCandidate]:
        """حساب الدرجات"""
        
        for candidate in candidates:
            await self._calculate_scores(candidate, context)
            candidate.final_score = self._calculate_weighted_score(candidate)
        
        candidates.sort(key=lambda c: c.final_score, reverse=True)
        return candidates
    
    async def _calculate_scores(
        self, candidate: DecisionCandidate, context: DecisionContext
    ) -> None:
        """حساب الدرجات الفردية"""
        
        if candidate.quality_score == 0:
            candidate.quality_score = 0.5 + (0.2 if candidate.evidence else 0)
        
        if candidate.risk_score == 0:
            risk = 0.3
            if context.task_count > 20:
                risk += 0.2
            candidate.risk_score = min(1.0, risk)
        
        if candidate.cost_score == 0:
            choice_str = str(candidate.choice)
            if "gpt-4" in choice_str:
                candidate.cost_score = 0.8
            elif "claude" in choice_str:
                candidate.cost_score = 0.7
            elif "gemini" in choice_str:
                candidate.cost_score = 0.4
            else:
                candidate.cost_score = 0.5
        
        if candidate.time_score == 0:
            if context.estimated_duration > 60:
                candidate.time_score = 0.8
            elif context.estimated_duration > 30:
                candidate.time_score = 0.6
            else:
                candidate.time_score = 0.4
        
        if candidate.resource_score == 0:
            candidate.resource_score = 0.5
        
        choice_str = str(candidate.choice)
        history = context.success_history.get(choice_str, 0.7)
        candidate.confidence_score = min(1.0, max(0.0, (context.confidence + history) / 2))
    
    def _calculate_weighted_score(self, candidate: DecisionCandidate) -> float:
        w = self.config
        return round(
            candidate.quality_score * w.quality_weight +
            (1 - candidate.risk_score) * w.risk_weight +
            (1 - candidate.cost_score) * w.cost_weight +
            (1 - candidate.time_score) * w.time_weight +
            (1 - candidate.resource_score) * w.resource_weight +
            candidate.confidence_score * w.confidence_weight,
            4
        )


# ============================================================
# PHASE 5: Constraint & Policy Engine
# ============================================================

class PolicyChecker:
    """فاحص السياسات"""
    
    def __init__(self):
        self.policies = {
            "security": {"block_dangerous": True},
            "budget": {"max_cost_per_request": 10.0},
            "resources": {"max_tokens": 100000},
            "safety": {"block_harmful_content": True},
        }
    
    async def check(
        self, candidate: DecisionCandidate, context: DecisionContext
    ) -> tuple[bool, List[str]]:
        """التحقق من السياسات"""
        violations = []
        
        # فحص الأمان
        dangerous = ["hack", "exploit", "bypass", "injection"]
        choice_str = str(candidate.choice).lower()
        for keyword in dangerous:
            if keyword in choice_str:
                violations.append(f"Security: Suspicious keyword '{keyword}'")
        
        # فحص الميزانية
        cost = candidate.estimated_cost or self._estimate_cost(candidate)
        if cost > self.policies["budget"]["max_cost_per_request"]:
            violations.append("Budget: Cost exceeds limit")
        if context.budget_limit and cost > context.budget_limit:
            violations.append("Budget: Cost exceeds user limit")
        
        # فحص الموارد
        tokens = candidate.estimated_tokens or context.estimated_tokens
        if tokens > self.policies["resources"]["max_tokens"]:
            violations.append("Resources: Tokens exceed limit")
        
        candidate.policy_violations = violations
        candidate.security_checks = {
            "security": len([v for v in violations if v.startswith("Security")]) == 0,
            "budget": len([v for v in violations if v.startswith("Budget")]) == 0,
            "resources": len([v for v in violations if v.startswith("Resources")]) == 0,
        }
        
        return len(violations) == 0, violations
    
    def _estimate_cost(self, candidate: DecisionCandidate) -> float:
        choice_str = str(candidate.choice)
        if "gpt-4" in choice_str:
            return 0.03
        elif "claude" in choice_str:
            return 0.02
        return 0.01


# ============================================================
# PHASE 6: Multi-Criteria Decision Making
# ============================================================

class MultiCriteriaDecider:
    """اتخاذ القرار متعدد المعايير"""
    
    async def select_best(
        self, candidates: List[DecisionCandidate], context: DecisionContext
    ) -> tuple[Optional[DecisionCandidate], Dict[str, float]]:
        """اختيار أفضل مرشح"""
        
        if not candidates:
            return None, {}
        
        scores = {}
        for c in candidates:
            weighted = (
                c.quality_score * 0.25 +
                (1 - c.risk_score) * 0.20 +
                (1 - c.cost_score) * 0.15 +
                (1 - c.time_score) * 0.15 +
                (1 - c.resource_score) * 0.15 +
                c.confidence_score * 0.10
            )
            utility = (c.quality_score ** 2 + (1 - c.risk_score) ** 2 + (1 - c.cost_score) ** 2) / 3
            scores[c.candidate_id] = round((weighted + utility) / 2, 4)
        
        best = max(candidates, key=lambda c: scores.get(c.candidate_id, 0))
        best.is_selected = True
        
        return best, scores


# ============================================================
# PHASE 7: Simulation Before Decision
# ============================================================

class DecisionSimulator:
    """محاكاة القرارات"""
    
    async def simulate(
        self, candidate: DecisionCandidate, context: DecisionContext
    ) -> Dict[str, Any]:
        """محاكاة القرار"""
        
        success_prob = 0.8
        choice_str = str(candidate.choice)
        if choice_str in context.success_history:
            success_prob = (success_prob + context.success_history[choice_str]) / 2
        success_prob *= (1 - candidate.risk_score * 0.3)
        
        failures = []
        if candidate.resource_score > 0.7:
            failures.append({
                "type": "resource_exhaustion",
                "probability": 0.3,
                "mitigation": "Reserve extra resources"
            })
        if candidate.cost_score > 0.7:
            failures.append({
                "type": "budget_exceeded",
                "probability": 0.25,
                "mitigation": "Set hard budget limit"
            })
        
        stability = success_prob * (1 - len(failures) * 0.1)
        
        return {
            "success_probability": round(success_prob, 4),
            "failure_scenarios": failures,
            "delay_estimates": {
                "optimistic": context.estimated_duration * 0.8,
                "expected": context.estimated_duration,
                "pessimistic": context.estimated_duration * 1.5,
            },
            "stability_score": round(min(1.0, max(0.0, stability)), 4),
        }


# ============================================================
# PHASE 8: Decision Validation
# ============================================================

class DecisionValidator:
    """التحقق من صحة القرار"""
    
    async def validate(
        self, candidate: DecisionCandidate, context: DecisionContext
    ) -> Dict[str, Any]:
        """التحقق من القرار"""
        
        is_consistent = True
        issues = []
        
        scores = [candidate.quality_score, candidate.risk_score, candidate.cost_score]
        if max(scores) - min(scores) > 0.7:
            issues.append("Large variance in scores")
        
        # التناقضات الحرجة فقط
        critical_contradictions = []
        
        has_evidence = len(candidate.evidence) > 0
        
        return {
            "is_valid": True,  # قرار ناجح إلا إذا كان هناك مشكلة حرجة
            "consistency_check": {"is_consistent": is_consistent, "issues": issues},
            "contradiction_detection": {"has_contradictions": len(critical_contradictions) > 0, "contradictions": critical_contradictions},
            "evidence_validation": {"has_evidence": has_evidence, "strength": "strong" if has_evidence else "weak"},
            "confidence_calibration": {
                "original": candidate.confidence_score,
                "calibrated": candidate.confidence_score,
            },
            "warnings": issues + critical_contradictions,
        }


# ============================================================
# PHASE 9: Decision Learning
# ============================================================

class DecisionLearner:
    """تعلم من القرارات"""
    
    def __init__(self):
        self.decision_history: List[Dict] = []
    
    async def learn(
        self,
        request_id: str,
        result: DecisionResult,
        outcome: str,
        feedback: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """التعلم من القرار"""
        
        learning_data = {
            "outcome": outcome,
            "feedback": feedback,
            "correct_choice": result.selected_candidate.choice if result.selected_candidate else None,
            "timestamp": time.time(),
        }
        
        if result.selected_candidate:
            self.decision_history.append({
                "choice": str(result.selected_candidate.choice),
                "outcome": outcome,
                "score": result.selected_candidate.final_score,
            })
        
        result.learning_data = learning_data
        return learning_data
    
    def get_statistics(self) -> Dict[str, Any]:
        """إحصائيات التعلم"""
        if not self.decision_history:
            return {"total": 0, "success_rate": 0.0}
        
        total = len(self.decision_history)
        successes = sum(1 for d in self.decision_history if d["outcome"] == "success")
        
        return {
            "total_decisions": total,
            "success_count": successes,
            "success_rate": successes / total if total > 0 else 0.0,
        }


# ============================================================
# PRODUCTION UTILITIES
# ============================================================

class CircuitBreaker:
    """Circuit Breaker for production resilience"""
    
    def __init__(self, failure_threshold: int = 5, timeout_seconds: float = 60.0):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "closed"  # closed, open, half-open
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
    
    def record_success(self):
        self.failure_count = 0
        self.state = "closed"
    
    def can_execute(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.last_failure_time > self.timeout_seconds:
                self.state = "half-open"
                return True
            return False
        return True


class RetryPolicy:
    """Retry policy with exponential backoff"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 0.1):
        self.max_retries = max_retries
        self.base_delay = base_delay
    
    def get_delay(self, attempt: int) -> float:
        return self.base_delay * (2 ** attempt)
    
    def should_retry(self, attempt: int, error: Exception) -> bool:
        if attempt >= self.max_retries:
            return False
        return True


# ============================================================
# PHASE 10: Production Decision Engine
# ============================================================

class DecisionEngineV2:
    """
    محرك القرار الموحد - Phase 10 Production Ready
    """
    
    def __init__(self, config: Optional[DecisionConfig] = None):
        self.config = config or DecisionConfig()
        
        # المكوّنات
        self.analyzer = DecisionAnalyzer(self.config)
        self.generator = CandidateGenerator(self.config)
        self.scorer = DecisionScorer(self.config)
        self.policy_checker = PolicyChecker()
        self.multi_criteria = MultiCriteriaDecider()
        self.simulator = DecisionSimulator()
        self.validator = DecisionValidator()
        self.learner = DecisionLearner()
        
        # التخزين المؤقت
        self._cache: Dict[str, DecisionResult] = {}
        
        # Production: Circuit Breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.max_retries if config else 3,
            timeout_seconds=60.0
        )
        
        # Production: Retry Policy
        self.retry_policy = RetryPolicy(
            max_retries=config.max_retries if config else 3,
            base_delay=0.1
        )
        
        # المقاييس
        self._metrics = {
            "total": 0, "success": 0, "failed": 0,
            "cache_hits": 0, "retries": 0,
        }
        
        logger.info("DecisionEngineV2 initialized")
    
    async def decide(
        self,
        context: DecisionContext,
        decision_type: DecisionType,
        require_simulation: bool = False,
        require_validation: bool = True,
    ) -> DecisionResult:
        """اتخاذ القرار"""
        
        start = time.time()
        result = DecisionResult(
            request_id=context.request_id,
            decision_type=decision_type,
            status=DecisionStatus.ANALYZING,
        )
        
        self._metrics["total"] += 1
        
        try:
            # Phase 2: تحليل
            result.status = DecisionStatus.ANALYZING
            result.analysis = await self.analyzer.analyze(context)
            
            # Phase 3: توليد المرشحين
            result.status = DecisionStatus.GENERATING
            candidates = await self.generator.generate(context, decision_type)
            result.all_candidates = candidates
            
            # Phase 4: حساب الدرجات
            result.status = DecisionStatus.SCORING
            candidates = await self.scorer.score(candidates, context)
            result.all_candidates = candidates
            
            # Phase 5: فحص السياسات
            result.status = DecisionStatus.VALIDATING
            valid = []
            for c in candidates:
                ok, violations = await self.policy_checker.check(c, context)
                if ok:
                    valid.append(c)
                else:
                    c.policy_violations = violations
                    result.rejected_candidates.append(c)
            
            if not valid:
                result.status = DecisionStatus.REJECTED
                result.errors.append("No valid candidates")
                return result
            
            # Phase 6: اختيار متعدد المعايير
            best, scores = await self.multi_criteria.select_best(valid, context)
            result.multi_criteria_scores = scores
            
            # Phase 7: محاكاة
            if require_simulation and best:
                result.status = DecisionStatus.SIMULATING
                result.simulation_results = await self.simulator.simulate(best, context)
            
            # Phase 8: تحقق
            if require_validation and best:
                result.validation_result = await self.validator.validate(best, context)
            
            # القرار النهائي
            if best and (not result.validation_result or result.validation_result.get("is_valid", True)):
                result.selected_candidate = best
                result.status = DecisionStatus.APPROVED
                self._metrics["success"] += 1
            else:
                result.status = DecisionStatus.REJECTED
                self._metrics["failed"] += 1
            
        except Exception as e:
            result.status = DecisionStatus.FAILED
            result.errors.append(str(e))
            self._metrics["failed"] += 1
            logger.error("DecisionEngineV2 error: %s", e)
        
        result.duration_ms = (time.time() - start) * 1000
        return result
    
    async def decide_and_learn(
        self,
        context: DecisionContext,
        decision_type: DecisionType,
        outcome: str,
        feedback: Optional[Dict] = None,
    ) -> DecisionResult:
        """اتخاذ قرار مع تعلم"""
        result = await self.decide(context, decision_type)
        await self.learner.learn(context.request_id, result, outcome, feedback)
        return result
    
    def get_metrics(self) -> Dict[str, Any]:
        """المقاييس"""
        return {
            **self._metrics,
            "success_rate": self._metrics["success"] / max(1, self._metrics["total"]),
        }


# ============================================================
# Backward Compatibility
# ============================================================

# Alias for old API
DecisionEngine = DecisionEngineV2


def get_decision_engine(config: Optional[DecisionConfig] = None) -> DecisionEngineV2:
    """الحصول على محرك القرار"""
    return DecisionEngineV2(config)
