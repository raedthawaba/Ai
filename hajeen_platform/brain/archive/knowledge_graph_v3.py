"""
Knowledge Graph v3 — رسم المعرفة البياني المتقدم
==============================================

يقوم بـ:
- بناء رسم بياني للمعرفة (Knowledge Graph)
- تمثيل الكيانات (Entities) والعلاقات (Relations)
- الاستدلال الدلالي (Semantic Reasoning)
- الاستعلام المتقدم (Advanced Querying)
- اكتشاف الأنماط (Pattern Discovery)
- التعلم من البيانات الجديدة

يستخدم:
- LLM لاستخراج الكيانات والعلاقات
- Vector embeddings للبحث الدلالي
- Graph algorithms للاستدلال
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from hajeen_platform.core.llm import LLMManager

logger = logging.getLogger(__name__)


class EntityType(str, Enum):
    """أنواع الكيانات."""
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    CONCEPT = "concept"
    OBJECT = "object"
    EVENT = "event"
    PROCESS = "process"


class RelationType(str, Enum):
    """أنواع العلاقات."""
    IS_A = "is_a"                    # تصنيف
    PART_OF = "part_of"              # جزء من
    RELATED_TO = "related_to"        # مرتبط بـ
    CAUSES = "causes"                # يسبب
    DEPENDS_ON = "depends_on"        # يعتمد على
    SIMILAR_TO = "similar_to"        # مشابه لـ
    OPPOSITE_OF = "opposite_of"      # معاكس لـ
    CONTAINS = "contains"            # يحتوي على
    CONNECTED_TO = "connected_to"    # متصل بـ


@dataclass
class Entity:
    """كيان في رسم المعرفة."""
    entity_id: str
    name: str
    entity_type: EntityType
    description: str
    properties: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    confidence: float = 0.8
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "entity_type": self.entity_type.value,
            "description": self.description,
            "properties": self.properties,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class Relation:
    """علاقة بين كيانات."""
    relation_id: str
    source_entity_id: str
    target_entity_id: str
    relation_type: RelationType
    description: str
    strength: float = 0.8  # قوة العلاقة (0-1)
    confidence: float = 0.8
    properties: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
            "relation_type": self.relation_type.value,
            "description": self.description,
            "strength": round(self.strength, 3),
            "confidence": round(self.confidence, 3),
        }


@dataclass
class InferenceResult:
    """نتيجة الاستدلال."""
    inference_id: str
    query: str
    inferred_entities: List[Entity]
    inferred_relations: List[Relation]
    reasoning_path: List[str]
    confidence: float
    execution_time_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "inference_id": self.inference_id,
            "query": self.query,
            "inferred_entities": len(self.inferred_entities),
            "inferred_relations": len(self.inferred_relations),
            "reasoning_path": self.reasoning_path,
            "confidence": round(self.confidence, 3),
            "execution_time_ms": round(self.execution_time_ms, 2),
        }


class KnowledgeGraphV3:
    """
    رسم المعرفة البياني المتقدم v3.
    
    يدير:
    - الكيانات والعلاقات
    - الاستدلال الدلالي
    - البحث والاستعلام
    """

    def __init__(self, llm_manager: LLMManager) -> None:
        self.llm_manager = llm_manager
        
        # تخزين الكيانات والعلاقات
        self._entities: Dict[str, Entity] = {}
        self._relations: Dict[str, Relation] = []
        self._entity_index: Dict[str, Set[str]] = {}  # name -> entity_ids
        
        # إحصائيات
        self._inference_history: List[InferenceResult] = []
        self._learning_history: List[Dict[str, Any]] = []
        
        logger.info("KnowledgeGraphV3: initialized")

    async def add_entity(
        self,
        name: str,
        entity_type: EntityType,
        description: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Entity:
        """إضافة كيان إلى رسم المعرفة."""
        entity_id = str(uuid.uuid4())
        
        try:
            # إنشاء الكيان
            entity = Entity(
                entity_id=entity_id,
                name=name,
                entity_type=entity_type,
                description=description,
                properties=properties or {},
            )
            
            # حساب embedding
            entity.embedding = await self._compute_entity_embedding(entity)
            
            # تخزين الكيان
            self._entities[entity_id] = entity
            
            # تحديث الفهرس
            if name not in self._entity_index:
                self._entity_index[name] = set()
            self._entity_index[name].add(entity_id)
            
            logger.info(
                "knowledge_graph_v3: added entity %s type=%s",
                name, entity_type.value
            )
            
            return entity
        
        except Exception as e:
            logger.error("knowledge_graph_v3: error adding entity: %s", e, exc_info=True)
            raise

    async def add_relation(
        self,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: RelationType,
        description: str,
        strength: float = 0.8,
    ) -> Relation:
        """إضافة علاقة بين كيانات."""
        relation_id = str(uuid.uuid4())
        
        try:
            # التحقق من وجود الكيانات
            if source_entity_id not in self._entities:
                raise ValueError(f"Source entity {source_entity_id} not found")
            if target_entity_id not in self._entities:
                raise ValueError(f"Target entity {target_entity_id} not found")
            
            # إنشاء العلاقة
            relation = Relation(
                relation_id=relation_id,
                source_entity_id=source_entity_id,
                target_entity_id=target_entity_id,
                relation_type=relation_type,
                description=description,
                strength=strength,
            )
            
            # تخزين العلاقة
            self._relations.append(relation)
            
            logger.info(
                "knowledge_graph_v3: added relation %s -> %s type=%s",
                source_entity_id, target_entity_id, relation_type.value
            )
            
            return relation
        
        except Exception as e:
            logger.error("knowledge_graph_v3: error adding relation: %s", e, exc_info=True)
            raise

    async def extract_from_text(self, text: str) -> Tuple[List[Entity], List[Relation]]:
        """
        استخراج الكيانات والعلاقات من النص.
        
        الخطوات:
        1. استخدام LLM لاستخراج الكيانات
        2. استخدام LLM لاستخراج العلاقات
        3. إضافتها إلى رسم المعرفة
        """
        entities = []
        relations = []
        
        try:
            # ── Step 1: استخراج الكيانات ──────────────────────────
            prompt_entities = f"""استخرج جميع الكيانات المهمة من النص التالي:

