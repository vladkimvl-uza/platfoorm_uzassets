"""Pydantic schemas for /auth/login-mfa + /auth/verify-mfa.

Kept in routes/ rather than schemas/ to avoid touching `app.schemas.auth`,
which is part of the protected core auth surface.
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class LoginMfaResponse(BaseModel):
    """Unified shape — frontend checks `mfa_required` flag.

    Variants:
      A) mfa_required=False — full TokenPair fields populated
      B) mfa_required=True  — challenge_id + method + masked_destination
    """
    mfa_required: bool = False

    # Variant A — TokenPair fields
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: Optional[str] = None
    expires_in: Optional[int] = None

    # Variant B — MFA challenge fields
    challenge_id: Optional[str] = None
    method: Optional[Literal["telegram", "totp", "both"]] = None
    masked_destination: Optional[str] = None
    ttl_minutes: Optional[int] = None


class VerifyMfaIn(BaseModel):
    """Either (challenge_id + code) OR (login + recovery_code)."""
    challenge_id: Optional[str] = None
    code: Optional[str] = Field(None, min_length=4, max_length=12)
    login: Optional[str] = Field(None, max_length=255)
    recovery_code: Optional[str] = Field(None, min_length=8, max_length=20)
