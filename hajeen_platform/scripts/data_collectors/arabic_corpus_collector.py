"""
arabic_corpus_collector.py — جامع المدونة العربية الشاملة
يجلب نصوصاً عربية من مصادر متعددة متخصصة ومتنوعة
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

ARABIC_SOURCES = {
    "oscar_arabic": {
        "dataset_id": "oscar-corpus/OSCAR-2301",
        "config": "ar",
        "split": "train",
        "text_field": "content",
        "description": "OSCAR — نصوص عربية من Common Crawl",
    },
    "arabic_billion_words": {
        "dataset_id": "acl-anthology/arabicnlp",
        "split": "train",
        "text_field": "text",
        "description": "مليار كلمة عربية",
    },
    "cc_100_arabic": {
        "dataset_id": "cc100",
        "config": "ar",
        "split": "train",
        "text_field": "text",
        "description": "CC-100 Arabic",
    },
    "arabic_poetry": {
        "dataset_id": "arbml/ashaar",
        "split": "train",
        "text_field": "poem",
        "description": "ديوان الشعر العربي",
    },
    "quran_dataset": {
        "dataset_id": "aryoyudanta/quran",
        "split": "train",
        "text_field": "arabic",
        "description": "القرآن الكريم",
    },
    "arabic_news": {
        "dataset_id": "saradhix/arabic_news",
        "split": "train",
        "text_field": "text",
        "description": "أخبار عربية",
    },
}


class ArabicCorpusCollector:
    """
    جامع شامل للمدونة العربية من مصادر متعددة.
    يدعم التنظيف والتطبيع والتصنيف التلقائي.
    """

    ARABIC_UNICODE_RANGE = re.compile(r"[\u0600-\u06FF]")
    MIN_ARABIC_RATIO = 0.4
    MIN_TEXT_LENGTH = 100

    def __init__(
        self,
        sources: Optional[List[str]] = None,
        max_samples: int = 100_000,
        upload_to_hf: bool = True,
        normalize: bool = True,
    ):
        self.sources = sources or ["oscar_arabic", "cc_100_arabic"]
        self.max_samples = max_samples
        self.upload_to_hf = upload_to_hf
        self.normalize = normalize

    def _normalize_arabic(self, text: str) -> str:
        """تطبيع النص العربي."""
        text = re.sub(r"[أإآا]", "ا", text)
        text = re.sub(r"[ىي]", "ي", text)
        text = re.sub(r"ة", "ه", text)
        text = re.sub(r"[\u064B-\u065F]", "", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _is_arabic_text(self, text: str) -> bool:
        """التحقق من أن النص عربي بنسبة كافية."""
        arabic_count = len(self.ARABIC_UNICODE_RANGE.findall(text))
        total = len(text.replace(" ", ""))
        if total == 0:
            return False
        ratio = arabic_count / total
        return ratio >= self.MIN_ARABIC_RATIO

    def _clean_arabic(self, text: str) -> str:
        """تنظيف شامل للنص العربي."""
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"[^\u0600-\u06FF\u0750-\u077F\s\d\.\,\!\?\(\)\-\:]", " ", text)
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        if self.normalize:
            text = self._normalize_arabic(text)

        return text

    def _classify_content_type(self, text: str) -> str:
        """تصنيف نوع المحتوى."""
        if re.search(r"بسم الله|قال الله|سورة|آية", text):
            return "religious"
        if re.search(r"فعل|مفعول|نحو|صرف|بلاغة", text):
            return "linguistic"
        if re.search(r"[\?\؟]", text) and len(text) < 500:
            return "qa"
        if len(text.split("\n")) > 5 and len(text) < 2000:
            return "poetry"
        return "general"

    def collect_source(self, source_name: str) -> List[Dict]:
        """جمع مصدر عربي محدد."""
        from datasets import load_dataset

        cfg = ARABIC_SOURCES.get(source_name)
        if not cfg:
            logger.warning(f"⚠️  مصدر غير معروف: {source_name}")
            return []

        logger.info(f"🌙 جمع عربي من: {source_name} — {cfg['description']}")

        try:
            kwargs: Dict[str, Any] = {
                "path": cfg["dataset_id"],
                "split": cfg["split"],
                "streaming": True,
                "trust_remote_code": True,
            }
            if "config" in cfg:
                kwargs["name"] = cfg["config"]

            ds = load_dataset(**kwargs)
        except Exception as e:
            logger.error(f"❌ فشل تحميل {source_name}: {e}")
            return []

        records = []
        for sample in ds:
            if len(records) >= self.max_samples:
                break

            raw = sample.get(cfg["text_field"], "")
            if not raw or len(raw) < self.MIN_TEXT_LENGTH:
                continue

            text = self._clean_arabic(raw)
            if not text or not self._is_arabic_text(text):
                continue

            content_type = self._classify_content_type(text)

            records.append({
                "text": text,
                "source": source_name,
                "language": "ar",
                "content_type": content_type,
                "word_count": len(text.split()),
                "char_count": len(text),
                "description": cfg["description"],
            })

            if len(records) % 5000 == 0:
                logger.info(f"  ✓ {len(records)} نص عربي من {source_name}")

        logger.info(f"✅ {source_name}: {len(records)} نص عربي نظيف")
        return records

    def collect_all(self) -> List[Dict]:
        """جمع جميع المصادر العربية."""
        all_records: List[Dict] = []
        stats: Dict[str, int] = {}

        for source in self.sources:
            records = self.collect_source(source)
            stats[source] = len(records)
            all_records.extend(records)

        logger.info("📊 إحصائيات المدونة العربية:")
        for src, count in stats.items():
            logger.info(f"  {src}: {count:,} نص")
        logger.info(f"  الإجمالي: {len(all_records):,} نص")

        return all_records

    def collect_and_upload(self) -> Dict[str, Any]:
        """جمع المدونة العربية ورفعها."""
        records = self.collect_all()
        if not records or not self.upload_to_hf:
            return {"count": len(records)}

        try:
            from cloud.hf_client import HFClient
            from cloud.dataset_manager import DatasetManager
            client = HFClient()
            dm = DatasetManager(hf_client=client)
            url = dm.upload_cleaned_dataset(
                data=records, name="arabic_corpus", source="arabic"
            )
            return {"count": len(records), "url": url}
        except Exception as e:
            logger.error(f"❌ فشل رفع المدونة العربية: {e}")
            return {"count": len(records), "error": str(e)}


def main():
    logging.basicConfig(level=logging.INFO)
    collector = ArabicCorpusCollector(
        sources=["oscar_arabic", "arabic_poetry"],
        max_samples=50_000,
        upload_to_hf=True,
    )
    result = collector.collect_and_upload()
    print(f"\n📊 نتيجة المدونة العربية: {result}")


if __name__ == "__main__":
    main()
