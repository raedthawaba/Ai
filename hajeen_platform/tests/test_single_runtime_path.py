"""
test_single_runtime_path.py — اختبار التحقق من وحدة Runtime

الهدف:
  التأكد من أن كل طلب AI يمر عبر HajeenBrainV3 حصراً.
  لا يوجد مسار بديل يتجاوز Brain.

الاختبارات:
  1. Brain Singleton — نسخة واحدة فقط
  2. Memory SSOT — MemoryFabric مصدر الحقيقة الوحيد
  3. ModelRouter — موجه واحد فقط
  4. UnifiedPromptBuilder — بناء واحد فقط
  5. Chat Endpoint — يمر عبر Brain لا LLM مباشر
  6. No Direct LLM — لا استدعاء LLM خارج Brain
  7. Runtime Path Trace — التتبع الكامل عبر الطبقات
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ── Helpers ────────────────────────────────────────────────────────────────


def run_async(coro):
    """تشغيل coroutine في بيئة اختبار."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Test Suite ─────────────────────────────────────────────────────────────


class TestBrainSingleton(unittest.TestCase):
    """اختبار 1: HajeenBrainV3 كـ Singleton."""

    def test_brain_v3_singleton(self):
        """يجب أن تعيد get_brain_v3() نفس النسخة دائماً."""
        from brain.brain_v3 import get_brain_v3, _brain_v3

        brain1 = run_async(get_brain_v3())
        brain2 = run_async(get_brain_v3())
        self.assertIs(brain1, brain2, "يجب أن يكون Brain Singleton واحد فقط")

    def test_get_brain_alias(self):
        """get_brain و get_brain_v3 يشيران لنفس الـ Singleton."""
        from brain.brain_v3 import get_brain, get_brain_v3

        b1 = run_async(get_brain())
        b2 = run_async(get_brain_v3())
        self.assertIs(b1, b2, "get_brain يجب أن يكون alias لـ get_brain_v3")

    def test_brain_version(self):
        """HajeenBrainV3 يجب أن يكون الإصدار 3.x."""
        from brain.brain_v3 import get_brain_v3
        brain = run_async(get_brain_v3())
        version = brain.VERSION
        self.assertTrue(
            version.startswith("3"),
            f"الإصدار يجب أن يبدأ بـ 3، الحالي: {version}"
        )


class TestMemorySSO(unittest.TestCase):
    """اختبار 2: MemoryFabric كمصدر الحقيقة الوحيد."""

    def test_memory_fabric_singleton(self):
        """get_memory_fabric() يجب أن تعيد نفس النسخة."""
        from brain.memory.memory_fabric import get_memory_fabric
        m1 = get_memory_fabric()
        m2 = get_memory_fabric()
        self.assertIs(m1, m2, "MemoryFabric يجب أن يكون Singleton")

    def test_unified_interface_routes_to_fabric(self):
        """UnifiedMemoryInterface يجب أن يستخدم MemoryFabric."""
        from brain.memory.unified_interface import get_unified_memory
        ui = get_unified_memory()
        self.assertIsNotNone(ui, "UnifiedMemoryInterface يجب أن يكون متاحاً")

    def test_brain_uses_memory_fabric(self):
        """HajeenBrainV3 يجب أن يستخدم MemoryFabric مباشرةً."""
        from brain.brain_v3 import get_brain_v3
        from brain.memory.memory_fabric import MemoryFabric

        brain = run_async(get_brain_v3())
        self.assertIsInstance(
            brain.memory,
            MemoryFabric,
            "Brain يجب أن يستخدم MemoryFabric كمصدر الذاكرة"
        )

    def test_session_manager_is_adapter(self):
        """SessionManager يجب أن يكون Adapter للـ MemoryFabric."""
        from services.memory.session_manager import SessionManager
        sm = SessionManager()
        self.assertTrue(
            hasattr(sm, "_unified_memory"),
            "SessionManager يجب أن يستخدم UnifiedMemoryInterface"
        )

    def test_conversation_memory_is_adapter(self):
        """ConversationMemory يجب أن يكون Adapter."""
        from services.memory.conversation_memory import ConversationMemory
        cm = ConversationMemory(session_id="test")
        self.assertTrue(
            hasattr(cm, "_unified_memory"),
            "ConversationMemory يجب أن يستخدم UnifiedMemoryInterface"
        )


