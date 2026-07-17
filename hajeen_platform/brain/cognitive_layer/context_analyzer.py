"""
Context Analyzer — محلّل السياق المتقدم
=====================================

يحلل السياق الكامل للطلب:
- السياق التاريخي (محفوظات المحادثة)
- الذاكرة طويلة الأمد
- المجال والتخصص
- مستوى التعقيد
- القيود والموارد المتاحة
- الأولويات والتفضيلات

يستخدم استدلالاً عميقاً وليس مطابقة بسيطة.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hajeen_platform.core.llm import LLMManager
from hajeen_platform.core.embeddings import EmbeddingManager
from hajeen_platform.brain.memory.memory_fabric import MemoryFabric

logger = logging.getLogger(__name__)


@dataclass
class ContextAnalysis:
    """تمثيل تحليل السياق."""
    analysis_id: str
    session_id: str
    
    # السياق التاريخي
    conversation_history: List[Dict[str, str]]
    conversation_summary: str
    
    # الذاكرة والمعرفة السابقة
    relevant_memories: List[Dict[str, Any]]
    previous_goals: List[str]
    user_preferences: Dict[str, Any]
    
    # تحليل المجال والتخصص
    detected_domain: str
    domain_expertise_level: str  # novice, intermediate, expert
    
    # تحليل التعقيد والموارد
    estimated_complexity: str  # simple, medium, complex, enterprise
    estimated_tokens: int
    required_capabilities: List[str]
    
    # القيود والأولويات
    constraints: List[str]
    priorities: List[str]
    time_sensitivity: str  # low, medium, high, critical
    
    # درجة الثقة والتوصيات
    confidence: float
    reasoning: str
    recommendations: List[str]
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "session_id": self.session_id,
            "conversation_summary": self.conversation_summary,
            "relevant_memories": self.relevant_memories,
            "detected_domain": self.detected_domain,
            "domain_expertise_level": self.domain_expertise_level,
            "estimated_complexity": self.estimated_complexity,
            "estimated_tokens": self.estimated_tokens,
            "required_capabilities": self.required_capabilities,
            "constraints": self.constraints,
            "priorities": self.priorities,
            "time_sensitivity": self.time_sensitivity,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "recommendations": self.recommendations,
            "created_at": self.created_at,
        }


class ContextAnalyzer:
    """
    محلّل السياق المتقدم.
    
    يستخدم:
    - LLM للاستدلال العميق
    - Embeddings للبحث الدلالي
    - Memory Fabric للوصول إلى الذاكرة
    """

    def __init__(
        self,
        llm_manager: LLMManager,
        embedding_manager: EmbeddingManager,
        memory_fabric: MemoryFabric,
    ) -> None:
        self.llm_manager = llm_manager
        self.embedding_manager = embedding_manager
        self.memory_fabric = memory_fabric
        self._analyses_cache: Dict[str, ContextAnalysis] = {}
        logger.info("ContextAnalyzer: initialized")

    async def analyze(
        self,
        user_message: str,
        session_id: str,
        user_id: Optional[str] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> ContextAnalysis:
        """
        تحليل السياق الكامل للطلب.
        
        الخطوات:
        1. استرجاع محفوظات المحادثة
        2. استرجاع الذاكرة ذات الصلة
        3. تحليل المجال والتخصص
        4. تقدير التعقيد والموارد
        5. تحديد القيود والأولويات
        6. إنشاء توصيات
        """
        analysis_id = str(uuid.uuid4())
        
        try:
            # ── Step 1: استرجاع محفوظات المحادثة ──────────────────────────
            conversation = self.memory_fabric.get_conversation(session_id)
            conversation_window = conversation.get_window()
            
            # تلخيص المحادثة إذا كانت طويلة
            conversation_summary = await self._summarize_conversation(
                conversation_window, user_message
            )
            
            # ── Step 2: استرجاع الذاكرة ذات الصلة ──────────────────────────
            relevant_memories = await self._retrieve_relevant_memories(
                user_message, session_id, user_id
            )
            
            # ── Step 3: استرجاع الأهداف والتفضيلات السابقة ──────────────────
            session = self.memory_fabric.get_session(session_id)
            previous_goals = session.get_all("previous_goals", [])[-5:]  # آخر 5 أهداف
            user_preferences = session.get_all("preferences", {})
            
            # ── Step 4: تحليل المجال والتخصص ────────────────────────────
            domain_analysis = await self._analyze_domain(
                user_message, conversation_summary, relevant_memories
            )
            
            # ── Step 5: تقدير التعقيد والموارد ──────────────────────────
            complexity_analysis = await self._analyze_complexity(
                user_message, domain_analysis, conversation_window
            )
            
            # ── Step 6: تحديد القيود والأولويات ────────────────────────
            constraints_analysis = await self._analyze_constraints(
                user_message, user_preferences, additional_context or {}
            )
            
            # ── Step 7: إنشاء توصيات ────────────────────────────────────
            recommendations = await self._generate_recommendations(
                user_message,
                domain_analysis,
                complexity_analysis,
                constraints_analysis,
            )
            
            # ── Step 8: بناء كائن ContextAnalysis ──────────────────────
            analysis = ContextAnalysis(
                analysis_id=analysis_id,
                session_id=session_id,
                conversation_history=conversation_window,
                conversation_summary=conversation_summary,
                relevant_memories=relevant_memories,
                previous_goals=previous_goals,
                user_preferences=user_preferences,
                detected_domain=domain_analysis["domain"],
                domain_expertise_level=domain_analysis["expertise_level"],
                estimated_complexity=complexity_analysis["complexity"],
                estimated_tokens=complexity_analysis["estimated_tokens"],
                required_capabilities=complexity_analysis["required_capabilities"],
                constraints=constraints_analysis["constraints"],
                priorities=constraints_analysis["priorities"],
                time_sensitivity=constraints_analysis["time_sensitivity"],
                confidence=min(
                    domain_analysis.get("confidence", 0.7),
                    complexity_analysis.get("confidence", 0.7),
                ),
                reasoning=self._build_reasoning(
                    domain_analysis, complexity_analysis, constraints_analysis
                ),
                recommendations=recommendations,
                metadata={
                    "user_message": user_message,
                    "user_id": user_id,
                    "additional_context": additional_context or {},
                },
            )
            
            # تخزين مؤقت
            self._analyses_cache[analysis_id] = analysis
            
            logger.info(
                "context_analyzer: analyzed context analysis_id=%s domain=%s complexity=%s",
                analysis_id, analysis.detected_domain, analysis.estimated_complexity
            )
            
            return analysis
        
        except Exception as e:
            logger.error("context_analyzer: error analyzing context: %s", e, exc_info=True)
            # استجابة احتياطية
            return ContextAnalysis(
                analysis_id=analysis_id,
                session_id=session_id,
                conversation_history=[],
                conversation_summary="فشل تحليل المحادثة",
                relevant_memories=[],
                previous_goals=[],
                user_preferences={},
                detected_domain="general",
                domain_expertise_level="unknown",
                estimated_complexity="medium",
                estimated_tokens=1024,
                required_capabilities=[],
                constraints=[],
                priorities=[],
                time_sensitivity="medium",
                confidence=0.5,
                reasoning="فشل التحليل، استجابة احتياطية",
                recommendations=[],
                metadata={"error": str(e)},
            )

    async def _summarize_conversation(
        self,
        conversation_window: List[Dict[str, str]],
        current_message: str,
    ) -> str:
        """تلخيص المحادثة باستخدام LLM."""
        if len(conversation_window) <= 2:
            return "محادثة جديدة"
        
        try:
            messages_text = "\n".join([
                f"{msg['role']}: {msg['content'][:100]}"
                for msg in conversation_window[:-1]  # بدون الرسالة الحالية
            ])
            
            prompt = f"""لخّص المحادثة التالية بإيجاز (جملة واحدة):

