"""Tests for GitHubConnector — section 4.8."""

from __future__ import annotations

import json
from datetime import timezone

import httpx
import pytest
import respx

from data_engine.ingestion.connectors.github_connector import (
    GitHubConnector,
    _parse_gh_date,
)
from data_engine.ingestion.connectors.base_connector import ConnectorError
from shared.schemas.article import Article


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_REPOS = [
    {
        "full_name": "openai/openai-python",
        "html_url": "https://github.com/openai/openai-python",
        "description": "The official Python library for the OpenAI API.",
        "stargazers_count": 15000,
        "forks_count": 2000,
        "language": "Python",
        "created_at": "2020-01-01T00:00:00Z",
    },
    {
        "full_name": "huggingface/transformers",
        "html_url": "https://github.com/huggingface/transformers",
        "description": "Transformers: State-of-the-art ML.",
        "stargazers_count": 120000,
        "forks_count": 24000,
        "language": "Python",
        "created_at": "2019-09-01T00:00:00Z",
    },
]

SAMPLE_COMMITS = [
    {
        "sha": "abc12345678",
        "html_url": "https://github.com/owner/repo/commit/abc12345",
        "commit": {
            "message": "Fix critical bug in parser\n\nExtended description.",
            "author": {"name": "Alice Dev", "date": "2024-05-20T09:00:00Z"},
        },
    },
    {
        "sha": "def98765432",
        "html_url": "https://github.com/owner/repo/commit/def98765",
        "commit": {
            "message": "Add new feature",
            "author": {"name": "Bob Coder", "date": "2024-05-19T15:00:00Z"},
        },
    },
]

SAMPLE_ISSUES = [
    {
        "number": 42,
        "html_url": "https://github.com/owner/repo/issues/42",
        "title": "Memory leak in data processor",
        "body": "Detailed reproduction steps here.",
        "state": "open",
        "user": {"login": "reporter_user"},
        "labels": [{"name": "bug"}, {"name": "high-priority"}],
        "created_at": "2024-05-18T12:00:00Z",
    },
]

SAMPLE_RELEASES = [
    {
        "tag_name": "v2.1.0",
        "name": "Version 2.1.0",
        "html_url": "https://github.com/owner/repo/releases/tag/v2.1.0",
        "body": "## Changelog\n- Feature A\n- Bug fix B",
        "author": {"login": "maintainer"},
        "published_at": "2024-05-15T10:00:00Z",
        "prerelease": False,
    },
]


def _gh_search_response(items: list) -> httpx.Response:
    return httpx.Response(
        200,
        content=json.dumps({"total_count": len(items), "items": items}).encode(),
    )


def _gh_list_response(items: list) -> httpx.Response:
    return httpx.Response(200, content=json.dumps(items).encode())


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_authenticate_with_token():
    c = GitHubConnector(token="ghp_test_token")
    await c.authenticate()
    assert c._headers["Authorization"] == "Bearer ghp_test_token"
    assert c.is_authenticated


@pytest.mark.asyncio
async def test_authenticate_without_token():
    c = GitHubConnector(token=None)
    await c.authenticate()
    assert "Authorization" not in c._headers
    assert c.is_authenticated


@pytest.mark.asyncio
async def test_authenticate_reads_env_var(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "env_gh_token")
    c = GitHubConnector(token=None)
    await c.authenticate()
    assert c._headers["Authorization"] == "Bearer env_gh_token"


# ---------------------------------------------------------------------------
# validate_response
# ---------------------------------------------------------------------------

def test_validate_list_response():
    c = GitHubConnector()
    assert c.validate_response([]) is True
    assert c.validate_response([{"id": 1}]) is True


def test_validate_dict_with_items():
    c = GitHubConnector()
    assert c.validate_response({"items": [], "total_count": 0}) is True


def test_validate_invalid():
    c = GitHubConnector()
    assert c.validate_response("string") is False
    assert c.validate_response(None) is False


# ---------------------------------------------------------------------------
# fetch_repositories
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_repositories_success():
    async with respx.mock:
        respx.get("https://api.github.com/search/repositories").mock(
            return_value=_gh_search_response(SAMPLE_REPOS)
        )
        c = GitHubConnector(token="tok")
        articles = await c.fetch_repositories(query="language:python stars:>1000")

    assert len(articles) == 2
    assert all(isinstance(a, Article) for a in articles)
    assert all("[Repo]" in a.title for a in articles)


