"""Библиотека документов компании — вкладка «Документы» + сквозные привязки.

Один файл хранится один раз (`documents`) и показывается везде, куда привязан
(`document_links`): в библиотеке компании И в карточке задачи/проекта/отчёта.

  GET    /documents/{code}/tree                папки компании (дерево)
  POST   /documents/{code}/folders             создать папку
  PATCH  /documents/{code}/folders/{id}        переименовать / переместить
  DELETE /documents/{code}/folders/{id}        удалить (пустую, не системную)
  GET    /documents/{code}/items               файлы: папка / поиск / привязка
  POST   /documents/{code}/upload              загрузить (multipart)
  PATCH  /documents/{code}/items/{id}          переименовать / переместить
  DELETE /documents/{code}/items/{id}          в корзину (soft) / ?hard=true
  POST   /documents/{code}/items/{id}/restore  вернуть из корзины
  GET    /documents/{code}/items/{id}/url      подписанная ссылка на скачивание
  POST   /documents/{code}/items/{id}/links    привязать к задаче/проекту/отчёту
  DELETE /documents/{code}/items/{id}/links/{link_id}  отвязать

Права: читать — доступ к компании; писать — по источнику файла
(task/project → tasks.edit, financials → financials.edit, library →
companies.edit). Проверка в одном месте: `_require_write`.
"""
from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi import status as http_status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.access import ensure_company_access
from app.core.i18n import current_locale, tr
from app.core.security import get_current_user, has_effective_permission
from app.database import get_db
from app.models.company import Company
from app.models.document import Document, DocumentFolder, DocumentLink
from app.models.user import User
from app.services.moderation_service import gate_or_apply
from app.services.storage import StorageError, get_storage

log = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

# Право на запись по источнику файла. Библиотека — часть карточки компании,
# поэтому её собственные файлы под companies.edit.
_WRITE_PERMISSION: dict[str, str] = {
    "library": "companies.edit",
    "task": "tasks.edit",
    "project": "tasks.edit",
    "financials": "financials.edit",
    "esg": "esg.edit",
    "governance": "governance.edit",
}
# Тип привязки → модуль-источник (и, значит, требуемое право).
_ENTITY_SOURCE: dict[str, str] = {
    "task": "task",
    "project": "project",
    "financial_report": "financials",
    "company": "library",
    # Документы этапа ESG-зрелости (климат/риски/ISO). Источник esg → право
    # esg.edit + системная папка «ESG». entity_id = "<dim>:<stageIdx>" (D4:1..4 /
    # D5:1..3 / D1:iso14001|iso45001|iso50001), без года (этапы программные).
    "esg_stage": "esg",
}
_MAX_UPLOAD_BYTES = 64 * 1024 * 1024      # 64 МБ на файл
_SAFE_NAME = re.compile(r"[\\/\x00-\x1f]")

