"""
Expert Models Layer — طبقة النماذج الخبيرة
=============================================
جزء من HajeenBrainV3 Pipeline الموحّد.

يقوم بـ:
1. تنسيق استدعاء نماذج متخصصة
2. دمج نتائج نماذج متعددة (Ensemble, Debate, Voting)
3. إدارة fallback بين النماذج
4. تسجيل الأداء لكل نموذج
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class CollaborationMode(Enum):
    """أنماط التعاون بين النماذج."""
    CHAIN = "chain"              # كل نموذج يحسّن إجابة السابق
    ENSEMBLE = "ensemble"        # دمج الإجابات
    DEBATE = "debate"            # تجادل
    VOTING = "voting"            # تصويت
    EXPERT = "expert"            # كل نموذج خبير في جانب
    CASCADE = "cascade"          # fallback تسلسلي


@dataclass
class ExpertModel:
    """نموذج خبير واحد."""
    model_id: str
    provider: str
    expertise: List[str]  # مجالات الخبرة
    confidence_threshold: float = 0.7
    max_tokens: int = 2048
    temperature: float = 0.7
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExpertResult:
    """نتيجة من نموذج خبير واحد."""
    model_id: str
    response: str
    confidence: float
    latency_ms: float
    tokens_used: int
    expertise_match: float  # 0.0 to 1.0


@dataclass
class CollaborationResult:
    """نتيجة التعاون بين النماذج."""
    mode: CollaborationMode
    final_answer: str
    individual_results: List[ExpertResult]
    consensus_score: float  # 0.0 to 1.0
    total_latency_ms: float
    total_tokens: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class ExpertModelsLayer:
    """
    طبقة النماذج الخبيرة — تنسيق نماذج متعددة.

    يستخدم ضمن HajeenBrainV3 Pipeline:
      Policy → Intent → Context → Reasoning → Planning → Decision → [Expert Models] → Execute
    """

    def __init__(self, llm_manager=None):
        self.llm_manager = llm_manager
        self.experts: Dict[str, ExpertModel] = {}
        self.performance_log: List[Dict[str, Any]] = []
        self._register_default_experts()
        logger.info("ExpertModelsLayer initialized with %d experts", len(self.experts))

    # ── Core Methods ──────────────────────────────────────────────────────

    async def collaborate(
        self,
        query: str,
        mode: CollaborationMode = CollaborationMode.ENSEMBLE,
        required_expertise: Optional[List[str]] = None,
        max_models: int = 3,
    ) -> CollaborationResult:
        """
        التعاون الرئيسي بين النماذج الخبيرة.

        Args:
            query: الاستعلام
            mode: نمط التعاون
            required_expertise: الخبرات المطلوبة
            max_models: الحد الأقصى للنماذج
        """
        start = time.perf_counter()

        # 1. Select relevant experts
        selected = self._select_experts(query, required_expertise, max_models)

        if not selected:
            return CollaborationResult(
                mode=mode,
                final_answer="No suitable experts available",
                individual_results=[],
                consensus_score=0.0,
                total_latency_ms=0.0,
                total_tokens=0,
            )

        logger.info("Collaboration: mode=%s, experts=%s", mode.value, [e.model_id for e in selected])

        # 2. Execute based on mode
        if mode == CollaborationMode.CHAIN:
            results = await self._chain_mode(query, selected)
        elif mode == CollaborationMode.ENSEMBLE:
            results = await self._ensemble_mode(query, selected)
        elif mode == CollaborationMode.DEBATE:
            results = await self._debate_mode(query, selected)
        elif mode == CollaborationMode.VOTING:
            results = await self._voting_mode(query, selected)
        elif mode == CollaborationMode.EXPERT:
            results = await self._expert_mode(query, selected)
        else:
            results = await self._ensemble_mode(query, selected)

        # 3. Merge results
        final_answer = self._merge_results(results, mode)
        consensus = self._calculate_consensus(results)

        elapsed = (time.perf_counter() - start) * 1000

        result = CollaborationResult(
            mode=mode,
            final_answer=final_answer,
            individual_results=results,
            consensus_score=consensus,
            total_latency_ms=elapsed,
            total_tokens=sum(r.tokens_used for r in results),
            metadata={
                "models_used": [r.model_id for r in results],
                "avg_confidence": sum(r.confidence for r in results) / len(results) if results else 0,
            }
        )

        self.performance_log.append({
            "query": query[:100],
            "mode": mode.value,
            "latency_ms": elapsed,
            "consensus": consensus,
        })

        return result

    async def stream_collaborate(
        self,
        query: str,
        mode: CollaborationMode = CollaborationMode.ENSEMBLE,
    ) -> AsyncIterator[str]:
        """تعاون متدفق — يُرسل chunks تدريجياً."""
        result = await self.collaborate(query, mode)

        # Stream the final answer in chunks
        words = result.final_answer.split()
        chunk_size = max(1, len(words) // 10)

        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i+chunk_size])
            yield chunk + " "
            await asyncio.sleep(0.05)  # Simulate streaming

    # ── Collaboration Modes ───────────────────────────────────────────────

    async def _chain_mode(self, query: str, experts: List[ExpertModel]) -> List[ExpertResult]:
        """كل نموذج يحسّن إجابة السابق."""
        results = []
        current_input = query

        for expert in experts:
            prompt = f"حسّن الإجابة التالية:

{current_input}

أجب باختصار:"
            response, latency, tokens = await self._call_model(expert, prompt)

            results.append(ExpertResult(
                model_id=expert.model_id,
                response=response,
                confidence=0.7,
                latency_ms=latency,
                tokens_used=tokens,
                expertise_match=self._match_expertise(expert, query),
            ))

            current_input = response

        return results

    async def _ensemble_mode(self, query: str, experts: List[ExpertModel]) -> List[ExpertResult]:
        """جميع النماذج بالتوازي ثم دمج."""
        tasks = [self._call_model_async(expert, query) for expert in experts]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        results = []
        for expert, resp in zip(experts, responses):
            if isinstance(resp, Exception):
                logger.warning("Model %s failed: %s", expert.model_id, resp)
                continue

            response, latency, tokens = resp
            results.append(ExpertResult(
                model_id=expert.model_id,
                response=response,
                confidence=0.7,
                latency_ms=latency,
                tokens_used=tokens,
                expertise_match=self._match_expertise(expert, query),
            ))

        return results

    async def _debate_mode(self, query: str, experts: List[ExpertModel]) -> List[ExpertResult]:
        """النماذج تتجادل للوصول لإجابة أفضل."""
        # Round 1: Each model gives initial answer
        round1 = await self._ensemble_mode(query, experts)

        # Round 2: Each model critiques others
        critiques = []
        for i, expert in enumerate(experts):
            others = [r for j, r in enumerate(round1) if j != i]
            critique_prompt = f"نقد الإجابات التالية وقدّم الإجابة الأفضل:

"
            for r in others:
                critique_prompt += f"- {r.model_id}: {r.response[:200]}...
"

            response, latency, tokens = await self._call_model(expert, critique_prompt)
            critiques.append(ExpertResult(
                model_id=expert.model_id,
                response=response,
                confidence=0.8,
                latency_ms=latency,
                tokens_used=tokens,
                expertise_match=self._match_expertise(expert, query),
            ))

        return critiques

    async def _voting_mode(self, query: str, experts: List[ExpertModel]) -> List[ExpertResult]:
        """الإجابة الأكثر تشابهاً تفوز."""
        results = await self._ensemble_mode(query, experts)

        # Find most common answer (simple similarity)
        if len(results) < 2:
            return results

        # Use first answer as reference, score others by similarity
        reference = results[0].response
        for r in results[1:]:
            similarity = self._text_similarity(reference, r.response)
            r.confidence = similarity

        return results

    async def _expert_mode(self, query: str, experts: List[ExpertModel]) -> List[ExpertResult]:
        """كل نموذج خبير في جانب محدد."""
        # Assign sub-tasks based on expertise
        results = []

        for expert in experts:
            sub_task = f"[{expert.expertise[0] if expert.expertise else 'general'}] {query}"
            response, latency, tokens = await self._call_model(expert, sub_task)

            results.append(ExpertResult(
                model_id=expert.model_id,
                response=response,
                confidence=0.75,
                latency_ms=latency,
                tokens_used=tokens,
                expertise_match=self._match_expertise(expert, query),
            ))

        return results

    # ── Model Calling ────────────────────────────────────────────────────

    async def _call_model_async(
        self,
        expert: ExpertModel,
        prompt: str,
    ) -> Tuple[str, float, int]:
        """استدعاء نموذج غير متزامن."""
        return await self._call_model(expert, prompt)

    async def _call_model(
        self,
        expert: ExpertModel,
        prompt: str,
    ) -> Tuple[str, float, int]:
        """استدعاء نموذج واحد."""
        start = time.perf_counter()

        if self.llm_manager:
            try:
                response = await self.llm_manager.agenerate(
                    prompt,
                    model_id=expert.model_id,
                    max_tokens=expert.max_tokens,
                    temperature=expert.temperature,
                )
                latency = (time.perf_counter() - start) * 1000
                tokens = len(response.split())  # rough estimate
                return response, latency, tokens
            except Exception as exc:
                logger.warning("Model %s failed: %s", expert.model_id, exc)

        # Fallback
        latency = (time.perf_counter() - start) * 1000
        return f"[Fallback response from {expert.model_id}]", latency, 0

    # ── Result Merging ────────────────────────────────────────────────────

    def _merge_results(self, results: List[ExpertResult], mode: CollaborationMode) -> str:
        """دمج نتائج النماذج."""
        if not results:
            return "No results available"

        if mode == CollaborationMode.CHAIN:
            return results[-1].response  # Last model's output

        if mode == CollaborationMode.VOTING:
            # Return the most confident
            best = max(results, key=lambda r: r.confidence)
            return best.response

        # Default: concatenate with attribution
        merged = []
        for r in results:
            merged.append(f"[{r.model_id}]: {r.response}")
        return "

".join(merged)

    def _calculate_consensus(self, results: List[ExpertResult]) -> float:
        """حساب درجة التوافق."""
        if len(results) < 2:
            return 1.0

        # Average pairwise similarity
        similarities = []
        for i in range(len(results)):
            for j in range(i+1, len(results)):
                sim = self._text_similarity(results[i].response, results[j].response)
                similarities.append(sim)

        return sum(similarities) / len(similarities) if similarities else 0.0

    def _text_similarity(self, text1: str, text2: str) -> float:
        """حساب تشابه نصي بسيط."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = words1 & words2
        union = words1 | words2
        return len(intersection) / len(union)

    # ── Expert Management ────────────────────────────────────────────────

    def _select_experts(
        self,
        query: str,
        required_expertise: Optional[List[str]],
        max_models: int,
    ) -> List[ExpertModel]:
        """اختيار النماذج المناسبة."""
        scored = []

        for expert in self.experts.values():
            match = self._match_expertise(expert, query)
            if required_expertise:
                req_match = sum(1 for e in required_expertise if any(e in ex for ex in expert.expertise))
                match = max(match, req_match / len(required_expertise))

            scored.append((expert, match))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [e for e, _ in scored[:max_models]]

    def _match_expertise(self, expert: ExpertModel, query: str) -> float:
        """تطابق خبرة النموذج مع الاستعلام."""
        query_lower = query.lower()
        matches = sum(1 for exp in expert.expertise if exp.lower() in query_lower)
        return min(matches / max(len(expert.expertise), 1), 1.0)

    def _register_default_experts(self):
        """تسجيل النماذج الخبيرة الافتراضية."""
        self.experts = {
            "general": ExpertModel(
                model_id="general",
                provider="openai",
                expertise=["general", "conversation", "analysis"],
                confidence_threshold=0.6,
            ),
            "code": ExpertModel(
                model_id="code",
                provider="openai",
                expertise=["code", "programming", "debugging", "algorithms"],
                confidence_threshold=0.8,
                temperature=0.2,
            ),
            "creative": ExpertModel(
                model_id="creative",
                provider="openai",
                expertise=["creative", "writing", "storytelling", "design"],
                confidence_threshold=0.7,
                temperature=0.9,
            ),
            "math": ExpertModel(
                model_id="math",
                provider="openai",
                expertise=["math", "mathematics", "statistics", "logic"],
                confidence_threshold=0.85,
                temperature=0.1,
            ),
            "science": ExpertModel(
                model_id="science",
                provider="openai",
                expertise=["science", "physics", "chemistry", "biology"],
                confidence_threshold=0.8,
            ),
        }

    def register_expert(self, expert: ExpertModel):
        """تسجيل نموذج خبير جديد."""
        self.experts[expert.model_id] = expert
        logger.info("Registered expert: %s", expert.model_id)

    def get_performance_stats(self) -> Dict[str, Any]:
        """إحصائيات الأداء."""
        if not self.performance_log:
            return {}

        avg_latency = sum(p["latency_ms"] for p in self.performance_log) / len(self.performance_log)
        avg_consensus = sum(p["consensus"] for p in self.performance_log) / len(self.performance_log)

        return {
            "total_collaborations": len(self.performance_log),
            "avg_latency_ms": avg_latency,
            "avg_consensus": avg_consensus,
            "mode_distribution": self._mode_distribution(),
        }

    def _mode_distribution(self) -> Dict[str, int]:
        """توزيع أنماط التعاون."""
        from collections import Counter
        return Counter(p["mode"] for p in self.performance_log)


# ── Singleton ─────────────────────────────────────────────────────────────

_expert_layer: Optional[ExpertModelsLayer] = None


def get_expert_models_layer(llm_manager=None) -> ExpertModelsLayer:
    """الحصول على طبقة النماذج الخبيرة — Singleton."""
    global _expert_layer
    if _expert_layer is None:
        _expert_layer = ExpertModelsLayer(llm_manager=llm_manager)
    return _expert_layer