{messages_text}

الرسالة الحالية: {current_message}

التلخيص:"""
            
            summary = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=100,
            )
            
            return summary.strip()
        except Exception as e:
            logger.warning("context_analyzer: failed to summarize conversation: %s", e)
            return f"محادثة بـ {len(conversation_window)} رسائل"

    async def _retrieve_relevant_memories(
        self,
        user_message: str,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """استرجاع الذاكرة ذات الصلة باستخدام البحث الدلالي."""
        try:
            import numpy as np

            # ── الحصول على embedding للرسالة الحالية ─────────────────────
            message_embedding = await self.embedding_manager.embed(user_message)

            # ── البحث الدلالي في الذاكرة طويلة الأمد ────────────────────
            long_term = self.memory_fabric.get_long_term_memory(session_id)
            all_keys = long_term.list_keys() if hasattr(long_term, "list_keys") else []

            scored: list = []
            for key in all_keys:
                entry = long_term.recall(key)
                if entry is None:
                    continue
                content_str = entry.get("content", str(entry)) if isinstance(entry, dict) else str(entry)
                try:
                    entry_emb = await self.embedding_manager.embed(content_str[:512])
                    a = np.array(message_embedding, dtype=float)
                    b = np.array(entry_emb, dtype=float)
                    norm_a = np.linalg.norm(a)
                    norm_b = np.linalg.norm(b)
                    score = float(np.dot(a, b) / (norm_a * norm_b)) if norm_a > 0 and norm_b > 0 else 0.0
                    scored.append((score, key, content_str, entry))
                except Exception:
                    continue

            scored.sort(key=lambda x: x[0], reverse=True)
            memories: list = []
            for score, key, content_str, raw_entry in scored[:5]:
                if score >= 0.4:
                    memories.append({
                        "key": key,
                        "content": content_str[:300],
                        "relevance_score": round(score, 3),
                        "metadata": raw_entry.get("metadata", {}) if isinstance(raw_entry, dict) else {},
                    })

            # ── البحث في الذاكرة الدلالية ─────────────────────────────────
            try:
                semantic = self.memory_fabric.semantic
                sem_results = semantic.search(user_message, top_k=3)
                for sem_entry in sem_results:
                    memories.append({
                        "key": sem_entry.key,
                        "content": sem_entry.content[:300],
                        "relevance_score": round(sem_entry.relevance, 3),
                        "metadata": sem_entry.metadata,
                    })
            except Exception:
                pass

            # إزالة المكررات
            seen_keys: set = set()
            unique_memories: list = []
            for m in memories:
                if m["key"] not in seen_keys:
                    seen_keys.add(m["key"])
                    unique_memories.append(m)

            logger.debug(
                "context_analyzer: retrieved %d relevant memories for session=%s",
                len(unique_memories), session_id,
            )
            return unique_memories[:7]

        except Exception as e:
            logger.warning("context_analyzer: failed to retrieve memories: %s", e)
            return []

    async def _analyze_domain(
        self,
        user_message: str,
        conversation_summary: str,
        relevant_memories: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """تحليل المجال والتخصص."""
        try:
            prompt = f"""حلّل المجال والتخصص للرسالة التالية:

