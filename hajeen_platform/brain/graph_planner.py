"""
Graph Planner — محوّل المهام إلى Directed Acyclic Graph (DAG)
=============================================================
كل عقدة يمكن أن تكون: نموذج، أداة، RAG، وكيل، قاعدة بيانات، قرار.
يدعم: Parallel, Conditional, Retry, Dynamic Routing, Nested Graphs.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from .task_decomposer import DecompositionPlan, MicroTask, ExecutionMode

logger = logging.getLogger(__name__)


class NodeType(str, Enum):
    LLM = "llm"            # نموذج لغوي
    TOOL = "tool"          # أداة خارجية
    RAG = "rag"            # استرجاع معزّز
    AGENT = "agent"        # وكيل ذكي
    DATABASE = "database"  # قاعدة بيانات
    CODE = "code"          # تنفيذ كود
    COMPUTE = "compute"    # عملية حسابية
    DECISION = "decision"  # نقطة قرار
    MERGE = "merge"        # دمج نتائج


class EdgeType(str, Enum):
    SEQUENCE = "sequence"       # تسلسل بسيط
    PARALLEL = "parallel"       # تنفيذ متوازٍ
    CONDITIONAL = "conditional" # شرطي
    RETRY = "retry"             # إعادة المحاولة
    FEEDBACK = "feedback"       # حلقة تغذية راجعة


@dataclass
class GraphNode:
    node_id: str
    name: str
    node_type: NodeType
    config: Dict[str, Any]
    max_retries: int = 3
    timeout_seconds: int = 120
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "name": self.name,
            "node_type": self.node_type,
            "config": self.config,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass
class GraphEdge:
    edge_id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    condition: Optional[str] = None  # تعبير للتقييم في الحواف الشرطية
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type,
            "condition": self.condition,
        }


@dataclass
class ExecutionGraph:
    graph_id: str
    plan_id: str
    nodes: Dict[str, GraphNode]
    edges: List[GraphEdge]
    entry_nodes: List[str]
    exit_nodes: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def get_successors(self, node_id: str) -> List[str]:
        return [e.target_id for e in self.edges if e.source_id == node_id]

    def get_predecessors(self, node_id: str) -> List[str]:
        return [e.source_id for e in self.edges if e.target_id == node_id]

    def topological_sort(self) -> List[List[str]]:
        """ترتيب طبولوجي مع دعم التوازي (طبقات)."""
        in_degree = {nid: 0 for nid in self.nodes}
        for edge in self.edges:
            if edge.edge_type != EdgeType.FEEDBACK:
                in_degree[edge.target_id] += 1

        layers: List[List[str]] = []
        available = [nid for nid, deg in in_degree.items() if deg == 0]

        while available:
            layers.append(list(available))
            next_available = []
            for nid in available:
                for succ in self.get_successors(nid):
                    in_degree[succ] -= 1
                    if in_degree[succ] == 0:
                        next_available.append(succ)
            available = next_available

        return layers

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "plan_id": self.plan_id,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "entry_nodes": self.entry_nodes,
            "exit_nodes": self.exit_nodes,
            "execution_layers": self.topological_sort(),
        }


class GraphPlanner:
    """
    يحوّل DecompositionPlan إلى ExecutionGraph قابل للتنفيذ.
    """

    def __init__(self) -> None:
        self._graphs: Dict[str, ExecutionGraph] = {}

    async def build_graph(self, plan: DecompositionPlan) -> ExecutionGraph:
        """بناء الـ DAG من خطة التحليل."""
        nodes: Dict[str, GraphNode] = {}
        edges: List[GraphEdge] = []

        # بناء العقد
        for task in plan.tasks:
            node = self._task_to_node(task)
            nodes[node.node_id] = node

        # ربط العقد بالحواف
        task_id_to_node_id = {t.task_id: t.task_id for t in plan.tasks}

        for task in plan.tasks:
            for dep_id in task.depends_on:
                if dep_id in task_id_to_node_id:
                    edge_type = (
                        EdgeType.PARALLEL
                        if task.execution_mode == ExecutionMode.PARALLEL
                        else EdgeType.SEQUENCE
                    )
                    edges.append(GraphEdge(
                        edge_id=str(uuid.uuid4()),
                        source_id=dep_id,
                        target_id=task.task_id,
                        edge_type=edge_type,
                    ))

        # تحديد نقاط الدخول والخروج
        has_incoming: Set[str] = {e.target_id for e in edges}
        has_outgoing: Set[str] = {e.source_id for e in edges}
        entry_nodes = [nid for nid in nodes if nid not in has_incoming]
        exit_nodes = [nid for nid in nodes if nid not in has_outgoing]

        # إضافة عقدة دمج إذا كانت هناك مهام متوازية
        if plan.can_parallelize and len(exit_nodes) > 1:
            merge_node = GraphNode(
                node_id=str(uuid.uuid4()),
                name="merge_results",
                node_type=NodeType.MERGE,
                config={"strategy": "combine"},
            )
            nodes[merge_node.node_id] = merge_node
            for exit_id in exit_nodes:
                edges.append(GraphEdge(
                    edge_id=str(uuid.uuid4()),
                    source_id=exit_id,
                    target_id=merge_node.node_id,
                    edge_type=EdgeType.PARALLEL,
                ))
            exit_nodes = [merge_node.node_id]

        graph = ExecutionGraph(
            graph_id=str(uuid.uuid4()),
            plan_id=plan.plan_id,
            nodes=nodes,
            edges=edges,
            entry_nodes=entry_nodes,
            exit_nodes=exit_nodes,
            metadata={
                "can_parallelize": plan.can_parallelize,
                "total_nodes": len(nodes),
                "total_edges": len(edges),
            },
        )
        self._graphs[graph.graph_id] = graph
        logger.info(
            "graph_planner: graph=%s nodes=%d edges=%d layers=%d",
            graph.graph_id, len(nodes), len(edges), len(graph.topological_sort())
        )
        return graph

    def _task_to_node(self, task: MicroTask) -> GraphNode:
        node_type = NodeType.LLM
        if task.assigned_tool:
            tool_type_map = {
                "training_pipeline": NodeType.COMPUTE,
                "data_cleaner": NodeType.COMPUTE,
                "web_search": NodeType.TOOL,
                "model_evaluator": NodeType.COMPUTE,
                "deployment_manager": NodeType.TOOL,
                "vector_search": NodeType.RAG,
            }
            node_type = tool_type_map.get(task.assigned_tool, NodeType.TOOL)

        return GraphNode(
            node_id=task.task_id,
            name=task.name,
            node_type=node_type,
            config={
                "model": task.assigned_model,
                "tool": task.assigned_tool,
                "max_tokens": task.estimated_tokens,
                "timeout": task.timeout_seconds,
            },
            max_retries=task.max_retries,
            timeout_seconds=task.timeout_seconds,
            metadata=task.metadata,
        )

    def get_graph(self, graph_id: str) -> Optional[ExecutionGraph]:
        return self._graphs.get(graph_id)

    def visualize(self, graph: ExecutionGraph) -> str:
        """تمثيل نصي للرسم البياني."""
        lines = [f"Graph: {graph.graph_id}", f"Nodes: {len(graph.nodes)}", ""]
        for layer_idx, layer in enumerate(graph.topological_sort()):
            lines.append(f"Layer {layer_idx + 1}:")
            for nid in layer:
                node = graph.nodes[nid]
                lines.append(f"  [{node.node_type}] {node.name}")
        return "\n".join(lines)


# Singleton
_planner: Optional[GraphPlanner] = None


def get_graph_planner() -> GraphPlanner:
    global _planner
    if _planner is None:
        _planner = GraphPlanner()
    return _planner
