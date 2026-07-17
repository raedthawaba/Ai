"""
Memory Fabric v3 — نسيج الذاكرة المتقدم
======================================

يقوم بـ:
- إدارة الذاكرة متعددة المستويات
- الذاكرة قصيرة المدى (Context Window)
- الذاكرة المتوسطة (Session Memory)
- الذاكرة طويلة المدى (Episodic Memory)
- الذاكرة الدلالية (Semantic Memory)
- الذاكرة الإجرائية (Procedural Memory)

يستخدم:
- Vector embeddings للبحث الدلالي
- Compression للذاكرة الطويلة
- Retrieval-Augmented Generation (RAG)
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from hajeen_platform.core.llm import LLMManager

logger = logging.getLogger(__name__)


class MemoryType(str, Enum):
    """أنواع الذاكرة."""
    CONTEXT = "context"              # قصيرة المدى (السياق الحالي)
    SESSION = "session"              # متوسطة المدى (جلسة العمل)
    EPISODIC = "episodic"            # طويلة المدى (الأحداث والتجارب)
    SEMANTIC = "semantic"            # المعرفة العامة والمفاهيم
    PROCEDURAL = "procedural"        # الإجراءات والمهارات


class MemoryPriority(str, Enum):
    """أولويات الذاكرة."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class MemoryItem:
    """عنصر في الذاكرة."""
    item_id: str
    memory_type: MemoryType
    content: str
    priority: MemoryPriority
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    access_count: int = 0
    last_accessed_at: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    relevance_score: float = 0.0
    compressed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "memory_type": self.memory_type.value,
            "content": self.content[:200] + "..." if len(self.content) > 200 else self.content,
            "priority": self.priority.value,
            "access_count": self.access_count,
            "relevance_score": round(self.relevance_score, 3),
            "compressed": self.compressed,
        }


@dataclass
class MemoryRetrievalResult:
    """نتيجة استرجاع الذاكرة."""
    query: str
    retrieved_items: List[MemoryItem]
    total_items_searched: int
    retrieval_time_ms: float
    relevance_scores: Dict[str, float]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "retrieved_count": len(self.retrieved_items),
            "total_searched": self.total_items_searched,
            "retrieval_time_ms": round(self.retrieval_time_ms, 2),
            "items": [item.to_dict() for item in self.retrieved_items],
        }


