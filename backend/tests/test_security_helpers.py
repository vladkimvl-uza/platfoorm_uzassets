"""Unit tests for is_super_admin / _has_permission (no DB).

Covers H4 contract — owner OR role admin bypasses everything, others must
have the explicit permission. Used as a sanity-net so that future edits
to security.py don't silently break the bypass semantics.
"""
import pytest

pytestmark = pytest.mark.unit


def test_owner_is_super_admin(make_user_stub):
    from app.core.security import is_super_admin
    u = make_user_stub(is_owner=True, roles=[])
    assert is_super_admin(u) is True


def test_admin_role_is_super_admin(make_user_stub):
    from app.core.security import is_super_admin
    u = make_user_stub(is_owner=False, roles=[("admin", ())])
    assert is_super_admin(u) is True


def test_regular_user_is_not_super_admin(make_user_stub):
    from app.core.security import is_super_admin
    u = make_user_stub(is_owner=False, roles=[("organization", ())])
    assert is_super_admin(u) is False


def test_user_without_roles_is_not_super_admin(make_user_stub):
    from app.core.security import is_super_admin
    u = make_user_stub(is_owner=False, roles=[])
    assert is_super_admin(u) is False


def test_has_permission_owner_bypass(make_user_stub):
    from app.core.security import _has_permission
    u = make_user_stub(is_owner=True, roles=[])
    assert _has_permission(u, "kpi.edit") is True
    assert _has_permission(u, "admin.users") is True
    assert _has_permission(u, "made-up.permission") is True


def test_has_permission_admin_role_bypass(make_user_stub):
    from app.core.security import _has_permission
    u = make_user_stub(roles=[("admin", ())])
    assert _has_permission(u, "kpi.edit") is True


def test_has_permission_explicit_grant(make_user_stub):
    from app.core.security import _has_permission
    u = make_user_stub(roles=[("financier", ("kpi.view", "bp.view"))])
    assert _has_permission(u, "kpi.view") is True
    assert _has_permission(u, "kpi.edit") is False


def test_has_permission_negative(make_user_stub):
    from app.core.security import _has_permission
    u = make_user_stub(roles=[("organization", ())])
    assert _has_permission(u, "admin.users") is False