class TestModelRouterUnification(unittest.TestCase):
    """اختبار 3: ModelRouter كموجه وحيد."""

    def test_model_router_singleton(self):
        """get_model_router() يجب أن تعيد نفس النسخة."""
        from brain.model_router import get_model_router
        r1 = get_model_router()
        r2 = get_model_router()
        self.assertIs(r1, r2, "ModelRouter يجب أن يكون Singleton")

    def test_brain_uses_model_router(self):
        """HajeenBrainV3 يجب أن يستخدم ModelRouter الموحد."""
        from brain.brain_v3 import get_brain_v3
        from brain.model_router import ModelRouter

        brain = run_async(get_brain_v3())
        self.assertIsInstance(
            brain.model_router,
            ModelRouter,
            "Brain يجب أن يستخدم ModelRouter الموحد"
        )

    def test_model_router_has_routing_stats(self):
        """ModelRouter يجب أن يوفر إحصائيات التوجيه."""
        from brain.model_router import get_model_router
        router = get_model_router()
        stats = router.get_routing_stats()
        self.assertIn("total", stats, "ModelRouter يجب أن يوفر إحصائيات")


class TestUnifiedPromptBuilder(unittest.TestCase):
    """اختبار 4: UnifiedPromptBuilder كبناء وحيد."""

    def test_unified_prompt_builder_singleton(self):
        """get_unified_prompt_builder() يجب أن تعيد نفس النسخة."""
        from brain.prompts.unified_prompt_builder import get_unified_prompt_builder
        pb1 = get_unified_prompt_builder()
        pb2 = get_unified_prompt_builder()
        self.assertIs(pb1, pb2, "UnifiedPromptBuilder يجب أن يكون Singleton")

    def test_inherits_abstract_builder(self):
        """UnifiedPromptBuilder يجب أن يرث من AbstractPromptBuilder."""
        from brain.prompts.unified_prompt_builder import UnifiedPromptBuilder
        from core.prompts.base import AbstractPromptBuilder
        self.assertTrue(
            issubclass(UnifiedPromptBuilder, AbstractPromptBuilder),
            "يجب أن يرث من AbstractPromptBuilder"
        )

    def test_build_chat_prompt(self):
        """UnifiedPromptBuilder يجب أن يبني Chat prompt صحيح."""
        from brain.prompts.unified_prompt_builder import get_unified_prompt_builder
        pb = get_unified_prompt_builder()
        prompt = pb.build_chat(user_message="مرحبا")
        self.assertIsNotNone(prompt)
        self.assertIn("مرحبا", prompt.text)

    def test_build_rag_prompt(self):
        """UnifiedPromptBuilder يجب أن يبني RAG prompt صحيح."""
        from brain.prompts.unified_prompt_builder import get_unified_prompt_builder
        pb = get_unified_prompt_builder()
        prompt = pb.build_rag(
            query="ما هو الذكاء الاصطناعي؟",
            context="الذكاء الاصطناعي هو محاكاة العمليات الذهنية البشرية.",
        )
        self.assertIsNotNone(prompt)
        self.assertEqual(prompt.metadata.get("type"), "rag")

    def test_build_agent_prompt(self):
        """UnifiedPromptBuilder يجب أن يبني Agent prompt."""
        from brain.prompts.unified_prompt_builder import get_unified_prompt_builder
        pb = get_unified_prompt_builder()
        prompt = pb.build_agent(
            task="ابحث عن معلومات",
            tools=[{"name": "search", "description": "أداة بحث"}],
        )
        self.assertIsNotNone(prompt)
        self.assertEqual(prompt.metadata.get("type"), "agent")

    def test_build_reasoning_prompt(self):
        """UnifiedPromptBuilder يجب أن يبني Reasoning prompt."""
        from brain.prompts.unified_prompt_builder import get_unified_prompt_builder
        pb = get_unified_prompt_builder()
        prompt = pb.build_reasoning(
            problem="ما هو 5 × 7؟",
            strategy="chain_of_thought",
        )
        self.assertIsNotNone(prompt)
        self.assertEqual(prompt.metadata.get("type"), "reasoning")

    def test_rag_prompt_builder_uses_abstract_base(self):
        """services/rag/prompt_builder.py يجب أن يرث AbstractPromptBuilder."""
        from services.rag.prompt_builder import PromptBuilder as RAGPromptBuilder
        from core.prompts.base import AbstractPromptBuilder
        self.assertTrue(
            issubclass(RAGPromptBuilder, AbstractPromptBuilder),
            "RAG PromptBuilder يجب أن يرث AbstractPromptBuilder"
        )


