"""Крипто-провайдер (СКЗИ seam).

Единая точка абстракции над криптопримитивами платформы, позволяющая
подменить встроенную крипту на СЕРТИФИЦИРОВАННОЕ СКЗИ с национальными
алгоритмами Узбекистана:
  * O'zMSt 270:2024 — алгоритм шифрования данных (MShA, блок 256);
  * O'zMSt 285:2024 — функция хэширования (дайджест 256);
  * требование O'zMSt 149 пп.6.17, 7.4, 8.3 — применять сертифицированные
    средства криптозащиты для конфиденциальной/государственной информации.

ВАЖНО (статус соответствия):
  - Провайдер ``default`` использует встроенные Fernet (AES-128-CBC+HMAC),
    SHA-256, HMAC-SHA256. Это НЕ сертифицированное СКЗИ и НЕ нацалгоритмы —
    пригодно для разработки и негосударственных данных.
  - Провайдер ``national`` — адаптер к внешнему сертифицированному
    криптомодулю (E-IMZO / PKCS#11 / HTTP-шлюз DTS). По умолчанию методы
    шифрования/хэширования поднимают ``NotImplementedError`` с явным
    указанием, что нужно подключить сертифицированный модуль.

Это АДДИТИВНЫЙ seam: модуль НЕ меняет текущие вызовы крипты в коде. Чтобы
перевести систему на СКЗИ, точки вызова (encryption.py, password.py,
audit_chain.py) постепенно маршрутизируются через ``get_crypto_provider()``.
"""
from __future__ import annotations

import abc
import hashlib
import hmac
from typing import Optional

from app.config import settings


class CryptoProvider(abc.ABC):
    """Контракт крипто-провайдера. Все байтовые операции — bytes-in/bytes-out;
    строковые обёртки шифрования совместимы с app.core.encryption."""

    #: Машинное имя провайдера (default | national).
    name: str = "abstract"
    #: Является ли провайдер сертифицированным СКЗИ с нацалгоритмами.
    certified: bool = False
    #: Человеко-читаемое описание используемых алгоритмов.
    algorithms: str = ""

    # --- симметричное шифрование (конфиденциальность at-rest) ---
    @abc.abstractmethod
    def encrypt_str(self, plaintext: Optional[str]) -> Optional[bytes]:
        """Зашифровать строку. None → None."""

    @abc.abstractmethod
    def decrypt_str(self, token: Optional[bytes]) -> Optional[str]:
        """Расшифровать токен. None → None."""

    # --- хэширование (целостность, дайджесты) ---
    @abc.abstractmethod
    def digest(self, data: bytes) -> bytes:
        """Криптографический хэш данных."""

    # --- имитозащита / подпись на симметричном ключе ---
    @abc.abstractmethod
    def mac(self, key: bytes, data: bytes) -> bytes:
        """Код аутентификации сообщения (MAC) на ключе."""

    def mac_verify(self, key: bytes, data: bytes, tag: bytes) -> bool:
        """Проверка MAC в постоянном времени."""
        return hmac.compare_digest(self.mac(key, data), tag)


class DefaultCryptoProvider(CryptoProvider):
    """Встроенная крипта (Fernet / SHA-256 / HMAC-SHA256).

    НЕ сертифицирована и НЕ реализует нацалгоритмы 270/285 — это базовая
    защита для dev и негосударственных данных.
    """

    name = "default"
    certified = False
    algorithms = "Fernet(AES-128-CBC+HMAC-SHA256) / SHA-256 / HMAC-SHA256"

    def encrypt_str(self, plaintext: Optional[str]) -> Optional[bytes]:
        from app.core.encryption import encrypt as _encrypt
        return _encrypt(plaintext)

    def decrypt_str(self, token: Optional[bytes]) -> Optional[str]:
        from app.core.encryption import decrypt as _decrypt
        return _decrypt(token)

    def digest(self, data: bytes) -> bytes:
        return hashlib.sha256(data).digest()

    def mac(self, key: bytes, data: bytes) -> bytes:
        return hmac.new(key, data, hashlib.sha256).digest()


