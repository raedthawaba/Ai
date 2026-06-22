"""
wikipedia_collector.py — جمع مقالات Wikipedia
يجلب مقالات Wikipedia العربية والإنجليزية، ينظفها، ويرفعها إلى HuggingFace
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class WikipediaCollector:
    """
    جامع مقالات Wikipedia.
    يدعم العربية والإنجليزية والفرنسية وغيرها.
    """

    SUPPORTED_LANGUAGES = {
        "ar": "العربية",
        "en": "الإنجليزية",
        "fr": "الفرنسية",
        "de": "الألمانية",
        "es": "الإسبانية",
    }

    def __init__(
        self,
        languages: Optional[List[str]] = None,
        upload_to_hf: bool = True,
        max_samples: int = 100_000,
    ):
        self.languages = languages or ["ar", "en"]
        self.upload_to_hf = upload_to_hf
        self.max_samples = max_samples
        self._hf_client = None

    def _get_hf_client(self):
        if self._hf_client is None:
            from cloud.hf_client import HFClient
            self._hf_client = HFClient()
            self._hf_client.authenticate()
        return self._hf_client

    def _clean_text(self, text: str) -> str:
        """تنظيف نص Wikipedia."""
        text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
        text = re.sub(r"\{\{[^}]*\}\}", "", text)
        text = re.sub(r"={2,}.*?={2,}", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _is_valid_article(self, text: str, min_length: int = 200) -> bool:
        """التحقق من صلاحية المقال."""
        if len(text) < min_length:
            return False
        if text.count("#REDIRECT") > 0:
            return False
        return True

    def _detect_duplicates(self, records: List[Dict]) -> List[Dict]:
        """إزالة التكرار باستخدام hashing."""
        seen = set()
        unique = []
        for r in records:
            h = hash(r["text"][:200])
            if h not in seen:
                seen.add(h)
                unique.append(r)
        removed = len(records) - len(unique)
        if removed:
            logger.info(f"🗑️  أُزيل {removed} تكرار")
        return unique

    def collect(self, language: str = "ar") -> List[Dict]:
        """
        جمع مقالات Wikipedia لغة معينة.

        Args:
            language: رمز اللغة ('ar', 'en', ...)

        Returns:
            قائمة من السجلات المنظفة
        """
        from datasets import load_dataset

        lang_name = self.SUPPORTED_LANGUAGES.get(language, language)
        logger.info(f"📚 جمع Wikipedia [{lang_name}] — حتى {self.max_samples} مقال")

        try:
            dataset = load_dataset(
                "wikipedia",
                f"20220301.{language}",
                split="train",
                streaming=True,
                trust_remote_code=True,
            )
        except Exception as e:
            logger.error(f"❌ فشل تحميل Wikipedia/{language}: {e}")
            return []

        records = []
        for i, article in enumerate(dataset):
            if i >= self.max_samples:
                break

            text = self._clean_text(article.get("text", ""))
            if not self._is_valid_article(text):
                continue

            records.append({
                "id": article.get("id", str(i)),
                "title": article.get("title", ""),
                "text": text,
                "source": "wikipedia",
                "language": language,
                "url": article.get("url", ""),
                "word_count": len(text.split()),
            })

            if len(records) % 1000 == 0:
                logger.info(f"  ✓ {len(records)} مقال جُمع حتى الآن...")

        records = self._detect_duplicates(records)
        logger.info(f"✅ Wikipedia [{language}]: {len(records)} مقال نظيف")
        return records

    def collect_all_languages(self) -> Dict[str, List[Dict]]:
        """جمع Wikipedia لجميع اللغات المحددة."""
        all_data = {}
        for lang in self.languages:
            logger.info(f"\n{'='*50}")
            logger.info(f"🌍 معالجة اللغة: {lang}")
            all_data[lang] = self.collect(language=lang)
        return all_data

    def collect_and_upload(self) -> Dict[str, Any]:
        """جمع وتنظيف ورفع تلقائي."""
        results: Dict[str, Any] = {}
        all_data = self.collect_all_languages()

        if self.upload_to_hf:
            client = self._get_hf_client()
            from cloud.dataset_manager import DatasetManager
            dm = DatasetManager(hf_client=client)

            for lang, records in all_data.items():
                if not records:
                    continue
                try:
                    url = dm.upload_cleaned_dataset(
                        data=records,
                        name=f"wikipedia_{lang}",
                        source="wikipedia",
                    )
                    results[f"wikipedia_{lang}"] = {"count": len(records), "url": url}
                    logger.info(f"✅ Wikipedia/{lang} → {url}")
                except Exception as e:
                    logger.error(f"❌ فشل رفع Wikipedia/{lang}: {e}")
                    results[f"wikipedia_{lang}"] = {"count": len(records), "error": str(e)}

        return results


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    )
    collector = WikipediaCollector(
        languages=["ar", "en"],
        upload_to_hf=True,
        max_samples=50_000,
    )
    results = collector.collect_and_upload()
    print("\n📊 النتائج:")
    for key, val in results.items():
        print(f"  {key}: {val}")


if __name__ == "__main__":
    main()
