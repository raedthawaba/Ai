from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from shared.schemas import (
    Article,
    ChannelConfig,
    ChannelStatus,
    PipelineConfig,
)


def test_channel_config_validation():
    data = {
        "id": "ch_1",
        "name": "Test Channel",
        "status": "active",
        "source": {"url": "https://example.com/rss", "type": "rss"},
    }
    config = ChannelConfig(**data)
    assert config.id == "ch_1"
    assert config.status == ChannelStatus.ACTIVE

    data["source"]["url"] = "not-a-url"
    with pytest.raises(ValidationError):
        ChannelConfig(**data)


def test_article_validation():
    data = {
        "id": "art_1",
        "title": "Test Article",
        "content": "Content here",
        "url": "https://example.com/art1",
        "published_at": datetime.now(timezone.utc),
        "metadata": {"source_id": "ch_1", "language": "ar"},
    }
    article = Article(**data)
    assert article.title == "Test Article"
    assert article.metadata.language == "ar"

    del data["title"]
    with pytest.raises(ValidationError):
        Article(**data)


def test_pipeline_config():
    data = {
        "id": "pipe_1",
        "name": "Default Pipeline",
        "stages": ["fetch", "clean", "store"],
    }
    pipe = PipelineConfig(**data)
    assert len(pipe.stages) == 3
    assert pipe.name == "Default Pipeline"


def test_default_values():
    data = {
        "id": "ch_2",
        "name": "Draft Channel",
        "source": {"url": "https://example.com", "type": "api"},
    }
    config = ChannelConfig(**data)
    assert config.status == ChannelStatus.DRAFT
    assert isinstance(config.created_at, datetime)