class NationalCryptoProvider(CryptoProvider):
    """Адаптер к сертифицированному СКЗИ с нацалгоритмами 270/285.

    Реализация проксирует операции во внешний криптомодуль (E-IMZO,
    PKCS#11-токен или HTTP-шлюз DTS, см. ``CRYPTO_NATIONAL_GATEWAY_URL``).
    До подключения модуля операции явно не реализованы — это «обозначенный
    seam», который не даёт молча использовать несертифицированную крипту,
    думая, что работает нацалгоритм.
    """

    name = "national"
    certified = True
    algorithms = "O'zMSt 270 (MShA-256) / O'zMSt 285 (hash-256) через сертиф. СКЗИ"

    def _gateway(self) -> str:
        url = (settings.CRYPTO_NATIONAL_GATEWAY_URL or "").strip()
        if not url:
            raise NotImplementedError(
                "CRYPTO_PROVIDER=national, но CRYPTO_NATIONAL_GATEWAY_URL не задан. "
                "Подключите сертифицированное СКЗИ (E-IMZO / PKCS#11 / HTTP-шлюз DTS), "
                "реализующее O'zMSt 270 (шифрование) и O'zMSt 285 (хэш)."
            )
        return url

    def encrypt_str(self, plaintext: Optional[str]) -> Optional[bytes]:
        if plaintext is None:
            return None
        self._gateway()
        raise NotImplementedError(
            "Нацшифрование (O'zMSt 270) выполняется в сертифицированном СКЗИ — "
            "реализуйте вызов криптомодуля в NationalCryptoProvider.encrypt_str()."
        )

    def decrypt_str(self, token: Optional[bytes]) -> Optional[str]:
        if token is None:
            return None
        self._gateway()
        raise NotImplementedError(
            "Нацрасшифрование (O'zMSt 270) выполняется в сертифицированном СКЗИ — "
            "реализуйте вызов криптомодуля в NationalCryptoProvider.decrypt_str()."
        )

    def digest(self, data: bytes) -> bytes:
        self._gateway()
        raise NotImplementedError(
            "Нацхэш (O'zMSt 285) выполняется в сертифицированном СКЗИ — "
            "реализуйте вызов криптомодуля в NationalCryptoProvider.digest()."
        )

    def mac(self, key: bytes, data: bytes) -> bytes:
        self._gateway()
        raise NotImplementedError(
            "Имитозащита по нацалгоритму (O'zMSt 285, Алгоритм 1) выполняется в "
            "сертифицированном СКЗИ — реализуйте вызов в NationalCryptoProvider.mac()."
        )


_PROVIDERS: dict[str, type[CryptoProvider]] = {
    "default": DefaultCryptoProvider,
    "national": NationalCryptoProvider,
}

_instance: Optional[CryptoProvider] = None


def get_crypto_provider() -> CryptoProvider:
    """Возвращает (кэширует) активный крипто-провайдер по settings.CRYPTO_PROVIDER."""
    global _instance
    if _instance is None or _instance.name != settings.CRYPTO_PROVIDER:
        cls = _PROVIDERS.get(settings.CRYPTO_PROVIDER, DefaultCryptoProvider)
        _instance = cls()
    return _instance


def crypto_compliance_status() -> dict:
    """Диагностика соответствия крипты (для /health/security или аудита)."""
    p = get_crypto_provider()
    return {
        "provider": p.name,
        "certified_szki": p.certified,
        "algorithms": p.algorithms,
        "national_crypto_270_285": p.certified,
        "note": (
            "Соответствует O'zMSt 270/285" if p.certified
            else "НЕ сертифицировано: встроенная крипта, не нацалгоритмы 270/285"
        ),
    }
