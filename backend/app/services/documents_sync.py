"""Зеркалирование вложений карточек в библиотеку документов компании.

Файл, загруженный в карточке задачи/проекта/компании, должен лежать в
«Документах» компании и одновременно оставаться в своей карточке. Старые
эндпоинты /attachments/* при этом не переписываем: они по-прежнему пишут свою
строку, а эта функция добавляет ЗЕРКАЛО в `documents` + `document_links`.

Идентификатор документа = идентификатор вложения. Так зеркало идемпотентно
(повтор не создаёт дубль) и совпадает с разовым бэкфиллом
`_patch_documents_library`, который перенёс уже существующие вложения.

Best-effort: сбой зеркалирования не должен ронять загрузку файла — он лишь
означает, что файл не появится в библиотеке, о чём пишем в лог.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# Куда класть зеркало: системная папка библиотеки по источнику.
_SYSTEM_FOLDER = {
    "task": "tasks",
    "project": "tasks",
    "library": "general",
    "financials": "financials",
}


async def mirror_attachment(
    db: AsyncSession,
    *,
    attachment_id: UUID | str,
    company_id: Optional[UUID],
    entity_type: str,          # 'task' | 'project' | 'company'
    entity_id: str,
    entity_label: Optional[str],
    filename: str,
    storage_key: str,
    mime_type: Optional[str],
    size_bytes: Optional[int],
    uploader_id: Optional[UUID],
    source: str,               # 'task' | 'project' | 'library' | 'financials'
) -> None:
    """Создать/обновить запись документа и привязку к сущности."""
    if company_id is None:
        return                 # вне компании библиотеки нет — зеркалить некуда
    try:
        folder_key = _SYSTEM_FOLDER.get(source, "general")
        await db.execute(
            text("""
                INSERT INTO documents (id, company_id, folder_id, name, storage_key,
                                       mime_type, size_bytes, source_module, uploader_id)
                VALUES (
                    :id, :co,
                    (SELECT f.id FROM document_folders f
                      WHERE f.company_id = :co AND f.system_key = :fkey LIMIT 1),
                    :name, :key, :mime, :size, :src, :uid
                )
                ON CONFLICT (id) DO UPDATE
                   SET name = EXCLUDED.name,
                       storage_key = EXCLUDED.storage_key,
                       mime_type = EXCLUDED.mime_type,
                       size_bytes = EXCLUDED.size_bytes,
                       is_deleted = false,
                       updated_at = now()
            """),
            {
                "id": str(attachment_id), "co": str(company_id), "fkey": folder_key,
                "name": filename[:512], "key": storage_key[:1024],
                "mime": (mime_type or None), "size": size_bytes,
                "src": source, "uid": str(uploader_id) if uploader_id else None,
            },
        )
        if entity_type and entity_id:
            await db.execute(
                text("""
                    INSERT INTO document_links (document_id, entity_type, entity_id, label, created_by)
                    VALUES (:doc, :et, :eid, :lbl, :uid)
                    ON CONFLICT (document_id, entity_type, entity_id) DO NOTHING
                """),
                {
                    "doc": str(attachment_id), "et": entity_type, "eid": str(entity_id),
                    "lbl": (entity_label or None), "uid": str(uploader_id) if uploader_id else None,
                },
            )
        await db.commit()
    except Exception as e:  # noqa: BLE001 — загрузка файла важнее зеркала
        log.warning("documents mirror failed for %s: %s", attachment_id, e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def mirror_delete(db: AsyncSession, attachment_id: UUID | str) -> None:
    """Вложение удалили в карточке — документ уходит в корзину библиотеки."""
    try:
        await db.execute(
            text("UPDATE documents SET is_deleted = true, updated_at = now() WHERE id = :id"),
            {"id": str(attachment_id)},
        )
        await db.commit()
    except Exception as e:  # noqa: BLE001
        log.warning("documents mirror delete failed for %s: %s", attachment_id, e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
