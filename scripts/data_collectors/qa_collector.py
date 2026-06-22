"""
qa_collector.py — جامع بيانات Question & Answer
يجلب datasets QA عربية وإنجليزية من HuggingFace ويرفعها للمشروع
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


QA_SOURCES = {
    "arabic_qa": {
        "dataset_id": "wissamantoun/arabic-nlp-benchmark",
        "split": "train",
        "q_field": "question",
        "a_field": "answer",
        "lang": "ar",
    },
    "squad_en": {
        "dataset_id": "rajpurkar/squad",
        "split": "train",
        "q_field": "question",
        "a_field": "answers",
        "lang": "en",
    },
    "mlqa_ar": {
        "dataset_id": "facebook/mlqa",
        "config": "mlqa.ar.ar",
        "split": "train",
        "q_field": "question",
        "a_field": "answers",
        "lang": "ar",
    },
    "mlqa_en": {
        "dataset_id": "facebook/mlqa",
        "config": "mlqa.en.en",
        "split": "train",
        "q_field": "question",
        "a_field": "answers",
        "lang": "en",
    },
    "arabic_poetry": {
        "dataset_id": "arbml/ashaar",
        "split": "train",
        "q_field": None,
        "a_field": "poem",
        "lang": "ar",
    },
}


class QACollector:
    """
    جامع بيانات QA متعدد المصادر.
    """

    def __init__(
        self,
        sources: Optional[List[str]] = None,
        max_samples: int = 50_000,
        upload_to_hf: bool = True,
    ):
        self.sources = sources or list(QA_SOURCES.keys())
        self.max_samples = max_samples
        self.upload_to_hf = upload_to_hf

    def _extract_answer(self, answer_field: Any) -> str:
        """استخراج الإجابة بصيغ مختلفة."""
        if isinstance(answer_field, str):
            return answer_field
        if isinstance(answer_field, dict):
            texts = answer_field.get("text", [])
            if texts:
                return texts[0] if isinstance(texts, list) else texts
        if isinstance(answer_field, list):
            return answer_field[0] if answer_field else ""
        return str(answer_field)

    def _clean_text(self, text: str) -> str:
        """تنظيف النص."""
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _build_qa_record(
        self,
        question: Optional[str],
        answer: str,
        context: Optional[str],
        source: str,
        lang: str,
    ) -> Dict:
        """بناء سجل QA موحّد."""
        record: Dict[str, Any] = {
            "source": source,
            "language": lang,
            "type": "qa",
        }
        if question:
            record["question"] = self._clean_text(question)
            record["answer"] = self._clean_text(answer)
            record["text"] = f"سؤال: {record['question']}\nإجابة: {record['answer']}"
        else:
            record["text"] = self._clean_text(answer)

        if context:
            record["context"] = self._clean_text(context)

        return record

    def collect_source(self, source_name: str) -> List[Dict]:
        """جمع dataset مصدر واحد."""
        from datasets import load_dataset

        cfg = QA_SOURCES.get(source_name)
        if not cfg:
            logger.warning(f"⚠️  مصدر غير معروف: {source_name}")
            return []

        logger.info(f"❓ جمع QA من: {source_name} ({cfg['dataset_id']})")

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

            q_field = cfg.get("q_field")
            a_field = cfg.get("a_field")

            question = self._clean_text(sample.get(q_field, "")) if q_field else None
            answer_raw = sample.get(a_field, "")
            answer = self._extract_answer(answer_raw)
            context = sample.get("context", None)

            if not answer or len(answer) < 5:
                continue

            record = self._build_qa_record(
                question=question,
                answer=answer,
                context=context,
                source=source_name,
                lang=cfg["lang"],
            )
            records.append(record)

        logger.info(f"✅ {source_name}: {len(records)} سجل QA")
        return records

    def collect_all(self) -> List[Dict]:
        """جمع جميع مصادر QA."""
        all_records = []
        for source in self.sources:
            records = self.collect_source(source)
            all_records.extend(records)
        logger.info(f"📊 إجمالي QA: {len(all_records)} سجل")
        return all_records

    def collect_and_upload(self) -> Dict[str, Any]:
        """جمع ورفع QA datasets."""
        records = self.collect_all()
        if not records:
            return {"count": 0}

        if not self.upload_to_hf:
            return {"count": len(records)}

        try:
            from cloud.hf_client import HFClient
            from cloud.dataset_manager import DatasetManager
            client = HFClient()
            dm = DatasetManager(hf_client=client)
            url = dm.upload_cleaned_dataset(
                data=records, name="qa_dataset", source="qa"
            )
            return {"count": len(records), "url": url}
        except Exception as e:
            logger.error(f"❌ فشل رفع QA: {e}")
            return {"count": len(records), "error": str(e)}


def main():
    logging.basicConfig(level=logging.INFO)
    collector = QACollector(
        sources=["mlqa_ar", "mlqa_en"],
        max_samples=10_000,
        upload_to_hf=True,
    )
    result = collector.collect_and_upload()
    print(f"\n📊 نتيجة QA: {result}")


if __name__ == "__main__":
    main()
