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
from typing import Optional
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
    permissions: list[PermissionBrief] = Field(default_factory=list)


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
    permission_codes: list[str] = Field(default_factory=list)


class RoleUpdatePayload(BaseModel):
    name_ru: Optional[str] = Field(None, min_length=1, max_length=255)
    name_en: Optional[str] = Field(None, max_length=255)
    description_ru: Optional[str] = Field(None, max_length=512)
    sort_order: Optional[int] = Field(None, ge=0, le=9999)


class RolePermissionsUpdate(BaseModel):
    permission_codes: list[str] = Field(default_factory=list)


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
    password_changed_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime

    role_codes: list[str] = Field(default_factory=list)
    role_names: list[str] = Field(default_factory=list)

    organization_id: Optional[UUID] = None
    allowed_companies: Optional[list[str]] = None


class UserGroupMembership(BaseModel):
    """Pack 147: one row of (group, role) membership for a user.

    Used by UserDetail.group_memberships. Each entry says "this user
    has role X inside group Y (which is bound to company Z)".
    """
    group_id: UUID
    group_code: str
    group_name: str
    company_id: Optional[UUID] = None
    role_code: str
    role_name: str


class UserDetail(UserBrief):
    effective_permissions: list[str] = Field(default_factory=list)
    role_by_email_rule: Optional[dict] = None
    # Pack 147: per-(user, group) role assignments.
    group_memberships: list[UserGroupMembership] = Field(default_factory=list)
    # Pack 148-followup: moderation flags surfaced in the user-detail drawer.
    is_external:        bool = False
    bypass_moderation:  bool = False
    external_org_name:  Optional[str] = None
    allowed_sectors:    Optional[list[str]] = None    # Область доступа «По секторам»


class UserCreatePayload(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    department: Optional[str] = Field(None, max_length=128)
    password: str = Field(..., min_length=12, description="Initial password (min 12 chars)")
    must_change_password: bool = True
    role_codes: list[str] = Field(default_factory=list)
    organization_id: Optional[UUID] = None
    allowed_companies: Optional[list[str]] = None
    allowed_sectors: Optional[list[str]] = None    # Область доступа «По секторам»


class UserUpdatePayload(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    department: Optional[str] = Field(None, max_length=128)
    is_active: Optional[bool] = None
    role_codes: Optional[list[str]] = None
    organization_id: Optional[UUID] = None
    allowed_companies: Optional[list[str]] = None
    allowed_sectors: Optional[list[str]] = None


class PasswordResetPayload(BaseModel):
    new_password: str = Field(..., min_length=12)
    must_change_password: bool = True


class SetOwnerPayload(BaseModel):
    is_owner: bool


class UserListResponse(BaseModel):
    items: list[UserBrief]
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
    role_codes: list[str] = Field(default_factory=list)
    department: Optional[str] = None
    allowed_sectors: Optional[list[str]] = None
    allowed_companies: Optional[list[str]] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class RoleByEmailCreatePayload(BaseModel):
    email: EmailStr
    role_codes: list[str] = Field(..., min_length=1)
    department: Optional[str] = Field(None, max_length=128)
    allowed_sectors: Optional[list[str]] = None
    allowed_companies: Optional[list[str]] = None
    notes: Optional[str] = Field(None, max_length=512)


class RoleByEmailUpdatePayload(BaseModel):
    """Все поля опциональны — partial update. Email не меняется (он же идентификатор правила)."""
    role_codes: Optional[list[str]] = Field(None, min_length=1)
    department: Optional[str] = Field(None, max_length=128)
    allowed_sectors: Optional[list[str]] = None
    allowed_companies: Optional[list[str]] = None
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
    # Pack 147: 1:1 group↔company. Null = free-form group.
    company_id: Optional[UUID] = None
    organization_id: Optional[UUID] = None
    department: Optional[str] = None
    member_count: int = 0
    permission_count: int = 0
    role_codes: list[str] = Field(default_factory=list)


class GroupMember(BaseModel):
    id: UUID
    email: str
    full_name: Optional[str] = None
    # Pack 147: role of this user inside this group (None for legacy
    # memberships from user_group association table without a role).
    role_code: Optional[str] = None
    role_name: Optional[str] = None


class GroupPermission(BaseModel):
    code: str
    description: Optional[str] = None


class GroupDetail(GroupBrief):
    members: list[GroupMember] = Field(default_factory=list)
    permissions: list[GroupPermission] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)


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


class GroupMemberAssignment(BaseModel):
    user_id: UUID
    role_code: str


class UserMembershipUpsert(BaseModel):
    """Add a user to a group (or change their role inside it).

    Used by the User-detail drawer so admins don't have to rewrite the
    whole group membership list to edit a single user.
    """
    role_code: str


class GroupMembersUpdate(BaseModel):
    """Replace all members of a group with the supplied (user_id, role_code) pairs.

    Pack 147 preferred shape: `members: [{user_id, role_code}, ...]`.
    Legacy shape `user_ids: [UUID]` is still accepted for backward-compat;
    each legacy user gets role `viewer` by default.
    """
    members: Optional[list[GroupMemberAssignment]] = None
    user_ids: Optional[list[UUID]] = None  # legacy


class GroupPermissionsUpdate(BaseModel):
    """Replace all permissions of a group with the supplied list of codes.

    Совместимо с фронтом rbacV3.ts (groupsApi.setPermissions: { permission_codes }).
    """
    permission_codes: list[str] = Field(default_factory=list)


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
    most_assigned_roles: list[dict] = Field(default_factory=list)
