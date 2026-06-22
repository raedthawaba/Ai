"""
books_collector.py — جامع الكتب والنصوص الطويلة
يجلب مجموعات الكتب العربية والإنجليزية من مصادر HuggingFace
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


BOOK_SOURCES = {
    "gutenberg_en": {
        "dataset_id": "storytracer/US-PD-Books",
        "split": "train",
        "text_field": "text",
        "lang": "en",
        "description": "مشروع Gutenberg — كتب إنجليزية قديمة متاحة للعموم",
    },
    "arabic_books": {
        "dataset_id": "arbml/CIINA",
        "split": "train",
        "text_field": "text",
        "lang": "ar",
        "description": "كتب عربية كلاسيكية",
    },
    "books3_sample": {
        "dataset_id": "the_pile_books3",
        "split": "train",
        "text_field": "text",
        "lang": "en",
        "description": "Books3 — كتب إنجليزية حديثة",
    },
}


class BooksCollector:
    """
    جامع الكتب والنصوص الطويلة من HuggingFace.
    """

    MIN_BOOK_LENGTH = 1_000
    MAX_CHUNK_SIZE = 4_096

    def __init__(
        self,
        sources: Optional[List[str]] = None,
        max_books: int = 10_000,
        chunk_books: bool = True,
        upload_to_hf: bool = True,
    ):
        self.sources = sources or ["gutenberg_en", "arabic_books"]
        self.max_books = max_books
        self.chunk_books = chunk_books
        self.upload_to_hf = upload_to_hf

    def _clean_book_text(self, text: str) -> str:
        """تنظيف نص الكتاب."""
        text = re.sub(r"-{3,}", "—", text)
        text = re.sub(r"\*{3,}", "", text)
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        text = re.sub(r"Project Gutenberg.*", "", text, flags=re.IGNORECASE | re.DOTALL)
        return text.strip()

    def _chunk_text(self, text: str, chunk_size: int = 2_048) -> List[str]:
        """تقسيم الكتاب إلى chunks."""
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i: i + chunk_size])
            if len(chunk) > 200:
                chunks.append(chunk)
        return chunks

    def collect_source(self, source_name: str) -> List[Dict]:
        """جمع مصدر كتب محدد."""
        from datasets import load_dataset

        cfg = BOOK_SOURCES.get(source_name)
        if not cfg:
            logger.warning(f"⚠️  مصدر غير معروف: {source_name}")
            return []

        logger.info(f"📖 جمع كتب من: {source_name} — {cfg['description']}")

        try:
            ds = load_dataset(
                cfg["dataset_id"],
                split=cfg["split"],
                streaming=True,
                trust_remote_code=True,
            )
        except Exception as e:
            logger.error(f"❌ فشل تحميل {source_name}: {e}")
            return []

        records = []
        book_count = 0

        for book in ds:
            if book_count >= self.max_books:
                break

            raw_text = book.get(cfg["text_field"], "")
            text = self._clean_book_text(raw_text)

            if len(text) < self.MIN_BOOK_LENGTH:
                continue

            book_count += 1

            if self.chunk_books:
                chunks = self._chunk_text(text)
                for i, chunk in enumerate(chunks):
                    records.append({
                        "text": chunk,
                        "source": source_name,
                        "language": cfg["lang"],
                        "type": "book_chunk",
                        "book_index": book_count,
                        "chunk_index": i,
                        "total_chunks": len(chunks),
                        "word_count": len(chunk.split()),
                    })
            else:
                records.append({
                    "text": text,
                    "source": source_name,
                    "language": cfg["lang"],
                    "type": "book",
                    "book_index": book_count,
                    "word_count": len(text.split()),
                    "char_count": len(text),
                })

            if book_count % 100 == 0:
                logger.info(f"  ✓ {book_count} كتاب، {len(records)} chunk")

        logger.info(f"✅ {source_name}: {book_count} كتاب → {len(records)} سجل")
        return records

    def collect_all(self) -> List[Dict]:
        """جمع جميع مصادر الكتب."""
        all_records = []
        for source in self.sources:
            records = self.collect_source(source)
            all_records.extend(records)
        logger.info(f"📚 إجمالي الكتب: {len(all_records)} سجل")
        return all_records

    def collect_and_upload(self) -> Dict[str, Any]:
        """جمع ورفع الكتب."""
        records = self.collect_all()
        if not records or not self.upload_to_hf:
            return {"count": len(records)}

        try:
            from cloud.hf_client import HFClient
            from cloud.dataset_manager import DatasetManager
            client = HFClient()
            dm = DatasetManager(hf_client=client)
            url = dm.upload_cleaned_dataset(
                data=records, name="books_dataset", source="books"
            )
            return {"count": len(records), "url": url}
        except Exception as e:
            logger.error(f"❌ فشل رفع الكتب: {e}")
            return {"count": len(records), "error": str(e)}


def main():
    logging.basicConfig(level=logging.INFO)
    collector = BooksCollector(
        sources=["gutenberg_en"],
        max_books=1_000,
        chunk_books=True,
        upload_to_hf=True,
    )
    result = collector.collect_and_upload()
    print(f"\n📊 نتيجة الكتب: {result}")


if __name__ == "__main__":
    main()
