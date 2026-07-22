"""
Integration Tests — Brain V3 Cognitive Pipeline (Phase 2 Complete)
==================================================================
يختبر تكامل:
- brain_v3.py → IntentAnalyzer → ContextAnalyzer → ReasoningEngine
- التدفق الكامل من الطلب إلى الاستجابة عبر الطبقة المعرفية
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
import pytest


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_llm_response(content: str) -> MagicMock:
    mock = MagicMock()
    mock.generate = AsyncMock(return_value=content)
    return mock


INTENT_RESPONSE = '''{
  "primary_intent": "تطوير خوارزمية فرز",
  "category": "code_development",
  "secondary_intents": ["شرح المفهوم"],
  "implicit_requirements": ["كود نظيف"],
  "confidence": 0.92,
  "reasoning": "الطلب برمجي واضح",
  "alternative_interpretations": []
}'''

CONTEXT_RESPONSE = '''{
  "domain": "code",
  "expertise_level": "intermediate",
  "confidence": 0.85,
  "reasoning": "مفاهيم تقنية",
  "complexity": "medium",
  "estimated_tokens": 300,
  "required_capabilities": ["code_generation"],
  "constraints": [],
  "priorities": ["correctness"],
  "time_sensitivity": "low",
  "recommendations": ["استخدم مكتبة قياسية"],
  "summary": "طلب برمجي"
}'''

REASONING_RESPONSE = '''{
  "strategy": "chain_of_thought",
  "steps": [{"description": "تحليل", "reasoning": "...", "conclusion": "...", "confidence": 0.9, "alternatives": []}],
  "missing_information": [],
  "risks": [],
  "solution_options": [{
    "title": "Quicksort",
    "description": "استخدام quicksort",
    "pros": ["سريع"], "cons": ["غير مستقر"],
    "effort_estimate": "low", "time_estimate": "30 min",
    "risk_level": "low", "feasibility_score": 0.95, "recommended": true
  }],
  "recommended_solution_index": 0,
  "confidence": 0.9,
  "summary": "استخدام quicksort هو الأفضل"
}'''

GOAL_RESPONSE = '''{
  "final_objective": "تطوير دالة فرز فعالة",
  "intent": "code_development",
  "sub_goals": ["تحديد الخوارزمية", "كتابة الكود"],
  "complexity": "medium",
  "domain": "code",
  "required_tools": [],
  "confidence": 0.9,
  "reasoning": "..."
}'''


class TestBrainV3CognitivePipeline:
    """اختبارات تكامل الطبقة المعرفية في Brain V3."""

    def _make_brain(self):
        """إنشاء Brain V3 مع mocks للمكونات الخارجية."""
        from hajeen_platform.brain.brain_v3 import HajeenBrainV3, BrainRequest, RequestType

        with patch.multiple(
            "hajeen_platform.brain.brain_v3",
            get_goal_manager=MagicMock(return_value=MagicMock(
                analyze=AsyncMock(return_value=MagicMock(
                    goal_id="g1", final_objective="target",
                    intent="code_development", complexity="medium", domain="code",
                    confidence=0.9,
                ))
            )),
            get_task_decomposer=MagicMock(return_value=MagicMock(
                decompose=AsyncMock(return_value=MagicMock(
                    plan_id="p1", tasks=[], to_dict=MagicMock(return_value={})
                ))
            )),
            get_graph_planner=MagicMock(return_value=MagicMock(
                build_graph=AsyncMock(return_value=MagicMock(
                    graph_id="gr1", nodes=[], edges=[]
                ))
            )),
            get_decision_engine=MagicMock(return_value=MagicMock(
                decide=AsyncMock(return_value=MagicMock(
                    decision_id="d1", model_id="gpt-4o",
                    use_rag=False, use_web_search=False,
                    use_multi_model=False, resource_type=MagicMock(value="cloud_model"),
                    reasoning="اختيار النموذج",
                ))
            )),
            get_model_router=MagicMock(return_value=MagicMock(
                route=AsyncMock(return_value=MagicMock(
                    route_id="rt1", model_id="gpt-4o",
                    generate=AsyncMock(return_value="استجابة الاختبار"),
                ))
            )),
            get_multi_model_collaborator=MagicMock(return_value=MagicMock()),
            get_state_machine=MagicMock(return_value=MagicMock()),
            get_memory_fabric=MagicMock(return_value=MagicMock(
                get_session=MagicMock(return_value=MagicMock()),
                get_conversation=MagicMock(return_value=MagicMock(
                    add_message=MagicMock(),
                    get_window=MagicMock(return_value=[]),
                    add_ai_response=MagicMock(),
                )),
                get_long_term_memory=MagicMock(return_value=MagicMock(list_keys=MagicMock(return_value=[]))),
                semantic=MagicMock(store=MagicMock()),
                episodic=MagicMock(record=MagicMock()),
            )),
            get_knowledge_graph=MagicMock(return_value=MagicMock(
                add_node=MagicMock(), add_relation=MagicMock(),
            )),
            get_distillation_pipeline=MagicMock(return_value=MagicMock(
                distill=AsyncMock(return_value=None),
            )),
            get_self_reflection=MagicMock(return_value=MagicMock(
                reflect=AsyncMock(return_value=MagicMock(to_dict=MagicMock(return_value={}))),
                get_recent_reports=MagicMock(return_value=[]),
            )),
            get_self_evolution=MagicMock(return_value=MagicMock(
                analyze_and_evolve=AsyncMock(return_value=[]),
            )),
            get_policy_engine=MagicMock(return_value=MagicMock(
                evaluate=AsyncMock(return_value=MagicMock(
                    blocked=False, final_decision="allowed", rule_results=[],
                )),
            )),
            get_performance_db=MagicMock(return_value=MagicMock(
                record_request=AsyncMock(), get_statistics=MagicMock(return_value={}),
            )),
            get_sovereignty_layer=MagicMock(return_value=MagicMock(
                record_request=MagicMock(),
                get_sovereignty_report=MagicMock(return_value={}),
            )),
            get_autonomous_improvement=MagicMock(return_value=MagicMock(
                run_weekly_analysis=AsyncMock(return_value=MagicMock(to_dict=MagicMock(return_value={}))),
            )),
            get_intent_analyzer=MagicMock(return_value=MagicMock(
                analyze=AsyncMock(return_value=MagicMock(
                    intent_id="i1", category=MagicMock(value="code_development"),
                    primary_intent="تطوير خوارزمية", secondary_intents=[],
                    implicit_requirements=[], confidence=0.92, reasoning="واضح",
                    alternative_interpretations=[],
                ))
            )),
            get_context_analyzer=MagicMock(return_value=MagicMock(
                analyze=AsyncMock(return_value=MagicMock(
                    analysis_id="ca1", detected_domain="code",
                    domain_expertise_level="intermediate",
                    estimated_complexity="medium",
                    relevant_memories=[], constraints=[], priorities=[],
                    time_sensitivity="low", conversation_length=0,
                    confidence=0.85, reasoning="",
                ))
            )),
            get_reasoning_engine=MagicMock(return_value=MagicMock(
                reason=AsyncMock(return_value=MagicMock(
                    result_id="re1",
                    strategy=MagicMock(value="chain_of_thought"),
                    recommended_solution=MagicMock(title="Quicksort"),
                    reasoning_steps=[MagicMock()],
                    risks=[], solution_options=[MagicMock()],
                    confidence=0.9, missing_information=[],
                ))
            )),
        ):
            brain = HajeenBrainV3()
        return brain, BrainRequest, RequestType

    def test_brain_v3_has_cognitive_components(self):
        """التحقق من أن Brain V3 يحتوي على المكونات المعرفية."""
        brain, _, _ = self._make_brain()
        assert hasattr(brain, "intent_analyzer")
        assert hasattr(brain, "context_analyzer")
        assert hasattr(brain, "reasoning_engine")

    @pytest.mark.asyncio
    async def test_process_calls_intent_analyzer(self):
        """التحقق من أن process() يستدعي IntentAnalyzer."""
        brain, BrainRequest, RequestType = self._make_brain()
        req = BrainRequest(
            request_id=str(uuid.uuid4()),
            user_message="اكتب دالة فرز",
            session_id="s1",
        )
        response = await brain.process(req)
        brain.intent_analyzer.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_calls_context_analyzer(self):
        """التحقق من أن process() يستدعي ContextAnalyzer."""
        brain, BrainRequest, RequestType = self._make_brain()
        req = BrainRequest(
            request_id=str(uuid.uuid4()),
            user_message="اشرح خوارزمية BFS",
            session_id="s2",
        )
        response = await brain.process(req)
        brain.context_analyzer.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_calls_reasoning_engine(self):
        """التحقق من أن process() يستدعي ReasoningEngine."""
        brain, BrainRequest, RequestType = self._make_brain()
        req = BrainRequest(
            request_id=str(uuid.uuid4()),
            user_message="حل مشكلة النسخة الطويلة",
            session_id="s3",
        )
        response = await brain.process(req)
        brain.reasoning_engine.reason.assert_called_once()

    @pytest.mark.asyncio
    async def test_trace_contains_all_cognitive_layers(self):
        """التحقق من أن ExecutionTrace يحتوي على بيانات كل الطبقات."""
        brain, BrainRequest, RequestType = self._make_brain()
        req = BrainRequest(
            request_id=str(uuid.uuid4()),
            user_message="تحليل بيانات",
            session_id="s4",
        )
        response = await brain.process(req)
        trace = response.trace
        assert trace.intent_analysis.get("intent_id") == "i1"
        assert trace.context_analysis.get("analysis_id") == "ca1"
        assert trace.reasoning_result.get("result_id") == "re1"
        assert trace.goal_analysis.get("goal_id") == "g1"

    @pytest.mark.asyncio
    async def test_policy_blocked_request(self):
        """التحقق من أن الطلبات المحظورة لا تصل إلى الطبقة المعرفية."""
        brain, BrainRequest, RequestType = self._make_brain()
        brain.policy.evaluate = AsyncMock(return_value=MagicMock(
            blocked=True,
            final_decision="blocked",
            rule_results=[MagicMock(reason="محتوى غير مسموح")],
        ))

        req = BrainRequest(
            request_id=str(uuid.uuid4()),
            user_message="محتوى مرفوض",
            session_id="s5",
        )
        response = await brain.process(req)
        # لا يجب استدعاء الطبقة المعرفية
        brain.intent_analyzer.analyze.assert_not_called()
        assert "⚠️" in response.content


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
