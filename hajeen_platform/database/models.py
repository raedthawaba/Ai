"""PostgreSQL Async Models — SQLAlchemy 2.0 + asyncpg.

جداول النظام:
  users, sessions, api_keys, audit_log,
  conversations, messages, vector_documents
"""
from __future__ import annotations

import time
import uuid
from typing import Any, AsyncGenerator, Optional

from sqlalchemy import (
    JSON, Boolean, Column, Float, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint, text,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://hajeen:hajeen_pass@localhost:5432/hajeen_db",
)


class Base(DeclarativeBase):
    pass


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username   = Column(String(100), unique=True, nullable=False, index=True)
    email      = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    roles      = Column(JSON, default=list)
    tenant_id  = Column(String(100), nullable=False, default="default", index=True)
    is_active  = Column(Boolean, default=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)
    last_login_at = Column(Float, nullable=True)
    metadata_  = Column("metadata", JSON, default=dict)

    sessions      = relationship("Session", back_populates="user", cascade="all, delete")
    api_keys      = relationship("APIKey", back_populates="user", cascade="all, delete")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete")


# ── Sessions ──────────────────────────────────────────────────────────────────

class Session(Base):
    __tablename__ = "sessions"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id   = Column(String(100), nullable=False, default="default")
    jti         = Column(String(36), unique=True, nullable=False, index=True)
    ip_address  = Column(String(45), nullable=True)
    user_agent  = Column(String(500), nullable=True)
    created_at  = Column(Float, default=time.time)
    expires_at  = Column(Float, nullable=False)
    is_active   = Column(Boolean, default=True)

    user = relationship("User", back_populates="sessions")

    __table_args__ = (Index("ix_sessions_user_active", "user_id", "is_active"),)


# ── API Keys ──────────────────────────────────────────────────────────────────

class APIKey(Base):
    __tablename__ = "api_keys"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    key_id      = Column(String(32), unique=True, nullable=False, index=True)
    key_hash    = Column(String(64), unique=True, nullable=False)
    name        = Column(String(200), nullable=False)
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id   = Column(String(100), nullable=False, default="default")
    scopes      = Column(JSON, default=list)
    is_active   = Column(Boolean, default=True)
    created_at  = Column(Float, default=time.time)
    expires_at  = Column(Float, nullable=True)
    last_used_at = Column(Float, nullable=True)

    user = relationship("User", back_populates="api_keys")


# ── Audit Log ─────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id      = Column(String(36), unique=True, nullable=False, index=True)
    action        = Column(String(100), nullable=False, index=True)
    actor_id      = Column(String(100), nullable=False, index=True)
    tenant_id     = Column(String(100), nullable=False, default="default", index=True)
    resource      = Column(String(500), nullable=True)
    ip_address    = Column(String(45), nullable=True)
    user_agent    = Column(String(500), nullable=True)
    status        = Column(String(20), nullable=False, default="success")
    details       = Column(JSON, default=dict)
    hash          = Column(String(64), nullable=True)
    previous_hash = Column(String(64), nullable=True)
    timestamp     = Column(Float, default=time.time, index=True)
    duration_ms   = Column(Float, nullable=True)

    __table_args__ = (Index("ix_audit_tenant_ts", "tenant_id", "timestamp"),)


# ── Conversations ─────────────────────────────────────────────────────────────

class Conversation(Base):
    __tablename__ = "conversations"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id  = Column(String(100), unique=True, nullable=False, index=True)
    user_id     = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    tenant_id   = Column(String(100), nullable=False, default="default")
    title       = Column(String(500), nullable=True)
    language    = Column(String(10), default="ar")
    created_at  = Column(Float, default=time.time)
    updated_at  = Column(Float, default=time.time, onupdate=time.time)
    metadata_   = Column("metadata", JSON, default=dict)

    user     = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete", order_by="Message.created_at")


# ── Messages ──────────────────────────────────────────────────────────────────

class Message(Base):
    __tablename__ = "messages"

    id              = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role            = Column(String(20), nullable=False)
    content         = Column(Text, nullable=False)
    model           = Column(String(100), nullable=True)
    provider        = Column(String(50), nullable=True)
    tokens_used     = Column(Integer, nullable=True)
    latency_ms      = Column(Float, nullable=True)
    created_at      = Column(Float, default=time.time)
    sources         = Column(JSON, default=list)

    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (Index("ix_messages_conv_ts", "conversation_id", "created_at"),)


# ── Vector Documents ──────────────────────────────────────────────────────────

class VectorDocument(Base):
    __tablename__ = "vector_documents"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    doc_id      = Column(String(200), unique=True, nullable=False, index=True)
    title       = Column(String(1000), nullable=True)
    content     = Column(Text, nullable=False)
    source_url  = Column(String(2000), nullable=True)
    channel_id  = Column(String(100), nullable=True, index=True)
    tenant_id   = Column(String(100), nullable=False, default="default", index=True)
    language    = Column(String(10), default="ar")
    indexed_at  = Column(Float, default=time.time)
    metadata_   = Column("metadata", JSON, default=dict)
    chunk_count = Column(Integer, default=1)


# ── Engine & Session Factory ──────────────────────────────────────────────────

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_URL,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
        )
    return _engine


def get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            autocommit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """إنشاء جميع الجداول (للتطوير — استخدم Alembic في الإنتاج)."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
