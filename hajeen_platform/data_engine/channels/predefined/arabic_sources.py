"""
Arabic News Sources — مصادر الأخبار العربية المُعرَّفة مسبقاً.

تشمل قنوات RSS عربية وإنجليزية لتوسيع بيانات التدريب.
"""
from __future__ import annotations

from typing import List, Dict

ARABIC_RSS_SOURCES: List[Dict] = [
    # ── أخبار التقنية العربية ──────────────────────────────────────────
    {
        "name": "عرب هاردوير",
        "url": "https://www.arabhardware.net/feed/",
        "language": "ar",
        "category": "technology",
        "country": "sa",
    },
    {
        "name": "تك عربي",
        "url": "https://www.tech-wd.com/wd/feed/",
        "language": "ar",
        "category": "technology",
        "country": "jo",
    },
    {
        "name": "مدى مصر تقنية",
        "url": "https://feeds.feedburner.com/masrawy-technology",
        "language": "ar",
        "category": "technology",
        "country": "eg",
    },
    # ── أخبار عامة ────────────────────────────────────────────────────
    {
        "name": "BBC Arabic",
        "url": "https://feeds.bbci.co.uk/arabic/rss.xml",
        "language": "ar",
        "category": "general",
        "country": "int",
    },
    {
        "name": "France24 Arabic",
        "url": "https://www.france24.com/ar/rss",
        "language": "ar",
        "category": "general",
        "country": "int",
    },
    {
        "name": "RT Arabic",
        "url": "https://arabic.rt.com/rss/",
        "language": "ar",
        "category": "general",
        "country": "int",
    },
    {
        "name": "Al Jazeera Arabic",
        "url": "https://www.aljazeera.net/xml/rss/all.xml",
        "language": "ar",
        "category": "general",
        "country": "qa",
    },
    # ── اقتصاد وأعمال ────────────────────────────────────────────────
    {
        "name": "Al-Iqtisadi",
        "url": "https://www.al-iqtisadi.com/feed/",
        "language": "ar",
        "category": "economy",
        "country": "sa",
    },
]

ENGLISH_RSS_SOURCES: List[Dict] = [
    {
        "name": "TechCrunch",
        "url": "https://techcrunch.com/feed/",
        "language": "en",
        "category": "technology",
    },
    {
        "name": "MIT Technology Review",
        "url": "https://www.technologyreview.com/topnews.rss",
        "language": "en",
        "category": "ai",
    },
    {
        "name": "The Verge",
        "url": "https://www.theverge.com/rss/index.xml",
        "language": "en",
        "category": "technology",
    },
    {
        "name": "Hacker News",
        "url": "https://hnrss.org/frontpage",
        "language": "en",
        "category": "technology",
    },
    {
        "name": "VentureBeat AI",
        "url": "https://venturebeat.com/category/ai/feed/",
        "language": "en",
        "category": "ai",
    },
    {
        "name": "Reuters Technology",
        "url": "https://feeds.reuters.com/reuters/technologyNews",
        "language": "en",
        "category": "technology",
    },
]

ALL_SOURCES = ARABIC_RSS_SOURCES + ENGLISH_RSS_SOURCES


def get_sources_by_language(lang: str) -> List[Dict]:
    return [s for s in ALL_SOURCES if s.get("language") == lang]


def get_sources_by_category(category: str) -> List[Dict]:
    return [s for s in ALL_SOURCES if s.get("category") == category]


def get_all_source_urls() -> List[str]:
    return [s["url"] for s in ALL_SOURCES]
