"""Schemas for RBAC v3 — единый модуль управления доступом.

Объединяет схемы из старых rbac.py (v1) и rbac_v2.py (v2). Включает только
сущности, реально используемые фронтом rbacV3.ts:
  * users, roles, role-by-email, groups, permissions catalog, RBAC overview.

Что НЕ перенесено (как мёртвый код):
  * direct user grants (UserPermissionGrant)
  * permission templates
  * module visibility overrides
  * RBAC change log (есть общий audit_log)
  * group_role (роли группе) — фронт не поддерживает.
"""
from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# =====================================================================
# Permissions
# =====================================================================

class PermissionBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    name: Optional[str] = None
    module: str
    action: Optional[str] = None
    description: Optional[str] = None


# =====================================================================
# Roles
# =====================================================================

class RoleBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name_ru: str
    name_uz: Optional[str] = None
    name_en: Optional[str] = None
    description_ru: Optional[str] = None
    is_system: bool = False
    sort_order: int = 0
    permission_count: int = 0


class RoleDetail(RoleBrief):
    permissions: List[PermissionBrief] = Field(default_factory=list)


class RoleCreatePayload(BaseModel):
    code: str = Field(
        ...,
        min_length=2,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Lowercase slug, snake_case (e.g. mining_lead)",
    )
    name_ru: str = Field(..., min_length=1, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    description_ru: Optional[str] = Field(None, max_length=512)
    sort_order: int = Field(100, ge=0, le=9999)
    permission_codes: List[str] = Field(default_factory=list)


class RoleUpdatePayload(BaseModel):
    name_ru: Optional[str] = Field(None, min_length=1, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    description_ru: Optional[str] = Field(None, max_length=512)
    sort_order: Optional[int] = Field(None, ge=0, le=9999)


class RolePermissionsUpdate(BaseModel):
    permission_codes: List[str] = Field(default_factory=list)


# =====================================================================
# Users
# =====================================================================

class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: Optional[str] = None
    department: Optional[str] = None
    is_active: bool = True
    is_owner: bool = False
    must_change_password: bool = False
    last_login_at: Optional[datetime] = None
    created_at: datetime

    role_codes: List[str] = Field(default_factory=list)
    role_names: List[str] = Field(default_factory=list)

    organization_id: Optional[UUID] = None
    allowed_companies: Optional[List[str]] = None


class UserDetail(UserBrief):
    effective_permissions: List[str] = Field(default_factory=list)
    role_by_email_rule: Optional[dict] = None


class UserCreatePayload(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    department: Optional[str] = Field(None, max_length=128)
    password: str = Field(..., min_length=12, description="Initial password (min 12 chars)")
    must_change_password: bool = True
    role_codes: List[str] = Field(default_factory=list)
    organization_id: Optional[UUID] = None
    allowed_companies: Optional[List[str]] = None


class UserUpdatePayload(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    department: Optional[str] = Field(None, max_length=128)
    is_active: Optional[bool] = None
    role_codes: Optional[List[str]] = None
    organization_id: Optional[UUID] = None
    allowed_companies: Optional[List[str]] = None


class PasswordResetPayload(BaseModel):
    new_password: str = Field(..., min_length=12)
    must_change_password: bool = True


class UserListResponse(BaseModel):
    items: List[UserBrief]
    total: int


# =====================================================================
# Impersonate / preview-token
# =====================================================================

class PreviewTokenResponse(BaseModel):
    access_token: str
    expires_in: int
    target_user_id: UUID
    target_email: str


# =====================================================================
# Role-by-email auto-assignment
# =====================================================================

class RoleByEmailRule(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role_codes: List[str] = Field(default_factory=list)
    department: Optional[str] = None
    allowed_sectors: Optional[List[str]] = None
    allowed_companies: Optional[List[str]] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RoleByEmailCreatePayload(BaseModel):
    email: EmailStr
    role_codes: List[str] = Field(..., min_length=1)
    department: Optional[str] = Field(None, max_length=128)
    allowed_sectors: Optional[List[str]] = None
    allowed_companies: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=512)


class RoleByEmailUpdatePayload(BaseModel):
    """Все поля опциональны — partial update. Email не меняется (он же идентификатор правила)."""
    role_codes: Optional[List[str]] = Field(None, min_length=1)
    department: Optional[str] = Field(None, max_length=128)
    allowed_sectors: Optional[List[str]] = None
    allowed_companies: Optional[List[str]] = None
    notes: Optional[str] = Field(None, max_length=512)


# =====================================================================
# Groups (управление через группы — единственный реально работающий
# не-роль механизм назначения прав сверх роли)
# =====================================================================

class GroupBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: Optional[str] = None
    organization_id: Optional[UUID] = None
    department: Optional[str] = None
    member_count: int = 0
    permission_count: int = 0
    role_codes: List[str] = Field(default_factory=list)


class GroupMember(BaseModel):
    id: UUID
    email: str
    full_name: Optional[str] = None


class GroupPermission(BaseModel):
    code: str
    description: Optional[str] = None


class GroupDetail(GroupBrief):
    members: List[GroupMember] = Field(default_factory=list)
    permissions: List[GroupPermission] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)


class GroupCreatePayload(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    organization_id: Optional[UUID] = None
    department: Optional[str] = None


class GroupUpdatePayload(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    organization_id: Optional[UUID] = None
    department: Optional[str] = None


class GroupMembersUpdate(BaseModel):
    user_ids: List[UUID]


class GroupPermissionsUpdate(BaseModel):
    """Replace all permissions of a group with the supplied list of codes.

    Совместимо с фронтом rbacV3.ts (groupsApi.setPermissions: { permission_codes }).
    """
    permission_codes: List[str] = Field(default_factory=list)


# =====================================================================
# Overview
# =====================================================================

class RBACOverview(BaseModel):
    users_total: int
    users_active: int
    users_inactive: int
    roles_total: int
    permissions_total: int
    role_by_email_rules: int
    users_without_roles: int
    most_assigned_roles: List[dict] = Field(default_factory=list)