class MemoryFabricV3:
    """
    نسيج الذاكرة المتقدم v3.
    
    يدير:
    - الذاكرة قصيرة المدى (Context)
    - الذاكرة المتوسطة (Session)
    - الذاكرة طويلة المدى (Episodic, Semantic, Procedural)
    """

    def __init__(
        self,
        llm_manager: LLMManager,
        max_context_items: int = 50,
        max_session_items: int = 500,
        max_episodic_items: int = 5000,
    ) -> None:
        self.llm_manager = llm_manager
        self.max_context_items = max_context_items
        self.max_session_items = max_session_items
        self.max_episodic_items = max_episodic_items
        
        # تخزين الذاكرة
        self._context_memory: List[MemoryItem] = []
        self._session_memory: List[MemoryItem] = []
        self._episodic_memory: List[MemoryItem] = []
        self._semantic_memory: List[MemoryItem] = []
        self._procedural_memory: List[MemoryItem] = []
        
        # إحصائيات
        self._retrieval_history: List[MemoryRetrievalResult] = []
        self._compression_history: List[Dict[str, Any]] = []
        
        logger.info("MemoryFabricV3: initialized")

    async def store(
        self,
        content: str,
        memory_type: MemoryType,
        priority: MemoryPriority = MemoryPriority.MEDIUM,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MemoryItem:
        """
        تخزين عنصر في الذاكرة.
        
        الخطوات:
        1. إنشاء عنصر ذاكرة
        2. حساب embedding
        3. تخزين في المستوى المناسب
        4. إدارة السعة
        """
        item_id = str(uuid.uuid4())
        
        try:
            # ── Step 1: إنشاء عنصر ذاكرة ──────────────────────────
            item = MemoryItem(
                item_id=item_id,
                memory_type=memory_type,
                content=content,
                priority=priority,
                metadata=metadata or {},
            )
            
            # ── Step 2: حساب embedding ────────────────────────────
            embedding = await self._compute_embedding(content)
            item.embedding = embedding
            
            # ── Step 3: تخزين في المستوى المناسب ──────────────────
            await self._store_in_appropriate_level(item)
            
            # ── Step 4: إدارة السعة ────────────────────────────────
            await self._manage_capacity()
            
            logger.info(
                "memory_fabric_v3: stored item type=%s priority=%s",
                memory_type.value, priority.value
            )
            
            return item
        
        except Exception as e:
            logger.error("memory_fabric_v3: error storing item: %s", e, exc_info=True)
            raise

    async def retrieve(
        self,
        query: str,
        memory_types: Optional[List[MemoryType]] = None,
        limit: int = 10,
    ) -> MemoryRetrievalResult:
        """
        استرجاع عناصر من الذاكرة.
        
        الخطوات:
        1. حساب embedding للاستعلام
        2. البحث في كل مستوى ذاكرة
        3. ترتيب النتائج حسب الصلة
        4. إرجاع أفضل النتائج
        """
        t0 = time.perf_counter()
        
        try:
            # ── Step 1: حساب embedding للاستعلام ──────────────────
            query_embedding = await self._compute_embedding(query)
            
            # ── Step 2: البحث في كل مستوى ذاكرة ──────────────────
            memory_types = memory_types or list(MemoryType)
            all_items = []
            
            for mem_type in memory_types:
                items = await self._search_memory_level(
                    mem_type, query_embedding, limit
                )
                all_items.extend(items)
            
            # ── Step 3: ترتيب النتائج حسب الصلة ──────────────────
            ranked_items = sorted(
                all_items,
                key=lambda x: x.relevance_score,
                reverse=True
            )[:limit]
            
            # ── Step 4: تحديث إحصائيات الوصول ────────────────────
            for item in ranked_items:
                item.access_count += 1
                item.last_accessed_at = time.time()
            
            retrieval_time_ms = (time.perf_counter() - t0) * 1000
            
            # ── Step 5: بناء النتيجة ────────────────────────────────
            result = MemoryRetrievalResult(
                query=query,
                retrieved_items=ranked_items,
                total_items_searched=len(all_items),
                retrieval_time_ms=retrieval_time_ms,
                relevance_scores={
                    item.item_id: item.relevance_score for item in ranked_items
                },
            )
            
            # تخزين في السجل
            self._retrieval_history.append(result)
            
            logger.info(
                "memory_fabric_v3: retrieved %d items in %.1f ms",
                len(ranked_items), retrieval_time_ms
            )
            
            return result
        
        except Exception as e:
            logger.error("memory_fabric_v3: error retrieving items: %s", e, exc_info=True)
            
            return MemoryRetrievalResult(
                query=query,
                retrieved_items=[],
                total_items_searched=0,
                retrieval_time_ms=(time.perf_counter() - t0) * 1000,
                relevance_scores={},
                metadata={"error": str(e)},
            )

    async def _compute_embedding(self, text: str) -> List[float]:
        """حساب embedding للنص."""
        try:
            # استخدام LLM لحساب embedding
            # في التطبيق الفعلي، يمكن استخدام OpenAI Embeddings API
            prompt = f"احسب embedding للنص التالي: {text[:100]}"
            
            # محاكاة embedding (في الواقع يجب استخدام API حقيقي)
            embedding = [hash(text) % 1000 / 1000 for _ in range(384)]
            return embedding
        except Exception as e:
            logger.warning("memory_fabric_v3: failed to compute embedding: %s", e)
            return [0.0] * 384

    async def _store_in_appropriate_level(self, item: MemoryItem) -> None:
        """تخزين العنصر في المستوى المناسب."""
        if item.memory_type == MemoryType.CONTEXT:
            self._context_memory.append(item)
        elif item.memory_type == MemoryType.SESSION:
            self._session_memory.append(item)
        elif item.memory_type == MemoryType.EPISODIC:
            self._episodic_memory.append(item)
        elif item.memory_type == MemoryType.SEMANTIC:
            self._semantic_memory.append(item)
        elif item.memory_type == MemoryType.PROCEDURAL:
            self._procedural_memory.append(item)

    async def _search_memory_level(
        self,
        memory_type: MemoryType,
        query_embedding: List[float],
        limit: int,
    ) -> List[MemoryItem]:
        """البحث في مستوى ذاكرة معين."""
        if memory_type == MemoryType.CONTEXT:
            items = self._context_memory
        elif memory_type == MemoryType.SESSION:
            items = self._session_memory
        elif memory_type == MemoryType.EPISODIC:
            items = self._episodic_memory
        elif memory_type == MemoryType.SEMANTIC:
            items = self._semantic_memory
        elif memory_type == MemoryType.PROCEDURAL:
            items = self._procedural_memory
        else:
            items = []
        
        # حساب درجة الصلة (Relevance Score)
        for item in items:
            if item.embedding:
                # حساب التشابه بين embeddings
                similarity = self._compute_similarity(query_embedding, item.embedding)
                item.relevance_score = similarity
            else:
                item.relevance_score = 0.5
        
        # ترتيب وإرجاع أفضل العناصر
        sorted_items = sorted(items, key=lambda x: x.relevance_score, reverse=True)
        return sorted_items[:limit]

    def _compute_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float],
    ) -> float:
        """حساب التشابه بين embedding (Cosine Similarity)."""
        if not embedding1 or not embedding2:
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        norm1 = sum(a ** 2 for a in embedding1) ** 0.5
        norm2 = sum(b ** 2 for b in embedding2) ** 0.5
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)

    async def _manage_capacity(self) -> None:
        """إدارة سعة الذاكرة."""
        # تنظيف Context Memory
        if len(self._context_memory) > self.max_context_items:
            # نقل العناصر القديمة إلى Session Memory
            items_to_move = self._context_memory[:-self.max_context_items]
            for item in items_to_move:
                item.memory_type = MemoryType.SESSION
                self._session_memory.append(item)
            self._context_memory = self._context_memory[-self.max_context_items:]
        
        # تنظيف Session Memory
        if len(self._session_memory) > self.max_session_items:
            # نقل العناصر القديمة إلى Episodic Memory
            items_to_move = self._session_memory[:-self.max_session_items]
            for item in items_to_move:
                item.memory_type = MemoryType.EPISODIC
                self._episodic_memory.append(item)
            self._session_memory = self._session_memory[-self.max_session_items:]
        
        # تنظيف Episodic Memory
        if len(self._episodic_memory) > self.max_episodic_items:
            # حذف العناصر الأقل أهمية
            self._episodic_memory.sort(key=lambda x: (x.priority.value, x.access_count))
            self._episodic_memory = self._episodic_memory[-self.max_episodic_items:]

    async def compress_memory(self, memory_type: MemoryType) -> Dict[str, Any]:
        """ضغط الذاكرة لتوفير المساحة."""
        try:
            if memory_type == MemoryType.EPISODIC:
                items = self._episodic_memory
            elif memory_type == MemoryType.SESSION:
                items = self._session_memory
            else:
                return {"status": "skipped", "reason": "Cannot compress this memory type"}
            
            # جمع المحتوى
            contents = [item.content for item in items[:10]]
            
            # استخدام LLM لتلخيص
            if contents:
                prompt = f"""لخّص النقاط التالية بإيجاز:

{chr(10).join(contents)}

قدّم ملخصاً موجزاً يحافظ على المعلومات الأساسية."""
                
                summary = await self.llm_manager.generate(
                    prompt=prompt,
                    model="gpt-4o-mini",
                    temperature=0.3,
                    max_tokens=300,
                )
                
                # إنشاء عنصر مضغوط
                compressed_item = MemoryItem(
                    item_id=str(uuid.uuid4()),
                    memory_type=memory_type,
                    content=summary,
                    priority=MemoryPriority.HIGH,
                    compressed=True,
                )
                
                # تخزين الملخص
                await self._store_in_appropriate_level(compressed_item)
                
                # حذف العناصر الأصلية
                items[:10] = []
                
                result = {
                    "status": "success",
                    "items_compressed": 10,
                    "summary": summary[:100],
                }
            else:
                result = {"status": "skipped", "reason": "No items to compress"}
            
            self._compression_history.append(result)
            return result
        
        except Exception as e:
            logger.error("memory_fabric_v3: error compressing memory: %s", e)
            return {"status": "error", "error": str(e)}

    def get_memory_stats(self) -> Dict[str, Any]:
        """إحصائيات الذاكرة."""
        return {
            "context_items": len(self._context_memory),
            "session_items": len(self._session_memory),
            "episodic_items": len(self._episodic_memory),
            "semantic_items": len(self._semantic_memory),
            "procedural_items": len(self._procedural_memory),
            "total_items": (
                len(self._context_memory) + len(self._session_memory) +
                len(self._episodic_memory) + len(self._semantic_memory) +
                len(self._procedural_memory)
            ),
            "total_retrievals": len(self._retrieval_history),
            "total_compressions": len(self._compression_history),
        }

    def get_recent_retrievals(self, limit: int = 5) -> List[Dict[str, Any]]:
        """آخر عمليات الاسترجاع."""
        recent = self._retrieval_history[-limit:]
        return [r.to_dict() for r in recent]

    def clear_context_memory(self) -> int:
        """مسح الذاكرة قصيرة المدى."""
        count = len(self._context_memory)
        self._context_memory = []
        logger.info("memory_fabric_v3: cleared %d context items", count)
        return count


# Singleton
_memory_fabric_v3: Optional[MemoryFabricV3] = None


def get_memory_fabric_v3(
    llm_manager: Optional[LLMManager] = None,
) -> MemoryFabricV3:
    """الحصول على instance من MemoryFabricV3."""
    global _memory_fabric_v3
    if _memory_fabric_v3 is None:
        if llm_manager is None:
            from hajeen_platform.core.llm import get_llm_manager
            llm_manager = get_llm_manager()
        _memory_fabric_v3 = MemoryFabricV3(llm_manager)
    return _memory_fabric_v3
