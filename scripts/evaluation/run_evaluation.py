#!/usr/bin/env python3
"""
سكريبت تقييم Hajeen Model v1.

يُجري اختبارات شاملة على النموذج وكأن مستخدمين مختلفين يستخدمونه.

الاستخدام:
    python scripts/evaluation/run_evaluation.py [--full] [--load-test]
"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hajeen.eval")

# ─── Test Suites ──────────────────────────────────────────────────────────────

GENERAL_QUESTIONS = [
    {"q": "ما هو الذكاء الاصطناعي؟", "lang": "ar", "type": "general"},
    {"q": "ما الفرق بين Machine Learning و Deep Learning؟", "lang": "ar", "type": "knowledge"},
    {"q": "اشرح مفهوم RAG في الذكاء الاصطناعي", "lang": "ar", "type": "knowledge"},
    {"q": "ما هي اللغة العربية ومميزاتها؟", "lang": "ar", "type": "language"},
    {"q": "What is artificial intelligence?", "lang": "en", "type": "general"},
    {"q": "Explain Large Language Models", "lang": "en", "type": "knowledge"},
]

ANALYTICAL_QUESTIONS = [
    {"q": "قارن بين GPT-4 و LLaMA من ناحية الاستخدامات", "lang": "ar", "type": "analytical"},
    {"q": "ما إيجابيات وسلبيات الذكاء الاصطناعي المحلي مقارنة بالسحابي؟", "lang": "ar", "type": "analytical"},
    {"q": "Analyze the impact of AI on the job market", "lang": "en", "type": "analytical"},
]

RAG_TEST_QUESTIONS = [
    {"q": "ما هو محتوى المقالات المخزنة في المنصة؟", "lang": "ar", "type": "rag"},
    {"q": "ابحث في قاعدة البيانات عن أخبار الذكاء الاصطناعي", "lang": "ar", "type": "rag"},
]

CONTEXT_QUESTIONS = [
    {"q": "تحدثنا عن الذكاء الاصطناعي. ما أهم نقطة ذكرتها؟", "lang": "ar", "type": "context"},
    {"q": "ما الذي قلته في ردك السابق؟", "lang": "ar", "type": "context"},
]

STABILITY_QUESTIONS = [
    {"q": "ما 1+1؟", "lang": "ar", "type": "stability"},
    {"q": "قل مرحبا", "lang": "ar", "type": "stability"},
    {"q": "Hello!", "lang": "en", "type": "stability"},
]

ALL_QUESTIONS = (
    GENERAL_QUESTIONS + ANALYTICAL_QUESTIONS +
    RAG_TEST_QUESTIONS + CONTEXT_QUESTIONS + STABILITY_QUESTIONS
)


async def run_single_test(model, question: dict, idx: int, total: int) -> dict:
    """تشغيل اختبار واحد."""
    from hajeen_model.hajeen_model_v1 import HajeenRequest, HajeenMessage
    t0 = time.perf_counter()
    try:
        request = HajeenRequest(messages=[HajeenMessage("user", question["q"])])
        resp = await model.complete(request)
        latency = round((time.perf_counter() - t0) * 1000, 1)
        result = {
            "idx": idx,
            "question": question["q"],
            "type": question["type"],
            "language": question["lang"],
            "answer": resp.content[:300],
            "answer_length": len(resp.content),
            "tokens": resp.total_tokens,
            "latency_ms": latency,
            "provider": resp.provider,
            "is_mock": resp.is_mock,
            "status": "pass",
        }
        status = "✅" if not resp.is_mock else "🔶"
        print(f"  [{idx}/{total}] {status} {question['type']} ({latency:.0f}ms) — {question['q'][:50]}")
    except Exception as e:
        latency = round((time.perf_counter() - t0) * 1000, 1)
        result = {
            "idx": idx,
            "question": question["q"],
            "type": question["type"],
            "language": question["lang"],
            "error": str(e),
            "latency_ms": latency,
            "status": "fail",
        }
        print(f"  [{idx}/{total}] ❌ {question['type']} — ERROR: {e}")
    return result


async def run_load_test(model, concurrent: int = 5, total_requests: int = 20) -> dict:
    """اختبار الأحمال."""
    print(f"\n  🔄 Load Test: {concurrent} طلب متزامن × {total_requests // concurrent} جولة")
    questions = [
        "ما هو الذكاء الاصطناعي؟",
        "ما هو تعلم الآلة؟",
        "ما هي النماذج اللغوية الكبيرة؟",
        "اشرح Deep Learning",
        "ما تأثير الذكاء الاصطناعي على المجتمع؟",
    ]

    t0 = time.perf_counter()
    successes = 0
    errors = 0
    latencies = []

    for batch in range(total_requests // concurrent):
        batch_q = [questions[i % len(questions)] for i in range(concurrent)]
        tasks = [model.chat(q) for q in batch_q]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                errors += 1
            else:
                successes += 1
                latencies.append(r.latency_ms)

    total_time = time.perf_counter() - t0
    return {
        "total_requests": total_requests,
        "concurrent": concurrent,
        "successes": successes,
        "errors": errors,
        "total_time_sec": round(total_time, 2),
        "avg_latency_ms": round(sum(latencies) / max(len(latencies), 1), 1),
        "throughput_rps": round(total_requests / total_time, 2),
    }


async def run_full_evaluation(load_test: bool = False) -> dict:
    """تقييم شامل."""
    from hajeen_model.hajeen_model_v1 import get_hajeen_model
    model = get_hajeen_model()

    print("\n" + "═" * 70)
    print("  🧪  Hajeen Model v1 — Comprehensive Evaluation")
    print("═" * 70)

    # فحص الحالة
    health = await model.health()
    print(f"\n  النموذج:  {health['model']}")
    print(f"  المزود:   {health['active_provider']}")
    print(f"  Ollama:   {'✅ متاح' if health['ollama_available'] else '❌ غير متاح (Mock)'}")

    # تشغيل الاختبارات
    print(f"\n  تشغيل {len(ALL_QUESTIONS)} اختبار...")
    t_start = time.perf_counter()
    results = []
    for i, q in enumerate(ALL_QUESTIONS, 1):
        r = await run_single_test(model, q, i, len(ALL_QUESTIONS))
        results.append(r)
        await asyncio.sleep(0.1)  # تجنب الإفراط

    total_time = time.perf_counter() - t_start

    # تجميع النتائج
    passed = [r for r in results if r["status"] == "pass"]
    failed = [r for r in results if r["status"] == "fail"]
    by_type = {}
    for r in passed:
        t = r["type"]
        by_type.setdefault(t, []).append(r)

    # اختبار الأحمال
    load_results = None
    if load_test:
        load_results = await run_load_test(model)

    # تقرير نهائي
    avg_latency = sum(r["latency_ms"] for r in passed) / max(len(passed), 1)
    using_real = sum(1 for r in passed if not r.get("is_mock", True))

    report = {
        "summary": {
            "total": len(results),
            "passed": len(passed),
            "failed": len(failed),
            "pass_rate_pct": round(len(passed) / len(results) * 100, 1),
            "avg_latency_ms": round(avg_latency, 1),
            "total_time_sec": round(total_time, 2),
            "real_ai_responses": using_real,
            "mock_responses": len(passed) - using_real,
            "provider": health["active_provider"],
        },
        "by_type": {t: len(v) for t, v in by_type.items()},
        "results": results,
        "load_test": load_results,
        "health": health,
        "timestamp": time.time(),
    }

    # طباعة الملخص
    print("\n" + "═" * 70)
    print("  📊  نتائج التقييم")
    print("═" * 70)
    print(f"  المجموع:      {len(results)} اختبار")
    print(f"  نجح:          {len(passed)} ({report['summary']['pass_rate_pct']}%)")
    print(f"  فشل:          {len(failed)}")
    print(f"  متوسط Latency: {avg_latency:.0f}ms")
    print(f"  استجابات حقيقية: {using_real} | Mock: {len(passed) - using_real}")
    print()
    for t, items in by_type.items():
        avg = sum(r["latency_ms"] for r in items) / len(items)
        print(f"  {t:15} — {len(items)} اختبار ({avg:.0f}ms)")

    if load_results:
        print(f"\n  Load Test: {load_results['throughput_rps']} req/s | avg {load_results['avg_latency_ms']}ms")

    print("═" * 70)

    # حفظ التقرير
    output_dir = Path("hajeen_model/evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"eval_report_{int(time.time())}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  💾 التقرير محفوظ: {report_path}\n")

    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Hajeen Model v1 Evaluation")
    parser.add_argument("--full", action="store_true", help="تقييم شامل")
    parser.add_argument("--load-test", action="store_true", help="اختبار الأحمال")
    args = parser.parse_args()

    asyncio.run(run_full_evaluation(load_test=args.load_test))


if __name__ == "__main__":
    main()
