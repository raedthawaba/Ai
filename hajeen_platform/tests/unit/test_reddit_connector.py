"""Tests for RedditConnector — section 4.9."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from data_engine.ingestion.connectors.reddit_connector import (
    RedditConnector,
    _from_utc_timestamp,
)
from shared.schemas.article import Article


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _reddit_listing(posts: list, after: str = None) -> httpx.Response:
    children = [{"kind": "t3", "data": p} for p in posts]
    payload = {
        "kind": "Listing",
        "data": {
            "children": children,
            "after": after,
            "before": None,
            "dist": len(posts),
        },
    }
    return httpx.Response(200, content=json.dumps(payload).encode())


SAMPLE_POSTS = [
    {
        "id": "abc123",
        "title": "Python 3.12 is amazing",
        "url": "https://python.org/release/3.12",
        "selftext": "",
        "author": "user_python",
        "subreddit": "programming",
        "score": 1500,
        "num_comments": 234,
        "created_utc": 1716192000.0,
        "permalink": "/r/programming/comments/abc123/python_312_is_amazing/",
        "is_self": False,
        "over_18": False,
        "link_flair_text": "News",
    },
    {
        "id": "def456",
        "title": "Ask HN: Best Python libraries in 2024?",
        "url": "https://www.reddit.com/r/programming/comments/def456/",
        "selftext": "Looking for recommendations...",
        "author": "curious_dev",
        "subreddit": "programming",
        "score": 890,
        "num_comments": 120,
        "created_utc": 1716105600.0,
        "permalink": "/r/programming/comments/def456/ask_hn/",
        "is_self": True,
        "over_18": False,
        "link_flair_text": None,
    },
]

SAMPLE_COMMENT_RESPONSE = [
    {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": "abc123",
                        "title": "Python 3.12",
                        "num_comments": 234,
                        "permalink": "/r/programming/comments/abc123/",
                    },
                }
            ]
        },
    },
    {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t1",
                    "data": {"author": "top_commenter", "score": 500, "body": "Great!"},
                }
            ]
        },
    },
]


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_authenticate_sets_flag():
    c = RedditConnector()
    await c.authenticate()
    assert c.is_authenticated


# ---------------------------------------------------------------------------
# validate_response
# ---------------------------------------------------------------------------

def test_validate_valid_listing():
    c = RedditConnector()
    data = {"kind": "Listing", "data": {"children": []}}
    assert c.validate_response(data) is True


def test_validate_missing_kind():
    c = RedditConnector()
    assert c.validate_response({"data": {}}) is False


def test_validate_wrong_kind():
    c = RedditConnector()
    assert c.validate_response({"kind": "t3", "data": {}}) is False


def test_validate_not_dict():
    c = RedditConnector()
    assert c.validate_response([]) is False
    assert c.validate_response(None) is False


# ---------------------------------------------------------------------------
# fetch_subreddit_posts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_subreddit_posts_success():
    url = "https://www.reddit.com/r/programming/hot.json"
    async with respx.mock:
        respx.get(url).mock(return_value=_reddit_listing(SAMPLE_POSTS))
        c = RedditConnector()
        articles = await c.fetch_subreddit_posts(subreddit="programming", listing="hot")

    assert len(articles) == 2
    assert all(isinstance(a, Article) for a in articles)


@pytest.mark.asyncio
async def test_fetch_subreddit_posts_article_fields():
    url = "https://www.reddit.com/r/programming/hot.json"
    async with respx.mock:
        respx.get(url).mock(return_value=_reddit_listing([SAMPLE_POSTS[0]]))
        c = RedditConnector(source_id="reddit_test")
        articles = await c.fetch_subreddit_posts(subreddit="programming")

    a = articles[0]
    assert a.title == "Python 3.12 is amazing"
    assert a.metadata.source_id == "reddit_test"
    assert a.metadata.author == "user_python"
    assert "r/programming" in a.metadata.tags
    assert "News" in a.metadata.tags
    assert a.metadata.extra["score"] == 1500
    assert a.metadata.extra["num_comments"] == 234


@pytest.mark.asyncio
async def test_fetch_subreddit_posts_pagination():
    url = "https://www.reddit.com/r/tech/new.json"
    page1_posts = [SAMPLE_POSTS[0]]
    page2_posts = [SAMPLE_POSTS[1]]

    call_count = 0

    async def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _reddit_listing(page1_posts, after="t3_def456")
        return _reddit_listing(page2_posts, after=None)

    async with respx.mock:
        respx.get(url).mock(side_effect=side_effect)
        c = RedditConnector()
        articles = await c.fetch_subreddit_posts(
            subreddit="tech", listing="new", limit=1, max_pages=2
        )

    assert call_count == 2
    assert len(articles) == 2


@pytest.mark.asyncio
async def test_fetch_subreddit_posts_invalid_listing_defaults_to_hot():
    url = "https://www.reddit.com/r/python/hot.json"
    async with respx.mock:
        respx.get(url).mock(return_value=_reddit_listing([]))
        c = RedditConnector()
        articles = await c.fetch_subreddit_posts(subreddit="python", listing="invalid_sort")
    assert articles == []


@pytest.mark.asyncio
async def test_fetch_subreddit_posts_error_returns_empty():
    url = "https://www.reddit.com/r/programming/hot.json"
    async with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(429))

        import asyncio
        orig = asyncio.sleep
        asyncio.sleep = lambda x: orig(0)
        try:
            c = RedditConnector(max_retries=1)
            articles = await c.fetch_subreddit_posts(subreddit="programming")
        finally:
            asyncio.sleep = orig

    assert articles == []


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_global():
    url = "https://www.reddit.com/search.json"
    async with respx.mock:
        respx.get(url).mock(return_value=_reddit_listing(SAMPLE_POSTS))
        c = RedditConnector()
        articles = await c.search(query="python 3.12")

    assert len(articles) == 2


@pytest.mark.asyncio
async def test_search_restricted_to_subreddit():
    url = "https://www.reddit.com/r/python/search.json"
    async with respx.mock:
        route = respx.get(url).mock(return_value=_reddit_listing([SAMPLE_POSTS[0]]))
        c = RedditConnector()
        articles = await c.search(query="async await", subreddit="python")

    assert route.called
    params = dict(route.calls.last.request.url.params)
    assert params.get("restrict_sr") == "on"
    assert len(articles) == 1


@pytest.mark.asyncio
async def test_search_empty_results():
    async with respx.mock:
        respx.get("https://www.reddit.com/search.json").mock(
            return_value=_reddit_listing([])
        )
        c = RedditConnector()
        articles = await c.search(query="zzz_no_results_zzz")

    assert articles == []


# ---------------------------------------------------------------------------
# get_comment_metadata
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_comment_metadata_success():
    url = "https://www.reddit.com/r/programming/comments/abc123.json"
    async with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(
                200, content=json.dumps(SAMPLE_COMMENT_RESPONSE).encode()
            )
        )
        c = RedditConnector()
        metadata = await c.get_comment_metadata(
            post_id="abc123", subreddit="programming"
        )

    assert metadata["num_comments"] == 234
    assert metadata["top_comment_author"] == "top_commenter"
    assert metadata["top_comment_score"] == 500


@pytest.mark.asyncio
async def test_get_comment_metadata_error_returns_empty():
    url = "https://www.reddit.com/r/programming/comments/xyz.json"
    async with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(404))

        import asyncio
        orig = asyncio.sleep
        asyncio.sleep = lambda x: orig(0)
        try:
            c = RedditConnector(max_retries=1)
            metadata = await c.get_comment_metadata("xyz", "programming")
        finally:
            asyncio.sleep = orig

    assert metadata == {}


# ---------------------------------------------------------------------------
# fetch (entry point)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_delegates_to_subreddit():
    url = "https://www.reddit.com/r/technology/hot.json"
    async with respx.mock:
        route = respx.get(url).mock(return_value=_reddit_listing(SAMPLE_POSTS))
        c = RedditConnector()
        articles = await c.fetch(subreddit="technology", listing="hot", limit=10)

    assert route.called
    assert len(articles) == 2


# ---------------------------------------------------------------------------
# _from_utc_timestamp
# ---------------------------------------------------------------------------

def test_from_utc_timestamp_valid():
    dt = _from_utc_timestamp(0.0)
    assert dt.tzinfo == timezone.utc
    assert dt.year == 1970


def test_from_utc_timestamp_recent():
    ts = 1716192000.0
    dt = _from_utc_timestamp(ts)
    assert dt.year == 2024
    assert dt.tzinfo == timezone.utc


def test_from_utc_timestamp_none():
    dt = _from_utc_timestamp(None)
    assert dt.tzinfo == timezone.utc


def test_from_utc_timestamp_invalid_string():
    dt = _from_utc_timestamp("bad")
    assert dt.tzinfo == timezone.utc
