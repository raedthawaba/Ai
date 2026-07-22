"""
Knowledge Graph — الرسم البياني للمعرفة
=========================================
يربط: الأشخاص، المفاهيم، المشاريع، الأدوات، الأحداث، العلاقات.
أكثر من مجرد قاعدة بيانات — بنية معرفية علائقية قابلة للاستعلام.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class NodeCategory(str, Enum):
    PERSON = "person"
    CONCEPT = "concept"
    PROJECT = "project"
    TOOL = "tool"
    EVENT = "event"
    MODEL = "model"
    DATASET = "dataset"
    FACT = "fact"
    TASK = "task"
    DOMAIN = "domain"


class RelationType(str, Enum):
    IS_A = "is_a"
    HAS = "has"
    USES = "uses"
    CREATED_BY = "created_by"
    RELATED_TO = "related_to"
    PART_OF = "part_of"
    DEPENDS_ON = "depends_on"
    LEADS_TO = "leads_to"
    CONTRADICTS = "contradicts"
    SIMILAR_TO = "similar_to"


@dataclass
class KGNode:
    node_id: str
    name: str
    category: NodeCategory
    properties: Dict[str, Any]
    embedding: Optional[List[float]]
    created_at: float
    updated_at: float
    access_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "category": self.category,
            "properties": self.properties,
            "created_at": self.created_at,
            "access_count": self.access_count,
        }


@dataclass
class KGEdge:
    edge_id: str
    source_id: str
    target_id: str
    relation: RelationType
    weight: float  # قوة العلاقة 0-1
    properties: Dict[str, Any]
    created_at: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "weight": self.weight,
        }


class KnowledgeGraph:
    """
    الرسم البياني للمعرفة — يخزن ويربط المفاهيم والعلاقات.
    يُستخدم بواسطة Brain لفهم السياق وتحسين القرارات.
    """

    def __init__(self, storage_path: str = "storage_data/brain/knowledge_graph") -> None:
        self._path = Path(storage_path)
        self._path.mkdir(parents=True, exist_ok=True)
        self._nodes: Dict[str, KGNode] = {}
        self._edges: List[KGEdge] = {}
        self._name_index: Dict[str, str] = {}  # name → node_id
        self._load()
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        """بذور المعرفة الأساسية عن Hajeen."""
        defaults = [
            ("Hajeen AI", NodeCategory.PROJECT, {"description": "منصة ذكاء اصطناعي سيادية"}),
            ("Hajeen Brain", NodeCategory.CONCEPT, {"description": "العقل المدبّر للمنصة"}),
            ("Ollama", NodeCategory.TOOL, {"description": "تشغيل نماذج LLM محلياً"}),
            ("Qwen", NodeCategory.MODEL, {"description": "نموذج Alibaba متعدد اللغات"}),
            ("OpenAI", NodeCategory.MODEL, {"description": "نماذج GPT السحابية"}),
            ("RAG", NodeCategory.CONCEPT, {"description": "Retrieval-Augmented Generation"}),
            ("Fine-tuning", NodeCategory.CONCEPT, {"description": "ضبط دقيق للنماذج"}),
            ("Arabic NLP", NodeCategory.DOMAIN, {"description": "معالجة اللغة العربية"}),
        ]
        for name, category, props in defaults:
            if name not in self._name_index:
                self.add_node(name, category, props)

        # ربط العقد
        self._try_relate("Hajeen Brain", "Hajeen AI", RelationType.PART_OF)
        self._try_relate("Hajeen Brain", "Ollama", RelationType.USES)
        self._try_relate("Hajeen Brain", "RAG", RelationType.USES)
        self._try_relate("Qwen", "Arabic NLP", RelationType.RELATED_TO)

    def _try_relate(self, source_name: str, target_name: str, relation: RelationType) -> None:
        src = self._name_index.get(source_name)
        tgt = self._name_index.get(target_name)
        if src and tgt:
            self.add_edge(src, tgt, relation)

    def add_node(
        self, name: str, category: NodeCategory,
        properties: Optional[Dict] = None,
        embedding: Optional[List[float]] = None,
    ) -> str:
        if name in self._name_index:
            return self._name_index[name]

        node = KGNode(
            node_id=str(uuid.uuid4()),
            name=name,
            category=category,
            properties=properties or {},
            embedding=embedding,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self._nodes[node.node_id] = node
        self._name_index[name] = node.node_id
        logger.debug("knowledge_graph: added node '%s' [%s]", name, category)
        return node.node_id

    def add_edge(
        self, source_id: str, target_id: str,
        relation: RelationType, weight: float = 0.8,
        properties: Optional[Dict] = None,
    ) -> Optional[str]:
        if source_id not in self._nodes or target_id not in self._nodes:
            return None
        # تجنب التكرار
        existing = [
            e for e in self._edges.values()
            if e.source_id == source_id and e.target_id == target_id and e.relation == relation
        ]
        if existing:
            return existing[0].edge_id

        edge = KGEdge(
            edge_id=str(uuid.uuid4()),
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            weight=weight,
            properties=properties or {},
            created_at=time.time(),
        )
        self._edges[edge.edge_id] = edge
        return edge.edge_id

    def get_node_by_name(self, name: str) -> Optional[KGNode]:
        nid = self._name_index.get(name)
        return self._nodes.get(nid) if nid else None

    def get_neighbors(self, node_id: str, relation: Optional[RelationType] = None) -> List[KGNode]:
        neighbor_ids = set()
        for edge in self._edges.values():
            if edge.source_id == node_id:
                if relation is None or edge.relation == relation:
                    neighbor_ids.add(edge.target_id)
            if edge.target_id == node_id:
                if relation is None or edge.relation == relation:
                    neighbor_ids.add(edge.source_id)
        result = [self._nodes[nid] for nid in neighbor_ids if nid in self._nodes]
        for n in result:
            n.access_count += 1
        return result

    def search_nodes(self, query: str, category: Optional[NodeCategory] = None, top_k: int = 10) -> List[KGNode]:
        """Search for knowledge nodes by query string."""
        query_lower = query.lower()
        scored = []
        
        for node_id, node in self._nodes.items():
            if category and node.category != category:
                continue
            
            # Score by name and properties match
            name_match = query_lower in node.name.lower()
            # Check properties for description
            props_str = str(node.properties).lower()
            desc_match = query_lower in props_str
            
            if name_match or desc_match:
                score = 1.0 if name_match else 0.5
                scored.append((score, node))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [node for _, node in scored[:top_k]]

    # ── Knowledge Query (Phase 2) ─────────────────────────────────────────
    async def query(
        self, 
        query: str, 
        domain: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Query knowledge graph for relevant information.
        This is used for early knowledge retrieval before Reasoning.
        
        Args:
            query: The query string
            domain: Optional domain filter
            limit: Maximum number of results
            
        Returns:
            List of knowledge items with relevance scores
        """
        results = []
        
        # Search for matching nodes
        nodes = self.search_nodes(query, top_k=limit * 2)
        
        for node in nodes:
            # Get neighbors for context
            neighbors = self.get_neighbors(node.node_id)
            
            # Extract description from properties if available
            description = node.properties.get("description", str(node.properties))
            
            results.append({
                "type": "knowledge",
                "name": node.name,
                "category": node.category.value if hasattr(node.category, 'value') else str(node.category),
                "description": description,
                "properties": node.properties,
                "neighbors": [
                    {"name": n.name, "relation": "related"}
                    for n in neighbors[:3]
                ],
                "relevance": 0.8 if query.lower() in node.name.lower() else 0.5,
            })
        
        # Sort by relevance
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:limit]

    def add_knowledge(
        self, subject: str, predicate: RelationType,
        obj: str, subject_category: NodeCategory = NodeCategory.CONCEPT,
        obj_category: NodeCategory = NodeCategory.CONCEPT,
        properties: Optional[Dict] = None,
    ) -> Tuple[str, str, str]:
        """إضافة معرفة جديدة بصيغة: subject → predicate → object."""
        sid = self.add_node(subject, subject_category)
        oid = self.add_node(obj, obj_category)
        eid = self.add_edge(sid, oid, predicate, properties=properties)
        return sid, oid, eid

    def get_context_for(self, entity_name: str, depth: int = 2) -> Dict[str, Any]:
        """جمع السياق المعرفي لكيان معيّن (BFS بعمق محدد)."""
        root = self.get_node_by_name(entity_name)
        if not root:
            return {"entity": entity_name, "found": False}

        visited: Set[str] = {root.node_id}
        context_nodes: List[Dict] = [root.to_dict()]
        context_edges: List[Dict] = []
        queue = [(root.node_id, 0)]

        while queue:
            nid, d = queue.pop(0)
            if d >= depth:
                continue
            neighbors = self.get_neighbors(nid)
            for n in neighbors:
                if n.node_id not in visited:
                    visited.add(n.node_id)
                    context_nodes.append(n.to_dict())
                    queue.append((n.node_id, d + 1))
            for edge in self._edges.values():
                if edge.source_id == nid or edge.target_id == nid:
                    if edge.source_id in visited and edge.target_id in visited:
                        context_edges.append(edge.to_dict())

        return {
            "entity": entity_name,
            "found": True,
            "nodes": context_nodes,
            "edges": context_edges,
            "total_related": len(context_nodes) - 1,
        }

    def _save(self) -> None:
        try:
            data = {
                "nodes": {nid: n.to_dict() for nid, n in self._nodes.items()},
                "edges": {eid: e.to_dict() for eid, e in self._edges.items()},
                "name_index": self._name_index,
            }
            with open(self._path / "graph.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("knowledge_graph: save error: %s", e)

    def _load(self) -> None:
        path = self._path / "graph.json"
        if not path.exists():
            self._edges = {}
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            for nid, nd in data.get("nodes", {}).items():
                self._nodes[nid] = KGNode(
                    node_id=nid, name=nd["name"],
                    category=NodeCategory(nd["category"]),
                    properties=nd.get("properties", {}),
                    embedding=None,
                    created_at=nd.get("created_at", now),
                    updated_at=nd.get("created_at", now),
                    access_count=nd.get("access_count", 0),
                )
            for eid, ed in data.get("edges", {}).items():
                self._edges[eid] = KGEdge(
                    edge_id=eid, source_id=ed["source_id"],
                    target_id=ed["target_id"],
                    relation=RelationType(ed["relation"]),
                    weight=ed.get("weight", 0.8),
                    properties={},
                    created_at=ed.get("created_at", now),
                )
            self._name_index = data.get("name_index", {})
            logger.info(
                "knowledge_graph: loaded %d nodes, %d edges",
                len(self._nodes), len(self._edges)
            )
        except Exception as e:
            logger.error("knowledge_graph: load error: %s", e)
            self._edges = {}

    def get_stats(self) -> Dict[str, Any]:
        by_category: Dict[str, int] = {}
        for n in self._nodes.values():
            by_category[n.category] = by_category.get(n.category, 0) + 1
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "by_category": by_category,
        }


# Singleton
_graph: Optional[KnowledgeGraph] = None


def get_knowledge_graph() -> KnowledgeGraph:
    global _graph
    if _graph is None:
        _graph = KnowledgeGraph()
    return _graph