# Группировка «по типу документа» — вторая (наряду с папками) структура
# библиотеки: пользователь ищет либо «где лежит», либо «что это за файл».
_KIND_EXT: dict[str, tuple[str, ...]] = {
    "pdf":   ("pdf",),
    "doc":   ("doc", "docx", "rtf", "odt"),
    "sheet": ("xls", "xlsx", "xlsm", "csv", "ods"),
    "slide": ("ppt", "pptx", "odp"),
    "image": ("png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "heic"),
    "archive": ("zip", "rar", "7z", "tar", "gz"),
}


def _kind_of(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    for kind, exts in _KIND_EXT.items():
        if ext in exts:
            return kind
    return "other"


_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _clean_color(value: Optional[str]) -> Optional[str]:
    """Только #RRGGBB — цвет приходит из фиксированной палитры фронта, но
    проверяем на сервере: поле уходит в style, произвольная строка там не нужна."""
    v = (value or "").strip()
    if not v:
        return None
    if not _HEX.match(v):
        raise HTTPException(
            http_status.HTTP_422_UNPROCESSABLE_ENTITY, "Цвет должен быть в формате #RRGGBB",
        )
    return v.upper()


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: Optional[UUID] = None
    color: Optional[str] = Field(default=None, max_length=9)


class FolderPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    parent_id: Optional[UUID] = None
    color: Optional[str] = Field(default=None, max_length=9)


class ItemPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=512)
    folder_id: Optional[UUID] = None
    description: Optional[str] = None


class LinkIn(BaseModel):
    entity_type: str = Field(max_length=32)
    entity_id: str = Field(max_length=128)
    label: Optional[str] = Field(default=None, max_length=255)


async def _company(db: AsyncSession, code: str, user: User) -> Company:
    co = (await db.execute(
        select(Company).where(Company.code == code.lower())
    )).scalar_one_or_none()
    if co is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Company not found")
    await ensure_company_access(db, user, co.id)
    return co


async def _require_write(db: AsyncSession, user: User, source: str) -> None:
    """Право на изменение файла = право поверхности, откуда он пришёл."""
    code = _WRITE_PERMISSION.get(source, "companies.edit")
    if await has_effective_permission(db, user, code):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        tr(
            "Недостаточно прав: требуется {permission}",
            current_locale(),
            permission=code,
        ),
    )


def _folder_out(f: DocumentFolder) -> dict:
    return {
        "id": str(f.id),
        "parent_id": str(f.parent_id) if f.parent_id else None,
        "name": f.name,
        "color": f.color,
        "system_key": f.system_key,
        "is_system": f.is_system,
    }


def _doc_out(d: Document, links: list[DocumentLink], uploader: Optional[str]) -> dict:
    return {
        "id": str(d.id),
        "name": d.name,
        "folder_id": str(d.folder_id) if d.folder_id else None,
        "mime_type": d.mime_type,
        "size_bytes": d.size_bytes,
        "description": d.description,
        "source_module": d.source_module,
        "kind": _kind_of(d.name),
        "ext": (d.name.rsplit(".", 1)[-1].lower() if "." in d.name else ""),
        "uploader_id": str(d.uploader_id) if d.uploader_id else None,
        "uploader_name": uploader,
        "is_deleted": d.is_deleted,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        "links": [
            {
                "id": str(x.id),
                "entity_type": x.entity_type,
                "entity_id": x.entity_id,
                "label": x.label,
            }
            for x in links
        ],
    }


async def _links_by_doc(db: AsyncSession, doc_ids: list[UUID]) -> dict[UUID, list[DocumentLink]]:
    if not doc_ids:
        return {}
    rows = (await db.execute(
        select(DocumentLink).where(DocumentLink.document_id.in_(doc_ids))
    )).scalars().all()
    out: dict[UUID, list[DocumentLink]] = {}
    for r in rows:
        out.setdefault(r.document_id, []).append(r)
    return out


async def _uploaders(db: AsyncSession, ids: list[UUID]) -> dict[UUID, str]:
    ids = [i for i in ids if i]
    if not ids:
        return {}
    rows = (await db.execute(
        select(User.id, User.full_name, User.email).where(User.id.in_(ids))
    )).all()
    return {r[0]: (r[1] or r[2]) for r in rows}


# ─── папки ────────────────────────────────────────────────────────

