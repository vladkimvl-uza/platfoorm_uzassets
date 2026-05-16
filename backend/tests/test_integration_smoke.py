"""Sanity test for integration infra — verifies the pg container boots
and we can issue a query through the session fixture.

If this fails, fix conftest before writing other integration tests.
"""
import pytest


pytestmark = pytest.mark.integration


async def test_db_session_works(db):
    """A trivial query to confirm the engine connects to the fresh pg container."""
    from sqlalchemy import text
    result = await db.execute(text("SELECT 1"))
    assert result.scalar() == 1


async def test_alembic_migrations_applied(db):
    """Schema should have the core RBAC tables after upgrade head."""
    from sqlalchemy import text
    rows = (await db.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"),
    )).scalars().all()
    expected = {"users", "roles", "permissions", "user_role", "role_permission", "group_permission_grant"}
    missing = expected - set(rows)
    assert not missing, f"missing tables: {missing}"


async def test_make_user_factory(make_user):
    """Can we create a user and load their roles?"""
    u = await make_user(email="alice@test", role_codes=["admin"], is_owner=False)
    assert u.email == "alice@test"
    role_codes = {r.code for r in u.roles}
    assert "admin" in role_codes


async def test_auth_header_roundtrip(make_user, auth_header):
    """Token issued for a test user decodes back to the same subject."""
    from app.core import jwt as J
    u = await make_user(email="bob@test")
    hdr = auth_header(u)
    assert hdr["Authorization"].startswith("Bearer ")
    token = hdr["Authorization"][7:]
    claims = J.decode_token(token, expected_type="access")
    assert claims["sub"] == str(u.id)