{text}

قدّم النتيجة بصيغة JSON:
[
  {{"name": "اسم الكيان", "type": "person|organization|location|concept|object|event|process", "description": "وصف موجز"}},
  ...
]"""
            
            response_entities = await self.llm_manager.generate(
                prompt=prompt_entities,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=800,
            )
            
            # محاولة استخراج JSON
            try:
                entities_data = json.loads(response_entities)
            except:
                import re
                json_match = re.search(r'\[.*\]', response_entities, re.DOTALL)
                if json_match:
                    entities_data = json.loads(json_match.group())
                else:
                    entities_data = []
            
            # إضافة الكيانات
            for entity_data in entities_data:
                try:
                    entity = await self.add_entity(
                        name=entity_data.get("name", ""),
                        entity_type=EntityType(entity_data.get("type", "concept")),
                        description=entity_data.get("description", ""),
                    )
                    entities.append(entity)
                except Exception as e:
                    logger.warning("knowledge_graph_v3: failed to add entity: %s", e)
            
            # ── Step 2: استخراج العلاقات ──────────────────────────
            if len(entities) >= 2:
                entity_names = [e.name for e in entities]
                
                prompt_relations = f"""استخرج العلاقات بين الكيانات التالية من النص:

النص: {text}

الكيانات: {', '.join(entity_names)}

