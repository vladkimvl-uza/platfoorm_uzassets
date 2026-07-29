"""Единая библиотека документов компании.

Одна запись файла — одно физическое хранение. Файл, загруженный в карточке
задачи, проекта или в редакторе МСФО/НСБУ, ЖИВЁТ в библиотеке компании и
показывается одновременно и там, и в своей карточке — через `document_links`
(один документ → сколько угодно мест показа).

Почему так, а не три отдельные таблицы вложений (как было):
  * файл, приложенный к задаче, был невидим в «Документах» компании и наоборот;
  * один и тот же файл приходилось грузить дважды, и версии расходились;
  * права проверялись у каждой таблицы по-своему.

Права (единое правило): ЧИТАТЬ библиотеку — доступ к компании; ЗАГРУЖАТЬ и
удалять — право той поверхности, откуда файл пришёл (задачи → tasks.edit,
отчётность → financials.edit, сама библиотека → companies.edit).
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin, UUIDMixin


class DocumentFolder(Base, UUIDMixin, TimestampMixin):
    """Папка библиотеки. Дерево внутри одной компании; NULL parent = корень.

    Системные папки (`is_system`) создаются платформой под источники — «Задачи и
    проекты», «Финансовая отчётность» и т.п. Их нельзя удалить: в них
    складываются файлы, приходящие из карточек.
    """

    __tablename__ = "document_folders"
    __table_args__ = (
        UniqueConstraint("company_id", "parent_id", "name", name="uq_docfolder_name"),
        Index("ix_docfolder_company_parent", "company_id", "parent_id"),
    )

    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    parent_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("document_folders.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Цвет папки (#RRGGBB) — визуальная навигация по библиотеке. Палитра
    # пастельная и корпоративная, задаётся на фронте; NULL = цвет по умолчанию.
    color: Mapped[Optional[str]] = mapped_column(String(9), nullable=True)
    # Системный ключ источника: 'tasks' | 'financials' | 'esg' | … — по нему
    # загрузка из карточки находит свою папку, не создавая дублей.
    system_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )


class Document(Base, UUIDMixin, TimestampMixin):
    """Файл библиотеки компании — единственная запись на физический объект."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_company_folder", "company_id", "folder_id"),
        Index("ix_documents_company_deleted", "company_id", "is_deleted"),
    )

    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    folder_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("document_folders.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    # Ключ в объектном хранилище (S3/local). При миграции старых вложений
    # переносим ключ КАК ЕСТЬ — файлы физически не двигаются.
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Откуда файл пришёл: 'library' | 'task' | 'project' | 'financials' | …
    # Определяет, какое право нужно для его изменения/удаления.
    source_module: Mapped[str] = mapped_column(
        String(32), nullable=False, default="library", server_default="library",
    )
    uploader_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    # Мягкое удаление: файл уходит в «Корзину» и восстановим, ссылка из карточки
    # при этом сразу перестаёт его показывать.
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false",
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False, server_default="1")


class DocumentLink(Base, UUIDMixin, TimestampMixin):
    """Где документ показывается, кроме библиотеки.

    entity_type: 'task' | 'project' | 'financial_report' | 'company' | …
    Один документ может висеть в нескольких местах — файл один, показов много.
    """

    __tablename__ = "document_links"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "entity_type", "entity_id", name="uq_doclink_target",
        ),
        Index("ix_doclink_entity", "entity_type", "entity_id"),
    )

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Человекочитаемая подпись места («МСФО · 2025», «Задача: …») — чтобы в
    # библиотеке было видно происхождение файла без доп. запросов.
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