الرسالة: {user_message}

ملخص المحادثة: {conversation_summary}

قم بـ:
1. تحديد المجال (nlp, data, code, rag, agent, math, general, etc.)
2. تقدير مستوى الخبرة المطلوب (novice, intermediate, expert)
3. درجة الثقة (0-1)

أرجع JSON:
{{
  "domain": "...",
  "expertise_level": "...",
  "confidence": 0.85,
  "reasoning": "..."
}}"""
            
            response = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=200,
            )
            
            data = json.loads(response)
            return data
        except Exception as e:
            logger.warning("context_analyzer: failed to analyze domain: %s", e)
            return {
                "domain": "general",
                "expertise_level": "intermediate",
                "confidence": 0.5,
                "reasoning": "فشل التحليل",
            }

    async def _analyze_complexity(
        self,
        user_message: str,
        domain_analysis: Dict[str, Any],
        conversation_window: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """تحليل التعقيد والموارد المطلوبة."""
        try:
            prompt = f"""قيّم تعقيد الطلب التالي:

الرسالة: {user_message}

المجال: {domain_analysis.get('domain', 'general')}

قم بـ:
1. تقدير مستوى التعقيد (simple, medium, complex, enterprise)
2. تقدير عدد الرموز المطلوبة (100-10000)
3. تحديد القدرات المطلوبة (reasoning, code, analysis, etc.)
4. درجة الثقة (0-1)

أرجع JSON:
{{
  "complexity": "...",
  "estimated_tokens": 1024,
  "required_capabilities": [...],
  "confidence": 0.85,
  "reasoning": "..."
}}"""
            
            response = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=250,
            )
            
            data = json.loads(response)
            return data
        except Exception as e:
            logger.warning("context_analyzer: failed to analyze complexity: %s", e)
            return {
                "complexity": "medium",
                "estimated_tokens": 1024,
                "required_capabilities": [],
                "confidence": 0.5,
                "reasoning": "فشل التحليل",
            }

    async def _analyze_constraints(
        self,
        user_message: str,
        user_preferences: Dict[str, Any],
        additional_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """تحليل القيود والأولويات."""
        try:
            preferences_str = json.dumps(user_preferences, ensure_ascii=False)
            context_str = json.dumps(additional_context, ensure_ascii=False)
            
            prompt = f"""حدّد القيود والأولويات للطلب:

