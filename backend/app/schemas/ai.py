"""
Pydantic schemas for AI Assistant endpoints.

Pack 7.7: VALID_ROLES expanded from 5 to 13 (added investor + 7 Big4 roles).
"""
from __future__ import annotations
from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─────────────── Chat request / streaming ───────────────

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    conversation_id: Optional[UUID] = None
    messages: List[ChatMessage] = Field(..., min_length=1)
    role: Optional[str] = None
    style: Optional[str] = None
    model: Optional[str] = None  # per-request override; falls back to saved cfg
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(None, ge=128, le=64000)


# ─────────────── Conversation CRUD ───────────────

class ConversationCreate(BaseModel):
    title: Optional[str] = None


class ConversationOut(BaseModel):
    id: UUID
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0
    last_message_preview: Optional[str] = None

    class Config:
        from_attributes = True


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    stop_reason: Optional[str] = None

    class Config:
        from_attributes = True


class ConversationDetailOut(ConversationOut):
    messages: List[MessageOut] = []


# ─────────────── Health ───────────────

class AiHealthOut(BaseModel):
    enabled: bool
    model: str
    has_api_key: bool


# ─────────────── Per-user config ───────────────

VALID_ROLES = {
    # Базовые (Pack 7.2)
    "analyst", "assistant", "expert", "universal", "financial",
    # Pack 7.7 — Финансы
    "investor",
    # Pack 7.7 — Big4 specialisations
    "audit_big4", "tax_big4", "strategy_big4", "risk_big4",
    "esg_big4", "ma_big4", "forensic_big4",
}
VALID_STYLES = {"laconic", "detailed", "structured", "adaptive"}

# Pack 7.9d: per-user model override.
# Defaults: Sonnet 4.6 (balanced). Opus 4.7 = умнее но дороже+медленнее.
# Haiku 4.5 = мгновенный, для коротких вопросов.
VALID_MODELS = {
    "claude-sonnet-4-6",         # default — best balance speed/cost/quality
    "claude-opus-4-7",            # premium — для стратегических запросов
    "claude-haiku-4-5-20251001",  # ультра-быстрый — для коротких ответов
}


class AiConfigOut(BaseModel):
    role: str = "analyst"
    style: str = "structured"
    model: str = "claude-sonnet-4-6"
    temperature: float = 0.10  # Pack 7.8: lowered for more deterministic analytics
    max_tokens: int = 16000
    custom_instructions: Optional[str] = None

    class Config:
        from_attributes = True


class AiConfigIn(BaseModel):
    role: Optional[str] = None
    style: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(None, ge=128, le=64000)
    custom_instructions: Optional[str] = Field(None, max_length=4000)
