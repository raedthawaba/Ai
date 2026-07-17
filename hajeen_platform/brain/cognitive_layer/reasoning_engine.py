"""
Reasoning Engine — محرك الاستدلال العميق
========================================

يقوم بـ:
- تحليل المشكلة بعمق
- اكتشاف المعلومات الناقصة
- تقييم المخاطر
- اقتراح الحلول
- المقارنة بين البدائل
- اختيار أفضل خطة

يستخدم chain-of-thought reasoning و multi-step analysis.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from hajeen_platform.core.llm import LLMManager

logger = logging.getLogger(__name__)


class ReasoningStrategy(str, Enum):
    """استراتيجيات الاستدلال."""
    CHAIN_OF_THOUGHT = "chain_of_thought"          # سلسلة من الخطوات
    TREE_OF_THOUGHT = "tree_of_thought"            # شجرة من الخيارات
    DECOMPOSITION = "decomposition"                # تفكيك المشكلة
    ANALOGY = "analogy"                            # القياس والتشبيه
    FIRST_PRINCIPLES = "first_principles"          # المبادئ الأساسية
    MULTI_PERSPECTIVE = "multi_perspective"        # وجهات نظر متعددة


@dataclass
class ReasoningStep:
    """خطوة واحدة في الاستدلال."""
    step_id: str
    step_number: int
    description: str
    reasoning: str
    conclusion: str
    confidence: float
    alternatives: List[str]


@dataclass
class RiskAssessment:
    """تقييم المخاطر."""
    risk_id: str
    risk_type: str  # technical, operational, security, etc.
    description: str
    severity: str  # low, medium, high, critical
    probability: float  # 0-1
    impact: str
    mitigation_strategy: str


@dataclass
class SolutionOption:
    """خيار حل."""
    option_id: str
    title: str
    description: str
    pros: List[str]
    cons: List[str]
    effort_estimate: str  # low, medium, high
    time_estimate: str
    risk_level: str
    feasibility_score: float  # 0-1
    recommended: bool


@dataclass
class ReasoningResult:
    """نتيجة الاستدلال الكاملة."""
    reasoning_id: str
    strategy_used: ReasoningStrategy
    
    # الخطوات
    reasoning_steps: List[ReasoningStep]
    
    # المعلومات الناقصة
    missing_information: List[str]
    
    # تقييم المخاطر
    risks: List[RiskAssessment]
    
    # الحلول المقترحة
    solution_options: List[SolutionOption]
    
    # الخيار الأفضل
    recommended_solution: Optional[SolutionOption]
    
    # الثقة والاستدلال
    overall_confidence: float
    reasoning_summary: str
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reasoning_id": self.reasoning_id,
            "strategy_used": self.strategy_used.value,
            "reasoning_steps": len(self.reasoning_steps),
            "missing_information": self.missing_information,
            "risks": len(self.risks),
            "solution_options": len(self.solution_options),
            "recommended_solution": self.recommended_solution.title if self.recommended_solution else None,
            "overall_confidence": round(self.overall_confidence, 3),
            "reasoning_summary": self.reasoning_summary,
            "created_at": self.created_at,
        }


class ReasoningEngine:
    """
    محرك الاستدلال العميق.
    
    يستخدم LLM مع prompts متخصصة لإجراء استدلال متعدد الخطوات.
    """

    def __init__(self, llm_manager: LLMManager) -> None:
        self.llm_manager = llm_manager
        self._reasoning_cache: Dict[str, ReasoningResult] = {}
        logger.info("ReasoningEngine: initialized")

    async def reason(
        self,
        problem: str,
        context: Optional[Dict[str, Any]] = None,
        strategy: ReasoningStrategy = ReasoningStrategy.CHAIN_OF_THOUGHT,
    ) -> ReasoningResult:
        """
        إجراء استدلال عميق حول مشكلة.
        
        الخطوات:
        1. تحليل المشكلة
        2. اكتشاف المعلومات الناقصة
        3. تقييم المخاطر
        4. اقتراح الحلول
        5. المقارنة والتقييم
        """
        reasoning_id = str(uuid.uuid4())
        
        try:
            # ── Step 1: تحليل المشكلة ─────────────────────────────────
            reasoning_steps = await self._perform_chain_of_thought(
                problem, context, strategy
            )
            
            # ── Step 2: اكتشاف المعلومات الناقصة ──────────────────────
            missing_info = await self._identify_missing_information(
                problem, context, reasoning_steps
            )
            
            # ── Step 3: تقييم المخاطر ─────────────────────────────────
            risks = await self._assess_risks(problem, context, reasoning_steps)
            
            # ── Step 4: اقتراح الحلول ─────────────────────────────────
            solutions = await self._propose_solutions(
                problem, context, reasoning_steps, risks
            )
            
            # ── Step 5: اختيار أفضل حل ───────────────────────────────
            recommended = await self._select_best_solution(solutions)
            
            # ── Step 6: بناء الملخص ──────────────────────────────────
            summary = self._build_reasoning_summary(
                reasoning_steps, missing_info, risks, solutions, recommended
            )
            
            # ── Step 7: حساب الثقة الكلية ────────────────────────────
            overall_confidence = self._calculate_overall_confidence(
                reasoning_steps, solutions, recommended
            )
            
            # بناء النتيجة
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
                metadata={"problem": problem, "context": context or {}},
            )
            
            # تخزين مؤقت
            self._reasoning_cache[reasoning_id] = result
            
            logger.info(
                "reasoning_engine: completed reasoning reasoning_id=%s steps=%d solutions=%d confidence=%.3f",
                reasoning_id, len(reasoning_steps), len(solutions), overall_confidence
            )
            
            return result
        
        except Exception as e:
            logger.error("reasoning_engine: error during reasoning: %s", e, exc_info=True)
            # استجابة احتياطية
            return ReasoningResult(
                reasoning_id=reasoning_id,
                strategy_used=strategy,
                reasoning_steps=[],
                missing_information=["فشل التحليل"],
                risks=[],
                solution_options=[],
                recommended_solution=None,
                overall_confidence=0.3,
                reasoning_summary="فشل الاستدلال، يرجى المحاولة لاحقاً",
                metadata={"error": str(e)},
            )

    async def _perform_chain_of_thought(
        self,
        problem: str,
        context: Optional[Dict[str, Any]],
        strategy: ReasoningStrategy,
    ) -> List[ReasoningStep]:
        """إجراء chain-of-thought reasoning."""
        try:
            context_str = json.dumps(context, ensure_ascii=False) if context else ""
            
            prompt = f"""قم بتحليل المشكلة التالية خطوة بخطوة:

المشكلة: {problem}

السياق: {context_str}

اتبع هذا النمط:
1. فهم المشكلة
2. تحديد المتغيرات الرئيسية
3. تحديد الافتراضات
4. استكشاف الخيارات
5. تقييم كل خيار
6. الوصول إلى نتيجة

لكل خطوة، قدّم:
- الوصف
- الاستدلال
- الخلاصة
- درجة الثقة (0-1)
- البدائل المحتملة

أرجع JSON:
{{
  "steps": [
    {{
      "step_number": 1,
      "description": "...",
      "reasoning": "...",
      "conclusion": "...",
      "confidence": 0.85,
      "alternatives": [...]
    }},
    ...
  ]
}}"""
            
            response = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o",  # نموذج قوي للاستدلال
                temperature=0.5,
                max_tokens=2000,
            )
            
            # تحليل الاستجابة
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                steps = []
                for step_data in data.get("steps", []):
                    step = ReasoningStep(
                        step_id=str(uuid.uuid4()),
                        step_number=step_data.get("step_number", 0),
                        description=step_data.get("description", ""),
                        reasoning=step_data.get("reasoning", ""),
                        conclusion=step_data.get("conclusion", ""),
                        confidence=float(step_data.get("confidence", 0.5)),
                        alternatives=step_data.get("alternatives", []),
                    )
                    steps.append(step)
                return steps
        except Exception as e:
            logger.warning("reasoning_engine: failed to perform chain-of-thought: %s", e)
        
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
                f"Step {s.step_number}: {s.conclusion}" for s in reasoning_steps
            ])
            
            prompt = f"""بناءً على التحليل التالي، حدّد المعلومات الناقصة:

المشكلة: {problem}

التحليل:
{steps_summary}

ما هي المعلومات التي نحتاجها لاتخاذ قرار أفضل؟

أرجع قائمة JSON:
["معلومة 1", "معلومة 2", ...]"""
            
            response = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=500,
            )
            
            json_start = response.find("[")
            json_end = response.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(response[json_start:json_end])
        except Exception as e:
            logger.warning("reasoning_engine: failed to identify missing information: %s", e)
        
        return []

    async def _assess_risks(
        self,
        problem: str,
        context: Optional[Dict[str, Any]],
        reasoning_steps: List[ReasoningStep],
    ) -> List[RiskAssessment]:
        """تقييم المخاطر."""
        try:
            prompt = f"""قيّم المخاطر المحتملة:

المشكلة: {problem}

قم بـ:
1. تحديد المخاطر المحتملة (تقنية، تشغيلية، أمنية، إلخ)
2. تقدير الشدة (low, medium, high, critical)
3. تقدير الاحتمالية (0-1)
4. وصف التأثير
5. اقتراح استراتيجية التخفيف

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
    }},
    ...
  ]
}}"""
            
            response = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=800,
            )
            
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                risks = []
                for risk_data in data.get("risks", []):
                    risk = RiskAssessment(
                        risk_id=str(uuid.uuid4()),
                        risk_type=risk_data.get("risk_type", ""),
                        description=risk_data.get("description", ""),
                        severity=risk_data.get("severity", "medium"),
                        probability=float(risk_data.get("probability", 0.5)),
                        impact=risk_data.get("impact", ""),
                        mitigation_strategy=risk_data.get("mitigation_strategy", ""),
                    )
                    risks.append(risk)
                return risks
        except Exception as e:
            logger.warning("reasoning_engine: failed to assess risks: %s", e)
        
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
            ])
            
            prompt = f"""اقترح حلولاً للمشكلة:

المشكلة: {problem}

المخاطر المحتملة:
{risks_summary}

لكل حل، قدّم:
1. العنوان
2. الوصف
3. الإيجابيات (3-5)
4. السلبيات (2-4)
5. تقدير الجهد (low, medium, high)
6. تقدير الوقت
7. مستوى المخاطرة
8. درجة الجدوى (0-1)

أرجع JSON:
{{
  "solutions": [
    {{
      "title": "...",
      "description": "...",
      "pros": [...],
      "cons": [...],
      "effort_estimate": "...",
      "time_estimate": "...",
      "risk_level": "...",
      "feasibility_score": 0.8
    }},
    ...
  ]
}}"""
            
            response = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o",
                temperature=0.5,
                max_tokens=1500,
            )
            
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response[json_start:json_end])
                solutions = []
                for sol_data in data.get("solutions", []):
                    solution = SolutionOption(
                        option_id=str(uuid.uuid4()),
                        title=sol_data.get("title", ""),
                        description=sol_data.get("description", ""),
                        pros=sol_data.get("pros", []),
                        cons=sol_data.get("cons", []),
                        effort_estimate=sol_data.get("effort_estimate", "medium"),
                        time_estimate=sol_data.get("time_estimate", ""),
                        risk_level=sol_data.get("risk_level", "medium"),
                        feasibility_score=float(sol_data.get("feasibility_score", 0.5)),
                        recommended=False,
                    )
                    solutions.append(solution)
                return solutions
        except Exception as e:
            logger.warning("reasoning_engine: failed to propose solutions: %s", e)
        
        return []

    async def _select_best_solution(
        self,
        solutions: List[SolutionOption],
    ) -> Optional[SolutionOption]:
        """اختيار أفضل حل."""
        if not solutions:
            return None
        
        # اختيار الحل بأعلى درجة جدوى
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
        summary = f"تم إجراء {len(reasoning_steps)} خطوات استدلال. "
        
        if missing_info:
            summary += f"معلومات ناقصة: {', '.join(missing_info[:2])}. "
        
        if risks:
            critical_risks = [r for r in risks if r.severity == "critical"]
            if critical_risks:
                summary += f"مخاطر حرجة: {len(critical_risks)}. "
        
        if solutions:
            summary += f"تم اقتراح {len(solutions)} حل. "
        
        if recommended:
            summary += f"الحل الموصى به: {recommended.title}."
        
        return summary

    def _calculate_overall_confidence(
        self,
        reasoning_steps: List[ReasoningStep],
        solutions: List[SolutionOption],
        recommended: Optional[SolutionOption],
    ) -> float:
        """حساب درجة الثقة الكلية."""
        if not reasoning_steps:
            return 0.3
        
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


# Singleton
_reasoning_engine: Optional[ReasoningEngine] = None


def get_reasoning_engine(llm_manager: Optional[LLMManager] = None) -> ReasoningEngine:
    """الحصول على instance من ReasoningEngine."""
    global _reasoning_engine
    if _reasoning_engine is None:
        if llm_manager is None:
            from hajeen_platform.core.llm import get_llm_manager
            llm_manager = get_llm_manager()
        _reasoning_engine = ReasoningEngine(llm_manager)
    return _reasoning_engine
