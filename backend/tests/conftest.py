"""Test infrastructure for UzAssets backend.

Two layers:

1) **Unit tests** (`@pytest.mark.unit`): pure-function tests against helpers in
   `app.core.security` / `app.core.access`. No DB, no testcontainers. Fast.

2) **Integration tests** (`@pytest.mark.integration`): full FastAPI app against
   a fresh Postgres container (testcontainers), schema applied via alembic.

Both layers share a tmp set of test keys (RSA, Fernet, HMAC), generated in
`pytest_configure` BEFORE `app.*` imports happen. This avoids the need to ship
production keys in the repo, and isolates each test run from any local state.

Required env (auto-set if missing):
    JWT_PRIVATE_KEY_PATH, JWT_PUBLIC_KEY_PATH, FERNET_KEY_PATH,
    AUDIT_HMAC_SECRET_PATH, DATABASE_URL, DATABASE_URL_SYNC.

CI can pre-set them to skip container boot (e.g. shared pg).
"""
from __future__ import annotations

import os
import secrets
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from typing import AsyncGenerator, Optional

import pytest
import pytest_asyncio


# =====================================================================
# Phase 1: BEFORE any app.* import — set env vars
# pytest_configure runs once per session at the very start.
# =====================================================================

_TMP_KEYS_DIR: Optional[Path] = None
_PG_CONTAINER = None  # lazy: only when integration tests run


