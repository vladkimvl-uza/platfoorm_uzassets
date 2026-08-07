"""Documents (библиотека документов) apply handler — deny-by-default Phase 4.

Применяет одобренную правку структуры библиотеки документов. Зеркалит
CRUD-роуты `app/api/routes/documents.py`:
  POST   /documents/{code}/folders                 create_folder   (create/folder)
  PATCH  /documents/{code}/folders/{id}            patch_folder    (edit/folder)
  DELETE /documents/{code}/folders/{id}            delete_folder   (delete/folder)
  PATCH  /documents/{code}/items/{id}              patch_item      (edit/item)
  DELETE /documents/{code}/items/{id}              delete_item     (delete/item)
  POST   /documents/{code}/items/{id}/restore      restore_item    (edit/restore)
  POST   /documents/{code}/items/{id}/links        add_link        (create/link)
  DELETE /documents/{code}/items/{id}/links/{id}   drop_link       (delete/link)

Бинарная загрузка (`upload_document`) — бакет D, НЕ модерируется.

У модуля documents НЕТ сервис-слоя: роуты работают с моделями напрямую
(Document / DocumentFolder / DocumentLink). Поэтому хендлер зеркалит именно
эту «сырую» логику роутов на переданной сессии `db` (её коммитит
`_dispatch_apply`), а не через UoW-сервис.

Действие несёт несколько разных операций (create = папка ЛИБО привязка,
edit = папка / файл / восстановление, delete = папка / файл / привязка),
поэтому в payload лежит дискриминатор `op` — ровно как notes различает
правку заметки и правку пункта чек-листа по `checklist_item_id`.

Идемпотентность: у create-папки после вставки штампуем `target_entity_id`
id-ом новой папки (коммитит `_dispatch_apply`); повтор apply не плодит дубль.

exclude_unset: patch_folder / patch_item сериализуются в гейте с
exclude_unset=True — «правим только присланные поля»; полный дамп затёр бы
неприсланные поля.

Атрибуция (created_by / uploader_id) — ПРЕДЛОЖИВШИЙ (proposer), не модератор.
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select

from app.models.company import Company
from app.models.document import Document, DocumentFolder, DocumentLink
from app.models.moderation import ModerationSubmission
from app.models.user import User
from app.services.moderation_service import register_apply_handler
from app.services.storage import get_storage

log = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[\\/\x00-\x1f]")


def _clean(name: str) -> str:
    return _SAFE_NAME.sub("", name or "").strip()


def _as_uuid(value) -> Optional[UUID]:
    if value in (None, ""):
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


async def _company_by_code(db, code: str) -> Company:
    co = (await db.execute(
        select(Company).where(Company.code == (code or "").lower())
    )).scalar_one_or_none()
    if co is None:
        raise ValueError(f"documents: company '{code}' not found")
    return co


async def apply(db, *, sub: ModerationSubmission, user: User) -> dict:
    if not sub.proposed_value:
        raise ValueError("proposed_value is empty")
    action = (sub.action or "").lower()
    pv = dict(sub.proposed_value)
    op = str(pv.get("op") or "").lower()

    proposer = (await db.execute(
        select(User).where(User.id == sub.proposer_user_id)
    )).scalar_one_or_none()
    author = proposer or user
    author_id = author.id

    co = await _company_by_code(db, str(pv.get("code") or ""))

    # ── create ────────────────────────────────────────────────────
    if action in ("create", "created"):
        if op == "folder":
            # Идемпотентность: прошлый apply уже создал папку и застолбил её id.
            fid = _as_uuid(sub.target_entity_id)
            if fid is not None:
                exists = (await db.execute(
                    select(DocumentFolder.id).where(DocumentFolder.id == fid)
                )).scalar_one_or_none()
                if exists is not None:
                    return {"action": "create", "folder_id": str(fid), "idempotent": True}
            name = _clean(str(pv.get("name") or ""))
            if not name:
                raise ValueError("documents: empty folder name")
            parent_id = _as_uuid(pv.get("parent_id"))
            dup = (await db.execute(
                select(DocumentFolder.id).where(
                    DocumentFolder.company_id == co.id,
                    DocumentFolder.parent_id.is_(None) if parent_id is None
                    else DocumentFolder.parent_id == parent_id,
                    func.lower(DocumentFolder.name) == name.lower(),
                )
            )).first()
            if dup:
                raise ValueError("documents: folder with this name already exists")
            f = DocumentFolder(
                company_id=co.id, parent_id=parent_id, name=name,
                color=pv.get("color") or None, is_system=False, created_by=author_id,
            )
            db.add(f)
            await db.flush()
            sub.target_entity_id = str(f.id)  # застолбить id (коммитит _dispatch_apply)
            return {"action": "create", "folder_id": str(f.id)}

        if op == "link":
            doc_id = _as_uuid(pv.get("doc_id"))
            doc = (await db.execute(
                select(Document).where(Document.id == doc_id, Document.company_id == co.id)
            )).scalar_one_or_none()
            if doc is None:
                raise ValueError("documents: document not found for link")
            entity_type = str(pv.get("entity_type") or "")
            entity_id = str(pv.get("entity_id") or "")
            exists = (await db.execute(
                select(DocumentLink.id).where(
                    DocumentLink.document_id == doc.id,
                    DocumentLink.entity_type == entity_type,
                    DocumentLink.entity_id == entity_id,
                )
            )).first()
            if exists:
                return {"action": "create", "link_id": str(exists[0]), "already": True}
            link = DocumentLink(
                document_id=doc.id, entity_type=entity_type, entity_id=entity_id,
                label=(pv.get("label") or None), created_by=author_id,
            )
            db.add(link)
            await db.flush()
            return {"action": "create", "link_id": str(link.id)}

        raise ValueError(f"unknown documents create op: {op!r}")

    # ── edit ──────────────────────────────────────────────────────
    if action in ("edit", "update"):
        if op == "folder":
            fid = _as_uuid(pv.get("folder_id"))
            f = (await db.execute(
                select(DocumentFolder).where(
                    DocumentFolder.id == fid, DocumentFolder.company_id == co.id,
                )
            )).scalar_one_or_none()
            if f is None:
                raise ValueError("documents: folder not found")
            if f.is_system and pv.get("name"):
                raise ValueError("documents: system folder cannot be renamed")
            if pv.get("name"):
                f.name = _clean(str(pv["name"])) or f.name
            if pv.get("parent_id") is not None:
                new_parent = _as_uuid(pv.get("parent_id"))
                if new_parent == f.id:
                    raise ValueError("documents: folder cannot be nested in itself")
                f.parent_id = new_parent
            if pv.get("color") is not None:
                f.color = pv.get("color") or None
            return {"action": "edit", "folder_id": str(f.id)}

        if op == "item":
            doc_id = _as_uuid(pv.get("doc_id"))
            doc = (await db.execute(
                select(Document).where(Document.id == doc_id, Document.company_id == co.id)
            )).scalar_one_or_none()
            if doc is None:
                raise ValueError("documents: document not found")
            if pv.get("name"):
                doc.name = _clean(str(pv["name"])) or doc.name
            if pv.get("folder_id") is not None:
                doc.folder_id = _as_uuid(pv.get("folder_id"))
            if pv.get("description") is not None:
                doc.description = pv.get("description")
            return {"action": "edit", "doc_id": str(doc.id)}

        if op == "restore":
            doc_id = _as_uuid(pv.get("doc_id"))
            doc = (await db.execute(
                select(Document).where(Document.id == doc_id, Document.company_id == co.id)
            )).scalar_one_or_none()
            if doc is None:
                raise ValueError("documents: document not found")
            doc.is_deleted = False
            return {"action": "edit", "doc_id": str(doc.id), "restored": True}

        raise ValueError(f"unknown documents edit op: {op!r}")

    # ── delete ────────────────────────────────────────────────────
    if action in ("delete", "deleted"):
        if op == "folder":
            fid = _as_uuid(pv.get("folder_id"))
            f = (await db.execute(
                select(DocumentFolder).where(
                    DocumentFolder.id == fid, DocumentFolder.company_id == co.id,
                )
            )).scalar_one_or_none()
            if f is None:
                raise ValueError("documents: folder not found")
            if f.is_system:
                raise ValueError("documents: system folder cannot be deleted")
            has_files = (await db.execute(
                select(Document.id).where(
                    Document.folder_id == f.id, Document.is_deleted.is_(False),
                ).limit(1)
            )).first()
            has_sub = (await db.execute(
                select(DocumentFolder.id).where(DocumentFolder.parent_id == f.id).limit(1)
            )).first()
            if has_files or has_sub:
                raise ValueError("documents: folder is not empty")
            await db.delete(f)
            return {"action": "delete", "folder_id": str(fid)}

        if op == "item":
            doc_id = _as_uuid(pv.get("doc_id"))
            doc = (await db.execute(
                select(Document).where(Document.id == doc_id, Document.company_id == co.id)
            )).scalar_one_or_none()
            if doc is None:
                raise ValueError("documents: document not found")
            if pv.get("hard"):
                try:
                    await get_storage().delete(doc.storage_key)
                except Exception as e:  # noqa: BLE001 — запись удаляем в любом случае
                    log.warning("storage delete failed for %s: %s", doc.storage_key, e)
                await db.delete(doc)
            else:
                doc.is_deleted = True
            return {"action": "delete", "doc_id": str(doc_id), "hard": bool(pv.get("hard"))}

        if op == "link":
            doc_id = _as_uuid(pv.get("doc_id"))
            link_id = _as_uuid(pv.get("link_id"))
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
                raise ValueError("documents: link not found")
            await db.delete(link)
            return {"action": "delete", "link_id": str(link_id)}

        raise ValueError(f"unknown documents delete op: {op!r}")

    raise ValueError(f"unknown documents action: {action!r}")


register_apply_handler("documents", apply)