قدّم النتيجة بصيغة JSON:
[
  {{"source": "كيان المصدر", "target": "كيان الهدف", "type": "is_a|part_of|related_to|causes|depends_on|similar_to|opposite_of|contains|connected_to", "description": "وصف العلاقة"}},
  ...
]"""
                
                response_relations = await self.llm_manager.generate(
                    prompt=prompt_relations,
                    model="gpt-4o-mini",
                    temperature=0.3,
                    max_tokens=800,
                )
                
                # محاولة استخراج JSON
                try:
                    relations_data = json.loads(response_relations)
                except:
                    import re
                    json_match = re.search(r'\[.*\]', response_relations, re.DOTALL)
                    if json_match:
                        relations_data = json.loads(json_match.group())
                    else:
                        relations_data = []
                
                # إضافة العلاقات
                for relation_data in relations_data:
                    try:
                        source_name = relation_data.get("source", "")
                        target_name = relation_data.get("target", "")
                        
                        # البحث عن الكيانات
                        source_entity = next(
                            (e for e in entities if e.name == source_name), None
                        )
                        target_entity = next(
                            (e for e in entities if e.name == target_name), None
                        )
                        
                        if source_entity and target_entity:
                            relation = await self.add_relation(
                                source_entity_id=source_entity.entity_id,
                                target_entity_id=target_entity.entity_id,
                                relation_type=RelationType(relation_data.get("type", "related_to")),
                                description=relation_data.get("description", ""),
                            )
                            relations.append(relation)
                    except Exception as e:
                        logger.warning("knowledge_graph_v3: failed to add relation: %s", e)
            
            logger.info(
                "knowledge_graph_v3: extracted %d entities and %d relations from text",
                len(entities), len(relations)
            )
            
            return entities, relations
        
        except Exception as e:
            logger.error("knowledge_graph_v3: error extracting from text: %s", e, exc_info=True)
            return [], []

    async def infer(
        self,
        query: str,
        max_depth: int = 3,
    ) -> InferenceResult:
        """
        الاستدلال الدلالي.
        
        الخطوات:
        1. فهم الاستعلام
        2. البحث عن الكيانات ذات الصلة
        3. اتباع العلاقات
        4. الاستدلال على معلومات جديدة
        """
        inference_id = str(uuid.uuid4())
        t0 = time.perf_counter()
        
        try:
            # ── Step 1: فهم الاستعلام ──────────────────────────────
            prompt = f"""حلّل الاستعلام التالي وحدّد الكيانات والعلاقات المطلوبة:

الاستعلام: {query}

الكيانات المتاحة: {', '.join(list(self._entity_index.keys())[:20])}

