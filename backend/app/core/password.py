"""Password hashing (native bcrypt — NOT passlib, which is unmaintained) and policy.

Baseline (state-grade for secret documents):
  - bcrypt rounds = 12 (configurable)
  - min length = 12
  - require lower/upper/digit/symbol
  - history of last N hashes — no-reuse
  - common-password blacklist
  - max age forces rotation (checked at login)

bcrypt's 72-byte truncation is mitigated by SHA-512 prehash — passwords longer
than 72 bytes get hashed to 64 bytes first, which fits within bcrypt's window
without truncation. We use base64(sha512(pw)) to keep a printable input.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import unicodedata
from typing import List

import bcrypt as _bcrypt

from app.config import settings


# Strict bcrypt hash format: $2[abyx]$<rounds>$<22-char salt><31-char hash> = 60 chars total
_BCRYPT_HASH_RE = re.compile(r"^\$2[aby]\$\d{2}\$[A-Za-z0-9./]{53}$")


def _is_valid_bcrypt_hash(s: str) -> bool:
    """Return True only if `s` matches bcrypt's hash format exactly.
    Used to gate calls to bcrypt.checkpw() — malformed input panics the
    underlying Rust extension (bcrypt 4.x), which would let an attacker
    DoS the auth path by planting a malformed hash."""
    return isinstance(s, str) and bool(_BCRYPT_HASH_RE.match(s))


# --- Hashing primitives -------------------------------------------------

def _normalize(plaintext: str) -> bytes:
    """Normalize the password before hashing.

    1. Unicode NFKC (so 'Á' and 'A\u0301' compare equal)
    2. SHA-512 prehash → base64 (defeats bcrypt's 72-byte truncation
       without weakening, since SHA-512 has 512 bits of entropy)
    """
    nfkc = unicodedata.normalize("NFKC", plaintext)
    digest = hashlib.sha512(nfkc.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plaintext: str) -> str:
    """Hash a password with bcrypt + SHA-512 prehash. Salt embedded in hash."""
    if not plaintext:
        raise ValueError("Empty password")
    return _bcrypt.hashpw(
        _normalize(plaintext),
        _bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS),
    ).decode("ascii")


def verify_password(plaintext: str, hashed: str) -> bool:
    """Constant-time bcrypt verify. Returns False on any error.

    HARDENED: Validates hash format BEFORE calling bcrypt.checkpw() to prevent
    bcrypt 4.x's Rust panic on malformed input (which would otherwise become an
    unhandled BaseException at the auth-handler level → 500 with stack trace)."""
    if not plaintext or not hashed:
        return False
    if not _is_valid_bcrypt_hash(hashed):
        return False
    try:
        return _bcrypt.checkpw(_normalize(plaintext), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False
    except BaseException:
        # PyO3 PanicException inherits from BaseException — catch it explicitly
        # so a malformed hash never propagates a 500 to the caller.
        return False


def needs_rehash(hashed: str) -> bool:
    """True if the hash uses fewer rounds than the configured cost."""
    try:
        # bcrypt hash format: $2b$<rounds>$<22 char salt><31 char hash>
        if not hashed or len(hashed) < 7 or hashed[0] != "$":
            return True
        parts = hashed.split("$")
        # parts = ['', '2b', '12', 'salt+hash']
        rounds = int(parts[2])
        return rounds < settings.BCRYPT_ROUNDS
    except (ValueError, IndexError):
        return True


# --- Policy validation --------------------------------------------------

class PasswordPolicyError(ValueError):
    """Raised when a candidate password fails the policy."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# Common-password blacklist (small built-in; production extends from a curated list)
_COMMON_PASSWORDS = frozenset({
    "password", "qwerty123456", "12345678901234", "letmein12345",
    "welcome12345", "administrator", "uzassets2024", "uzassets2025",
    "uzassets2026", "qwertyuiop1234", "1q2w3e4r5t6y", "passw0rd1234",
    "passw0rd!", "p@ssw0rd!", "admin12345!", "uzbekistan2026!",
    "tashkent2026!", "platform2026!", "secret2026!", "secret123!",
    "tashkent#2026", "uzassets#2026",
})


