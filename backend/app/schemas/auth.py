"""Pydantic schemas for authentication."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# =====================================================================
# Login / tokens
# =====================================================================

class LoginRequest(BaseModel):
    """Login by username or email + password."""
    login: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=256)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds until access_token expires


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=8, max_length=256)


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = None  # if provided — revoke this refresh


# =====================================================================
# User info exposed to clients
# =====================================================================

class UserPublic(BaseModel):
    """User as seen by themselves (`/auth/me`) — full info."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    username: Optional[str]
    full_name: Optional[str]
    is_owner: bool
    is_active: bool
    must_change_password: bool
    password_changed_at: Optional[datetime] = None
    organization_id: Optional[UUID]
    company: Optional[str] = None      # name_ru компании (из organization_id)
    sector: Optional[str] = None       # сектор компании
    org_profile_set: bool = False      # завершена ли первичная настройка
    department: Optional[str]
    job_title: Optional[str]
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    website_url: Optional[str] = None
    telegram_username: Optional[str] = None
    last_login_at: Optional[datetime]
    welcome_seen: bool = False
    # Step-up / обяз. MFA: для привилегированных (owner/admin) без включённой MFA
    # фронт показывает блокирующий экран настройки 2FA (149 п.6.14, 841 5.3.3.1).
    mfa_setup_required: bool = False
    roles:       list[str]
    permissions: list[str]


class UpdateMeRequest(BaseModel):
    """Поля, которые пользователь может изменить в своём профиле сам."""
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    avatar_url: Optional[str] = None  # data-URL фото или "" для удаления
    linkedin_url: Optional[str] = None  # профиль LinkedIn ("" для удаления)
    website_url: Optional[str] = None   # личный сайт/портфолио
    # Компания (organization_id) — юзер задаёт ОДИН раз при первой настройке;
    # повторно сервер игнорирует (org_profile_set=true). Меняет только admin.
    organization_id: Optional[UUID] = None


class UserBrief(BaseModel):
    """Minimal user info — for lists."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: Optional[str]
    is_active: bool
    roles: list[str]