@pytest.mark.asyncio
async def test_fetch_repositories_article_fields():
    async with respx.mock:
        respx.get("https://api.github.com/search/repositories").mock(
            return_value=_gh_search_response([SAMPLE_REPOS[0]])
        )
        c = GitHubConnector(token="tok", source_id="gh_test")
        articles = await c.fetch_repositories()

    a = articles[0]
    assert "openai/openai-python" in a.title
    assert a.metadata.source_id == "gh_test"
    assert "Python" in a.metadata.tags


@pytest.mark.asyncio
async def test_fetch_repositories_error_returns_empty():
    async with respx.mock:
        respx.get("https://api.github.com/search/repositories").mock(
            return_value=httpx.Response(403)
        )
        c = GitHubConnector(token="tok")

        import asyncio
        orig = asyncio.sleep
        asyncio.sleep = lambda x: orig(0)
        try:
            articles = await c.fetch_repositories()
        finally:
            asyncio.sleep = orig

    assert articles == []


# ---------------------------------------------------------------------------
# fetch_commits
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_commits_success():
    async with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/commits").mock(
            return_value=_gh_list_response(SAMPLE_COMMITS)
        )
        c = GitHubConnector(token="tok")
        articles = await c.fetch_commits(repo="owner/repo")

    assert len(articles) == 2
    assert all("[Commit" in a.title for a in articles)


@pytest.mark.asyncio
async def test_fetch_commits_empty_repo_returns_empty():
    c = GitHubConnector(token="tok")
    articles = await c.fetch_commits(repo="")
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_commits_message_only_first_line():
    async with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/commits").mock(
            return_value=_gh_list_response([SAMPLE_COMMITS[0]])
        )
        c = GitHubConnector(token="tok")
        articles = await c.fetch_commits(repo="owner/repo")

    assert "Extended description" not in articles[0].title


# ---------------------------------------------------------------------------
# fetch_issues
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_issues_success():
    async with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=_gh_list_response(SAMPLE_ISSUES)
        )
        c = GitHubConnector(token="tok")
        articles = await c.fetch_issues(repo="owner/repo")

    assert len(articles) == 1
    assert "[Issue #42]" in articles[0].title
    assert "bug" in articles[0].metadata.tags


@pytest.mark.asyncio
async def test_fetch_issues_empty_repo_returns_empty():
    c = GitHubConnector(token="tok")
    articles = await c.fetch_issues(repo="")
    assert articles == []


# ---------------------------------------------------------------------------
# fetch_releases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_releases_success():
    async with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/releases").mock(
            return_value=_gh_list_response(SAMPLE_RELEASES)
        )
        c = GitHubConnector(token="tok")
        articles = await c.fetch_releases(repo="owner/repo")

    assert len(articles) == 1
    assert "v2.1.0" in articles[0].title
    assert "maintainer" == articles[0].metadata.author


@pytest.mark.asyncio
async def test_fetch_releases_empty_repo_returns_empty():
    c = GitHubConnector(token="tok")
    articles = await c.fetch_releases(repo="")
    assert articles == []


# ---------------------------------------------------------------------------
# fetch (dispatch)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_dispatches_repositories():
    async with respx.mock:
        route = respx.get("https://api.github.com/search/repositories").mock(
            return_value=_gh_search_response(SAMPLE_REPOS)
        )
        c = GitHubConnector(token="tok")
        articles = await c.fetch(resource="repositories", max_pages=1)

    assert route.called
    assert len(articles) > 0


@pytest.mark.asyncio
async def test_fetch_unknown_resource_raises():
    c = GitHubConnector(token="tok")
    await c.authenticate()
    with pytest.raises(ConnectorError, match="Unknown resource"):
        await c.fetch(resource="unknown_thing")


# ---------------------------------------------------------------------------
# _parse_gh_date
# ---------------------------------------------------------------------------

def test_parse_gh_date_valid():
    dt = _parse_gh_date("2024-05-20T10:00:00Z")
    assert dt.year == 2024
    assert dt.tzinfo == timezone.utc


def test_parse_gh_date_none():
    dt = _parse_gh_date(None)
    assert dt.tzinfo == timezone.utc


def test_parse_gh_date_invalid():
    dt = _parse_gh_date("not-a-date")
    assert dt.tzinfo == timezone.utc