@router.get("/{code}/tree")
async def folder_tree(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    co = await _company(db, code, user)
    folders = (await db.execute(
        select(DocumentFolder)
        .where(DocumentFolder.company_id == co.id)
        .order_by(DocumentFolder.is_system.desc(), DocumentFolder.name)
    )).scalars().all()
    counts = dict((await db.execute(
        select(Document.folder_id, func.count())
        .where(Document.company_id == co.id, Document.is_deleted.is_(False))
        .group_by(Document.folder_id)
    )).all())
    root_total = (await db.execute(
        select(func.count()).select_from(Document)
        .where(Document.company_id == co.id, Document.is_deleted.is_(False))
    )).scalar() or 0
    trash_total = (await db.execute(
        select(func.count()).select_from(Document)
        .where(Document.company_id == co.id, Document.is_deleted.is_(True))
    )).scalar() or 0
    return {
        "company_code": co.code,
        "folders": [
            {**_folder_out(f), "file_count": int(counts.get(f.id, 0))} for f in folders
        ],
        "total_files": int(root_total),
        "trash_count": int(trash_total),
    }


@router.post("/{code}/folders", status_code=http_status.HTTP_201_CREATED)
async def create_folder(
    code: str,
    payload: FolderIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    co = await _company(db, code, user)
    await _require_write(db, user, "library")
    name = _SAFE_NAME.sub("", payload.name).strip()
    if not name:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "Пустое имя папки")
    dup = (await db.execute(
        select(DocumentFolder.id).where(
            DocumentFolder.company_id == co.id,
            DocumentFolder.parent_id.is_(payload.parent_id) if payload.parent_id is None
            else DocumentFolder.parent_id == payload.parent_id,
            func.lower(DocumentFolder.name) == name.lower(),
        )
    )).first()
    if dup:
        raise HTTPException(http_status.HTTP_409_CONFLICT, "Папка с таким именем уже есть")
    color = _clean_color(payload.color)
    # Модерация (deny-by-default): внешний автор → в очередь. Scope компании и
    # право (companies.edit) проверены ВЫШЕ. Новой папки ещё нет → entity_id=None;
    # apply-хендлер создаёт и штампует id.
    queued, sub = await gate_or_apply(
        db, user=user, module="documents", action="create",
        entity_id=None, entity_label=name,
        company_id=co.id, sector_id=None, year=None,
        payload={"op": "folder", "code": co.code, "name": name,
                 "parent_id": str(payload.parent_id) if payload.parent_id else None,
                 "color": color},
        diff_summary=f"Создание папки документов: {name}",
    )
    if queued:
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
    f = DocumentFolder(
        company_id=co.id, parent_id=payload.parent_id, name=name,
        color=color, is_system=False, created_by=user.id,
    )
    db.add(f)
    await db.commit()
    await db.refresh(f)
    return _folder_out(f)


@router.patch("/{code}/folders/{folder_id}")
async def patch_folder(
    code: str,
    folder_id: UUID,
    payload: FolderPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    co = await _company(db, code, user)
    await _require_write(db, user, "library")
    f = (await db.execute(
        select(DocumentFolder).where(
            DocumentFolder.id == folder_id, DocumentFolder.company_id == co.id,
        )
    )).scalar_one_or_none()
    if f is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Папка не найдена")
    if f.is_system and payload.name:
        raise HTTPException(
            http_status.HTTP_400_BAD_REQUEST, "Системную папку нельзя переименовать",
        )
    # Цвет валидируем/нормализуем ДО гейта (_clean_color 422-ит невалидный
    # #RRGGBB) — иначе одобрение внесло бы сырой цвет в обход проверки прямого пути.
    cleaned_color = _clean_color(payload.color) if payload.color is not None else None
    # Модерация: scope + право проверены ВЫШЕ. exclude_unset — правим только
    # присланные поля (полный дамп затёр бы неприсланные в None при apply).
    queued, sub = await gate_or_apply(
        db, user=user, module="documents", action="edit",
        entity_id=str(folder_id), entity_label=f.name,
        company_id=co.id, sector_id=None, year=None,
        payload={"op": "folder", "code": co.code, "folder_id": str(folder_id),
                 **payload.model_dump(mode="json", exclude_unset=True),
                 **({"color": cleaned_color} if payload.color is not None else {})},
        diff_summary=f"Правка папки документов: {f.name}",
    )
    if queued:
        return {"queued": True, "submission_id": str(sub.id), "status": sub.status}
    if payload.name:
        f.name = _SAFE_NAME.sub("", payload.name).strip() or f.name
    if payload.parent_id is not None:
        if payload.parent_id == f.id:
            raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Папка не может быть вложена в себя")
        f.parent_id = payload.parent_id
    if payload.color is not None:
        # Цвет меняется и у системных папок: это оформление, а не структура.
        f.color = cleaned_color
    await db.commit()
    await db.refresh(f)
    return _folder_out(f)


@router.delete("/{code}/folders/{folder_id}",
               status_code=http_status.HTTP_204_NO_CONTENT,
               response_class=Response)
async def delete_folder(
    code: str,
    folder_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    co = await _company(db, code, user)
    await _require_write(db, user, "library")
    f = (await db.execute(
        select(DocumentFolder).where(
            DocumentFolder.id == folder_id, DocumentFolder.company_id == co.id,
        )
    )).scalar_one_or_none()
    if f is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Папка не найдена")
    if f.is_system:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, "Системную папку удалить нельзя")
    has_files = (await db.execute(
        select(Document.id).where(
            Document.folder_id == f.id, Document.is_deleted.is_(False),
        ).limit(1)
    )).first()
    has_sub = (await db.execute(
        select(DocumentFolder.id).where(DocumentFolder.parent_id == f.id).limit(1)
    )).first()
    if has_files or has_sub:
        raise HTTPException(
            http_status.HTTP_409_CONFLICT,
            "Папка не пуста — сначала переместите или удалите содержимое",
        )
    # Модерация: scope + право + guard'ы (системная/непустая) проверены ВЫШЕ.
    # Роут отдаёт 204 (response_class=Response) → при постановке в очередь
    # возвращаем JSONResponse(202), чтобы FastAPI пропустил тело.
    queued, sub = await gate_or_apply(
        db, user=user, module="documents", action="delete",
        entity_id=str(folder_id), entity_label=f.name,
        company_id=co.id, sector_id=None, year=None,
        payload={"op": "folder", "code": co.code, "folder_id": str(folder_id)},
        diff_summary=f"Удаление папки документов: {f.name}",
    )
    if queued:
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
    await db.delete(f)
    await db.commit()
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


# ─── файлы ────────────────────────────────────────────────────────

@router.get("/{code}/items")
async def list_items(
    code: str,
    folder_id: Optional[UUID] = Query(None, description="папка; не задана = все файлы"),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="поиск по имени"),
    kind: Optional[str] = Query(None, description="pdf|doc|sheet|slide|image|archive|other"),
    trash: bool = Query(False),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    co = await _company(db, code, user)
    stmt = select(Document).where(
        Document.company_id == co.id,
        Document.is_deleted.is_(trash),
    )
    if folder_id is not None:
        stmt = stmt.where(Document.folder_id == folder_id)
    if entity_type and entity_id:
        stmt = stmt.join(DocumentLink, DocumentLink.document_id == Document.id).where(
            DocumentLink.entity_type == entity_type,
            DocumentLink.entity_id == str(entity_id),
        )
    if q:
        needle = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(
            func.lower(Document.name).like(needle),
            func.lower(func.coalesce(Document.description, "")).like(needle),
        ))
    if kind:
        exts = _KIND_EXT.get(kind)
        if exts:
            stmt = stmt.where(or_(*[
                func.lower(Document.name).like(f"%.{e}") for e in exts
            ]))
        elif kind == "other":
            known = [e for group in _KIND_EXT.values() for e in group]
            for e in known:
                stmt = stmt.where(~func.lower(Document.name).like(f"%.{e}"))
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )).scalar() or 0
    rows = (await db.execute(
        stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()
    links = await _links_by_doc(db, [r.id for r in rows])
    names = await _uploaders(db, [r.uploader_id for r in rows])
    return {
        "items": [
            _doc_out(r, links.get(r.id, []), names.get(r.uploader_id) if r.uploader_id else None)
            for r in rows
        ],
        "total": int(total),
    }


@router.get("/{code}/kinds")
async def kind_counts(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Сколько файлов какого типа — вторая структура библиотеки (кроме папок)."""
    co = await _company(db, code, user)
    rows = (await db.execute(
        select(Document.name).where(
            Document.company_id == co.id, Document.is_deleted.is_(False),
        )
    )).scalars().all()
    counts: dict[str, int] = {}
    for n in rows:
        k = _kind_of(n)
        counts[k] = counts.get(k, 0) + 1
    return {"counts": counts, "total": len(rows)}


@router.post("/{code}/upload", status_code=http_status.HTTP_201_CREATED)
async def upload_document(
    code: str,
    file: UploadFile = File(...),
    folder_id: Optional[str] = Form(None),
    entity_type: Optional[str] = Form(None),
    entity_id: Optional[str] = Form(None),
    entity_label: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Загрузка файла в библиотеку. Если указана сущность (задача/проект/отчёт),
    файл СРАЗУ привязывается к ней: он появится и в карточке, и в библиотеке."""
    co = await _company(db, code, user)
    source = _ENTITY_SOURCE.get(entity_type or "", "library")
    await _require_write(db, user, source)

    data = await file.read()
    if not data:
        raise HTTPException(http_status.HTTP_422_UNPROCESSABLE_ENTITY, "Пустой файл")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            tr(
                "Файл больше {size} МБ",
                current_locale(),
                size=_MAX_UPLOAD_BYTES // (1024 * 1024),
            ),
        )
    filename = _SAFE_NAME.sub("", file.filename or "file").strip() or "file"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    now = datetime.now(UTC)
    key = f"documents/{co.code}/{now.year}/{uuid4()}.{ext}"
    try:
        stored = await get_storage().upload(
            key, data=data, mime_type=file.content_type or "application/octet-stream",
        )
    except StorageError as e:
        log.warning("document upload failed: %s", e)
        raise HTTPException(
            http_status.HTTP_502_BAD_GATEWAY, "Не удалось сохранить файл",
        ) from e

    # Папка: явная → системная по источнику → «Общие документы».
    target_folder: Optional[UUID] = None
    if folder_id:
        try:
            target_folder = UUID(folder_id)
        except (ValueError, TypeError):
            target_folder = None
    if target_folder is None:
        sys_key = "tasks" if source in ("task", "project") else (
            "financials" if source == "financials" else (
                "esg" if source == "esg" else "general"
            )
        )
        target_folder = (await db.execute(
            select(DocumentFolder.id).where(
                DocumentFolder.company_id == co.id,
                DocumentFolder.system_key == sys_key,
            )
        )).scalar_one_or_none()

    doc = Document(
        company_id=co.id, folder_id=target_folder, name=filename,
        storage_key=stored or key, mime_type=file.content_type,
        size_bytes=len(data), description=description,
        source_module=source, uploader_id=user.id,
    )
    db.add(doc)
    await db.flush()
    if entity_type and entity_id:
        db.add(DocumentLink(
            document_id=doc.id, entity_type=entity_type, entity_id=str(entity_id),
            label=(entity_label or None), created_by=user.id,
        ))
    await db.commit()
    await db.refresh(doc)
    links = await _links_by_doc(db, [doc.id])
    return _doc_out(doc, links.get(doc.id, []), user.full_name or user.email)


@router.patch("/{code}/items/{doc_id}")
async def patch_item(
    code: str,
    doc_id: UUID,
    payload: ItemPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    co = await _company(db, code, user)
    doc = (await db.execute(
        select(Document).where(Document.id == doc_id, Document.company_id == co.id)
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Документ не найден")
    await _require_write(db, user, doc.source_module)
    # Модерация: scope + право (по источнику файла) проверены ВЫШЕ. exclude_unset —
    # правим только присланные поля (полный дамп затёр бы неприсланные в None).
    queued, sub = await gate_or_apply(
        db, user=user, module="documents", action="edit",
        entity_id=str(doc_id), entity_label=doc.name,
        company_id=co.id, sector_id=None, year=None,
        payload={"op": "item", "code": co.code, "doc_id": str(doc_id),
                 **payload.model_dump(mode="json", exclude_unset=True)},
        diff_summary=f"Правка файла: {doc.name}",
    )
    if queued:
        return {"queued": True, "submission_id": str(sub.id), "status": sub.status}
    if payload.name:
        doc.name = _SAFE_NAME.sub("", payload.name).strip() or doc.name
    if payload.folder_id is not None:
        doc.folder_id = payload.folder_id
    if payload.description is not None:
        doc.description = payload.description
    await db.commit()
    await db.refresh(doc)
    links = await _links_by_doc(db, [doc.id])
    names = await _uploaders(db, [doc.uploader_id])
    return _doc_out(doc, links.get(doc.id, []),
                    names.get(doc.uploader_id) if doc.uploader_id else None)


@router.delete("/{code}/items/{doc_id}",
               status_code=http_status.HTTP_204_NO_CONTENT,
               response_class=Response)
async def delete_item(
    code: str,
    doc_id: UUID,
    hard: bool = Query(False, description="удалить безвозвратно вместе с файлом"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    co = await _company(db, code, user)
    doc = (await db.execute(
        select(Document).where(Document.id == doc_id, Document.company_id == co.id)
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Документ не найден")
    await _require_write(db, user, doc.source_module)
    # Модерация: scope + право проверены ВЫШЕ. Флаг hard (жёсткое удаление вместе
    # с файлом) переносим в payload — apply повторит ту же ветку. 204 → 202.
    queued, sub = await gate_or_apply(
        db, user=user, module="documents", action="delete",
        entity_id=str(doc_id), entity_label=doc.name,
        company_id=co.id, sector_id=None, year=None,
        payload={"op": "item", "code": co.code, "doc_id": str(doc_id), "hard": bool(hard)},
        diff_summary=f"Удаление файла: {doc.name}" + (" (безвозвратно)" if hard else ""),
    )
    if queued:
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
    if hard:
        try:
            await get_storage().delete(doc.storage_key)
        except Exception as e:  # noqa: BLE001 — запись удаляем в любом случае
            log.warning("storage delete failed for %s: %s", doc.storage_key, e)
        await db.delete(doc)
    else:
        doc.is_deleted = True
    await db.commit()
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.post("/{code}/items/{doc_id}/restore")
async def restore_item(
    code: str,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    co = await _company(db, code, user)
    doc = (await db.execute(
        select(Document).where(Document.id == doc_id, Document.company_id == co.id)
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Документ не найден")
    await _require_write(db, user, doc.source_module)
    # Модерация: восстановление из корзины = правка файла (edit/restore).
    queued, sub = await gate_or_apply(
        db, user=user, module="documents", action="edit",
        entity_id=str(doc_id), entity_label=doc.name,
        company_id=co.id, sector_id=None, year=None,
        payload={"op": "restore", "code": co.code, "doc_id": str(doc_id)},
        diff_summary=f"Восстановление файла из корзины: {doc.name}",
    )
    if queued:
        return {"queued": True, "submission_id": str(sub.id), "status": sub.status}
    doc.is_deleted = False
    await db.commit()
    return {"ok": True}


@router.get("/{code}/items/{doc_id}/url")
async def item_url(
    code: str,
    doc_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Подписанная ссылка на скачивание/просмотр. Доступ = доступ к компании:
    файл виден там же, где и карточка, из которой он загружен."""
    co = await _company(db, code, user)
    doc = (await db.execute(
        select(Document).where(Document.id == doc_id, Document.company_id == co.id)
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Документ не найден")
    try:
        url = await get_storage().signed_url(doc.storage_key, ttl_seconds=300)
    except StorageError as e:
        raise HTTPException(
            http_status.HTTP_502_BAD_GATEWAY, "Хранилище недоступно",
        ) from e
    return {"url": url, "filename": doc.name, "mime_type": doc.mime_type}


# ─── привязки (файл виден и в карточке, и в библиотеке) ───────────

@router.post("/{code}/items/{doc_id}/links", status_code=http_status.HTTP_201_CREATED)
async def add_link(
    code: str,
    doc_id: UUID,
    payload: LinkIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    co = await _company(db, code, user)
    doc = (await db.execute(
        select(Document).where(Document.id == doc_id, Document.company_id == co.id)
    )).scalar_one_or_none()
    if doc is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Документ не найден")
    await _require_write(db, user, _ENTITY_SOURCE.get(payload.entity_type, "library"))
    # Модерация: scope + право (по источнику привязки) проверены ВЫШЕ. Роут отдаёт
    # 201 → при постановке в очередь возвращаем JSONResponse(202).
    queued, sub = await gate_or_apply(
        db, user=user, module="documents", action="create",
        entity_id=str(doc_id), entity_label=doc.name,
        company_id=co.id, sector_id=None, year=None,
        payload={"op": "link", "code": co.code, "doc_id": str(doc_id),
                 "entity_type": payload.entity_type, "entity_id": payload.entity_id,
                 "label": payload.label},
        diff_summary=f"Привязка файла «{doc.name}» к {payload.entity_type}",
    )
    if queued:
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
    exists = (await db.execute(
        select(DocumentLink.id).where(
            DocumentLink.document_id == doc.id,
            DocumentLink.entity_type == payload.entity_type,
            DocumentLink.entity_id == payload.entity_id,
        )
    )).first()
    if exists:
        return {"id": str(exists[0]), "already": True}
    link = DocumentLink(
        document_id=doc.id, entity_type=payload.entity_type,
        entity_id=payload.entity_id, label=payload.label, created_by=user.id,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return {"id": str(link.id), "already": False}


@router.delete(
    "/{code}/items/{doc_id}/links/{link_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def drop_link(
    code: str,
    doc_id: UUID,
    link_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    co = await _company(db, code, user)
    link = (await db.execute(
        select(DocumentLink)
        .join(Document, Document.id == DocumentLink.document_id)
        .where(
            DocumentLink.id == link_id,
            DocumentLink.document_id == doc_id,
            Document.company_id == co.id,
        )
    )).scalar_one_or_none()
    if link is None:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Привязка не найдена")
    await _require_write(db, user, _ENTITY_SOURCE.get(link.entity_type, "library"))
    # Модерация: scope + право проверены ВЫШЕ. 204 → 202 при постановке в очередь.
    queued, sub = await gate_or_apply(
        db, user=user, module="documents", action="delete",
        entity_id=str(link_id), entity_label=f"Привязка → {link.entity_type}",
        company_id=co.id, sector_id=None, year=None,
        payload={"op": "link", "code": co.code, "doc_id": str(doc_id),
                 "link_id": str(link_id)},
        diff_summary=f"Отвязка файла от {link.entity_type}",
    )
    if queued:
        return JSONResponse(status_code=http_status.HTTP_202_ACCEPTED, content={
            "queued": True, "submission_id": str(sub.id), "status": sub.status})
    await db.delete(link)
    await db.commit()
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.get("/{code}/stats")
async def library_stats(
    code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Сводка библиотеки для шапки вкладки: файлов, объём, последняя загрузка."""
    co = await _company(db, code, user)
    row = (await db.execute(text("""
        SELECT COUNT(*) AS files,
               COALESCE(SUM(size_bytes), 0) AS bytes,
               MAX(created_at) AS last_at
        FROM documents WHERE company_id = :co AND is_deleted = false
    """), {"co": co.id})).first()
    return {
        "files": int(row[0] or 0),
        "size_bytes": int(row[1] or 0),
        "last_upload_at": row[2].isoformat() if row and row[2] else None,
    }
