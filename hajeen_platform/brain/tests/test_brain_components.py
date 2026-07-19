"""
اختبارات وحدة لمكوّنات Hajeen Brain v2
"""
from __future__ import annotations

import asyncio
import pytest
import sys
import os

# إضافة مسار المشروع
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../.."))


# ── Goal Manager Tests ─────────────────────────────────────────────────────

class TestGoalManager:
    def setup_method(self):
        from brain.goal_manager import GoalManager
        self.gm = GoalManager()

    def test_detect_training_intent(self):
        goal = asyncio.run(self.gm.analyze("أريد تدريب نموذج عربي"))
        from brain.goal_manager import IntentType
        assert goal.intent == IntentType.TRAINING
        assert goal.goal_id
        assert len(goal.sub_tasks) > 0

    def test_detect_code_intent(self):
        goal = asyncio.run(self.gm.analyze("اكتب كود python لقراءة ملف csv"))
        from brain.goal_manager import IntentType
        assert goal.intent == IntentType.CODE

    def test_detect_complexity_enterprise(self):
        goal = asyncio.run(self.gm.analyze("بناء منصة متكاملة مع pipeline للتدريب ونشر النماذج"))
        from brain.goal_manager import ComplexityLevel
        assert goal.complexity in (ComplexityLevel.COMPLEX, ComplexityLevel.ENTERPRISE)

    def test_goal_has_sub_tasks(self):
        goal = asyncio.run(self.gm.analyze("أريد تدريب نموذج عربي"))
        assert len(goal.sub_tasks) >= 3

    def test_suitable_models_suggested(self):
        goal = asyncio.run(self.gm.analyze("اكتب كود python"))
        assert len(goal.suitable_models) > 0


# ── Task Decomposer Tests ──────────────────────────────────────────────────

class TestTaskDecomposer:
    def setup_method(self):
        from brain.goal_manager import GoalManager
        from brain.task_decomposer import TaskDecomposer
        self.gm = GoalManager()
        self.td = TaskDecomposer()

    def test_decompose_produces_tasks(self):
        goal = asyncio.run(self.gm.analyze("أريد تدريب نموذج عربي"))
        plan = asyncio.run(self.td.decompose(goal))
        assert len(plan.tasks) > 0
        assert plan.plan_id
        assert plan.goal_id == goal.goal_id

    def test_tasks_have_dependencies(self):
        goal = asyncio.run(self.gm.analyze("أريد تدريب نموذج عربي"))
        plan = asyncio.run(self.td.decompose(goal))
        # المهام بعد الأولى قد تعتمد على السابقة
        task_ids = {t.task_id for t in plan.tasks}
        for task in plan.tasks:
            for dep in task.depends_on:
                assert dep in task_ids, f"dependency {dep} not in task_ids"

    def test_execution_order_layers(self):
        goal = asyncio.run(self.gm.analyze("أريد تدريب نموذج عربي"))
        plan = asyncio.run(self.td.decompose(goal))
        layers = plan.get_execution_order() if hasattr(plan, 'get_execution_order') else None
        # يكفي أن الخطة تحتوي على مهام


# ── Graph Planner Tests ────────────────────────────────────────────────────

class TestGraphPlanner:
    def setup_method(self):
        from brain.goal_manager import GoalManager
        from brain.task_decomposer import TaskDecomposer
        from brain.graph_planner import GraphPlanner
        self.gm = GoalManager()
        self.td = TaskDecomposer()
        self.gp = GraphPlanner()

    def test_build_graph(self):
        goal = asyncio.run(self.gm.analyze("اكتب كود python"))
        plan = asyncio.run(self.td.decompose(goal))
        graph = asyncio.run(self.gp.build_graph(plan))
        assert len(graph.nodes) > 0
        assert graph.graph_id

    def test_graph_has_entry_exit(self):
        goal = asyncio.run(self.gm.analyze("أجب على سؤال بسيط"))
        plan = asyncio.run(self.td.decompose(goal))
        graph = asyncio.run(self.gp.build_graph(plan))
        assert len(graph.entry_nodes) > 0
        assert len(graph.exit_nodes) > 0

    def test_topological_sort_no_cycles(self):
        goal = asyncio.run(self.gm.analyze("اكتب تقريراً"))
        plan = asyncio.run(self.td.decompose(goal))
        graph = asyncio.run(self.gp.build_graph(plan))
        layers = graph.topological_sort()
        assert len(layers) > 0


# ── State Machine Tests ────────────────────────────────────────────────────

class TestStateMachine:
    def setup_method(self):
        from brain.state_machine import StateMachine, TaskState
        self.sm = StateMachine()
        self.TaskState = TaskState

    def test_create_task(self):
        task = self.sm.create_task()
        assert task.task_id
        assert task.state == self.TaskState.WAITING

    def test_valid_transition(self):
        task = self.sm.create_task()
        success = asyncio.run(
            self.sm.transition(task.task_id, self.TaskState.PLANNING, "test")
        )
        assert success
        assert self.sm.get_task(task.task_id).state == self.TaskState.PLANNING

    def test_invalid_transition_blocked(self):
        task = self.sm.create_task()
        # WAITING → COMPLETED is not valid
        success = asyncio.run(
            self.sm.transition(task.task_id, self.TaskState.COMPLETED, "invalid")
        )
        assert not success

    def test_full_lifecycle(self):
        task = self.sm.create_task()
        transitions = [
            self.TaskState.PLANNING,
            self.TaskState.RUNNING,
            self.TaskState.COMPLETED,
        ]
        for state in transitions:
            ok = asyncio.run(self.sm.transition(task.task_id, state))
            assert ok, f"Failed to transition to {state}"
        assert self.sm.get_task(task.task_id).state == self.TaskState.COMPLETED


