"""
Reasoning Engine — محرك الاستدلال العميق
========================================

محرك استدلال مستقر وقابل للاعتماد مع:
- إعدادات مركزية (Pydantic)
- سجل تنفيذي كامل (Execution Trace)
- مقاييس موحدة (Metrics)
- معالجة أخطاء متقدمة (Error Recovery)
- تخزين مؤقت (Caching)
"""

from __future__ import annotations

import json
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import structlog
from pydantic import BaseModel, Field

from brain.config import (
    ReasoningEngineConfig,
    ReasoningStrategyType,
    get_default_config,
)
from brain.execution_trace import (
    ExecutionTrace,
    ExecutionTraceManager,
    TraceLevel,
)
from brain.metrics_engine import MetricsCollector, get_metrics_collector
from hajeen_platform.core.llm import LLMManager

logger = structlog.get_logger(__name__)


class ReasoningStrategy(str, Enum):
    """استراتيجيات الاستدلال."""
    CHAIN_OF_THOUGHT = "chain_of_thought"
    TREE_OF_THOUGHT = "tree_of_thought"
    DECOMPOSITION = "decomposition"
    ANALOGY = "analogy"
    FIRST_PRINCIPLES = "first_principles"
    MULTI_PERSPECTIVE = "multi_perspective"

    @classmethod
    def from_config(cls, strategy_type: Union[str, ReasoningStrategyType]) -> "ReasoningStrategy":
        """التحويل من نوع الإعدادات."""
        if isinstance(strategy_type, cls):
            return strategy_type
        if isinstance(strategy_type, ReasoningStrategyType):
            return cls(strategy_type.value)
        return cls(strategy_type)


class ReasoningStep(BaseModel):
    """خطوة واحدة في الاستدلال."""
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_number: int
    description: str
    reasoning: str
    conclusion: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    alternatives: List[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    """تقييم المخاطر."""
    risk_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    risk_type: str
    description: str
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    probability: float = Field(ge=0.0, le=1.0)
    impact: str
    mitigation_strategy: str


class SolutionOption(BaseModel):
    """خيار حل."""
    option_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)
    effort_estimate: str = Field(pattern="^(low|medium|high)$", default="medium")
    time_estimate: str = ""
    risk_level: str = Field(pattern="^(low|medium|high)$", default="medium")
    feasibility_score: float = Field(ge=0.0, le=1.0, default=0.5)
    recommended: bool = False


class ReasoningResult(BaseModel):
    """نتيجة الاستدلال الكاملة."""
    reasoning_id: str
    strategy_used: ReasoningStrategy
    
    reasoning_steps: List[ReasoningStep] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    risks: List[RiskAssessment] = Field(default_factory=list)
    solution_options: List[SolutionOption] = Field(default_factory=list)
    recommended_solution: Optional[SolutionOption] = None
    
    overall_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    reasoning_summary: str = ""
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    trace_id: Optional[str] = None

    model_config = {"use_enum_values": True}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reasoning_id": self.reasoning_id,
            "strategy_used": self.strategy_used.value if isinstance(self.strategy_used, ReasoningStrategy) else self.strategy_used,
            "reasoning_steps": len(self.reasoning_steps),
            "reasoning_steps_details": [s.model_dump() for s in self.reasoning_steps],
            "missing_information": self.missing_information,
            "risks": len(self.risks),
            "solution_options": len(self.solution_options),
            "recommended_solution": self.recommended_solution.title if self.recommended_solution else None,
            "overall_confidence": round(self.overall_confidence, 3),
            "reasoning_summary": self.reasoning_summary,
            "created_at": self.created_at,
            "trace_id": self.trace_id,
        }


class ReasoningEngineError(Exception):
    """خطأ في محرك الاستدلال."""
    pass


class LLMCallError(ReasoningEngineError):
    """خطأ في استدعاء LLM."""
    pass


class ValidationError(ReasoningEngineError):
    """خطأ في التحقق."""
    pass


