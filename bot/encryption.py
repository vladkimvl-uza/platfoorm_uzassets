"""Fernet symmetric encryption (shared with backend's app.core.encryption).

Bot only needs DECRYPT (to read chat_id from users.telegram_chat_id_encrypted).
The encrypt path is on backend side (when /mfa/link-telegram is called and
later when init_link_telegram stores the chat_id).
"""
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, MultiFernet, InvalidToken

import config


@lru_cache(maxsize=1)
def _fernet() -> Fernet | MultiFernet:
    keys = [k.strip() for k in config.ENCRYPTION_KEY.split(",") if k.strip()]
    fernets = [Fernet(k.encode()) for k in keys]
    if len(fernets) == 1:
        return fernets[0]
    return MultiFernet(fernets)


def decrypt(token: Optional[bytes]) -> Optional[str]:
    if token is None:
        return None
    if isinstance(token, memoryview):
        token = bytes(token)
    return _fernet().decrypt(token).decode("utf-8")


def decrypt_int(token: Optional[bytes]) -> Optional[int]:
    s = decrypt(token)
    return int(s) if s else None


def encrypt(value: Optional[str]) -> Optional[bytes]:
    if value is None:
        return None
    return _fernet().encrypt(value.encode("utf-8"))


def encrypt_int(value: Optional[int]) -> Optional[bytes]:
    if value is None:
        return None
    return encrypt(str(value))
