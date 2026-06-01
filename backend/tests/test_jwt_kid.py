"""Tests for L7 — JWT decode rejects tokens without `kid` header.

This guards against silent key-rotation regressions: any future token-issuer
that forgets to set headers={"kid": _KID} will trip decode_token loudly.
"""
from datetime import UTC

import pytest

pytestmark = pytest.mark.unit


def test_self_issued_token_roundtrip():
    """Own create_access_token should always decode."""
    from app.core import jwt as J
    token = J.create_access_token(subject="00000000-0000-0000-0000-000000000000")
    claims = J.decode_token(token, expected_type="access")
    assert claims["sub"] == "00000000-0000-0000-0000-000000000000"


def test_decode_rejects_token_without_kid():
    """Hand-craft a JWT signed with the same key but no kid in header."""
    from datetime import datetime, timedelta

    import jwt as pyjwt

    from app.config import settings
    from app.core import jwt as J

    payload = {
        "sub": "00000000-0000-0000-0000-000000000000",
        "type": "access",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int(datetime.now(tz=UTC).timestamp()),
        "nbf": int(datetime.now(tz=UTC).timestamp()),
        "exp": int((datetime.now(tz=UTC) + timedelta(minutes=5)).timestamp()),
        "jti": "test",
    }
    bad = pyjwt.encode(
        payload,
        J._PRIVATE_KEY,
        algorithm=settings.JWT_ALGORITHM,
        # NOTE: no headers={"kid": ...}
    )
    with pytest.raises(pyjwt.InvalidTokenError, match="Missing kid"):
        J.decode_token(bad, expected_type="access")


def test_decode_rejects_token_with_unknown_kid():
    """Bogus kid header — even with correct signature."""
    from datetime import datetime, timedelta

    import jwt as pyjwt

    from app.config import settings
    from app.core import jwt as J

    payload = {
        "sub": "00000000-0000-0000-0000-000000000000",
        "type": "access",
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": int(datetime.now(tz=UTC).timestamp()),
        "nbf": int(datetime.now(tz=UTC).timestamp()),
        "exp": int((datetime.now(tz=UTC) + timedelta(minutes=5)).timestamp()),
        "jti": "test",
    }
    bad = pyjwt.encode(
        payload,
        J._PRIVATE_KEY,
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": "rs256-attacker-controlled", "typ": "JWT"},
    )
    with pytest.raises(pyjwt.InvalidTokenError, match="Unknown key id"):
        J.decode_token(bad, expected_type="access")
