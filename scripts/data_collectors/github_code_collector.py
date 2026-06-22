"""
github_code_collector.py — جمع كود برمجي من GitHub عبر HuggingFace
يجلب مجموعات كود برمجي من datasets موجودة ويرفعها لـ Hajeen
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

SUPPORTED_LANGUAGES = [
    "python", "javascript", "typescript", "java",
    "c", "cpp", "go", "rust", "bash", "sql",
]


class GithubCodeCollector:
    """
    جامع الكود البرمجي.
    يستخدم CodeParrot / The Stack من HuggingFace.
    """

    CODE_DATASETS = {
        "python": ("codeparrot/github-code", "Python"),
        "javascript": ("codeparrot/github-code", "JavaScript"),
        "java": ("codeparrot/github-code", "Java"),
        "cpp": ("codeparrot/github-code", "C++"),
        "go": ("codeparrot/github-code", "Go"),
    }

    def __init__(
        self,
        languages: Optional[List[str]] = None,
        max_samples_per_lang: int = 10_000,
        min_code_length: int = 100,
        max_code_length: int = 8_192,
        upload_to_hf: bool = True,
    ):
        self.languages = languages or ["python", "javascript"]
        self.max_samples_per_lang = max_samples_per_lang
        self.min_code_length = min_code_length
        self.max_code_length = max_code_length
        self.upload_to_hf = upload_to_hf

    def _clean_code(self, code: str) -> str:
        """تنظيف الكود البرمجي."""
        code = code.replace("\r\n", "\n").replace("\r", "\n")
        code = re.sub(r"\n{4,}", "\n\n\n", code)
        return code.strip()

    def _is_valid_code(self, code: str) -> bool:
        """التحقق من صلاحية الكود."""
        if len(code) < self.min_code_length:
            return False
        if len(code) > self.max_code_length:
            return False
        lines = code.split("\n")
        non_empty = [l for l in lines if l.strip()]
        if len(non_empty) < 5:
            return False
        return True

    def _calculate_quality_score(self, code: str, lang: str) -> float:
        """حساب درجة جودة الكود (0-1)."""
        score = 0.5
        if "def " in code or "class " in code or "function " in code:
            score += 0.1
        comment_ratio = len([l for l in code.split("\n") if l.strip().startswith(("#", "//", "/*", "*"))]) / max(len(code.split("\n")), 1)
        if 0.05 < comment_ratio < 0.4:
            score += 0.1
        if len(code) > 500:
            score += 0.1
        return min(score, 1.0)

    def collect_language(self, lang: str) -> List[Dict]:
        """جمع كود لغة برمجية محددة."""
        from datasets import load_dataset

        dataset_id, lang_filter = self.CODE_DATASETS.get(
            lang, ("codeparrot/github-code", lang.capitalize())
        )

        logger.info(f"💻 جمع كود {lang} من {dataset_id}")

        try:
            ds = load_dataset(
                dataset_id,
                languages=[lang_filter],
                split="train",
                streaming=True,
                trust_remote_code=True,
            )
        except Exception as e:
            logger.warning(f"⚠️  فشل تحميل {dataset_id}/{lang}: {e} — محاولة بديل")
            try:
                ds = load_dataset(
                    "bigcode/the-stack-dedup",
                    data_dir=f"data/{lang}",
                    split="train",
                    streaming=True,
                    trust_remote_code=True,
                )
            except Exception as e2:
                logger.error(f"❌ فشل كلا المصدرين لـ {lang}: {e2}")
                return []

        records = []
        for sample in ds:
            if len(records) >= self.max_samples_per_lang:
                break

            code = self._clean_code(
                sample.get("code", "") or sample.get("content", "")
            )
            if not self._is_valid_code(code):
                continue

            records.append({
                "text": code,
                "language": lang,
                "source": "github_code",
                "repo_name": sample.get("repo_name", ""),
                "path": sample.get("path", ""),
                "license": sample.get("license", ""),
                "quality_score": self._calculate_quality_score(code, lang),
                "char_count": len(code),
                "line_count": len(code.split("\n")),
            })

            if len(records) % 1000 == 0:
                logger.info(f"  ✓ {len(records)} ملف {lang}...")

        logger.info(f"✅ {lang}: {len(records)} ملف كود")
        return records

    def collect_and_upload(self) -> Dict[str, Any]:
        """جمع كود جميع اللغات ورفعه."""
        results: Dict[str, Any] = {}

        for lang in self.languages:
            records = self.collect_language(lang)
            if not records:
                continue

            if self.upload_to_hf:
                try:
                    from cloud.hf_client import HFClient
                    from cloud.dataset_manager import DatasetManager
                    client = HFClient()
                    dm = DatasetManager(hf_client=client)
                    url = dm.upload_cleaned_dataset(
                        data=records,
                        name=f"code_{lang}",
                        source="github_code",
                    )
                    results[lang] = {"count": len(records), "url": url}
                except Exception as e:
                    logger.error(f"❌ فشل رفع كود {lang}: {e}")
                    results[lang] = {"count": len(records), "error": str(e)}
            else:
                results[lang] = {"count": len(records)}

        return results


def main():
    logging.basicConfig(level=logging.INFO)
    collector = GithubCodeCollector(
        languages=["python", "javascript"],
        max_samples_per_lang=5_000,
        upload_to_hf=True,
    )
    results = collector.collect_and_upload()
    print("\n📊 نتائج جمع الكود:")
    for lang, val in results.items():
        print(f"  {lang}: {val}")


if __name__ == "__main__":
    main()
