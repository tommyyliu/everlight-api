from uuid import uuid4
from typing import Optional
from datetime import datetime, date

import numpy as np
from numpy.typing import NDArray

from sqlalchemy import String, DateTime, ForeignKey, JSON, Text, UniqueConstraint, func, UUID, Date
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pgvector.sqlalchemy import HALFVEC

class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    firebase_user_id: Mapped[str] = mapped_column(String, unique=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class JournalEntry(Base):
    __tablename__ = 'journal_entries'
    
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    title: Mapped[Optional[str]] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    local_timestamp: Mapped[datetime] = mapped_column(DateTime)
    week: Mapped[str] = mapped_column(String)
    month: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Agent(Base):
    __tablename__ = 'agents'
    
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    name: Mapped[str] = mapped_column(String(50))
    prompt: Mapped[str] = mapped_column(Text)  # Agent's system prompt
    tools: Mapped[list[str]] = mapped_column(JSON)  # For future use
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AgentSubscription(Base):
    __tablename__ = 'agent_subscriptions'
    
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(ForeignKey('agents.id'))
    channel: Mapped[str] = mapped_column(String(50))  # Channel name
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Composite unique constraint - one subscription per ai per channel
    __table_args__ = (UniqueConstraint('agent_id', 'channel'),)


class Message(Base):
    __tablename__ = 'messages'
    
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    sender: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Brief(Base):
    __tablename__ = 'briefs'
    
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    utc_date: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)  # Markdown content
    display_at: Mapped[datetime] = mapped_column(DateTime)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Index for efficient queries by user_id and utc_date
    __table_args__ = (UniqueConstraint('user_id', 'utc_date', 'display_at'),)


class RawEntry(Base):
    __tablename__ = 'raw_entries'
    
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    source: Mapped[str] = mapped_column(String(100))  # e.g., 'journal', 'voice_note', 'import', etc.
    source_id: Mapped[Optional[str]] = mapped_column(String(255))  # External ID from source system (e.g., Notion page ID)
    content: Mapped[dict] = mapped_column(JSON)  # JSONB-like storage for flexible content structure
    embedding: Mapped[NDArray[np.float16]] = mapped_column(HALFVEC(3072))  # Store embedding vector (768 dimensions for Gemini)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    
    # Index for efficient lookups by source and source_id
    __table_args__ = (
        UniqueConstraint('user_id', 'source', 'source_id', name='uq_user_source_source_id'),
    )


class IntegrationToken(Base):
    __tablename__ = 'integration_tokens'
    
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    integration_type: Mapped[str] = mapped_column(String(50))  # e.g., 'notion', 'gmail', 'calendar'
    access_token: Mapped[str] = mapped_column(Text)  # Encrypted access token
    refresh_token: Mapped[Optional[str]] = mapped_column(Text)  # Optional refresh token
    token_metadata: Mapped[Optional[dict]] = mapped_column(JSON)  # Additional token info (expires_at, scope, etc.)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # Composite unique constraint - one token per user per integration type
    __table_args__ = (UniqueConstraint('user_id', 'integration_type'),)


class Note(Base):
    __tablename__ = 'notes'
    
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    owner: Mapped[UUID] = mapped_column(ForeignKey('agents.id')) # Agent that created the summary
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)  # Summary text content
    embedding: Mapped[NDArray[np.float16]] = mapped_column(HALFVEC(3072))  # Store embedding vector (768 dimensions for Gemini)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())


class WebhookToken(Base):
    __tablename__ = 'webhook_tokens'
    
    id: Mapped[UUID] = mapped_column(UUID, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    verification_token: Mapped[str] = mapped_column(String(255))
    source: Mapped[str] = mapped_column(String(50))  # e.g., 'notion', 'slack', etc.
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # Composite unique constraint - one token per user per source
    __table_args__ = (UniqueConstraint('user_id', 'source'),)
