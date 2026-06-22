"""Demo Pipeline — تشغيل pipeline حقيقي كامل بمصدر TechCrunch RSS.

الاستخدام:
    cd hajeen_platform
    python demo_pipeline.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# ── إعداد sys.path ──────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# ── إعداد Logging ──────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/demo_pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("demo_pipeline")


# ── RSS Feed للاختبار ────────────────────────────────────────────────────────
RSS_FEEDS = [
    ("TechCrunch", "https://techcrunch.com/feed/"),
    # يمكن إضافة المزيد:
    # ("BBC Arabic", "https://feeds.bbci.co.uk/arabic/rss.xml"),
]


async def run_demo() -> None:
    """تشغيل demo pipeline كامل."""
    print("\n" + "═" * 60)
    print("   Hajeen AI Platform — Demo Pipeline")
    print("═" * 60 + "\n")

    # 1. استيراد المكونات
    from data_engine.channels.builder import ChannelBuilder, RSSChannel
    from data_engine.channels.registry import ChannelRegistry
    from data_engine.pipelines.pipeline_orchestrator import PipelineOrchestrator
    from data_engine.storage.storage_manager import StorageManager
    from shared.schemas.channel import (
        ChannelConfig, ChannelStatus, ScheduleConfig, SourceConfig
    )
    from shared.utils.id_generator import generate_channel_id
    from shared.utils.datetime_utils import utc_now

    total_fetched = 0
    total_processed = 0
    total_stored = 0

    for feed_name, feed_url in RSS_FEEDS:
        print(f"\n{'─' * 50}")
        print(f"  القناة: {feed_name}")
        print(f"  URL:    {feed_url}")
        print(f"{'─' * 50}")

        # 2. إنشاء قناة RSS
        channel_id = generate_channel_id()
        now = utc_now()
        config = ChannelConfig(
            id=channel_id,
            name=feed_name,
            description=f"Demo channel for {feed_name}",
            source=SourceConfig(url=feed_url, type="rss"),  # type: ignore[arg-type]
            schedule=ScheduleConfig(cron="0 * * * *"),
            status=ChannelStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )

        channel = RSSChannel(config=config)
        # تسجيل إذا لم تكن موجودة
        if not ChannelRegistry.get(channel_id):
            ChannelRegistry.register(channel)

        # 3. Fetch
        print("\n▶ [1/5] Fetch — جلب البيانات...")
        t0 = time.time()
        fetch_result = await channel.fetch()
        articles = fetch_result.articles
        fetch_ms = (time.time() - t0) * 1000
        print(f"   ✓ تم جلب {len(articles)} مقال ({fetch_ms:.0f}ms)")

        if not articles:
            print("   ⚠ لا توجد مقالات — تخطي هذه القناة")
            continue

        # عرض عيّنة من المقالات
        print(f"\n   عيّنة من المقالات:")
        for i, art in enumerate(articles[:3]):
            print(f"   {i+1}. {art.title[:70]}...")

        # 4. إعداد Storage
        print("\n▶ [2/5] إعداد التخزين...")
        storage = StorageManager()
        await storage.connect()
        print(f"   ✓ التخزين جاهز: {storage.base_data_dir}")

        # 5. تشغيل Pipeline كامل
        print("\n▶ [3-5/5] Pipeline: Clean → Filter → Enrich → Transform → Store...")
        orchestrator = PipelineOrchestrator(
            name=f"demo:{feed_name}",
            source_id=channel_id,
            storage_manager=storage,
            allowed_languages=["ar", "en"],
        )

        t1 = time.time()
        context = await orchestrator.run(articles=articles)
        pipeline_ms = (time.time() - t1) * 1000

        stored = context.get("stored_count") or 0

        print(f"\n   ✓ Pipeline مكتمل ({pipeline_ms:.0f}ms)")
        print(f"   المدخلات : {len(articles)} مقال")
        print(f"   المخرجات : {context.article_count} مقال")
        print(f"   المحفوظة : {stored} مقال")

        # إحصائيات المراحل
        if context.stage_traces:
            print(f"\n   تفصيل المراحل:")
            for trace in context.stage_traces:
                status = "✓" if trace.error_count == 0 else "⚠"
                print(
                    f"   {status} {trace.stage_name:15} "
                    f"{trace.output_count}/{trace.input_count} مقال  "
                    f"({trace.duration_ms:.0f}ms)"
                )

        total_fetched += len(articles)
        total_processed += context.article_count
        total_stored += stored

    # 6. ملخص نهائي
    print("\n" + "═" * 60)
    print("   ✓ Demo Pipeline مكتمل!")
    print("═" * 60)
    print(f"   إجمالي الجلب      : {total_fetched} مقال")
    print(f"   إجمالي المعالجة   : {total_processed} مقال")
    print(f"   إجمالي المحفوظة   : {total_stored} مقال")
    print(f"\n   مجلدات التخزين:")
    for d in ["raw", "bronze", "silver", "gold", "metadata"]:
        p = Path(f"storage_data/{d}")
        count = len(list(p.rglob("*"))) if p.exists() else 0
        print(f"   storage_data/{d}/  — {count} ملف")
    print(f"\n   السجلات: logs/demo_pipeline.log")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(run_demo())
