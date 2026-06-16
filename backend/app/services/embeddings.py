"""Семантические эмбеддинги для базы знаний (Voyage AI).

Слой над лексическим FTS — даёт гибридный поиск (смысл + словоформы). Если
ключ VOYAGE_API_KEY не задан или провайдер недоступен, слой молча отключается,
а поиск падает обратно на чистый Postgres FTS.

Конфигурация (env):
  VOYAGE_API_KEY  — ключ (https://dashboard.voyageai.com)
  EMBED_MODEL     — модель эмбеддингов (по умолчанию voyage-3.5, multilingual)
  EMBED_DIM       — размерность вектора (256/512/1024/2048; по умолчанию 1024)

ВНИМАНИЕ: EMBED_DIM должен совпадать с размерностью колонки knowledge_chunk.embedding
(она фиксируется при миграции). Смена размерности требует ручного ALTER колонки.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_API_URL = "https://api.voyageai.com/v1/embeddings"
# Voyage допускает до 1000 строк за запрос, но ограничивает суммарные токены —
# режем на скромные батчи, чтобы не упираться в лимит на длинных чанках.
_BATCH = 96


def model() -> str:
    return os.environ.get("EMBED_MODEL", "voyage-3.5").strip() or "voyage-3.5"


def dim() -> int:
    try:
        return int(os.environ.get("EMBED_DIM", "1024"))
    except ValueError:
        return 1024


def is_enabled() -> bool:
    return bool(os.environ.get("VOYAGE_API_KEY", "").strip())


async def _embed(texts: list[str], input_type: str, timeout: float) -> list[list[float]]:
    key = os.environ.get("VOYAGE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("VOYAGE_API_KEY missing")
    out: list[list[float]] = []
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        for i in range(0, len(texts), _BATCH):
            part = texts[i:i + _BATCH]
            resp = await client.post(_API_URL, headers=headers, json={
                "input": part,
                "model": model(),
                "input_type": input_type,
                "output_dimension": dim(),
            })
            resp.raise_for_status()
            data = resp.json().get("data", [])
            # порядок не гарантирован — сортируем по index
            data.sort(key=lambda d: d.get("index", 0))
            out.extend(d["embedding"] for d in data)
    return out


async def embed_documents(texts: list[str], timeout: float = 60.0) -> list[list[float]]:
    """Эмбеддинги для индексации (input_type=document)."""
    if not texts:
        return []
    return await _embed(texts, "document", timeout)


async def embed_query(query: str, timeout: float = 20.0) -> list[float]:
    """Эмбеддинг поискового запроса (input_type=query)."""
    if not (query or "").strip():
        return []
    res = await _embed([query], "query", timeout)
    return res[0] if res else []


def to_pgvector(vec: list[float]) -> str:
    """Сериализация вектора в литерал pgvector: [0.1,0.2,...]."""
    return "[" + ",".join(str(float(x)) for x in vec) + "]"
