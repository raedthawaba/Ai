"""GitHub Connector — section 4.8.

Fetches data from the GitHub REST API v3 and normalises results into
Article objects. Supports:
- repositories search / listing
- commits
- issues
- releases
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.schemas.article import Article, ArticleMetadata
from shared.utils.datetime_utils import utc_now
from shared.utils.id_generator import generate_article_id
from .base_connector import BaseConnector, ConnectorError

logger = logging.getLogger(__name__)

_GITHUB_BASE = "https://api.github.com"


class GitHubConnector(BaseConnector):
    """Connector for the GitHub REST API v3.

    Parameters
    ----------
    token:
        Personal access token (PAT) or ``None`` for unauthenticated requests.
        If ``None`` the ``GITHUB_TOKEN`` environment variable is read.
    source_id:
        Identifier attached to every Article's metadata.
    requests_per_second:
        Rate limit.  GitHub allows ~60 req/hour unauthenticated, ~5000
        authenticated.  Default is 0.5 req/s (safe for both tiers).
    """

    def __init__(
        self,
        token: Optional[str] = None,
        source_id: str = "github",
        requests_per_second: float = 0.5,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        super().__init__(
            base_url=_GITHUB_BASE,
            timeout=timeout,
            max_retries=max_retries,
            requests_per_second=requests_per_second,
        )
        self._token: Optional[str] = token or os.environ.get("GITHUB_TOKEN")
        self.source_id = source_id
        self._headers["Accept"] = "application/vnd.github+json"
        self._headers["X-GitHub-Api-Version"] = "2022-11-28"

    # ------------------------------------------------------------------
    # BaseConnector interface
    # ------------------------------------------------------------------

    async def authenticate(self) -> None:
        """Add Bearer token to headers when a token is available."""
        if self._token:
            self._headers["Authorization"] = f"Bearer {self._token}"
        self._authenticated = True
        logger.info(
            "GitHubConnector.authenticate: token=%s",
            "set" if self._token else "not set (unauthenticated)",
        )

    async def fetch(
        self,
        repo: Optional[str] = None,
        resource: str = "repositories",
        query: Optional[str] = None,
        max_pages: int = 3,
        **kwargs: Any,
    ) -> List[Article]:
        """Fetch GitHub data and return normalised Article objects.

        Parameters
        ----------
        repo:
            ``owner/repo`` string required for commit, issue, and release
            resources.
        resource:
            One of: ``repositories``, ``commits``, ``issues``, ``releases``.
        query:
            Search query used when ``resource="repositories"``.
        max_pages:
            Maximum result pages to retrieve.

        Returns
        -------
        List of :class:`Article` objects.
        """
        if not self.is_authenticated:
            await self.authenticate()

        dispatch = {
            "repositories": lambda: self.fetch_repositories(query=query or "language:python", max_pages=max_pages),
            "commits": lambda: self.fetch_commits(repo=repo or "", max_pages=max_pages),
            "issues": lambda: self.fetch_issues(repo=repo or "", max_pages=max_pages),
            "releases": lambda: self.fetch_releases(repo=repo or ""),
        }

        handler = dispatch.get(resource)
        if handler is None:
            raise ConnectorError(f"Unknown resource type: {resource!r}")
        return await handler()

    def validate_response(self, data: Any) -> bool:
        """Accept lists and dicts with common GitHub pagination patterns."""
        if isinstance(data, list):
            return True
        if isinstance(data, dict):
            return "items" in data or "commit" in data or "id" in data
        return False

    # ------------------------------------------------------------------
    # Resource-specific fetch methods
    # ------------------------------------------------------------------

    async def fetch_repositories(
        self,
        query: str = "language:python",
        sort: str = "stars",
        order: str = "desc",
        per_page: int = 30,
        max_pages: int = 3,
    ) -> List[Article]:
        """Search GitHub repositories.

        Parameters
        ----------
        query:
            GitHub search query string.
        sort:
            Sort field (``stars``, ``forks``, ``updated``).
        order:
            ``asc`` or ``desc``.
        per_page:
            Results per page (max 100).
        max_pages:
            Maximum pages to fetch.

        Returns
        -------
        List of repository Articles.
        """
        articles: List[Article] = []
        for page in range(1, max_pages + 1):
            params = {
                "q": query,
                "sort": sort,
                "order": order,
                "per_page": per_page,
                "page": page,
            }
            try:
                data = await self.get("/search/repositories", params=params)
            except ConnectorError as exc:
                logger.warning("fetch_repositories: page=%d error=%s", page, exc)
                break

            items = data.get("items", [])
            articles.extend(self._repo_to_article(r) for r in items if r)
            if len(items) < per_page:
                break

        logger.info("fetch_repositories: query=%r articles=%d", query, len(articles))
        return [a for a in articles if a is not None]

    async def fetch_commits(
        self,
        repo: str,
        branch: str = "main",
        per_page: int = 30,
        max_pages: int = 3,
    ) -> List[Article]:
        """Fetch recent commits for *repo*.

        Parameters
        ----------
        repo:
            ``owner/repo`` string.
        branch:
            Branch name (default ``main``).
        per_page:
            Results per page.
        max_pages:
            Maximum pages to retrieve.

        Returns
        -------
        List of commit Articles.
        """
        if not repo:
            return []

        articles: List[Article] = []
        for page in range(1, max_pages + 1):
            params = {"sha": branch, "per_page": per_page, "page": page}
            try:
                data = await self.get(f"/repos/{repo}/commits", params=params)
            except ConnectorError as exc:
                logger.warning("fetch_commits: repo=%s page=%d error=%s", repo, page, exc)
                break

            if not isinstance(data, list):
                break

            articles.extend(self._commit_to_article(c, repo=repo) for c in data)
            if len(data) < per_page:
                break

        logger.info("fetch_commits: repo=%s articles=%d", repo, len(articles))
        return [a for a in articles if a is not None]

    async def fetch_issues(
        self,
        repo: str,
        state: str = "open",
        per_page: int = 30,
        max_pages: int = 3,
    ) -> List[Article]:
        """Fetch issues for *repo*.

        Parameters
        ----------
        repo:
            ``owner/repo`` string.
        state:
            ``open``, ``closed``, or ``all``.
        per_page:
            Results per page.
        max_pages:
            Maximum pages.

        Returns
        -------
        List of issue Articles.
        """
        if not repo:
            return []

        articles: List[Article] = []
        for page in range(1, max_pages + 1):
            params = {"state": state, "per_page": per_page, "page": page}
            try:
                data = await self.get(f"/repos/{repo}/issues", params=params)
            except ConnectorError as exc:
                logger.warning("fetch_issues: repo=%s page=%d error=%s", repo, page, exc)
                break

            if not isinstance(data, list):
                break

            articles.extend(self._issue_to_article(i, repo=repo) for i in data)
            if len(data) < per_page:
                break

        logger.info("fetch_issues: repo=%s articles=%d", repo, len(articles))
        return [a for a in articles if a is not None]

    async def fetch_releases(
        self,
        repo: str,
        per_page: int = 10,
    ) -> List[Article]:
        """Fetch the latest releases for *repo*.

        Parameters
        ----------
        repo:
            ``owner/repo`` string.
        per_page:
            Maximum number of releases to return.

        Returns
        -------
        List of release Articles.
        """
        if not repo:
            return []

        try:
            data = await self.get(f"/repos/{repo}/releases", params={"per_page": per_page})
        except ConnectorError as exc:
            logger.error("fetch_releases: repo=%s error=%s", repo, exc)
            return []

        if not isinstance(data, list):
            return []

        articles = [self._release_to_article(r, repo=repo) for r in data]
        logger.info("fetch_releases: repo=%s articles=%d", repo, len(articles))
        return [a for a in articles if a is not None]

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------

    def _repo_to_article(self, raw: Dict[str, Any]) -> Optional[Article]:
        name = raw.get("full_name") or raw.get("name", "")
        url = raw.get("html_url") or raw.get("url", "")
        if not name or not url:
            return None

        description = raw.get("description") or f"GitHub repository: {name}"
        stars = raw.get("stargazers_count", 0)
        language = raw.get("language") or "unknown"

        try:
            return Article(
                id=generate_article_id(url),
                title=f"[Repo] {name}",
                content=description,
                url=url,  # type: ignore[arg-type]
                published_at=_parse_gh_date(raw.get("created_at")),
                metadata=ArticleMetadata(
                    source_id=self.source_id,
                    language="en",
                    tags=[language, "github", "repository"],
                    extra={"stars": stars, "forks": raw.get("forks_count", 0)},
                ),
            )
        except Exception as exc:
            logger.debug("_repo_to_article: skip %s error=%s", url, exc)
            return None

    def _commit_to_article(
        self, raw: Dict[str, Any], repo: str
    ) -> Optional[Article]:
        sha = raw.get("sha", "")[:8]
        url = raw.get("html_url", "")
        commit = raw.get("commit", {})
        message = commit.get("message", "").split("\n")[0].strip()
        author_info = commit.get("author", {})
        author = author_info.get("name", "")

        if not url or not message:
            return None

        try:
            return Article(
                id=generate_article_id(url),
                title=f"[Commit {sha}] {message}",
                content=commit.get("message", message),
                url=url,  # type: ignore[arg-type]
                published_at=_parse_gh_date(author_info.get("date")),
                metadata=ArticleMetadata(
                    source_id=self.source_id,
                    author=author or None,
                    language="en",
                    tags=["github", "commit", repo],
                    extra={"sha": raw.get("sha"), "repo": repo},
                ),
            )
        except Exception as exc:
            logger.debug("_commit_to_article: skip %s error=%s", url, exc)
            return None

    def _issue_to_article(
        self, raw: Dict[str, Any], repo: str
    ) -> Optional[Article]:
        number = raw.get("number", "")
        url = raw.get("html_url", "")
        title = (raw.get("title") or "").strip()
        body = (raw.get("body") or "").strip()
        user = raw.get("user", {}).get("login", "")
        labels = [lbl.get("name", "") for lbl in raw.get("labels", []) if isinstance(lbl, dict)]

        if not title or not url:
            return None

        try:
            return Article(
                id=generate_article_id(url),
                title=f"[Issue #{number}] {title}",
                content=body or title,
                url=url,  # type: ignore[arg-type]
                published_at=_parse_gh_date(raw.get("created_at")),
                metadata=ArticleMetadata(
                    source_id=self.source_id,
                    author=user or None,
                    language="en",
                    tags=["github", "issue", repo] + labels,
                    extra={"state": raw.get("state"), "repo": repo},
                ),
            )
        except Exception as exc:
            logger.debug("_issue_to_article: skip %s error=%s", url, exc)
            return None

    def _release_to_article(
        self, raw: Dict[str, Any], repo: str
    ) -> Optional[Article]:
        tag = raw.get("tag_name", "")
        url = raw.get("html_url", "")
        name = raw.get("name") or tag
        body = (raw.get("body") or "").strip()
        author = raw.get("author", {}).get("login", "")

        if not url:
            return None

        try:
            return Article(
                id=generate_article_id(url),
                title=f"[Release {tag}] {name}",
                content=body or f"Release {tag} of {repo}",
                url=url,  # type: ignore[arg-type]
                published_at=_parse_gh_date(raw.get("published_at") or raw.get("created_at")),
                metadata=ArticleMetadata(
                    source_id=self.source_id,
                    author=author or None,
                    language="en",
                    tags=["github", "release", repo, tag],
                    extra={"tag": tag, "prerelease": raw.get("prerelease", False)},
                ),
            )
        except Exception as exc:
            logger.debug("_release_to_article: skip %s error=%s", url, exc)
            return None


def _parse_gh_date(raw: Optional[str]) -> datetime:
    """Parse a GitHub ISO 8601 timestamp (``YYYY-MM-DDTHH:MM:SSZ``)."""
    if not raw:
        return utc_now()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return utc_now()