class ReasoningEngine:
    """
    محرك الاستدلال العميق - نسخة مستقرة.
    
    المميزات:
    - إعدادات مركزية
    - سجل تنفيذي كامل
    - مقاييس موحدة
    - معالجة أخطاء متقدمة
    - تخزين مؤقت
    """

    def __init__(
        self,
        llm_manager: LLMManager,
        config: Optional[ReasoningEngineConfig] = None,
        trace_manager: Optional[ExecutionTraceManager] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ) -> None:
        self.llm_manager = llm_manager
        self.config = config or get_default_config()
        self.trace_manager = trace_manager or ExecutionTraceManager(
            enabled=self.config.execution_trace.enabled,
            level=TraceLevel.STANDARD,
            persist_traces=self.config.execution_trace.persist_traces,
            storage_path=self.config.execution_trace.trace_storage_path,
        )
        self.metrics = metrics_collector or get_metrics_collector()
        
        self._reasoning_cache: Dict[str, ReasoningResult] = {}
        self._init_cache()
        
        logger.info(
            "reasoning_engine_initialized",
            config_version=self.config.version,
            strategy=self.config.reasoning_strategy.default_strategy.value,
            cache_enabled=self.config.cache.enabled,
        )

    def _init_cache(self) -> None:
        """تهيئة التخزين المؤقت."""
        if self.config.cache.enabled:
            logger.info(
                "cache_initialized",
                max_entries=self.config.cache.max_entries,
                ttl_seconds=self.config.cache.ttl_seconds,
            )

    def _get_cache_key(self, problem: str, strategy: ReasoningStrategy, context: Optional[Dict[str, Any]]) -> str:
        """إنشاء مفتاح للـ cache."""
        import hashlib
        content = f"{problem}:{strategy.value}:{json.dumps(context or {}, sort_keys=True)}"
        return f"{self.config.cache.cache_key_prefix}_{hashlib.md5(content.encode()).hexdigest()}"

    def _get_from_cache(self, cache_key: str) -> Optional[ReasoningResult]:
        """الحصول من التخزين المؤقت."""
        if not self.config.cache.enabled:
            return None
        
        cached = self._reasoning_cache.get(cache_key)
        if cached:
            age = time.time() - cached.created_at
            if age > self.config.cache.ttl_seconds:
                del self._reasoning_cache[cache_key]
                return None
            return cached
        return None

    def _save_to_cache(self, cache_key: str, result: ReasoningResult) -> None:
        """حفظ في التخزين المؤقت."""
        if not self.config.cache.enabled:
            return
        
        if len(self._reasoning_cache) >= self.config.cache.max_entries:
            oldest = min(self._reasoning_cache.items(), key=lambda x: x[1].created_at)
            del self._reasoning_cache[oldest[0]]
        
        self._reasoning_cache[cache_key] = result

    async def reason(
        self,
        problem: str,
        context: Optional[Dict[str, Any]] = None,
        strategy: Optional[ReasoningStrategy] = None,
        enable_trace: bool = True,
    ) -> ReasoningResult:
        """
        إجراء استدلال عميق حول مشكلة.
        
        الخطوات:
        1. التحقق من المدخلات
        2. محاولة الحصول من التخزين المؤقت
        3. تحليل المشكلة
        4. اكتشاف المعلومات الناقصة
        5. تقييم المخاطر
        6. اقتراح الحلول
        7. اختيار أفضل حل
        """
        start_time = time.time()
        reasoning_id = str(uuid.uuid4())
        
        if strategy is None:
            strategy = ReasoningStrategy.from_config(
                self.config.reasoning_strategy.default_strategy
            )
        
        if not problem or not problem.strip():
            raise ValidationError("المشكلة لا يمكن أن تكون فارغة")
        
        if len(problem) > self.config.max_context_length:
            raise ValidationError(f"المشكلة طويلة جداً (الحد الأقصى: {self.config.max_context_length})")
        
        trace: Optional[ExecutionTrace] = None
        if enable_trace:
            trace = self.trace_manager.start_trace(
                reasoning_id=reasoning_id,
                problem=problem,
                strategy=strategy.value,
                context=context,
            )
        
        cache_key = self._get_cache_key(problem, strategy, context)
        cached_result = self._get_from_cache(cache_key)
        if cached_result:
            self.metrics.increment("reasoning_total")
            self.metrics.increment("reasoning_success")
            self.metrics.record_timing("reasoning", (time.time() - start_time) * 1000, success=True)
            return cached_result
        
        try:
            self.trace_manager.record_step(
                reasoning_id, "analyze_problem", 1,
                input_data={"problem": problem, "strategy": strategy.value},
            )
            
            reasoning_steps = await self._perform_reasoning(
                problem, context, strategy
            )
            
            self.trace_manager.record_step(
                reasoning_id, "analyze_problem", 1,
                output_data={"steps_count": len(reasoning_steps)},
                success=True,
            )
            
            missing_info = await self._identify_missing_information(
                problem, context, reasoning_steps
            )
            
            risks = []
            if self.config.risk_assessment.enabled:
                risks = await self._assess_risks(problem, context, reasoning_steps)
            
            solutions = []
            if self.config.solution.enabled:
                solutions = await self._propose_solutions(
                    problem, context, reasoning_steps, risks
                )
            
            recommended = await self._select_best_solution(solutions)
            
            summary = self._build_reasoning_summary(
                reasoning_steps, missing_info, risks, solutions, recommended
            )
            
            overall_confidence = self._calculate_overall_confidence(
                reasoning_steps, solutions, recommended
            )
            
            result = ReasoningResult(
                reasoning_id=reasoning_id,
                strategy_used=strategy,
                reasoning_steps=reasoning_steps,
                missing_information=missing_info,
                risks=risks,
                solution_options=solutions,
                recommended_solution=recommended,
                overall_confidence=overall_confidence,
                reasoning_summary=summary,
                metadata={
                    "problem": problem,
                    "context": context or {},
                    "config_version": self.config.version,
                },
                trace_id=trace.trace_id if trace else None,
            )
            
            self._save_to_cache(cache_key, result)
            
            if trace:
                self.trace_manager.end_trace(
                    reasoning_id,
                    success=True,
                    final_confidence=overall_confidence,
                )
            
            self.metrics.increment("reasoning_total")
            self.metrics.increment("reasoning_success")
            self.metrics.observe_histogram("reasoning_confidence", overall_confidence)
            self.metrics.record_timing(
                "reasoning",
                (time.time() - start_time) * 1000,
                success=True,
            )
            
            logger.info(
                "reasoning_completed",
                reasoning_id=reasoning_id,
                steps=len(reasoning_steps),
                solutions=len(solutions),
                confidence=round(overall_confidence, 3),
                duration_ms=round((time.time() - start_time) * 1000, 2),
            )
            
            return result
        
        except Exception as e:
            logger.error("reasoning_failed", reasoning_id=reasoning_id, error=str(e))
            
            if trace:
                self.trace_manager.end_trace(reasoning_id, success=False)
            
            self.metrics.increment("reasoning_total")
            self.metrics.increment("reasoning_errors")
            self.metrics.record_timing(
                "reasoning",
                (time.time() - start_time) * 1000,
                success=False,
            )
            
            if self.config.error_recovery.enable_fallback:
                return self._create_fallback_result(reasoning_id, strategy, str(e))
            
            raise

    def _create_fallback_result(
        self,
        reasoning_id: str,
        strategy: ReasoningStrategy,
        error: str,
    ) -> ReasoningResult:
        """إنشاء نتيجة احتياطية."""
        self.trace_manager.record_fallback(
            reasoning_id,
            original_strategy=strategy.value,
            fallback_strategy="fallback",
            reason=error,
        )
        
        return ReasoningResult(
            reasoning_id=reasoning_id,
            strategy_used=strategy,
            reasoning_steps=[],
            missing_information=["فشل التحليل"],
            risks=[],
            solution_options=[],
            recommended_solution=None,
            overall_confidence=self.config.error_recovery.fallback_confidence,
            reasoning_summary="فشل الاستدلال، يرجى المحاولة لاحقاً",
            metadata={"error": error, "fallback": True},
        )

    async def _perform_reasoning(
        self,
        problem: str,
        context: Optional[Dict[str, Any]],
        strategy: ReasoningStrategy,
    ) -> List[ReasoningStep]:
        """إجراء الاستدلال بناءً على الاستراتيجية."""
        strategy_map = {
            ReasoningStrategy.CHAIN_OF_THOUGHT: self._chain_of_thought,
            ReasoningStrategy.TREE_OF_THOUGHT: self._tree_of_thought,
            ReasoningStrategy.DECOMPOSITION: self._decomposition,
            ReasoningStrategy.FIRST_PRINCIPLES: self._first_principles,
            ReasoningStrategy.MULTI_PERSPECTIVE: self._multi_perspective,
            ReasoningStrategy.ANALOGY: self._analogy,
        }
        
        handler = strategy_map.get(strategy, self._chain_of_thought)
        return await handler(problem, context)

    async def _chain_of_thought(
        self,
        problem: str,
        context: Optional[Dict[str, Any]],
    ) -> List[ReasoningStep]:
        """استدلال سلسلة الأفكار."""
        return await self._execute_llm_reasoning(
            prompt=self._build_cot_prompt(problem, context),
            model=self.config.llm.reasoning_model,
        )

    async def _tree_of_thought(
        self,
        problem: str,
        context: Optional[Dict[str, Any]],
    ) -> List[ReasoningStep]:
        """استدلال شجرة الأفكار."""
        return await self._execute_llm_reasoning(
            prompt=self._build_tot_prompt(problem, context),
            model=self.config.llm.primary_model,
        )

    async def _decomposition(
        self,
        problem: str,
        context: Optional[Dict[str, Any]],
    ) -> List[ReasoningStep]:
        """تفكيك المشكلة."""
        return await self._execute_llm_reasoning(
            prompt=self._build_decomposition_prompt(problem, context),
            model=self.config.llm.reasoning_model,
        )

    async def _first_principles(
        self,
        problem: str,
        context: Optional[Dict[str, Any]],
    ) -> List[ReasoningStep]:
        """الاستدلال من المبادئ الأولى."""
        return await self._execute_llm_reasoning(
            prompt=self._build_first_principles_prompt(problem, context),
            model=self.config.llm.primary_model,
        )

    async def _multi_perspective(
        self,
        problem: str,
        context: Optional[Dict[str, Any]],
    ) -> List[ReasoningStep]:
        """وجهات نظر متعددة."""
        return await self._execute_llm_reasoning(
            prompt=self._build_multi_perspective_prompt(problem, context),
            model=self.config.llm.primary_model,
        )

    async def _analogy(
        self,
        problem: str,
        context: Optional[Dict[str, Any]],
    ) -> List[ReasoningStep]:
        """الاستدلال بالقياس."""
        return await self._execute_llm_reasoning(
            prompt=self._build_analogy_prompt(problem, context),
            model=self.config.llm.reasoning_model,
        )

    async def _execute_llm_reasoning(
        self,
        prompt: str,
        model: str,
    ) -> List[ReasoningStep]:
        """تنفيذ الاستدلال عبر LLM."""
        llm_start = time.time()
        
        for attempt in range(self.config.llm.retry_attempts):
            try:
                response = await self._call_llm_with_retry(
                    prompt=prompt,
                    model=model,
                )
                
                self.trace_manager.record_llm_call(
                    reasoning_id="",
                    model=model,
                    prompt_length=len(prompt),
                    start_time=llm_start,
                    end_time=time.time(),
                    success=True,
                    response_length=len(response),
                )
                
                steps = self._parse_steps_response(response)
                if steps:
                    return steps
                
                if attempt < self.config.llm.retry_attempts - 1:
                    self.trace_manager.record_retry(attempt + 1, self.config.llm.retry_attempts)
                    self.metrics.increment("llm_retry_total")
            
            except Exception as e:
                logger.warning("llm_call_failed", attempt=attempt + 1, error=str(e))
                
                if attempt < self.config.llm.retry_attempts - 1:
                    self.trace_manager.record_retry(attempt + 1, self.config.llm.retry_attempts, str(e))
                    await self._async_sleep(self.config.llm.retry_delay_seconds)
                else:
                    self.metrics.increment("llm_call_errors")
                    raise LLMCallError(f"فشل استدعاء LLM بعد {self.config.llm.retry_attempts} محاولات: {e}")
        
        return []

    async def _call_llm_with_retry(
        self,
        prompt: str,
        model: str,
    ) -> str:
        """استدعاء LLM مع إعادة المحاولة."""
        return await self.llm_manager.generate(
            prompt=prompt,
            model=model,
            temperature=self.config.llm.temperature,
            max_tokens=self.config.llm.max_tokens,
        )

    async def _async_sleep(self, seconds: float) -> None:
        """نوم غير متزامن."""
        import asyncio
        await asyncio.sleep(seconds)

    def _build_cot_prompt(self, problem: str, context: Optional[Dict[str, Any]]) -> str:
        """بناء prompt للـ Chain of Thought."""
        context_str = json.dumps(context, ensure_ascii=False) if context else ""
        
        return f"""قم بتحليل المشكلة التالية خطوة بخطوة:

المشكلة: {problem}

السياق: {context_str}

اتبع هذا النمط:
1. فهم المشكلة
2. تحديد المتغيرات الرئيسية
3. تحديد الافتراضات
4. استكشاف الخيارات
5. تقييم كل خيار
6. الوصول إلى نتيجة

أرجع JSON:
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "...",
      "reasoning": "...",
      "conclusion": "...",
      "confidence": 0.85,
      "alternatives": ["...", "..."]
    }}
  ]
}}"""

    def _build_tot_prompt(self, problem: str, context: Optional[Dict[str, Any]]) -> str:
        """بناء prompt للـ Tree of Thought."""
        context_str = json.dumps(context, ensure_ascii=False) if context else ""
        
        return f"""قم بتحليل المشكلة التالية باستخدام شجرة من القرارات:

المشكلة: {problem}
السياق: {context_str}

لكل عقدة في الشجرة:
- الوصف
- الاستدلال
- القرارات الفرعية
- الخلاصة

أرجع JSON:
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "...",
      "reasoning": "...",
      "conclusion": "...",
      "confidence": 0.85,
      "alternatives": ["...", "..."]
    }}
  ]
}}"""

    def _build_decomposition_prompt(self, problem: str, context: Optional[Dict[str, Any]]) -> str:
        """بناء prompt للـ Decomposition."""
        context_str = json.dumps(context, ensure_ascii=False) if context else ""
        
        return f"""قم بتفكيك المشكلة التالية إلى أجزاء صغيرة:

المشكلة: {problem}
السياق: {context_str}

لكل جزء:
- رقم الجزء
- الوصف
- العلاقة بالأجزاء الأخرى
- كيفية الحل

أرجع JSON:
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "...",
      "reasoning": "...",
      "conclusion": "...",
      "confidence": 0.85,
      "alternatives": []
    }}
  ]
}}"""

    def _build_first_principles_prompt(self, problem: str, context: Optional[Dict[str, Any]]) -> str:
        """بناء prompt للمبادئ الأولى."""
        context_str = json.dumps(context, ensure_ascii=False) if context else ""
        
        return f"""قم بتحليل المشكلة من المبادئ الأولى:

المشكلة: {problem}
السياق: {context_str}

1. ما هي الحقائق الأساسية؟
2. ما هي الافتراضات؟
3. كيف نبني الحل من الصفر؟

أرجع JSON:
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "...",
      "reasoning": "...",
      "conclusion": "...",
      "confidence": 0.85,
      "alternatives": []
    }}
  ]
}}"""

    def _build_multi_perspective_prompt(self, problem: str, context: Optional[Dict[str, Any]]) -> str:
        """بناء prompt لوجهات النظر المتعددة."""
        context_str = json.dumps(context, ensure_ascii=False) if context else ""
        
        return f"""قم بتحليل المشكلة من وجهات نظر متعددة:

المشكلة: {problem}
السياق: {context_str}

لكل وجهة نظر:
- المنظور
- التحليل
- الخلاصة

أرجع JSON:
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "...",
      "reasoning": "...",
      "conclusion": "...",
      "confidence": 0.85,
      "alternatives": []
    }}
  ]
}}"""

    def _build_analogy_prompt(self, problem: str, context: Optional[Dict[str, Any]]) -> str:
        """بناء prompt للقياس."""
        context_str = json.dumps(context, ensure_ascii=False) if context else ""
        
        return f"""قم بحل المشكلة بالقياس لمشكلة مشابهة:

المشكلة: {problem}
السياق: {context_str}

1. ما هي المشكلة المماثلة؟
2. كيف تم حلها؟
3. كيف نطبق الحل؟

أرجع JSON:
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "...",
      "reasoning": "...",
      "conclusion": "...",
      "confidence": 0.85,
      "alternatives": []
    }}
  ]
}}"""

    def _parse_steps_response(self, response: str) -> List[ReasoningStep]:
        """تحليل استجابة خطوات الاستدلال."""
        try:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                steps = []
                
                for step_data in data.get("steps", []):
                    step = ReasoningStep(
                        step_number=step_data.get("step_number", 0),
                        description=step_data.get("description", ""),
                        reasoning=step_data.get("reasoning", ""),
                        conclusion=step_data.get("conclusion", ""),
                        confidence=float(step_data.get("confidence", 0.5)),
                        alternatives=step_data.get("alternatives", []),
                    )
                    steps.append(step)
                
                return steps
        except json.JSONDecodeError as e:
            logger.warning("json_parse_failed", error=str(e))
        
        return []

    async def _identify_missing_information(
        self,
        problem: str,
        context: Optional[Dict[str, Any]],
        reasoning_steps: List[ReasoningStep],
    ) -> List[str]:
        """اكتشاف المعلومات الناقصة."""
        try:
            steps_summary = "\n".join([
                f"- {s.step_number}: {s.description}" for s in reasoning_steps
            ])
            
            prompt = f"""بناءً على خطوات الاستدلال التالية:

{steps_summary}

ما هي المعلومات التي نحتاجها لاتخاذ قرار أفضل؟

أرجع قائمة JSON:
["معلومة 1", "معلومة 2", ...]"""
            
            response = await self._call_llm_with_retry(
                prompt=prompt,
                model=self.config.llm.reasoning_model,
            )
            
            json_start = response.find("[")
            json_end = response.rfind("]") + 1
            
            if json_start >= 0 and json_end > json_start:
                return json.loads(response[json_start:json_end])
        except Exception as e:
            logger.warning("missing_info_failed", error=str(e))
        
        return []

    async def _assess_risks(
        self,
        problem: str,
        context: Optional[Dict[str, Any]],
        reasoning_steps: List[ReasoningStep],
    ) -> List[RiskAssessment]:
        """تقييم المخاطر."""
        try:
            prompt = f"""قيّم المخاطر المحتملة للمشكلة التالية:

المشكلة: {problem}

الحد الأقصى للمخاطر: {self.config.risk_assessment.max_risks_per_analysis}

أرجع JSON:
{{
  "risks": [
    {{
      "risk_type": "...",
      "description": "...",
      "severity": "...",
      "probability": 0.5,
      "impact": "...",
      "mitigation_strategy": "..."
    }}
  ]
}}"""
            
            response = await self._call_llm_with_retry(
                prompt=prompt,
                model=self.config.llm.reasoning_model,
            )
            
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                risks = []
                
                for risk_data in data.get("risks", []):
                    severity = risk_data.get("severity", "medium")
                    if severity not in ("low", "medium", "high", "critical"):
                        severity = "medium"
                    
                    risk = RiskAssessment(
                        risk_type=risk_data.get("risk_type", ""),
                        description=risk_data.get("description", ""),
                        severity=severity,
                        probability=float(risk_data.get("probability", 0.5)),
                        impact=risk_data.get("impact", ""),
                        mitigation_strategy=risk_data.get("mitigation_strategy", ""),
                    )
                    risks.append(risk)
                
                if self.config.risk_assessment.severity_threshold:
                    threshold_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
                    min_level = threshold_order.get(
                        self.config.risk_assessment.severity_threshold, 1
                    )
                    risks = [
                        r for r in risks
                        if threshold_order.get(r.severity, 0) >= min_level
                    ][:self.config.risk_assessment.max_risks_per_analysis]
                
                return risks
        except Exception as e:
            logger.warning("risk_assessment_failed", error=str(e))
        
        return []

    async def _propose_solutions(
        self,
        problem: str,
        context: Optional[Dict[str, Any]],
        reasoning_steps: List[ReasoningStep],
        risks: List[RiskAssessment],
    ) -> List[SolutionOption]:
        """اقتراح خيارات الحل."""
        try:
            risks_summary = "\n".join([
                f"- {r.risk_type}: {r.description}" for r in risks
            ]) or "لا توجد مخاطر محددة"
            
            prompt = f"""اقترح حلولاً للمشكلة التالية:

المشكلة: {problem}

المخاطر المحتملة:
{risks_summary}

الحد الأقصى للحلول: {self.config.solution.max_solutions}

لكل حل، قدّم:
- العنوان والوصف
- الإيجابيات ({self.config.solution.min_pros}-{self.config.solution.max_pros})
- السلبيات ({self.config.solution.min_cons}-{self.config.solution.max_cons})
- تقدير الجهد والوقت
- درجة الجدوى (0-1)

أرجع JSON:
{{
  "solutions": [
    {{
      "title": "...",
      "description": "...",
      "pros": ["..."],
      "cons": ["..."],
      "effort_estimate": "...",
      "time_estimate": "...",
      "risk_level": "...",
      "feasibility_score": 0.8
    }}
  ]
}}"""
            
            response = await self._call_llm_with_retry(
                prompt=prompt,
                model=self.config.llm.primary_model,
            )
            
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                solutions = []
                
                for sol_data in data.get("solutions", []):
                    solution = SolutionOption(
                        title=sol_data.get("title", ""),
                        description=sol_data.get("description", ""),
                        pros=sol_data.get("pros", [])[:self.config.solution.max_pros],
                        cons=sol_data.get("cons", [])[:self.config.solution.max_cons],
                        effort_estimate=sol_data.get("effort_estimate", "medium"),
                        time_estimate=sol_data.get("time_estimate", ""),
                        risk_level=sol_data.get("risk_level", "medium"),
                        feasibility_score=float(sol_data.get("feasibility_score", 0.5)),
                    )
                    solutions.append(solution)
                
                while len(solutions) < self.config.solution.min_solutions:
                    solutions.append(SolutionOption(
                        title=f"حل بديل {len(solutions) + 1}",
                        description="حل بديل يحتاج مزيداً من التحليل",
                        pros=["مرونة"],
                        cons=["غير مكتمل"],
                    ))
                
                return solutions[:self.config.solution.max_solutions]
        except Exception as e:
            logger.warning("solution_proposal_failed", error=str(e))
        
        return []

    async def _select_best_solution(
        self,
        solutions: List[SolutionOption],
    ) -> Optional[SolutionOption]:
        """اختيار أفضل حل."""
        if not solutions:
            return None
        
        best = max(solutions, key=lambda s: s.feasibility_score)
        best.recommended = True
        return best

    def _build_reasoning_summary(
        self,
        reasoning_steps: List[ReasoningStep],
        missing_info: List[str],
        risks: List[RiskAssessment],
        solutions: List[SolutionOption],
        recommended: Optional[SolutionOption],
    ) -> str:
        """بناء ملخص الاستدلال."""
        summary_parts = []
        
        if reasoning_steps:
            summary_parts.append(f"تم إجراء {len(reasoning_steps)} خطوات استدلال.")
        
        if missing_info:
            summary_parts.append(f"معلومات ناقصة: {', '.join(missing_info[:2])}.")
        
        if risks:
            critical = [r for r in risks if r.severity == "critical"]
            high = [r for r in risks if r.severity == "high"]
            
            if critical:
                summary_parts.append(f"مخاطر حرجة: {len(critical)}.")
            elif high:
                summary_parts.append(f"مخاطر عالية: {len(high)}.")
        
        if solutions:
            summary_parts.append(f"تم اقتراح {len(solutions)} حل.")
        
        if recommended:
            summary_parts.append(f"الحل الموصى به: {recommended.title}.")
        
        return " ".join(summary_parts) if summary_parts else "تم إكمال الاستدلال."

    def _calculate_overall_confidence(
        self,
        reasoning_steps: List[ReasoningStep],
        solutions: List[SolutionOption],
        recommended: Optional[SolutionOption],
    ) -> float:
        """حساب درجة الثقة الكلية."""
        if not reasoning_steps:
            return self.config.error_recovery.fallback_confidence
        
        steps_confidence = sum(s.confidence for s in reasoning_steps) / len(reasoning_steps)
        
        if recommended:
            return (steps_confidence + recommended.feasibility_score) / 2
        
        return steps_confidence * 0.7

    def get_reasoning(self, reasoning_id: str) -> Optional[ReasoningResult]:
        """الحصول على نتيجة استدلال محفوظة."""
        return self._reasoning_cache.get(reasoning_id)

    def list_reasoning(self, limit: int = 10) -> List[Dict[str, Any]]:
        """قائمة بآخر نتائج الاستدلال."""
        results = list(self._reasoning_cache.values())
        results.sort(key=lambda r: r.created_at, reverse=True)
        return [r.to_dict() for r in results[:limit]]

    def get_metrics_summary(self) -> Dict[str, Any]:
        """الحصول على ملخص المقاييس."""
        return self.metrics.get_summary()

    def get_trace_statistics(self) -> Dict[str, Any]:
        """الحصول على إحصائيات التتبع."""
        return self.trace_manager.get_statistics()

    def clear_cache(self) -> int:
        """مسح التخزين المؤقت."""
        count = len(self._reasoning_cache)
        self._reasoning_cache.clear()
        logger.info("cache_cleared", entries_removed=count)
        return count