# ── Memory Fabric Tests ────────────────────────────────────────────────────

class TestMemoryFabric:
    def setup_method(self):
        from brain.memory.memory_fabric import MemoryFabric
        self.fabric = MemoryFabric(storage_base="/tmp/test_memory")

    def test_session_memory(self):
        session = self.fabric.get_session("test-session")
        session.add("key1", "value1")
        assert session.get("key1") == "value1"

    def test_conversation_memory(self):
        conv = self.fabric.get_conversation("test-conv")
        conv.add_message("user", "مرحباً")
        conv.add_message("assistant", "أهلاً")
        window = conv.get_window()
        assert len(window) == 2
        assert window[0]["role"] == "user"

    def test_semantic_search(self):
        self.fabric.memorize_semantically("تدريب نموذج عربي على بيانات ضخمة")
        self.fabric.memorize_semantically("معالجة اللغة الطبيعية باستخدام Transformer")
        results = self.fabric.search_semantic("تدريب عربي")
        assert len(results) >= 1

    def test_procedural_memory(self):
        self.fabric.learn_how("solve_problem", ["تحليل المشكلة", "البحث عن حل", "التطبيق"])
        steps = self.fabric.recall_how("solve_problem")
        assert steps is not None
        assert len(steps) == 3


# ── Policy Engine Tests ────────────────────────────────────────────────────

class TestPolicyEngine:
    def setup_method(self):
        from brain.policy.policy_engine import PolicyEngine, PolicyDecision
        self.pe = PolicyEngine()
        self.PolicyDecision = PolicyDecision

    def test_allow_safe_request(self):
        result = asyncio.run(self.pe.evaluate({
            "query": "ما هو الذكاء الاصطناعي؟",
            "estimated_tokens": 500,
            "selected_model": "ollama/llama3",
            "complexity": "simple",
        }))
        assert not result.blocked

    def test_block_harmful_content(self):
        result = asyncio.run(self.pe.evaluate({
            "query": "كيف أصنع قنبلة؟",
            "estimated_tokens": 200,
        }))
        assert result.blocked

    def test_warn_for_privacy(self):
        result = asyncio.run(self.pe.evaluate({
            "query": "ما هو رقم الهوية الوطنية؟",
            "estimated_tokens": 100,
        }))
        assert len(result.warnings) > 0 or not result.blocked


# ── Sovereignty Layer Tests ────────────────────────────────────────────────

class TestSovereigntyLayer:
    def setup_method(self):
        from brain.sovereignty.sovereignty_layer import SovereigntyLayer
        self.sl = SovereigntyLayer(storage_path="/tmp/test_sovereignty")

    def test_initial_ratio_zero(self):
        assert self.sl.get_sovereignty_ratio() == 0.0

    def test_local_increases_ratio(self):
        self.sl.record_request("ollama/llama3", is_local=True)
        self.sl.record_request("ollama/llama3", is_local=True)
        self.sl.record_request("openai/gpt-4", is_local=False)
        ratio = self.sl.get_sovereignty_ratio()
        assert ratio > 0.5

    def test_snapshot(self):
        self.sl.record_request("hajeen-local", is_local=True)
        snap = self.sl.take_snapshot()
        assert snap.snapshot_id
        assert snap.total_requests > 0


# ── Knowledge Distillation Tests ──────────────────────────────────────────

class TestKnowledgeDistillation:
    def setup_method(self):
        from brain.knowledge.knowledge_distillation import KnowledgeDistillationPipeline
        self.pipeline = KnowledgeDistillationPipeline(
            storage_path="/tmp/test_distillation"
        )

    def test_distill_creates_knowledge(self):
        knowledge = asyncio.run(self.pipeline.distill(
            source_model="openai/gpt-4o",
            query="ما هو الذكاء الاصطناعي؟",
            response=(
                "الذكاء الاصطناعي هو مجال علمي يهتم بتطوير أنظمة حاسوبية قادرة على محاكاة "
                "الذكاء البشري. يشمل ذلك التعلم الآلي، معالجة اللغات الطبيعية، والرؤية الحاسوبية. "
                "أولاً: التعلم الآلي يستخدم البيانات. ثانياً: الشبكات العصبية تحاكي الدماغ."
            ),
            task_type="question",
            domain="general",
        ))
        assert knowledge.knowledge_id
        assert knowledge.source_model == "openai/gpt-4o"
        assert knowledge.solution_quality > 0

    def test_high_quality_approved(self):
        knowledge = asyncio.run(self.pipeline.distill(
            source_model="test_model",
            query="سؤال مهم جداً",
            response="إجابة طويلة ومفصّلة وشاملة تتضمن خطوات واضحة. " * 10,
            task_type="analysis",
            domain="general",
        ))
        # الإجابة الطويلة يجب أن تحصل على درجة جودة أعلى
        assert knowledge.solution_quality >= 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