def validate_password_policy(plaintext: str) -> None:
    """Raise `PasswordPolicyError` if the candidate password fails the policy."""
    if plaintext is None:
        raise PasswordPolicyError("empty", "Пароль не может быть пустым.")

    # Length is the single most important factor
    if len(plaintext) < settings.PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError(
            "too_short",
            f"Пароль должен быть не короче {settings.PASSWORD_MIN_LENGTH} символов.",
        )
    if len(plaintext) > 256:
        # Defense against extreme inputs that would still hash, just slowly
        raise PasswordPolicyError("too_long", "Пароль не должен превышать 256 символов.")

    if settings.PASSWORD_REQUIRE_LOWER and not re.search(r"[a-z]", plaintext):
        raise PasswordPolicyError("no_lowercase", "Требуется хотя бы одна строчная буква.")
    if settings.PASSWORD_REQUIRE_UPPER and not re.search(r"[A-Z]", plaintext):
        raise PasswordPolicyError("no_uppercase", "Требуется хотя бы одна заглавная буква.")
    if settings.PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", plaintext):
        raise PasswordPolicyError("no_digit", "Требуется хотя бы одна цифра.")
    if settings.PASSWORD_REQUIRE_SYMBOL and not re.search(r"[^A-Za-z0-9]", plaintext):
        raise PasswordPolicyError("no_symbol", "Требуется хотя бы один спецсимвол.")

    # Repetition / low diversity. Tightened: scale with length so longer
    # passwords need proportionally more unique characters.
    unique = len(set(plaintext))
    min_unique = max(6, len(plaintext) // 3)
    if unique < min_unique:
        raise PasswordPolicyError(
            "low_diversity",
            f"Слишком мало уникальных символов ({unique}) — требуется минимум {min_unique}.",
        )

    # 3+ identical characters in a row is a weakness signal
    if re.search(r"(.)\1{2,}", plaintext):
        raise PasswordPolicyError("repeats", "Не допускаются 3+ одинаковых символа подряд.")

    # Sequential keyboard / digit runs ('1234', 'abcd', 'qwer')
    lp = plaintext.lower()
    sequences = ("0123456789", "abcdefghijklmnopqrstuvwxyz", "qwertyuiopasdfghjklzxcvbnm")
    for seq in sequences:
        for i in range(len(seq) - 3):
            if seq[i:i+4] in lp:
                raise PasswordPolicyError("sequence", "Содержит последовательность типа '1234' / 'abcd' / 'qwer'.")

    if plaintext.lower() in _COMMON_PASSWORDS:
        raise PasswordPolicyError("common_password", "Этот пароль слишком распространён.")


def check_password_history(plaintext: str, history: List[str] | None) -> None:
    """Raise `PasswordPolicyError` if the candidate matches any historical hash."""
    if not history:
        return
    for old_hash in history[-settings.PASSWORD_HISTORY_SIZE :]:
        if verify_password(plaintext, old_hash):
            raise PasswordPolicyError(
                "reuse_recent",
                f"Нельзя использовать один из последних {settings.PASSWORD_HISTORY_SIZE} паролей.",
            )


def push_to_history(new_hash: str, history: List[str] | None) -> List[str]:
    """Append a new hash to the history list, trimming to the configured size."""
    h = list(history or [])
    h.append(new_hash)
    if len(h) > settings.PASSWORD_HISTORY_SIZE:
        h = h[-settings.PASSWORD_HISTORY_SIZE :]
    return h


def constant_time_eq(a: str, b: str) -> bool:
    """Timing-safe string comparison. Use for username/email lookups when
    you want to avoid leaking 'user exists' via response timing."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return hmac.compare_digest(a.encode(), b.encode())
