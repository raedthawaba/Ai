"""Reddit Connector — section 4.9.

Fetches posts from Reddit using the public JSON API (no OAuth required).
Supports:
- subreddit posts (hot / new / top / rising)
- search across subreddits
- comment metadata (author, score, count) without fetching individual comments
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.schemas.article import Article, ArticleMetadata
from shared.utils.datetime_utils import utc_now
from shared.utils.id_generator import generate_article_id
from .base_connector import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

_REDDIT_BASE = "https://www.reddit.com"
_JSON_SUFFIX = ".json"


class RedditConnector(BaseConnector):
    """Connector for Reddit's public JSON API (no authentication required).

    Reddit's public API does not require credentials for read-only access.
    The User-Agent header is the only requirement to avoid rate-limiting.

    Parameters
    ----------
    source_id:
        Identifier attached to every generated Article's metadata.
    requests_per_second:
        Rate limit (Reddit public API guideline: < 1 req/s without OAuth).
    """

    def __init__(
        self,
        source_id: str = "reddit",
        requests_per_second: float = 0.5,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            base_url=_REDDIT_BASE,
            timeout=timeout,
            max_retries=max_retries,
            requests_per_second=requests_per_second,
        )
        self._headers["User-Agent"] = "HajeenBot/1.0 (data collection; +https://hajeen.ai)"
        self._headers["Accept"] = "application/json"
        self.source_id = source_id

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> None:
        """Reddit public JSON API needs no authentication."""
        self._authenticated = True
        logger.info("RedditConnector.authenticate: public API — no token required")

    async def fetch(
        self,
        subreddit: str = "technology",
        listing: str = "hot",
        limit: int = 25,
        max_pages: int = 3,
        **kwargs: Any,
    ) -> List[Article]:
        """Fetch posts from *subreddit* using *listing* sort.

        Parameters
        ----------
        subreddit:
            Subreddit name without the ``r/`` prefix.
        listing:
            One of ``hot``, ``new``, ``top``, ``rising``.
        limit:
            Posts per page (max 100).
        max_pages:
            Maximum pages to retrieve.

        Returns
        -------
        List of :class:`Article` objects.
        """
        return await self.fetch_subreddit_posts(
            subreddit=subreddit,
            listing=listing,
            limit=limit,
            max_pages=max_pages,
        )

    def validate_response(self, data: Any) -> bool:
        """Validate Reddit's JSON envelope structure."""
        if not isinstance(data, dict):
            return False
        kind = data.get("kind")
        listing_data = data.get("data")
        return kind == "Listing" and isinstance(listing_data, dict)

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    async def fetch_subreddit_posts(
        self,
        subreddit: str,
        listing: str = "hot",
        limit: int = 25,
        time_filter: str = "week",
        max_pages: int = 3,
    ) -> List[Article]:
        """Fetch posts from ``r/subreddit``.

        Parameters
        ----------
        subreddit:
            Subreddit name (without ``r/`` prefix).
        listing:
            Sorting: ``hot``, ``new``, ``top``, ``rising``.
        limit:
            Posts per page (1–100).
        time_filter:
            Applies only when ``listing="top"``.
            One of: ``hour``, ``day``, ``week``, ``month``, ``year``, ``all``.
        max_pages:
            Maximum pages to retrieve for pagination.

        Returns
        -------
        List of :class:`Article` objects.
        """
        if not self.is_authenticated:
            await self.authenticate()

        valid_listings = {"hot", "new", "top", "rising"}
        if listing not in valid_listings:
            listing = "hot"

        articles: List[Article] = []
        after: Optional[str] = None
        limit = min(max(1, limit), 100)

        for page in range(max_pages):
            path = f"/r/{subreddit}/{listing}{_JSON_SUFFIX}"
            params: Dict[str, Any] = {"limit": limit, "raw_json": 1}
            if listing == "top":
                params["t"] = time_filter
            if after:
                params["after"] = after

            try:
                data = await self.get(path, params=params)
            except ConnectorError as exc:
                logger.warning(
                    "fetch_subreddit_posts: r/%s page=%d error=%s",
                    subreddit,
                    page,
                    exc,
                )
                break

            if not self.validate_response(data):
                break

            posts = data["data"].get("children", [])
            batch = [
                self._post_to_article(p, subreddit=subreddit)
                for p in posts
                if isinstance(p, dict) and p.get("kind") == "t3"
            ]
            articles.extend(a for a in batch if a is not None)

            after = data["data"].get("after")
            if not after or len(posts) < limit:
                break

        logger.info(
            "fetch_subreddit_posts: r/%s listing=%s articles=%d",
            subreddit,
            listing,
            len(articles),
        )
        return articles

    async def search(
        self,
        query: str,
        subreddit: Optional[str] = None,
        sort: str = "relevance",
        time_filter: str = "month",
        limit: int = 25,
        max_pages: int = 2,
    ) -> List[Article]:
        """Search Reddit posts by keyword.

        Parameters
        ----------
        query:
            Search query string.
        subreddit:
            Restrict search to a specific subreddit (optional).
        sort:
            One of ``relevance``, ``hot``, ``top``, ``new``, ``comments``.
        time_filter:
            One of ``hour``, ``day``, ``week``, ``month``, ``year``, ``all``.
        limit:
            Results per page.
        max_pages:
            Maximum pages to retrieve.

        Returns
        -------
        List of :class:`Article` objects.
        """
        if not self.is_authenticated:
            await self.authenticate()

        base_path = (
            f"/r/{subreddit}/search{_JSON_SUFFIX}"
            if subreddit
            else f"/search{_JSON_SUFFIX}"
        )

        articles: List[Article] = []
        after: Optional[str] = None
        limit = min(max(1, limit), 100)

        for page in range(max_pages):
            params: Dict[str, Any] = {
                "q": query,
                "sort": sort,
                "t": time_filter,
                "limit": limit,
                "raw_json": 1,
            }
            if subreddit:
                params["restrict_sr"] = "on"
            if after:
                params["after"] = after

            try:
                data = await self.get(base_path, params=params)
            except ConnectorError as exc:
                logger.warning("search: query=%r page=%d error=%s", query, page, exc)
                break

            if not self.validate_response(data):
                break

            posts = data["data"].get("children", [])
            sr_name = subreddit or "all"
            batch = [
                self._post_to_article(p, subreddit=sr_name)
                for p in posts
                if isinstance(p, dict) and p.get("kind") == "t3"
            ]
            articles.extend(a for a in batch if a is not None)

            after = data["data"].get("after")
            if not after or len(posts) < limit:
                break

        logger.info(
            "search: query=%r subreddit=%s articles=%d",
            query,
            subreddit,
            len(articles),
        )
        return articles

    async def get_comment_metadata(
        self,
        post_id: str,
        subreddit: str,
    ) -> Dict[str, Any]:
        """Return comment-level metadata for a post without fetching full thread.

        Parameters
        ----------
        post_id:
            Reddit post ID (the alphanumeric after ``/comments/``).
        subreddit:
            Subreddit containing the post.

        Returns
        -------
        Dictionary with ``num_comments``, ``top_comment_score``,
        ``top_comment_author``, and ``post_url``.
        """
        if not self.is_authenticated:
            await self.authenticate()

        path = f"/r/{subreddit}/comments/{post_id}{_JSON_SUFFIX}"
        try:
            data = await self.get(path, params={"limit": 1, "depth": 1, "raw_json": 1})
        except ConnectorError as exc:
            logger.warning("get_comment_metadata: post=%s error=%s", post_id, exc)
            return {}

        if not isinstance(data, list) or len(data) < 1:
            return {}

        post_listing = data[0]
        if not self.validate_response(post_listing):
            return {}

        post_data = {}
        children = post_listing["data"].get("children", [])
        if children and children[0].get("kind") == "t3":
            post_data = children[0].get("data", {})

        metadata: Dict[str, Any] = {
            "num_comments": post_data.get("num_comments", 0),
            "post_url": f"https://www.reddit.com{post_data.get('permalink', '')}",
            "top_comment_score": None,
            "top_comment_author": None,
        }

        if len(data) > 1 and self.validate_response(data[1]):
            comment_children = data[1]["data"].get("children", [])
            if comment_children and comment_children[0].get("kind") == "t1":
                top = comment_children[0].get("data", {})
                metadata["top_comment_score"] = top.get("score")
                metadata["top_comment_author"] = top.get("author")

        return metadata

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------

    def _post_to_article(
        self, child: Dict[str, Any], subreddit: str
    ) -> Optional[Article]:
        """Convert a Reddit ``t3`` (link/post) child to an :class:`Article`."""
        post = child.get("data", {})
        title = (post.get("title") or "").strip()
        permalink = post.get("permalink", "")
        url = (
            post.get("url")
            if not (post.get("is_self") or post.get("url", "").startswith("https://www.reddit.com"))
            else f"https://www.reddit.com{permalink}"
        )

        if not title or not url:
            return None

        content = (post.get("selftext") or post.get("url") or title).strip()
        if not content:
            content = title

        author = post.get("author", "")
        flair = post.get("link_flair_text") or post.get("author_flair_text")
        tags = [f"r/{subreddit}"]
        if flair:
            tags.append(str(flair))
        if post.get("over_18"):
            tags.append("nsfw")

        score = post.get("score", 0)
        num_comments = post.get("num_comments", 0)

        try:
            return Article(
                id=generate_article_id(f"reddit_{post.get('id', url)}"),
                title=title,
                content=content,
                url=url,  # type: ignore[arg-type]
                published_at=_from_utc_timestamp(post.get("created_utc")),
                metadata=ArticleMetadata(
                    source_id=self.source_id,
                    author=author or None,
                    language="en",
                    tags=tags,
                    extra={
                        "subreddit": subreddit,
                        "score": score,
                        "num_comments": num_comments,
                        "post_id": post.get("id"),
                        "permalink": permalink,
                        "is_self": post.get("is_self", False),
                    },
                ),
            )
        except Exception as exc:
            logger.debug("_post_to_article: skip title=%r error=%s", title, exc)
            return None


def _from_utc_timestamp(ts: Any) -> datetime:
    """Convert a Unix timestamp (UTC) to a timezone-aware datetime."""
    if ts is None:
        return utc_now()
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return utc_now()
