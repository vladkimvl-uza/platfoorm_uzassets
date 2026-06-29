"""flag dirty procurement_closures rows (untrustworthy benchmark)

Revision ID: 9b2_procurement_flag_dirty
Revises: 9b1_procurement_drop_dup_source
Create Date: 2026-06-29

Исторически `is_dirty` проставлялся хардкодом FALSE для ВСЕХ строк (см.
procurement_repository.bulk_insert), поэтому клиентские фильтры `if (p.is_dirty)`
в модалках и серверные `if c.is_dirty: continue` ничего не отсекали. При этом
в данных есть строки с недостоверным бенчмарком: нет market_avg, либо
экстремальное отклонение (>1000% = цена >11× медианы по коду; встречаются
сентинельные deviation_pct≈999999.9999 при мусорном market_avg).

Миграция размечает такие строки is_dirty=TRUE / is_clean=FALSE, чтобы:
  • line-level денежные агрегаты модалок (через p.is_dirty) реально отсекали мусор;
  • KPI clean_closures стал честным (раньше == total_closures).

Идемпотентна: повторный прогон лишь переустановит те же флаги.
Чистый ценовой движок (band/full_spread по коду) от is_dirty не зависит, поэтому
backfill безопасен и не меняет рейтинг/потенциал/премию.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b2_procurement_flag_dirty"
down_revision: Union[str, None] = "9b1_procurement_drop_dup_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DIRTY_PREDICATE = """
    market_avg IS NULL
    OR market_avg <= 0
    OR (deviation_pct IS NOT NULL AND ABS(deviation_pct) > 1000)
"""


def upgrade() -> None:
    bind = op.get_bind()
    # 1) пометить грязные
    res = bind.execute(sa.text(f"""
        UPDATE procurement_closures
        SET is_dirty = TRUE, is_clean = FALSE, updated_at = NOW()
        WHERE ({_DIRTY_PREDICATE})
          AND (is_dirty IS DISTINCT FROM TRUE)
        RETURNING id
    """))
    dirty = len(res.fetchall())
    # 2) гарантировать чистоту остальных (на случай ранее ошибочно проставленных)
    res2 = bind.execute(sa.text(f"""
        UPDATE procurement_closures
        SET is_dirty = FALSE, is_clean = TRUE, updated_at = NOW()
        WHERE NOT ({_DIRTY_PREDICATE})
          AND (is_dirty IS DISTINCT FROM FALSE OR is_clean IS DISTINCT FROM TRUE)
        RETURNING id
    """))
    clean = len(res2.fetchall())
    print(f"  ✓ procurement_closures: flagged {dirty} dirty, normalised {clean} clean")


def downgrade() -> None:
    # Возврат к прежнему (некорректному) состоянию «всё чистое».
    op.get_bind().execute(sa.text("""
        UPDATE procurement_closures SET is_dirty = FALSE, is_clean = TRUE
    """))
