"""
Knowledge Distillation Pipeline — استخلاص المعرفة من النماذج الخارجية
======================================================================
كل مرة يستخدم Hajeen نموذجاً خارجياً، لا يحفظ الإجابة فقط.
بل يستخرج: طريقة التفكير، ترتيب الخطوات، سبب القرار، نوع المهمة،
جودة الحل، الأدوات المستخدمة، نمط الاستدلال.
ثم يحوّلها إلى بيانات تدريب لـ Hajeen.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ReasoningPattern(str, Enum):
    STEP_BY_STEP = "step_by_step"       # خطوة بخطوة
    ANALOGICAL = "analogical"           # قياسي
    DEDUCTIVE = "deductive"             # استنتاجي
    INDUCTIVE = "inductive"             # استقرائي
    CAUSAL = "causal"                   # سببي
    COMPARATIVE = "comparative"         # مقارن
    CREATIVE = "creative"               # إبداعي
    UNKNOWN = "unknown"


@dataclass
class DistilledKnowledge:
    """وحدة المعرفة المستخلصة من تفاعل واحد مع نموذج خارجي."""
    knowledge_id: str
    source_model: str
    task_type: str
    domain: str
    original_query: str
    model_response: str
    # استخلاصات
    reasoning_pattern: ReasoningPattern
    thinking_steps: List[str]
    decision_reasons: List[str]
    solution_quality: float         # 0-1 تقدير جودة الحل
    tools_referenced: List[str]
    key_concepts: List[str]
    # بيانات التدريب
    training_sample: Optional[Dict]  # بصيغة Alpaca/ChatML
    is_approved: bool = False
    distilled_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_training_sample(self, format: str = "alpaca") -> Dict[str, Any]:
        """تحويل إلى عيّنة تدريب."""
        if format == "alpaca":
            return {
                "instruction": self.original_query,
                "input": "",
                "output": self.model_response,
                "metadata": {
                    "source_model": self.source_model,
                    "domain": self.domain,
                    "quality": self.solution_quality,
                    "reasoning": self.reasoning_pattern,
                },
            }
        elif format == "chatml":
            return {
                "messages": [
                    {"role": "system", "content": "أنت Hajeen، مساعد ذكاء اصطناعي متخصص."},
                    {"role": "user", "content": self.original_query},
                    {"role": "assistant", "content": self.model_response},
                ],
                "metadata": {
                    "source_model": self.source_model,
                    "quality": self.solution_quality,
                },
            }
        return {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "knowledge_id": self.knowledge_id,
            "source_model": self.source_model,
            "task_type": self.task_type,
            "domain": self.domain,
            "reasoning_pattern": self.reasoning_pattern,
            "thinking_steps": self.thinking_steps,
            "solution_quality": self.solution_quality,
            "key_concepts": self.key_concepts,
            "is_approved": self.is_approved,
            "distilled_at": self.distilled_at,
        }


class KnowledgeDistillationPipeline:
    """
    خط استخلاص المعرفة.
    يُشغَّل بعد كل تفاعل مع نموذج خارجي.
    """

    # الحد الأدنى لجودة الحل للقبول في قاعدة التدريب
    QUALITY_THRESHOLD = 0.6

    def __init__(
        self,
        storage_path: str = "storage_data/brain/distilled_knowledge",
        knowledge_graph=None,
    ) -> None:
        self._path = Path(storage_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._knowledge: List[DistilledKnowledge] = []
        self._kg = knowledge_graph
        self._stats = {
            "total_distilled": 0,
            "approved": 0,
            "by_model": {},
            "by_domain": {},
            "by_pattern": {},
        }

    async def distill(
        self,
        source_model: str,
        query: str,
        response: str,
        task_type: str,
        domain: str,
        latency_ms: float = 0,
        metadata: Optional[Dict] = None,
    ) -> DistilledKnowledge:
        """استخلاص المعرفة من تفاعل واحد مع نموذج."""
        # تحليل الاستجابة
        reasoning = self._detect_reasoning_pattern(response)
        steps = self._extract_thinking_steps(response)
        reasons = self._extract_decision_reasons(response)
        quality = self._assess_quality(response, query)
        tools = self._extract_tool_references(response)
        concepts = self._extract_key_concepts(response)

        knowledge = DistilledKnowledge(
            knowledge_id=str(uuid.uuid4()),
            source_model=source_model,
            task_type=task_type,
            domain=domain,
            original_query=query,
            model_response=response,
            reasoning_pattern=reasoning,
            thinking_steps=steps,
            decision_reasons=reasons,
            solution_quality=quality,
            tools_referenced=tools,
            key_concepts=concepts,
            training_sample=None,
            is_approved=quality >= self.QUALITY_THRESHOLD,
            metadata={
                "latency_ms": latency_ms,
                **(metadata or {}),
            },
        )

        # توليد عيّنة التدريب إذا كانت الجودة كافية
        if knowledge.is_approved:
            knowledge.training_sample = knowledge.to_training_sample("alpaca")
            self._save_training_sample(knowledge)

        # تحديث الرسم البياني للمعرفة
        if self._kg and concepts:
            for concept in concepts[:3]:
                self._kg.add_knowledge(
                    subject=concept,
                    predicate="related_to",
                    obj=domain,
                    properties={"source": source_model},
                )

        self._knowledge.append(knowledge)
        self._update_stats(knowledge)
        self._save_metadata(knowledge)

        logger.info(
            "distillation: model=%s domain=%s quality=%.2f approved=%s steps=%d",
            source_model, domain, quality, knowledge.is_approved, len(steps)
        )
        return knowledge

    def _detect_reasoning_pattern(self, response: str) -> ReasoningPattern:
        patterns = {
            ReasoningPattern.STEP_BY_STEP: ["أولاً", "ثانياً", "ثالثاً", "خطوة", "step", "1.", "2.", "first"],
            ReasoningPattern.COMPARATIVE: ["مقارنة", "بالمقارنة", "أفضل من", "compare", "vs", "versus"],
            ReasoningPattern.CAUSAL: ["لأن", "بسبب", "نتيجة", "يؤدي", "because", "therefore", "thus"],
            ReasoningPattern.ANALOGICAL: ["مثل", "يشبه", "كـ", "like", "similar to", "analogous"],
            ReasoningPattern.CREATIVE: ["يمكن", "إبداع", "فكرة", "اقتراح", "creative", "innovative"],
        }
        resp_lower = response.lower()
        for pattern, keywords in patterns.items():
            if any(kw.lower() in resp_lower for kw in keywords):
                return pattern
        return ReasoningPattern.UNKNOWN

    def _extract_thinking_steps(self, response: str) -> List[str]:
        lines = response.split("\n")
        steps = []
        for line in lines:
            line = line.strip()
            # البحث عن خطوات (أرقام، نقاط، أولاً/ثانياً)
            if any([
                line.startswith(f"{i}.") or line.startswith(f"{i})") or
                line.startswith(f"- ") or line.startswith(f"• ")
                for i in range(1, 10)
            ]) or any(kw in line for kw in ["أولاً", "ثانياً", "ثالثاً", "أخيراً"]):
                if len(line) > 10:
                    steps.append(line[:200])
        return steps[:10]

    def _extract_decision_reasons(self, response: str) -> List[str]:
        reasons = []
        causal_markers = ["لأن", "بسبب", "نتيجة", "لذلك", "because", "since", "therefore", "since"]
        sentences = response.replace(".", "\n").replace("،", "\n").split("\n")
        for sent in sentences:
            if any(m in sent for m in causal_markers) and len(sent) > 15:
                reasons.append(sent.strip()[:200])
        return reasons[:5]

    def _assess_quality(self, response: str, query: str) -> float:
        score = 0.5  # درجة افتراضية
        # معايير الجودة
        if len(response) > 100:
            score += 0.1
        if len(response) > 500:
            score += 0.1
        steps = self._extract_thinking_steps(response)
        if len(steps) >= 3:
            score += 0.1
        if "خطأ" not in response and "error" not in response.lower():
            score += 0.1
        if len(response.split()) > 50:
            score += 0.1
        return min(1.0, score)

    def _extract_tool_references(self, response: str) -> List[str]:
        tools_keywords = [
            "python", "api", "sql", "bash", "ollama", "openai",
            "vector", "embedding", "rag", "search", "database"
        ]
        resp_lower = response.lower()
        return [t for t in tools_keywords if t in resp_lower]

    def _extract_key_concepts(self, response: str) -> List[str]:
        # استخرج الكلمات العربية/الإنجليزية الطويلة كمفاهيم محتملة
        import re
        words = re.findall(r'\b[\u0600-\u06FF]{4,}\b|\b[A-Za-z]{5,}\b', response)
        # أزل الكلمات الشائعة
        stop_words = {"الذي", "التي", "يمكن", "يجب", "هناك", "حيث", "الإجابة", "السؤال"}
        concepts = [w for w in dict.fromkeys(words) if w not in stop_words]
        return concepts[:8]

    def _save_training_sample(self, knowledge: DistilledKnowledge) -> None:
        try:
            samples_path = self._path / "training_samples.jsonl"
            with open(samples_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(knowledge.training_sample, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error("distillation: save training sample error: %s", e)

    def _save_metadata(self, knowledge: DistilledKnowledge) -> None:
        try:
            meta_path = self._path / f"{knowledge.knowledge_id}.json"
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(knowledge.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("distillation: save metadata error: %s", e)

    def _update_stats(self, knowledge: DistilledKnowledge) -> None:
        self._stats["total_distilled"] += 1
        if knowledge.is_approved:
            self._stats["approved"] += 1
        model = knowledge.source_model
        self._stats["by_model"][model] = self._stats["by_model"].get(model, 0) + 1
        domain = knowledge.domain
        self._stats["by_domain"][domain] = self._stats["by_domain"].get(domain, 0) + 1

    def get_training_dataset(self, min_quality: float = 0.6) -> List[Dict]:
        return [
            k.training_sample for k in self._knowledge
            if k.is_approved and k.solution_quality >= min_quality
            and k.training_sample is not None
        ]

    def get_stats(self) -> Dict[str, Any]:
        total = self._stats["total_distilled"]
        approved = self._stats["approved"]
        return {
            **self._stats,
            "approval_rate": round(approved / total, 3) if total else 0,
            "pending_training": len(self.get_training_dataset()),
        }


# Singleton
_pipeline: Optional[KnowledgeDistillationPipeline] = None


def get_distillation_pipeline() -> KnowledgeDistillationPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = KnowledgeDistillationPipeline()
    return _pipeline