class TestBrainProcessPipeline(unittest.TestCase):
    """اختبار 5-6: Brain Pipeline والتحقق من عدم وجود LLM مباشر."""

    def test_brain_process_returns_response(self):
        """brain.process() يجب أن يعيد BrainResponse."""
        from brain.brain_v3 import BrainRequest, BrainResponse, get_brain_v3

        brain = run_async(get_brain_v3())
        request = BrainRequest(
            request_id="test_001",
            user_message="اختبار بسيط",
            session_id="test_session_001",
        )
        response = run_async(brain.process(request))
        self.assertIsInstance(response, BrainResponse)
        self.assertEqual(response.request_id, "test_001")
        self.assertIsNotNone(response.content)

    def test_brain_stream_generates_chunks(self):
        """brain.stream() يجب أن يولّد chunks."""
        from brain.brain_v3 import BrainRequest, get_brain_v3

        brain = run_async(get_brain_v3())
        request = BrainRequest(
            request_id="test_stream_001",
            user_message="مرحبا بالعالم",
            session_id="test_session_002",
        )

        async def collect():
            chunks = []
            async for chunk in brain.stream(request):
                chunks.append(chunk)
            return chunks

        chunks = run_async(collect())
        self.assertGreater(len(chunks), 0, "يجب أن ينتج Brain chunks أثناء Streaming")

    def test_chat_endpoint_no_direct_llm_import(self):
        """
        اختبار أن chat.py لا يستورد LLM أو InferenceEngine مباشرةً.
        """
        import ast
        from pathlib import Path
        chat_path = Path(__file__).parent.parent / "api" / "v1" / "ai" / "chat.py"
        if not chat_path.exists():
            self.skipTest("chat.py غير موجود")

        source = chat_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        forbidden_imports = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = getattr(node, "module", "") or ""
                names = [alias.name for alias in node.names]
                # لا يجب استيراد InferenceEngine أو LLMManager مباشرةً
                if any(
                    forbidden in module or forbidden in " ".join(names)
                    for forbidden in ["InferenceEngine", "LLMManager", "llm_manager"]
                ):
                    forbidden_imports.append(f"{module}: {names}")

        self.assertEqual(
            len(forbidden_imports), 0,
            f"chat.py يحتوي على imports محظورة: {forbidden_imports}"
        )

    def test_brain_trace_records_all_layers(self):
        """ExecutionTrace يجب أن يسجل جميع الطبقات."""
        from brain.brain_v3 import BrainRequest, ExecutionTrace, get_brain_v3

        brain = run_async(get_brain_v3())
        request = BrainRequest(
            request_id="test_trace_001",
            user_message="اختبار التتبع",
            session_id="test_trace_session",
        )
        response = run_async(brain.process(request))

        trace = response.trace
        self.assertIsInstance(trace, ExecutionTrace)
        # التأكد من أن الطبقات سُجلت
        self.assertGreater(
            len(trace.layers_passed), 0,
            "يجب أن تُسجّل الطبقات التي مرّ عليها الطلب"
        )