def _generate_test_keys(target: Path) -> None:
    """Generate fresh RSA pair + Fernet + HMAC keys into `target`."""
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    target.mkdir(parents=True, exist_ok=True)

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (target / "jwt_private.pem").write_bytes(
        priv.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    (target / "jwt_public.pem").write_bytes(
        priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    (target / "fernet.key").write_bytes(Fernet.generate_key())
    (target / "audit_hmac.key").write_bytes(secrets.token_bytes(32))


def pytest_configure(config):
    """Set up isolated test env BEFORE pytest collects tests.

    The `app.config.Settings()` is module-level — once imported it caches.
    So we must set env vars here. Also generate keys; production keys
    are gitignored and not available in CI.
    """
    global _TMP_KEYS_DIR

    if not os.environ.get("JWT_PRIVATE_KEY_PATH"):
        _TMP_KEYS_DIR = Path(tempfile.mkdtemp(prefix="uzassets-test-keys-"))
        _generate_test_keys(_TMP_KEYS_DIR)
        os.environ["JWT_PRIVATE_KEY_PATH"] = str(_TMP_KEYS_DIR / "jwt_private.pem")
        os.environ["JWT_PUBLIC_KEY_PATH"] = str(_TMP_KEYS_DIR / "jwt_public.pem")
        os.environ["FERNET_KEY_PATH"] = str(_TMP_KEYS_DIR / "fernet.key")
        os.environ["AUDIT_HMAC_SECRET_PATH"] = str(_TMP_KEYS_DIR / "audit_hmac.key")

    # Defaults for unit tests that touch settings but never connect to DB.
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://placeholder:placeholder@127.0.0.1:1/none",
    )
    os.environ.setdefault(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg://placeholder:placeholder@127.0.0.1:1/none",
    )
    os.environ.setdefault("JWT_ALGORITHM", "RS256")
    os.environ.setdefault("ENVIRONMENT", "test")
    os.environ.setdefault("RATE_LIMIT_ENABLED", "False")


def pytest_unconfigure(config):
    """Stop pg container (if started) and clean tmp keys."""
    global _PG_CONTAINER
    if _PG_CONTAINER is not None:
        try:
            _PG_CONTAINER.stop()
        except Exception:
            pass
        _PG_CONTAINER = None


# =====================================================================
# Phase 2: lightweight unit-test helpers (no DB needed)
# =====================================================================

class _RoleStub:
    """Mimic SQLAlchemy Role with .code + .permissions for sync checks."""
    def __init__(self, code: str, perms: tuple[str, ...] = ()):
        self.code = code
        self.permissions = [_PermStub(p) for p in perms]


class _PermStub:
    def __init__(self, code: str):
        self.code = code


class _UserStub:
    """Mimic User for `is_super_admin` / `_has_permission` checks.

    Use the `make_user_stub` factory below for tests."""
    def __init__(
        self,
        *,
        is_owner: bool = False,
        is_active: bool = True,
        roles: tuple[_RoleStub, ...] = (),
        allowed_companies: Optional[list] = None,
        organization_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        email: str = "u@test",
    ):
        self.id = user_id or uuid.uuid4()
        self.email = email
        self.is_owner = is_owner
        self.is_active = is_active
        self.roles = list(roles)
        self.allowed_companies = allowed_companies
        self.organization_id = organization_id


@pytest.fixture
def make_user_stub():
    """Factory for in-memory user-like objects (no DB)."""
    def _make(**kwargs) -> _UserStub:
        # Convert "roles=[('admin', ('admin.users',))]" syntax
        if "roles" in kwargs and kwargs["roles"]:
            kwargs["roles"] = tuple(
                _RoleStub(r[0], r[1] if len(r) > 1 else ())
                if isinstance(r, tuple) else _RoleStub(r)
                for r in kwargs["roles"]
            )
        return _UserStub(**kwargs)
    return _make


# =====================================================================
# Phase 3: integration — Postgres testcontainer + app + async client
# =====================================================================

_MIN_PERMS = [
    # (code, module, action, name)
    ("admin.users",          "admin",       "users",  "Manage users"),
    ("companies.view",       "companies",   "view",   "View companies"),
    ("companies.view_all",   "companies",   "view",   "View all companies (bypass scope)"),
    ("kpi.view",             "kpi",         "view",   "View KPI"),
    ("kpi.edit",             "kpi",         "edit",   "Edit KPI"),
    ("kpi.delete",           "kpi",         "delete", "Delete KPI"),
    ("bp.view",              "bp",          "view",   "View BP"),
    ("bp.edit",              "bp",          "edit",   "Edit BP"),
    ("bp.delete",            "bp",          "delete", "Delete BP"),
    ("tasks.view",           "tasks",       "view",   "View tasks"),
]

_MIN_ROLES = [
    ("admin",         "Администратор", True),
    ("organization",  "Сотрудник компании", True),
    ("financier",     "Финансист", False),
]


def _import_all_models() -> None:
    """Force-import every module under app.models so SQLAlchemy resolves
    cross-table FKs (e.g. users.partner_id → integration_partner) at
    metadata-build time. app.models.__init__ only imports a subset."""
    import importlib
    import pkgutil
    import app.models as _models_pkg
    for _f, name, _is_pkg in pkgutil.iter_modules(_models_pkg.__path__):
        try:
            importlib.import_module(f"app.models.{name}")
        except Exception:
            pass


def _create_schema_and_seed(sync_url: str) -> None:
    """Create schema from current SQLAlchemy models, seed minimal RBAC data."""
    from sqlalchemy import create_engine, text
    from app.database import Base

    _import_all_models()

    eng = create_engine(sync_url)
    Base.metadata.create_all(eng)

    with eng.begin() as conn:
        # Permissions
        for code, module, action, name in _MIN_PERMS:
            conn.execute(
                text("""
                    INSERT INTO permissions (id, code, name, module, action, created_at, updated_at)
                    VALUES (gen_random_uuid(), :code, :name, :module, :action, now(), now())
                    ON CONFLICT (code) DO NOTHING
                """),
                {"code": code, "name": name, "module": module, "action": action},
            )
        # Roles
        for code, name_ru, is_system in _MIN_ROLES:
            conn.execute(
                text("""
                    INSERT INTO roles (id, code, name_ru, is_system, is_active, sort_order, created_at, updated_at)
                    VALUES (gen_random_uuid(), :code, :name_ru, :is_system, true, 100, now(), now())
                    ON CONFLICT (code) DO NOTHING
                """),
                {"code": code, "name_ru": name_ru, "is_system": is_system},
            )
        # admin role gets every permission
        conn.execute(text("""
            INSERT INTO role_permission (role_id, permission_id)
            SELECT r.id, p.id FROM roles r CROSS JOIN permissions p WHERE r.code = 'admin'
            ON CONFLICT DO NOTHING
        """))
        # financier role gets kpi.view + bp.view
        conn.execute(text("""
            INSERT INTO role_permission (role_id, permission_id)
            SELECT r.id, p.id FROM roles r JOIN permissions p
                ON p.code IN ('kpi.view', 'bp.view', 'companies.view')
            WHERE r.code = 'financier'
            ON CONFLICT DO NOTHING
        """))
    eng.dispose()


@pytest.fixture(scope="session")
def pg_container():
    """Start a fresh Postgres container OR use externally-provided DB.

    Schema is built from `Base.metadata.create_all()` plus a minimal seed
    (~10 permissions, 3 roles). We intentionally bypass alembic because
    historical migrations have interleaved seeds that fight each other on
    a fresh schema — tests cover the CURRENT model, not migration history.
    A separate `test_migrations.py` (todo) can pin migration correctness.
    """
    global _PG_CONTAINER

    placeholder = "placeholder:placeholder@127.0.0.1:1"
    external_db = placeholder not in os.environ.get("DATABASE_URL", "")

    if external_db:
        _create_schema_and_seed(os.environ["DATABASE_URL_SYNC"])
        yield None
        return

    from testcontainers.postgres import PostgresContainer

    _PG_CONTAINER = PostgresContainer("postgres:15-alpine")
    _PG_CONTAINER.start()
    raw = _PG_CONTAINER.get_connection_url()

    async_url = raw.replace("postgresql+psycopg2", "postgresql+asyncpg")
    sync_url = raw.replace("postgresql+psycopg2", "postgresql+psycopg")
    os.environ["DATABASE_URL"] = async_url
    os.environ["DATABASE_URL_SYNC"] = sync_url

    _create_schema_and_seed(sync_url)

    yield _PG_CONTAINER


def _db_available() -> bool:
    """Whether DATABASE_URL points at a real DB (not the placeholder)."""
    url = os.environ.get("DATABASE_URL", "")
    return "placeholder:placeholder@127.0.0.1:1" not in url


@pytest_asyncio.fixture
async def db(pg_container) -> AsyncGenerator:
    """Function-scoped session. Truncates tables BEFORE each test
    instead of after — so a failed test leaves data for postmortem.

    `pg_container` boots a fresh pg if no real DATABASE_URL was injected.
    If a real URL is set (e.g. via CI), `pg_container` is None but we still
    have a working DB.
    """
    if pg_container is None and not _db_available():
        pytest.skip("No DB available (set DATABASE_URL or enable docker for testcontainers)")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    engine = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Full reset between tests: tables + roles/permissions seed.
    # Without re-seeding role_permission, mutations from previous tests leak
    # (e.g. test A grants companies.view_all to 'financier', test B then
    # observes that role bypassing scope).
    async with engine.begin() as conn:
        for tbl in (
            "api_key",
            "user_sessions", "user_group", "user_role",
            "group_permission_grant",
            "role_by_email",
            "companies",
            "groups",
            "role_permission",
            "roles",
            "permissions",
        ):
            await conn.execute(text(f"DELETE FROM {tbl}"))
        await conn.execute(text(
            "DELETE FROM users WHERE email NOT IN ('owner@test.uzassets', 'v.kim@uz-assets.uz')"
        ))

        # Re-seed permissions + roles (mirrors _create_schema_and_seed).
        for code, module, action, name in _MIN_PERMS:
            await conn.execute(
                text("""
                    INSERT INTO permissions (id, code, name, module, action, created_at, updated_at)
                    VALUES (gen_random_uuid(), :code, :name, :module, :action, now(), now())
                """),
                {"code": code, "name": name, "module": module, "action": action},
            )
        for code, name_ru, is_system in _MIN_ROLES:
            await conn.execute(
                text("""
                    INSERT INTO roles (id, code, name_ru, is_system, is_active, sort_order, created_at, updated_at)
                    VALUES (gen_random_uuid(), :code, :name_ru, :is_system, true, 100, now(), now())
                """),
                {"code": code, "name_ru": name_ru, "is_system": is_system},
            )
        await conn.execute(text("""
            INSERT INTO role_permission (role_id, permission_id)
            SELECT r.id, p.id FROM roles r CROSS JOIN permissions p WHERE r.code = 'admin'
        """))
        await conn.execute(text("""
            INSERT INTO role_permission (role_id, permission_id)
            SELECT r.id, p.id FROM roles r JOIN permissions p
                ON p.code IN ('kpi.view', 'bp.view', 'companies.view')
            WHERE r.code = 'financier'
        """))

    async with Session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def app_client(db):
    """ASGI httpx client against the real FastAPI app.

    Each request gets a FRESH session (mirrors production `get_db`); without
    this the FastAPI handler sees SQLAlchemy identity-map cached objects from
    the test setup and our INSERTs are invisible.
    Both sessions point at the same Postgres test DB so data is visible
    after commits.
    """
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
    from app.main import app
    from app.database import get_db

    engine = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db():
        async with Session() as new_sess:
            try:
                yield new_sess
                await new_sess.commit()
            except Exception:
                await new_sess.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        await engine.dispose()


# =====================================================================
# Phase 4: user / role / token factories (DB-backed)
# =====================================================================

@pytest_asyncio.fixture
async def make_user(db):
    """Async factory creating a real User in the test DB.

    Usage:
        u = await make_user(
            email="alice@test",
            role_codes=["admin"],
            is_owner=False,
            allowed_companies=None,
        )
    """
    from app.core.password import hash_password
    from app.models.user import Role, User, user_role
    from sqlalchemy import select

    async def _make(
        *,
        email: Optional[str] = None,
        full_name: str = "Test User",
        password: str = "TestPa$$word!12345",
        role_codes: Optional[list[str]] = None,
        is_owner: bool = False,
        is_active: bool = True,
        allowed_companies: Optional[list] = None,
        organization_id: Optional[uuid.UUID] = None,
        is_service_account: bool = False,
    ) -> User:
        email = email or f"u-{uuid.uuid4().hex[:8]}@test"
        u = User(
            email=email.lower(),
            full_name=full_name,
            password_hash=hash_password(password),
            must_change_password=False,
            is_active=is_active,
            is_owner=is_owner,
            allowed_companies=allowed_companies,
            organization_id=organization_id,
            is_service_account=is_service_account,
        )
        db.add(u)
        await db.flush()

        if role_codes:
            roles = (await db.execute(
                select(Role).where(Role.code.in_(role_codes))
            )).scalars().all()
            for r in roles:
                await db.execute(
                    user_role.insert().values(user_id=u.id, role_id=r.id)
                )
        await db.commit()
        await db.refresh(u, ["roles"])
        return u

    return _make


@pytest.fixture
def auth_header():
    """Sync helper that issues a short-lived JWT for a given user."""
    def _make(user) -> dict[str, str]:
        from app.core import jwt as J
        token = J.create_access_token(
            subject=str(user.id),
            extra_claims={
                "email": user.email,
                "is_owner": bool(user.is_owner),
                "roles": [r.code for r in (user.roles or [])],
            },
        )
        return {"Authorization": f"Bearer {token}"}
    return _make
