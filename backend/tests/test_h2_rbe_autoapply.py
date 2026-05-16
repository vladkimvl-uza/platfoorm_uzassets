"""Integration tests for H2 — RoleByEmail auto-apply at login.

Calls `auth_service.authenticate()` directly with seeded users + rules.

Covers:
  * Rule matches → roles added to user
  * Idempotent: second login does not duplicate roles
  * Existing roles preserved (add-only semantics)
  * department/allowed_sectors/allowed_companies filled only when empty
  * No rule → no changes
  * Unknown roles in rule are silently skipped
"""
import pytest
from sqlalchemy import select


pytestmark = pytest.mark.integration


async def _make_rbe(db, *, email, role_codes, department=None,
                   allowed_sectors=None, allowed_companies=None):
    from app.models.user import RoleByEmail
    rule = RoleByEmail(
        email=email.lower(),
        role_codes=role_codes,
        department=department,
        allowed_sectors=allowed_sectors,
        allowed_companies=allowed_companies,
    )
    db.add(rule)
    await db.commit()
    return rule


async def _authenticate(db, *, email, password):
    """Wrapper that picks up our test session for authenticate()."""
    from app.services.auth_service import authenticate
    return await authenticate(db, login_id=email, password=password, ip="127.0.0.1")


async def test_rbe_adds_missing_roles(db, make_user):
    pwd = "TestPa$$w0rdQ7K"
    u = await make_user(email="alice@example.com", password=pwd, role_codes=[])
    await _make_rbe(db, email="alice@example.com", role_codes=["financier", "organization"])

    user, _, _ = await _authenticate(db, email="alice@example.com", password=pwd)

    role_codes = {r.code for r in user.roles}
    assert role_codes == {"financier", "organization"}


async def test_rbe_idempotent_on_second_login(db, make_user, app_client):
    """Two consecutive logins via the HTTP boundary — mirrors how the
    real user would re-authenticate. Each request runs in its own
    FastAPI session (override_get_db in conftest) so SQLAlchemy
    identity-map state can't mask bugs.

    We go through /auth/login (no MFA) twice and re-fetch the user from
    DB at the end to assert the role wasn't duplicated.
    """
    import asyncio
    import uuid as _uuid
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select
    from app.models.user import User, Role

    pwd = "TestPa$$w0rdQ7K"
    email = f"bob-{_uuid.uuid4().hex[:8]}@example.com"
    await make_user(email=email, password=pwd, role_codes=[])
    await _make_rbe(db, email=email, role_codes=["financier"])

    # First login through HTTP — triggers _apply_role_by_email, persists.
    # audit_log.entry_hash has a UNIQUE constraint and the hash input
    # includes timestamp+actor+action+ip+user_agent. Two identical calls
    # at the same wall-clock millisecond collide; differentiate via
    # User-Agent to keep this test deterministic without leaning on sleeps
    # (which proved flaky under loaded test runners).
    r1 = await app_client.post(
        "/auth/login",
        json={"login": email, "password": pwd},
        headers={"User-Agent": "pytest-run-1"},
    )
    assert r1.status_code == 200, r1.text

    await asyncio.sleep(0.05)

    r2 = await app_client.post(
        "/auth/login",
        json={"login": email, "password": pwd},
        headers={"User-Agent": "pytest-run-2"},
    )
    assert r2.status_code == 200, r2.text

    # Re-read user from DB with roles eagerly loaded — assert no duplicates.
    refreshed = (await db.execute(
        select(User)
        .where(User.email == email)
        .options(selectinload(User.roles))
    )).scalar_one()
    role_codes = [r.code for r in refreshed.roles]
    assert role_codes.count("financier") == 1


async def test_rbe_preserves_admin_assigned_roles(db, make_user):
    """Admin manually assigned 'admin' → RBE adds 'financier' but keeps 'admin'."""
    pwd = "TestPa$$w0rdQ7K"
    await make_user(email="carol@example.com", password=pwd, role_codes=["admin"])
    await _make_rbe(db, email="carol@example.com", role_codes=["financier"])

    user, _, _ = await _authenticate(db, email="carol@example.com", password=pwd)
    role_codes = {r.code for r in user.roles}
    assert role_codes == {"admin", "financier"}


async def test_rbe_fills_empty_department(db, make_user):
    pwd = "TestPa$$w0rdQ7K"
    await make_user(email="dan@example.com", password=pwd, role_codes=[])
    await _make_rbe(db, email="dan@example.com", role_codes=["organization"], department="Finance")

    user, _, _ = await _authenticate(db, email="dan@example.com", password=pwd)
    assert user.department == "Finance"


async def test_rbe_does_not_overwrite_existing_department(db, make_user):
    pwd = "TestPa$$w0rdQ7K"
    from app.models.user import User
    from sqlalchemy import update
    u = await make_user(email="ed@example.com", password=pwd, role_codes=[])
    await db.execute(update(User).where(User.id == u.id).values(department="Manually-set"))
    await db.commit()
    await _make_rbe(db, email="ed@example.com", role_codes=["organization"], department="Finance")

    user, _, _ = await _authenticate(db, email="ed@example.com", password=pwd)
    assert user.department == "Manually-set"


async def test_rbe_fills_empty_allowed_companies(db, make_user):
    pwd = "TestPa$$w0rdQ7K"
    await make_user(email="frank@example.com", password=pwd, role_codes=[])
    await _make_rbe(
        db, email="frank@example.com", role_codes=["organization"],
        allowed_companies=["company-a", "company-b"],
    )

    user, _, _ = await _authenticate(db, email="frank@example.com", password=pwd)
    assert user.allowed_companies == ["company-a", "company-b"]


async def test_no_rbe_means_no_changes(db, make_user):
    pwd = "TestPa$$w0rdQ7K"
    await make_user(email="grace@example.com", password=pwd, role_codes=["financier"])

    user, _, _ = await _authenticate(db, email="grace@example.com", password=pwd)
    role_codes = {r.code for r in user.roles}
    assert role_codes == {"financier"}


async def test_rbe_skips_unknown_role_codes(db, make_user):
    """Rule references role 'nonexistent' alongside 'financier' → only known
    role is added; auth doesn't fail."""
    pwd = "TestPa$$w0rdQ7K"
    await make_user(email="hank@example.com", password=pwd, role_codes=[])
    await _make_rbe(db, email="hank@example.com", role_codes=["financier", "doesnotexist"])

    user, _, _ = await _authenticate(db, email="hank@example.com", password=pwd)
    role_codes = {r.code for r in user.roles}
    assert role_codes == {"financier"}