الرسالة: {user_message}

تفضيلات المستخدم: {preferences_str}

السياق الإضافي: {context_str}

قم بـ:
1. تحديد القيود (الموارد، الوقت، السياسات، إلخ)
2. تحديد الأولويات (السرعة، الجودة، التكلفة، إلخ)
3. تقدير حساسية الوقت (low, medium, high, critical)

أرجع JSON:
{{
  "constraints": [...],
  "priorities": [...],
  "time_sensitivity": "...",
  "reasoning": "..."
}}"""
            
            response = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=250,
            )
            
            data = json.loads(response)
            return data
        except Exception as e:
            logger.warning("context_analyzer: failed to analyze constraints: %s", e)
            return {
                "constraints": [],
                "priorities": [],
                "time_sensitivity": "medium",
                "reasoning": "فشل التحليل",
            }

    async def _generate_recommendations(
        self,
        user_message: str,
        domain_analysis: Dict[str, Any],
        complexity_analysis: Dict[str, Any],
        constraints_analysis: Dict[str, Any],
    ) -> List[str]:
        """إنشاء توصيات بناءً على التحليلات."""
        try:
            prompt = f"""بناءً على التحليلات التالية، قدّم توصيات:

الرسالة: {user_message}

المجال: {domain_analysis.get('domain', 'general')}
التعقيد: {complexity_analysis.get('complexity', 'medium')}
الأولويات: {', '.join(constraints_analysis.get('priorities', []))}

قدّم 3-5 توصيات عملية لمعالجة هذا الطلب بكفاءة.

أرجع قائمة JSON:
["توصية 1", "توصية 2", ...]"""
            
            response = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=300,
            )
            
            # محاولة استخراج JSON
            json_start = response.find("[")
            json_end = response.rfind("]") + 1
            if json_start >= 0 and json_end > json_start:
                recommendations = json.loads(response[json_start:json_end])
                return recommendations
            
            return []
        except Exception as e:
            logger.warning("context_analyzer: failed to generate recommendations: %s", e)
            return []

    def _build_reasoning(
        self,
        domain_analysis: Dict[str, Any],
        complexity_analysis: Dict[str, Any],
        constraints_analysis: Dict[str, Any],
    ) -> str:
        """بناء شرح الاستدلال."""
        return (
            f"المجال: {domain_analysis.get('domain', 'general')} "
            f"({domain_analysis.get('reasoning', '')}). "
            f"التعقيد: {complexity_analysis.get('complexity', 'medium')} "
            f"({complexity_analysis.get('reasoning', '')}). "
            f"الأولويات: {', '.join(constraints_analysis.get('priorities', []))}."
        )

    def get_analysis(self, analysis_id: str) -> Optional[ContextAnalysis]:
        """الحصول على تحليل محفوظ."""
        return self._analyses_cache.get(analysis_id)

    def list_analyses(self, limit: int = 10) -> List[Dict[str, Any]]:
        """قائمة بآخر التحليلات."""
        analyses = list(self._analyses_cache.values())
        analyses.sort(key=lambda a: a.created_at, reverse=True)
        return [a.to_dict() for a in analyses[:limit]]


# Singleton
_context_analyzer: Optional[ContextAnalyzer] = None


def get_context_analyzer(
    llm_manager: Optional[LLMManager] = None,
    embedding_manager: Optional[EmbeddingManager] = None,
    memory_fabric: Optional[MemoryFabric] = None,
) -> ContextAnalyzer:
    """الحصول على instance من ContextAnalyzer."""
    global _context_analyzer
    if _context_analyzer is None:
        if llm_manager is None:
            from hajeen_platform.core.llm import get_llm_manager
            llm_manager = get_llm_manager()
        if embedding_manager is None:
            from hajeen_platform.core.embeddings import get_embedding_manager
            embedding_manager = get_embedding_manager()
        if memory_fabric is None:
            from hajeen_platform.brain.memory.memory_fabric import get_memory_fabric
            memory_fabric = get_memory_fabric()
        
        _context_analyzer = ContextAnalyzer(llm_manager, embedding_manager, memory_fabric)
    return _context_analyzer
