"""
web_crawler.py — زاحف الويب
يجمع نصوصاً من الويب مع احترام robots.txt، التنظيف، كشف اللغة، ورفع النتائج
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class WebCrawler:
    """
    زاحف ويب أخلاقي مع:
    - احترام robots.txt
    - تنظيف HTML
    - كشف اللغة
    - إزالة التكرار
    - رفع تلقائي إلى HuggingFace
    """

    def __init__(
        self,
        seed_urls: Optional[List[str]] = None,
        max_pages: int = 1_000,
        delay: float = 1.0,
        upload_to_hf: bool = True,
        languages: Optional[List[str]] = None,
    ):
        self.seed_urls = seed_urls or self._default_arabic_seeds()
        self.max_pages = max_pages
        self.delay = delay
        self.upload_to_hf = upload_to_hf
        self.target_languages = languages or ["ar", "en"]
        self._visited: Set[str] = set()
        self._hashes: Set[str] = set()

    def _default_arabic_seeds(self) -> List[str]:
        """مواقع عربية افتراضية للزحف."""
        return [
            "https://ar.wikipedia.org/wiki/%D9%85%D8%A8%D8%A7%D8%AF%D8%B1%D8%A9",
            "https://www.aljazeera.net/",
            "https://arabic.rt.com/",
        ]

    def _is_allowed_by_robots(self, url: str) -> bool:
        """التحقق من robots.txt."""
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        try:
            rp.set_url(robots_url)
            rp.read()
            return rp.can_fetch("*", url)
        except Exception:
            return True

    def _extract_text_from_html(self, html: str) -> str:
        """استخراج النص من HTML."""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n")
        except ImportError:
            text = re.sub(r"<[^>]+>", "", html)

        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        return text.strip()

    def _detect_language(self, text: str) -> str:
        """كشف اللغة بطريقة بسيطة."""
        arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
        total_chars = len(text.replace(" ", ""))
        if total_chars == 0:
            return "unknown"
        arabic_ratio = arabic_chars / total_chars
        if arabic_ratio > 0.3:
            return "ar"
        return "en"

    def _is_duplicate(self, text: str) -> bool:
        """كشف المحتوى المكرر."""
        fingerprint = hashlib.md5(text[:500].encode()).hexdigest()
        if fingerprint in self._hashes:
            return True
        self._hashes.add(fingerprint)
        return False

    def _fetch_page(self, url: str) -> Optional[str]:
        """جلب صفحة ويب."""
        try:
            import requests
            headers = {
                "User-Agent": "HajeenBot/1.0 (research; hajeen-platform)",
                "Accept-Language": "ar,en;q=0.9",
            }
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                return resp.text
        except Exception as e:
            logger.debug(f"فشل جلب {url}: {e}")
        return None

    def crawl_url(self, url: str) -> Optional[Dict]:
        """زحف صفحة واحدة وإرجاع البيانات المنظفة."""
        if url in self._visited:
            return None
        self._visited.add(url)

        if not self._is_allowed_by_robots(url):
            logger.debug(f"🚫 robots.txt: {url}")
            return None

        html = self._fetch_page(url)
        if not html:
            return None

        text = self._extract_text_from_html(html)
        if len(text) < 200:
            return None

        if self._is_duplicate(text):
            return None

        lang = self._detect_language(text)
        if lang not in self.target_languages:
            return None

        time.sleep(self.delay)

        return {
            "url": url,
            "text": text,
            "language": lang,
            "source": "web_crawl",
            "word_count": len(text.split()),
            "char_count": len(text),
        }

    def crawl(self) -> List[Dict]:
        """تنفيذ الزحف الكامل."""
        logger.info(f"🕷️  بدء الزحف — {len(self.seed_urls)} بذرة، حد: {self.max_pages}")
        records = []
        queue = list(self.seed_urls)

        while queue and len(records) < self.max_pages:
            url = queue.pop(0)
            record = self.crawl_url(url)
            if record:
                records.append(record)
                if len(records) % 100 == 0:
                    logger.info(f"  ✓ {len(records)} صفحة زُحفت")

        logger.info(f"✅ انتهى الزحف: {len(records)} صفحة نظيفة")
        return records

    def crawl_and_upload(self) -> Dict[str, Any]:
        """زحف ورفع تلقائي."""
        records = self.crawl()
        if not records or not self.upload_to_hf:
            return {"count": len(records)}

        try:
            from cloud.hf_client import HFClient
            from cloud.dataset_manager import DatasetManager
            client = HFClient()
            dm = DatasetManager(hf_client=client)
            url = dm.upload_cleaned_dataset(
                data=records, name="web_crawl", source="web"
            )
            return {"count": len(records), "url": url}
        except Exception as e:
            logger.error(f"❌ فشل الرفع: {e}")
            return {"count": len(records), "error": str(e)}


def main():
    logging.basicConfig(level=logging.INFO)
    crawler = WebCrawler(max_pages=500, upload_to_hf=True)
    result = crawler.crawl_and_upload()
    print(f"\n📊 النتيجة: {result}")


if __name__ == "__main__":
    main()