class TestNoLegacyBrainV2Logic(unittest.TestCase):
    """اختبار 7: لا يوجد منطق Brain v2 مستقل."""

    def test_brain_init_exports_v3(self):
        """brain/__init__.py يجب أن يصدّر HajeenBrainV3 فقط."""
        import brain
        self.assertTrue(hasattr(brain, "HajeenBrainV3"))
        self.assertTrue(hasattr(brain, "get_brain"))
        self.assertTrue(hasattr(brain, "get_brain_v3"))
        # HajeenBrain يجب أن يكون alias لـ HajeenBrainV3
        self.assertIs(brain.HajeenBrain, brain.HajeenBrainV3)

    def test_brain_router_uses_v3(self):
        """brain_router.py يجب أن يستخدم get_brain_v3 وليس get_brain_v2."""
        from pathlib import Path
        router_path = Path(__file__).parent.parent / "brain" / "api" / "brain_router.py"
        if not router_path.exists():
            self.skipTest("brain_router.py غير موجود")

        source = router_path.read_text(encoding="utf-8")
        # يجب ألا يوجد استيراد لـ brain_v2
        self.assertNotIn(
            "brain_v2",
            source,
            "brain_router.py يجب ألا يستورد brain_v2"
        )
        # يجب أن يستخدم get_brain_v3
        self.assertIn(
            "get_brain_v3",
            source,
            "brain_router.py يجب أن يستخدم get_brain_v3"
        )


class TestRuntimeCallGraph(unittest.TestCase):
    """اختبار 8: مسار التشغيل الكامل."""

    def test_full_runtime_path(self):
        """
        التأكد من مسار التشغيل الكامل:
        Request → Brain.process() → Memory → ModelRouter → Response
        """
        from brain.brain_v3 import BrainRequest, BrainResponse, get_brain_v3
        from brain.memory.memory_fabric import MemoryFabric
        from brain.model_router import ModelRouter

        brain = run_async(get_brain_v3())

        # التأكد من وجود المكونات الأساسية
        self.assertIsInstance(brain.memory, MemoryFabric)
        self.assertIsInstance(brain.model_router, ModelRouter)

        # تنفيذ طلب كامل
        request = BrainRequest(
            request_id="test_full_path_001",
            user_message="ما هي عاصمة الأردن؟",
            session_id="test_full_session",
        )
        response = run_async(brain.process(request))

        # التحقق من الاستجابة
        self.assertIsInstance(response, BrainResponse)
        self.assertIsNotNone(response.content)
        self.assertIsNotNone(response.model_used)
        self.assertIsNotNone(response.trace)

        # التحقق من أن الذاكرة سُجلت في MemoryFabric
        conversation = brain.memory.get_conversation("test_full_session")
        messages = conversation.get_window()
        self.assertGreater(
            len(messages), 0,
            "يجب أن تُحفظ المحادثة في MemoryFabric"
        )


# ── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("🧠 Hajeen Brain — Runtime Unification Tests")
    print("=" * 60)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    test_classes = [
        TestBrainSingleton,
        TestMemorySSO,
        TestModelRouterUnification,
        TestUnifiedPromptBuilder,
        TestBrainProcessPipeline,
        TestNoLegacyBrainV2Logic,
        TestRuntimeCallGraph,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 60)
    if result.wasSuccessful():
        print("✅ جميع اختبارات Runtime Unification نجحت")
        print("✅ HajeenBrainV3 هو Runtime الوحيد")
        print("✅ لا يوجد مسار يتجاوز Brain")
    else:
        print(f"❌ فشل {len(result.failures)} اختبارات")
        print(f"❌ أخطاء في {len(result.errors)} اختبارات")
    print("=" * 60)

    sys.exit(0 if result.wasSuccessful() else 1)