_reasoning_engine: Optional[ReasoningEngine] = None


def get_reasoning_engine(
    llm_manager: Optional[LLMManager] = None,
    config: Optional[ReasoningEngineConfig] = None,
) -> ReasoningEngine:
    """
    الحصول على instance من ReasoningEngine.
    
    يستخدم singleton pattern للتأكد من وجود instance واحد فقط.
    """
    global _reasoning_engine
    
    if _reasoning_engine is None:
        if llm_manager is None:
            from hajeen_platform.core.llm import get_llm_manager
            llm_manager = get_llm_manager()
        
        _reasoning_engine = ReasoningEngine(
            llm_manager=llm_manager,
            config=config,
        )
    
    return _reasoning_engine


def reset_reasoning_engine() -> None:
    """إعادة تعيين محرك الاستدلال."""
    global _reasoning_engine
    _reasoning_engine = None
    logger.info("reasoning_engine_reset")


def create_reasoning_engine(
    llm_manager: LLMManager,
    config: Optional[ReasoningEngineConfig] = None,
) -> ReasoningEngine:
    """
    إنشاء محرك استدلال جديد.
    
    لا يستخدم singleton pattern - يُنشئ instance جديد في كل مرة.
    """
    return ReasoningEngine(
        llm_manager=llm_manager,
        config=config,
    )
