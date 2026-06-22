"""Connectors package — Phase 3 (Section 3.2).

يوفّر connectors لمصادر البيانات المختلفة.
"""
from .base_connector import BaseConnector, ConnectorError, RateLimiter
from .custom_connector import CustomConnector
from .newsapi_connector import NewsAPIConnector
from .github_connector import GitHubConnector
from .reddit_connector import RedditConnector
from .youtube_connector import YouTubeConnector
from .arxiv_connector import ArxivConnector

__all__ = [
    "BaseConnector",
    "ConnectorError",
    "RateLimiter",
    "CustomConnector",
    "NewsAPIConnector",
    "GitHubConnector",
    "RedditConnector",
    "YouTubeConnector",
    "ArxivConnector",
]
