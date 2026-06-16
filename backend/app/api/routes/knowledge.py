"""Knowledge base (RAG) — загрузка/список/удаление документов.

Текст извлекается, режется на чанки и индексируется Postgres FTS (tsv заполняет
триггер). Ассистент ищет по базе инструментом search_knowledge_base.
Управление — только super-admin/owner.
"""
from __future__ import annotations

import io
import re
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import is_super_admin
from app.models.knowledge import KnowledgeChunk, KnowledgeDoc
from app.models.user import User

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

MAX_BYTES = 8_000_000
CHUNK_SIZE = 900


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not is_super_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступ только для администратора")
    return user


def _extract_text(filename: Optional[str], raw: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        try:
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            parts: list[str] = []
            for ws in wb.worksheets:
                parts.append(f"# Лист: {ws.title}")
                for row in ws.iter_rows(values_only=True):
                    cells = [str(c) for c in row if c is not None]
                    if cells:
                        parts.append(" | ".join(cells))
            return "\n".join(parts)
        except Exception:
            return ""
    for enc in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _chunk(text: str, size: int = CHUNK_SIZE) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks: list[str] = []
    buf = ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) + 2 <= size:
            buf = (buf + "\n\n" + para).strip()
        else:
            if buf:
                chunks.append(buf)
                buf = ""
            if len(para) <= size:
                buf = para
            else:
                for i in range(0, len(para), size):
                    chunks.append(para[i:i + size])
    if buf:
        chunks.append(buf)
    return chunks[:2000]


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Файл больше 8 МБ")
    text = _extract_text(file.filename, raw)
    chunks = _chunk(text)
    if not chunks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Не удалось извлечь текст из файла")
    doc = KnowledgeDoc(
        title=(title or file.filename or "Документ")[:512],
        filename=file.filename,
        content_type=file.content_type,
        char_count=len(text),
        chunk_count=len(chunks),
        uploaded_by=user.id,
    )
    db.add(doc)
    await db.flush()
    for i, c in enumerate(chunks):
        db.add(KnowledgeChunk(doc_id=doc.id, chunk_index=i, content=c))
    await db.commit()
    return {"id": str(doc.id), "title": doc.title, "chunks": len(chunks), "chars": len(text)}


@router.get("")
async def list_docs(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(KnowledgeDoc).order_by(KnowledgeDoc.created_at.desc()),
    )).scalars().all()
    return [{
        "id": str(d.id), "title": d.title, "filename": d.filename,
        "chunks": d.chunk_count, "chars": d.char_count,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    } for d in rows]


@router.delete("/{doc_id}")
async def delete_doc(
    doc_id: UUID,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    d = await db.get(KnowledgeDoc, doc_id)
    if d:
        await db.delete(d)
        await db.commit()
    return {"ok": True}
