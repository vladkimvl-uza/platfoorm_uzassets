"""drop duplicate blank-source procurement_closures rows

Revision ID: 9b1_procurement_drop_dup_source
Revises: 9b0_procurement_reseed_umk
Create Date: 2026-06-26

В некоторых окружениях procurement_closures содержит ДВА набора одних и тех
же закупок Q1 2026: канонический сид `extra.source='q1-2026-xlsx'` и более
старый набор без тега источника (пустой/NULL source). Второй — полный
дубликат (его lot_id на 100% присутствуют в сиде), он задваивает row-level
агрегаты (рейтинг компаний, товары).

Эта миграция удаляет ТОЛЬКО строки с пустым/NULL источником. Канонический
сид (`q1-2026-xlsx`) и пользовательские импорты (`manual-upload`) не трогаются.
Идемпотентна: если дубля нет — удаляет 0 строк.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b1_procurement_drop_dup_source"
down_revision: Union[str, None] = "9b0_procurement_reseed_umk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    res = bind.execute(sa.text("""
        DELETE FROM procurement_closures
        WHERE NULLIF(extra->>'source', '') IS NULL
        RETURNING id
    """))
    print(f"  ✓ procurement_closures: removed {len(res.fetchall())} duplicate blank-source rows")


def downgrade() -> None:
    # Невосстановимо (это был дубликат) — no-op.
    pass