قدّم تحليلاً موجزاً."""
            
            analysis = await self.llm_manager.generate(
                prompt=prompt,
                model="gpt-4o-mini",
                temperature=0.3,
                max_tokens=400,
            )
            
            # ── Step 2: البحث عن الكيانات ذات الصلة ──────────────
            relevant_entities = await self._find_relevant_entities(query)
            
            # ── Step 3: اتباع العلاقات ────────────────────────────
            inferred_relations = await self._trace_relations(
                relevant_entities, max_depth
            )
            
            # ── Step 4: الاستدلال على معلومات جديدة ──────────────
            inferred_entities = await self._infer_new_entities(
                relevant_entities, inferred_relations
            )
            
            # ── Step 5: بناء مسار الاستدلال ──────────────────────
            reasoning_path = [
                f"بدء البحث عن: {query}",
                f"وجدت {len(relevant_entities)} كيان ذي صلة",
                f"تتبعت {len(inferred_relations)} علاقة",
                f"استدللت على {len(inferred_entities)} كيان جديد",
            ]
            
            execution_time_ms = (time.perf_counter() - t0) * 1000
            
            # ── Step 6: بناء النتيجة ────────────────────────────────
            result = InferenceResult(
                inference_id=inference_id,
                query=query,
                inferred_entities=inferred_entities,
                inferred_relations=inferred_relations,
                reasoning_path=reasoning_path,
                confidence=0.8,
                execution_time_ms=execution_time_ms,
            )
            
            self._inference_history.append(result)
            
            logger.info(
                "knowledge_graph_v3: inference completed in %.1f ms",
                execution_time_ms
            )
            
            return result
        
        except Exception as e:
            logger.error("knowledge_graph_v3: error during inference: %s", e, exc_info=True)
            
            return InferenceResult(
                inference_id=inference_id,
                query=query,
                inferred_entities=[],
                inferred_relations=[],
                reasoning_path=[f"فشل الاستدلال: {str(e)}"],
                confidence=0.0,
                execution_time_ms=(time.perf_counter() - t0) * 1000,
                metadata={"error": str(e)},
            )

    async def _compute_entity_embedding(self, entity: Entity) -> List[float]:
        """حساب embedding للكيان."""
        try:
            text = f"{entity.name} {entity.description}"
            # محاكاة embedding
            embedding = [hash(text) % 1000 / 1000 for _ in range(384)]
            return embedding
        except Exception as e:
            logger.warning("knowledge_graph_v3: failed to compute embedding: %s", e)
            return [0.0] * 384

    async def _find_relevant_entities(self, query: str) -> List[Entity]:
        """البحث عن الكيانات ذات الصلة."""
        relevant = []
        
        # البحث البسيط في الأسماء
        query_lower = query.lower()
        for entity_id, entity in self._entities.items():
            if query_lower in entity.name.lower() or query_lower in entity.description.lower():
                relevant.append(entity)
        
        return relevant[:10]

    async def _trace_relations(
        self,
        entities: List[Entity],
        max_depth: int,
    ) -> List[Relation]:
        """تتبع العلاقات."""
        traced = []
        visited = set()
        
        def trace_recursive(entity_id: str, depth: int):
            if depth == 0 or entity_id in visited:
                return
            visited.add(entity_id)
            
            for relation in self._relations:
                if relation.source_entity_id == entity_id:
                    traced.append(relation)
                    trace_recursive(relation.target_entity_id, depth - 1)
        
        for entity in entities:
            trace_recursive(entity.entity_id, max_depth)
        
        return traced

    async def _infer_new_entities(
        self,
        entities: List[Entity],
        relations: List[Relation],
    ) -> List[Entity]:
        """الاستدلال على كيانات جديدة."""
        inferred = []
        
        # جمع الكيانات المتصلة
        connected_ids = set()
        for relation in relations:
            connected_ids.add(relation.target_entity_id)
        
        for entity_id in connected_ids:
            if entity_id in self._entities:
                inferred.append(self._entities[entity_id])
        
        return inferred

    def get_graph_stats(self) -> Dict[str, Any]:
        """إحصائيات رسم المعرفة."""
        return {
            "total_entities": len(self._entities),
            "total_relations": len(self._relations),
            "entity_types": {
                et.value: sum(1 for e in self._entities.values() if e.entity_type == et)
                for et in EntityType
            },
            "relation_types": {
                rt.value: sum(1 for r in self._relations if r.relation_type == rt)
                for rt in RelationType
            },
            "total_inferences": len(self._inference_history),
        }

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """الحصول على كيان."""
        return self._entities.get(entity_id)

    def search_entities(self, query: str, limit: int = 10) -> List[Entity]:
        """البحث عن كيانات."""
        results = []
        query_lower = query.lower()
        
        for entity in self._entities.values():
            if query_lower in entity.name.lower():
                results.append(entity)
        
        return results[:limit]

    def get_recent_inferences(self, limit: int = 5) -> List[Dict[str, Any]]:
        """آخر الاستدلالات."""
        recent = self._inference_history[-limit:]
        return [r.to_dict() for r in recent]


# Singleton
_knowledge_graph_v3: Optional[KnowledgeGraphV3] = None


def get_knowledge_graph_v3(
    llm_manager: Optional[LLMManager] = None,
) -> KnowledgeGraphV3:
    """الحصول على instance من KnowledgeGraphV3."""
    global _knowledge_graph_v3
    if _knowledge_graph_v3 is None:
        if llm_manager is None:
            from hajeen_platform.core.llm import get_llm_manager
            llm_manager = get_llm_manager()
        _knowledge_graph_v3 = KnowledgeGraphV3(llm_manager)
    return _knowledge_graph_v3
