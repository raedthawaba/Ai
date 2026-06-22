"""Playwright Crawler — Phase 3 (Section 3.1).

Crawler للصفحات التي تعتمد JavaScript باستخدام Playwright.

المميزات:
- JavaScript rendering حقيقي
- Headless Chromium عبر Playwright
- timeout management (page + navigation)
- user-agent rotation
- rate limiting مدمج
- retry على فشل الجلب
- content-type detection
- graceful failures (لا crash عند فشل)
- CrawlResult موحّد
- Async non-blocking
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Optional Playwright import
# ─────────────────────────────────────────────────────────────────────────────

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    _PLAYWRIGHT_AVAILABLE = True
    logger.info("playwright_crawler: Playwright متاح")
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright_crawler: Playwright غير مثبّت — fallback لـ httpx")

# ─────────────────────────────────────────────────────────────────────────────
# User-Agent pool
# ─────────────────────────────────────────────────────────────────────────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PlaywrightCrawlerConfig:
    """إعدادات Playwright Crawler."""

    headless: bool = True
    timeout_ms: int = 30_000              # timeout الصفحة الكاملة
    navigation_timeout_ms: int = 20_000   # timeout التنقل
    wait_for_load: str = "networkidle"    # "load" | "domcontentloaded" | "networkidle"
    max_retries: int = 2
    retry_delay_s: float = 1.0
    requests_per_second: float = 1.0      # rate limit
    rotate_user_agents: bool = True
    extra_headers: Dict[str, str] = field(default_factory=dict)
    block_resources: List[str] = field(default_factory=lambda: ["image", "font", "media"])
    viewport_width: int = 1280
    viewport_height: int = 900
    max_concurrency: int = 3              # حد التوازي


# ─────────────────────────────────────────────────────────────────────────────
# Crawl Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CrawlResult:
    """نتيجة crawl لصفحة واحدة."""

    url: str
    success: bool
    html: str = ""
    text: str = ""
    title: str = ""
    status_code: int = 0
    content_type: str = ""
    elapsed_ms: float = 0.0
    retry_count: int = 0
    error: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    @property
    def word_count(self) -> int:
        return len(re.findall(r"\w+", self.text))

    @property
    def has_content(self) -> bool:
        return len(self.text.strip()) > 50


@dataclass
class BatchCrawlResult:
    """نتائج batch crawl."""

    total: int = 0
    success: int = 0
    failed: int = 0
    results: List[CrawlResult] = field(default_factory=list)
    total_elapsed_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.success / self.total if self.total else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Fallback HTTP crawler (عندما Playwright غير متاح)
# ─────────────────────────────────────────────────────────────────────────────

async def _httpx_fallback_crawl(url: str, cfg: PlaywrightCrawlerConfig) -> CrawlResult:
    """Fallback لـ httpx عندما Playwright غير متاح."""
    import httpx
    start = time.monotonic()

    ua = random.choice(_USER_AGENTS) if cfg.rotate_user_agents else _USER_AGENTS[0]
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5,ar;q=0.3",
        **cfg.extra_headers,
    }

    for attempt in range(cfg.max_retries + 1):
        try:
            async with httpx.AsyncClient(
                timeout=cfg.timeout_ms / 1000,
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = await client.get(url)

            elapsed_ms = (time.monotonic() - start) * 1000
            content_type = response.headers.get("content-type", "")

            # استخراج النص البسيط
            html = response.text
            from html.parser import HTMLParser
            class _TextParser(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self._parts = []
                    self._skip = False
                def handle_starttag(self, tag, attrs):
                    if tag in ("script", "style"):
                        self._skip = True
                def handle_endtag(self, tag):
                    if tag in ("script", "style"):
                        self._skip = False
                def handle_data(self, data):
                    if not self._skip and data.strip():
                        self._parts.append(data.strip())
                def get_text(self):
                    return " ".join(self._parts)

            parser = _TextParser()
            try:
                parser.feed(html)
                text = parser.get_text()
            except Exception:
                text = html[:5000]

            # استخراج العنوان
            title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else ""

            return CrawlResult(
                url=url,
                success=response.is_success,
                html=html,
                text=text,
                title=title,
                status_code=response.status_code,
                content_type=content_type,
                elapsed_ms=elapsed_ms,
                retry_count=attempt,
            )

        except Exception as exc:
            if attempt < cfg.max_retries:
                await asyncio.sleep(cfg.retry_delay_s * (attempt + 1))
                continue
            elapsed_ms = (time.monotonic() - start) * 1000
            return CrawlResult(
                url=url, success=False,
                elapsed_ms=elapsed_ms, retry_count=attempt,
                error=str(exc),
            )

    return CrawlResult(url=url, success=False, error="max_retries_exceeded")


# ─────────────────────────────────────────────────────────────────────────────
# PlaywrightCrawler
# ─────────────────────────────────────────────────────────────────────────────

class PlaywrightCrawler:
    """Crawler يعتمد Playwright لعرض JavaScript مع fallback لـ httpx.

    يُستخدم للصفحات التي تتطلب JavaScript rendering.

    Parameters
    ----------
    config:
        PlaywrightCrawlerConfig للتحكم في السلوك.
    """

    def __init__(self, config: Optional[PlaywrightCrawlerConfig] = None) -> None:
        self.config = config or PlaywrightCrawlerConfig()
        self._browser: Optional[object] = None
        self._playwright: Optional[object] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._rate_lock = asyncio.Lock()
        self._last_request_time: float = 0.0
        self._min_interval = 1.0 / max(self.config.requests_per_second, 0.1)

    # ─── Lifecycle ──────────────────────────────────────────────────────

    async def start(self) -> None:
        """تهيئة Playwright Browser."""
        if not _PLAYWRIGHT_AVAILABLE:
            logger.info("PlaywrightCrawler: Playwright غير متاح — fallback mode")
            return
        if self._browser:
            return
        try:
            self._playwright = await async_playwright().__aenter__()
            self._browser = await self._playwright.chromium.launch(
                headless=self.config.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            self._semaphore = asyncio.Semaphore(self.config.max_concurrency)
            logger.info("PlaywrightCrawler: browser started")
        except Exception as exc:
            logger.warning("PlaywrightCrawler: failed to start browser — %s", exc)
            self._browser = None

    async def close(self) -> None:
        """إغلاق Playwright Browser بشكل آمن."""
        if self._browser:
            try:
                await self._browser.close()
                logger.info("PlaywrightCrawler: browser closed")
            except Exception as exc:
                logger.warning("PlaywrightCrawler: error closing browser — %s", exc)
            finally:
                self._browser = None
        if self._playwright:
            try:
                await self._playwright.__aexit__(None, None, None)
            except Exception:
                pass
            finally:
                self._playwright = None

    # ─── Rate limiting ──────────────────────────────────────────────────

    async def _acquire_rate(self) -> None:
        async with self._rate_lock:
            now = time.monotonic()
            wait = self._min_interval - (now - self._last_request_time)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_time = time.monotonic()

    # ─── Core crawl ─────────────────────────────────────────────────────

    async def crawl(self, url: str) -> CrawlResult:
        """Crawl صفحة واحدة.

        Parameters
        ----------
        url:
            URL المستهدف.

        Returns
        -------
        CrawlResult مع HTML + text + title.
        """
        await self._acquire_rate()

        if not _PLAYWRIGHT_AVAILABLE or self._browser is None:
            logger.debug("PlaywrightCrawler.crawl: fallback url=%s", url)
            return await _httpx_fallback_crawl(url, self.config)

        sem = self._semaphore or asyncio.Semaphore(1)
        async with sem:
            return await self._playwright_crawl(url)

    async def _playwright_crawl(self, url: str) -> CrawlResult:
        """تنفيذ crawl فعلي باستخدام Playwright."""
        cfg = self.config
        start = time.monotonic()

        for attempt in range(cfg.max_retries + 1):
            context: Optional[object] = None
            page: Optional[object] = None
            try:
                ua = random.choice(_USER_AGENTS) if cfg.rotate_user_agents else _USER_AGENTS[0]
                context = await self._browser.new_context(
                    user_agent=ua,
                    viewport={"width": cfg.viewport_width, "height": cfg.viewport_height},
                    extra_http_headers=cfg.extra_headers,
                )

                page = await context.new_page()
                page.set_default_timeout(cfg.timeout_ms)
                page.set_default_navigation_timeout(cfg.navigation_timeout_ms)

                # Block unnecessary resources
                if cfg.block_resources:
                    async def _block_route(route):
                        if route.request.resource_type in cfg.block_resources:
                            await route.abort()
                        else:
                            await route.continue_()
                    await page.route("**/*", _block_route)

                response = await page.goto(
                    url,
                    wait_until=cfg.wait_for_load,
                    timeout=cfg.navigation_timeout_ms,
                )

                status_code = response.status if response else 0
                content_type = response.headers.get("content-type", "") if response else ""

                html = await page.content()
                text = await page.evaluate("() => document.body?.innerText || ''")
                title = await page.title()

                elapsed_ms = (time.monotonic() - start) * 1000

                return CrawlResult(
                    url=url,
                    success=200 <= status_code < 400 or status_code == 0,
                    html=html,
                    text=str(text or ""),
                    title=str(title or ""),
                    status_code=status_code,
                    content_type=content_type,
                    elapsed_ms=elapsed_ms,
                    retry_count=attempt,
                    metadata={"user_agent": ua},
                )

            except Exception as exc:
                logger.warning(
                    "PlaywrightCrawler: attempt=%d url=%s error=%s",
                    attempt, url, exc,
                )
                if attempt < cfg.max_retries:
                    await asyncio.sleep(cfg.retry_delay_s * (attempt + 1))
                    continue

                elapsed_ms = (time.monotonic() - start) * 1000
                return CrawlResult(
                    url=url, success=False,
                    elapsed_ms=elapsed_ms,
                    retry_count=attempt,
                    error=str(exc),
                )
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
                if context:
                    try:
                        await context.close()
                    except Exception:
                        pass

        return CrawlResult(url=url, success=False, error="max_retries_exceeded")

    # ─── Batch crawl ─────────────────────────────────────────────────────

    async def crawl_batch(self, urls: List[str]) -> BatchCrawlResult:
        """Crawl دُفعة من URLs بشكل متزامن.

        Parameters
        ----------
        urls:
            قائمة URLs.

        Returns
        -------
        BatchCrawlResult مع نتائج كل URL.
        """
        start = time.monotonic()
        results = await asyncio.gather(*[self.crawl(u) for u in urls])
        elapsed_ms = (time.monotonic() - start) * 1000

        batch = BatchCrawlResult(
            total=len(urls),
            results=list(results),
            total_elapsed_ms=elapsed_ms,
        )
        batch.success = sum(1 for r in results if r.success)
        batch.failed = batch.total - batch.success

        logger.info(
            "PlaywrightCrawler.crawl_batch: total=%d success=%d failed=%d elapsed=%.1fms",
            batch.total, batch.success, batch.failed, elapsed_ms,
        )
        return batch

    # ─── Context manager ─────────────────────────────────────────────────

    async def __aenter__(self) -> "PlaywrightCrawler":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()

    # ─── Helpers ─────────────────────────────────────────────────────────

    def detect_content_type(self, result: CrawlResult) -> str:
        """اكتشاف نوع المحتوى من headers أو HTML.

        Returns
        -------
        نوع المحتوى: "html" | "json" | "xml" | "pdf" | "unknown"
        """
        ct = result.content_type.lower()
        if "json" in ct:
            return "json"
        if "xml" in ct:
            return "xml"
        if "pdf" in ct:
            return "pdf"
        if "html" in ct or result.html.strip().startswith("<!"):
            return "html"
        return "unknown"

    def is_arabic_content(self, result: CrawlResult) -> bool:
        """هل المحتوى عربي؟"""
        arabic_chars = len(re.findall(r"[\u0600-\u06FF]", result.text))
        total_alpha = len(re.findall(r"[a-zA-Z\u0600-\u06FF]", result.text))
        return total_alpha > 0 and arabic_chars / total_alpha >= 0.4

    @staticmethod
    def validate_url(url: str) -> bool:
        """التحقق من صلاحية URL قبل الـ crawl."""
        try:
            parsed = urlparse(url)
            return bool(parsed.scheme in ("http", "https") and parsed.netloc)
        except Exception:
            return False
