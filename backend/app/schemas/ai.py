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
    # Базовые     "analyst", "assistant", "expert", "universal", "financial",
    # Финансы
    "investor",
    # Big4 specialisations
    "audit_big4", "tax_big4", "strategy_big4", "risk_big4",
    "esg_big4", "ma_big4", "forensic_big4",
}
VALID_STYLES = {"laconic", "detailed", "structured", "adaptive"}

# per-user model override.
# Тиры ИИ-движка (нейтральные алиасы; реальные provider-id — из окружения).
VALID_MODELS = {
    "ai-balanced",  # default — баланс скорости/качества
    "ai-deep",      # premium — для стратегических запросов
    "ai-fast",      # ультра-быстрый — для коротких ответов
}


class AiConfigOut(BaseModel):
    role: str = "analyst"
    style: str = "structured"
    model: str = "ai-balanced"
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
