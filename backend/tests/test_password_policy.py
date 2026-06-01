"""Unit tests for password policy + bcrypt verify (no DB).

Covers `validate_password_policy`, `verify_password` (malformed hash
defense), `needs_rehash`, `push_to_history`.
"""
import pytest

pytestmark = pytest.mark.unit


# ─── validate_password_policy: positive cases ────────────────────────

def test_strong_password_accepted():
    from app.core.password import validate_password_policy
    validate_password_policy("Q9k!#mB7vN$wL2pR")  # no raise


def test_strong_password_no_sequence_variant():
    from app.core.password import validate_password_policy
    # 12+ chars, mix, no sequence, no repeat
    validate_password_policy("Zm@Tp7K!hxNyQ")


# ─── validate_password_policy: rejection cases ───────────────────────

def test_too_short():
    from app.core.password import PasswordPolicyError, validate_password_policy
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy("Sh0rt!Aa")  # 8 chars, < 12
    assert exc.value.code == "too_short"


def test_too_long():
    from app.core.password import PasswordPolicyError, validate_password_policy
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy("Ab1!" * 100)  # > 256
    assert exc.value.code == "too_long"


def test_no_lowercase():
    from app.core.password import PasswordPolicyError, validate_password_policy
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy("ALLCAPS@#$%X7K")
    assert exc.value.code == "no_lowercase"


def test_no_uppercase():
    from app.core.password import PasswordPolicyError, validate_password_policy
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy("alllower@#$%x7k")
    assert exc.value.code == "no_uppercase"


def test_no_digit():
    from app.core.password import PasswordPolicyError, validate_password_policy
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy("OnlyLetters!@#X")
    assert exc.value.code == "no_digit"


def test_no_symbol():
    from app.core.password import PasswordPolicyError, validate_password_policy
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy("LettersAnd9Digits")
    assert exc.value.code == "no_symbol"


def test_three_repeated_chars():
    from app.core.password import PasswordPolicyError, validate_password_policy
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy("Aaaa1!bcDefGhJk")  # "aaaa"
    assert exc.value.code == "repeats"


def test_digit_sequence_rejected():
    from app.core.password import PasswordPolicyError, validate_password_policy
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy("StrongPa$$w0rd!1234")  # 1234
    assert exc.value.code == "sequence"


def test_qwerty_sequence_rejected():
    from app.core.password import PasswordPolicyError, validate_password_policy
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy("StrongPa$$wQwer!K7")
    assert exc.value.code == "sequence"


def test_low_diversity_rejected():
    from app.core.password import PasswordPolicyError, validate_password_policy
    # 14 chars but only 4 unique
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy("aB1!aB1!aB1!aB")
    assert exc.value.code == "low_diversity"


def test_common_password_rejected():
    from app.core.password import PasswordPolicyError, validate_password_policy
    # "uzassets#2026" is in the _COMMON_PASSWORDS blacklist (13 chars,
    # passes length and char-class checks)
    with pytest.raises(PasswordPolicyError) as exc:
        validate_password_policy("Uzassets#2026")
    # Could trip either common_password or sequence — both are legit reasons.
    assert exc.value.code in ("common_password", "sequence")


# ─── verify_password: defense against malformed hash ─────────────────

def test_verify_malformed_hash_returns_false():
    from app.core.password import verify_password
    # bcrypt 4.x panics on malformed input; verify_password must catch it.
    assert verify_password("anything", "not_a_bcrypt_hash") is False
    assert verify_password("anything", "") is False
    assert verify_password("anything", "$invalid") is False


def test_verify_correct_password_works():
    from app.core.password import hash_password, verify_password
    h = hash_password("Q9k!#mB7vN$wL2pR")
    assert verify_password("Q9k!#mB7vN$wL2pR", h) is True
    assert verify_password("wrong-password", h) is False


def test_hash_password_each_time_different_salt():
    from app.core.password import hash_password
    a = hash_password("Q9k!#mB7vN$wL2pR")
    b = hash_password("Q9k!#mB7vN$wL2pR")
    assert a != b  # different salts


# ─── needs_rehash ────────────────────────────────────────────────────

def test_needs_rehash_with_current_cost():
    from app.core.password import hash_password, needs_rehash
    h = hash_password("Q9k!#mB7vN$wL2pR")
    assert needs_rehash(h) is False


def test_needs_rehash_with_lower_cost():
    """Synthesize a hash with cost=4; needs_rehash should fire."""
    import bcrypt

    from app.core.password import _normalize, needs_rehash
    h_low = bcrypt.hashpw(_normalize("Q9k!#mB7vN$wL2pR"), bcrypt.gensalt(rounds=4)).decode()
    assert needs_rehash(h_low) is True


def test_needs_rehash_malformed():
    from app.core.password import needs_rehash
    assert needs_rehash("") is True
    assert needs_rehash("garbage") is True
    assert needs_rehash("$$bad$$") is True


# ─── push_to_history ────────────────────────────────────────────────

def test_push_to_history_trims():
    from app.config import settings
    from app.core.password import push_to_history
    # Build a history at exactly the limit
    hist = [f"hash_{i}" for i in range(settings.PASSWORD_HISTORY_SIZE)]
    new = push_to_history("hash_new", hist)
    assert len(new) == settings.PASSWORD_HISTORY_SIZE
    assert "hash_new" in new
    # Oldest dropped
    assert "hash_0" not in new


def test_push_to_history_from_empty():
    from app.core.password import push_to_history
    assert push_to_history("h1", None) == ["h1"]
    assert push_to_history("h1", []) == ["h1"]


def test_check_password_history_blocks_recent():
    from app.core.password import PasswordPolicyError, check_password_history, hash_password
    h1 = hash_password("Q9k!#mB7vN$wL2pR")
    with pytest.raises(PasswordPolicyError) as exc:
        check_password_history("Q9k!#mB7vN$wL2pR", [h1])
    assert exc.value.code == "reuse_recent"


def test_check_password_history_allows_different():
    from app.core.password import check_password_history, hash_password
    h1 = hash_password("Q9k!#mB7vN$wL2pR")
    # different password — must not raise
    check_password_history("XYZ#different!Pa", [h1])
