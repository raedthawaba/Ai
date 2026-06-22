"""Channel Builder — إنشاء قنوات حقيقية قابلة للتشغيل."""
from __future__ import annotations

import logging
from typing import Dict, Type

from shared.schemas.channel import ChannelConfig
from data_engine.channels.base import BaseChannel, FetchResult
from data_engine.channels.predefined.demo_channel import DemoChannel
from shared.exceptions import ChannelException, ValidationException

logger = logging.getLogger(__name__)


class RSSChannel(BaseChannel):
    """قناة RSS حقيقية تستخدم RSSParser لجلب المحتوى من مصادر RSS/Atom."""

    async def fetch(self, last_fetched_id: str | None = None) -> FetchResult:
        from data_engine.ingestion.crawlers.rss_parser import parse_rss_feed

        url = str(self.config.source.url)
        logger.info("RSSChannel.fetch: جلب من %s", url)
        try:
            articles = await parse_rss_feed(
                url,
                source_id=self.config.id,
                default_language=self.config.source.params.get("language", "en"),
            )
            logger.info("RSSChannel.fetch: تم جلب %d مقال", len(articles))
            return FetchResult(articles=articles, has_more=False)
        except Exception as exc:
            logger.error("RSSChannel.fetch: خطأ في الجلب — %s", exc)
            return FetchResult(articles=[], has_more=False)

    async def validate_source(self) -> bool:
        from data_engine.ingestion.crawlers.rss_parser import validate_rss_feed
        url = str(self.config.source.url)
        return await validate_rss_feed(url)


class APIChannel(BaseChannel):
    """قناة API عامة قابلة للتوسعة."""

    async def fetch(self, last_fetched_id: str | None = None) -> FetchResult:
        logger.info("APIChannel.fetch: %s", self.config.name)
        return FetchResult(articles=[], has_more=False)

    async def validate_source(self) -> bool:
        return True


class PlaceholderChannel(BaseChannel):
    """قناة وهمية للاختبار والتطوير."""

    async def fetch(self, last_fetched_id: str | None = None) -> FetchResult:
        logger.info("PlaceholderChannel.fetch: %s", self.config.name)
        return FetchResult(articles=[], has_more=False)

    async def validate_source(self) -> bool:
        return True


_CHANNEL_TYPE_MAP: Dict[str, Type[BaseChannel]] = {
    "rss": RSSChannel,
    "api": APIChannel,
    "demo": DemoChannel,
    "placeholder": PlaceholderChannel,
}


class ChannelBuilder:
    """مصنع لإنشاء قنوات بناءً على نوع التكوين."""

    _channel_types: Dict[str, Type[BaseChannel]] = _CHANNEL_TYPE_MAP

    @classmethod
    def register_channel_type(cls, type_name: str, channel_class: Type[BaseChannel]) -> None:
        if not issubclass(channel_class, BaseChannel):
            raise ChannelException("يجب أن ترث فئة القناة من BaseChannel.")
        cls._channel_types[type_name.lower()] = channel_class

    @classmethod
    async def create(cls, channel_type: str, config: ChannelConfig) -> BaseChannel:
        channel_class = cls._channel_types.get(channel_type.lower())
        if not channel_class:
            raise ChannelException(
                f"نوع القناة غير مدعوم: '{channel_type}'. "
                f"الأنواع المتاحة: {list(cls._channel_types.keys())}"
            )
        await cls.validate_config(config)
        if channel_type.lower() == "demo":
            return channel_class(config=config)
        return channel_class(config=config)

    @classmethod
    async def create_from_config(cls, config: ChannelConfig) -> BaseChannel:
        if not isinstance(config, ChannelConfig):
            raise ValidationException("المدخل يجب أن يكون ChannelConfig.")
        channel_type = config.source.type.lower()
        return await cls.create(channel_type, config)

    @classmethod
    async def validate_config(cls, config: ChannelConfig) -> bool:
        if not isinstance(config, ChannelConfig):
            raise ValidationException("المدخل يجب أن يكون ChannelConfig.")
        channel_type = config.source.type.lower()
        if channel_type not in cls._channel_types:
            raise ValidationException(
                f"نوع قناة غير مدعوم في التكوين: {config.source.type}"
            )
        return True
