"""Минимальный in-process TTL-кеш (single-worker).

Для тяжёлых read-only агрегатов, которые меняются медленно и допускают
ограниченное устаревание (напр. Executive Dashboard). НЕ для транзакционных
данных. Один воркер → один общий кеш на процесс; thread-safe не требуется,
т.к. get/set синхронны и не содержат await (asyncio single-loop).

Инвалидация — по TTL (без явного busting): простота важнее мгновенной
свежести для обзорных дашбордов.
"""
from __future__ import annotations

import time
from typing import Any, Hashable, Optional


class TTLCache:
    def __init__(self, ttl_seconds: float, max_entries: int = 256) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: dict[Hashable, tuple[float, Any]] = {}

    def get(self, key: Hashable) -> Optional[Any]:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.monotonic():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: Hashable, value: Any) -> None:
        # Грубая эвикция: при переполнении сбрасываем уже истёкшие, затем —
        # произвольную запись. Кеш мал (несколько ключей), сложный LRU излишен.
        if len(self._store) >= self._max:
            now = time.monotonic()
            for k, (exp, _) in list(self._store.items()):
                if exp < now:
                    self._store.pop(k, None)
            if len(self._store) >= self._max:
                self._store.pop(next(iter(self._store)), None)
        self._store[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._store.clear()
