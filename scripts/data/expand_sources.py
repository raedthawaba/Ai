#!/usr/bin/env python3
"""
سكريبت توسيع مصادر البيانات.

يضيف قنوات RSS عربية وإنجليزية جديدة إلى المنصة
لزيادة حجم بيانات التدريب.

الاستخدام:
    python scripts/data/expand_sources.py [--add-all] [--language ar|en]
"""
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hajeen.data")


async def add_channel(name: str, url: str, language: str = "ar", category: str = "general") -> bool:
    """إضافة قناة RSS إلى المنصة."""
    try:
        from data_engine.channels.registry import ChannelRegistry
        from data_engine.channels.builder import ChannelBuilder
        from shared.schemas.channel import ChannelConfig, ChannelType

        config = ChannelConfig(
            name=name,
            url=url,
            type=ChannelType.RSS,
            language=language,
            category=category,
            active=True,
            metadata={"auto_added": True, "source": "expand_sources.py"},
        )
        registry = ChannelRegistry()
        channel_id = await registry.register(config)
        logger.info("Added channel: %s (%s) → ID: %s", name, url, channel_id)
        return True
    except Exception as e:
        logger.error("Failed to add %s: %s", name, e)
        return False


async def expand_sources(language: str = "all"):
    """إضافة جميع مصادر البيانات."""
    from data_engine.channels.predefined.arabic_sources import ARABIC_RSS_SOURCES, ENGLISH_RSS_SOURCES

    sources = []
    if language in ("all", "ar"):
        sources += ARABIC_RSS_SOURCES
    if language in ("all", "en"):
        sources += ENGLISH_RSS_SOURCES

    print(f"\n  إضافة {len(sources)} مصدر...")
    success = 0
    for s in sources:
        ok = await add_channel(s["name"], s["url"], s.get("language", "ar"), s.get("category", "general"))
        if ok:
            success += 1

    print(f"\n  ✅ تمّت إضافة {success}/{len(sources)} مصادر\n")
    return success


async def show_current_stats():
    """عرض إحصائيات المصادر الحالية."""
    try:
        from data_engine.channels.registry import ChannelRegistry
        registry = ChannelRegistry()
        channels = await registry.list_channels()
        print(f"\n  المصادر الحالية: {len(channels)} قناة")
        for ch in channels[:10]:
            print(f"    • {ch.name} ({ch.language}) — {ch.url[:50]}...")
        if len(channels) > 10:
            print(f"    ... و{len(channels) - 10} قنوات أخرى")
    except Exception as e:
        print(f"  ⚠️  لا يمكن عرض المصادر: {e}")


async def analyze_data():
    """تحليل البيانات الحالية."""
    storage_dirs = [
        "storage_data/gold",
        "data/processed/pipeline",
    ]
    total_records = 0
    total_words = 0
    arabic_count = 0
    english_count = 0

    import re
    for d in storage_dirs:
        path = Path(d)
        if not path.exists():
            continue
        for f in path.glob("**/*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                items = data if isinstance(data, list) else [data]
                for item in items:
                    total_records += 1
                    text = item.get("content") or item.get("text") or ""
                    words = len(text.split())
                    total_words += words
                    ar_chars = len(re.findall(r"[\u0600-\u06FF]", text))
                    if ar_chars > len(text) * 0.1:
                        arabic_count += 1
                    else:
                        english_count += 1
            except Exception:
                pass

    print("\n" + "═" * 60)
    print("  تحليل البيانات الحالية")
    print("═" * 60)
    print(f"  إجمالي السجلات: {total_records}")
    print(f"  عربية:          {arabic_count}")
    print(f"  إنجليزية:       {english_count}")
    print(f"  إجمالي الكلمات: {total_words:,}")
    print(f"  Tokens تقريبي:  {int(total_words * 1.3):,}")
    print(f"  للتدريب الجيد:  يُنصح بـ 1,000,000+ token")
    delta = max(0, 1000 - total_records)
    print(f"  يحتاج:          {delta} سجل إضافي على الأقل")
    print("═" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="توسيع مصادر بيانات Hajeen Platform")
    parser.add_argument("--add-all", action="store_true", help="إضافة جميع المصادر")
    parser.add_argument("--language", default="all", choices=["all", "ar", "en"])
    parser.add_argument("--analyze", action="store_true", help="تحليل البيانات الحالية")
    parser.add_argument("--stats", action="store_true", help="عرض المصادر الحالية")
    args = parser.parse_args()

    print("\n" + "═" * 60)
    print("  📊  Hajeen Platform — Data Source Expander")
    print("═" * 60)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    if args.analyze:
        loop.run_until_complete(analyze_data())
    elif args.stats:
        loop.run_until_complete(show_current_stats())
    elif args.add_all:
        loop.run_until_complete(expand_sources(args.language))
    else:
        loop.run_until_complete(analyze_data())
        print("  استخدم --add-all لإضافة المصادر")
        print("  استخدم --analyze لتحليل البيانات\n")


if __name__ == "__main__":
    main()
