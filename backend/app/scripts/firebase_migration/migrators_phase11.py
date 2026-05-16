"""Phase 11: Consultants seed + assignments migrator.

Two migrators:
  1. ConsultantsMigrator       — seeds 17 firms into `consultants` table
                                  (PwC, EY, KPMG, Deloitte, McKinsey, BCG, …).
                                  Embedded from monolith CONSULTANTS array.
  2. ConsultantAssignmentsMigrator — links tasks to consultants by reading:
                                      a) Firebase /pf/tasks → task.consultant field
                                         (string or array of consultant codes)
                                      b) CONSULTANT_LOOKUP (115 board::num pairs,
                                         applies only to portfolio_year=2025 tasks)

Both migrators are idempotent (TRUNCATE + reinsert the consultants table on
each rerun; assignments use UPSERT-by-(task_id, consultant_id) semantics
realised as ON CONFLICT DO NOTHING).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.board import Board
from app.models.consultant import Consultant, ConsultantAssignment
from app.models.task import Task
from .base import Migrator, MigrationContext, normalize_array

log = logging.getLogger(__name__)


# =====================================================================
# CONSULTANTS seed (extracted from monolith line ~7119)
# =====================================================================

CONSULTANTS_SEED: list[dict[str, Any]] = [
    {
        "id": "pwc",
        "name": "PwC",
        "color": "#0066CC",
        "abbr": "PwC"
    },
    {
        "id": "ey",
        "name": "EY",
        "color": "#008A00",
        "abbr": "EY"
    },
    {
        "id": "deloitte",
        "name": "Deloitte",
        "color": "#222222",
        "abbr": "Del."
    },
    {
        "id": "kpmg",
        "name": "KPMG",
        "color": "#0033A0",
        "abbr": "KPMG"
    },
    {
        "id": "mckinsey",
        "name": "McKinsey",
        "color": "#003366",
        "abbr": "McK."
    },
    {
        "id": "bcg",
        "name": "BCG",
        "color": "#009B77",
        "abbr": "BCG"
    },
    {
        "id": "rothschild",
        "name": "Rothschild",
        "color": "#7C3AED",
        "abbr": "R&Co"
    },
    {
        "id": "cmt",
        "name": "CMT Consulting",
        "color": "#D97706",
        "abbr": "CMT"
    },
    {
        "id": "techenergy",
        "name": "Techenergy",
        "color": "#0891B2",
        "abbr": "Tech"
    },
    {
        "id": "degolyer",
        "name": "DeGolyer & MacN.",
        "color": "#6D4C41",
        "abbr": "D&M"
    },
    {
        "id": "envisa",
        "name": "Env-isa",
        "color": "#16A34A",
        "abbr": "Env"
    },
    {
        "id": "hpbs",
        "name": "HPBS",
        "color": "#7E22CE",
        "abbr": "HPBS"
    },
    {
        "id": "jpmorgan",
        "name": "JP Morgan",
        "color": "#065F46",
        "abbr": "JPM"
    },
    {
        "id": "silkcapital",
        "name": "Silk Capital",
        "color": "#A16207",
        "abbr": "Silk"
    },
    {
        "id": "vema",
        "name": "Vema S.A.",
        "color": "#B45309",
        "abbr": "Vema"
    },
    {
        "id": "worldbank",
        "name": "Всемирный банк",
        "color": "#378ADD",
        "abbr": "WB"
    },
    {
        "id": "other",
        "name": "Другие",
        "color": "#8B8DAA",
        "abbr": "др."
    }
]

BIG4 = {"kpmg", "pwc", "ey", "deloitte"}


# =====================================================================
# CONSULTANT_LOOKUP seed (board_name::task_num → list of consultant codes)
# Year-locked to 2025 (per monolith comment).
# =====================================================================

CONSULTANT_LOOKUP_SEED: dict[str, list[str]] = {
    "UzGasTrade::1": [
        "ey"
    ],
    "UzGasTrade::1.1.": [
        "ey"
    ],
    "UzGasTrade::2": [
        "ey"
    ],
    "UzGasTrade::2.1.": [
        "ey"
    ],
    "UzGasTrade::3.2.": [
        "ey"
    ],
    "UzGasTrade::4": [
        "ey"
    ],
    "UzGasTrade::4.1.": [
        "ey"
    ],
    "UzGasTrade::4.2.": [
        "ey"
    ],
    "UzGasTrade::4.3.": [
        "ey"
    ],
    "UzGasTrade::5.1.": [
        "ey"
    ],
    "АГМК::2.1.": [
        "pwc"
    ],
    "АГМК::7.1.": [
        "kpmg"
    ],
    "АГМК::7.2.": [
        "kpmg"
    ],
    "АГМК::8.1.": [
        "kpmg"
    ],
    "АГМК::11.1.": [
        "kpmg"
    ],
    "АГМК::11.4.": [
        "pwc"
    ],
    "АГМК::11.5.": [
        "kpmg"
    ],
    "НГМК::1.2.": [
        "cmt"
    ],
    "НГМК::1.3.": [
        "rothschild"
    ],
    "НГМК::2.1.": [
        "rothschild"
    ],
    "НГМК::3.1.": [
        "rothschild"
    ],
    "НГМК::4.1.": [
        "kpmg"
    ],
    "НГМК::4.3.": [
        "kpmg"
    ],
    "НГМК::4.4.": [
        "kpmg"
    ],
    "НГМК::5.1.": [
        "kpmg"
    ],
    "НГМК::6.1.": [
        "kpmg"
    ],
    "НГМК::6.2.": [
        "kpmg"
    ],
    "НГМК::7.3.": [
        "pwc"
    ],
    "НГМК::8.1.": [
        "kpmg"
    ],
    "НГМК::8.2.": [
        "pwc"
    ],
    "Навоийазот::4.1.": [
        "kpmg"
    ],
    "Навоийазот::5.1.": [
        "kpmg",
        "pwc",
        "ey"
    ],
    "Навоийазот::6.1.": [
        "kpmg"
    ],
    "Навоийазот::6.2.": [
        "kpmg"
    ],
    "Навоийазот::6.3.": [
        "kpmg"
    ],
    "Навоийазот::7.1.": [
        "ey"
    ],
    "Навоийазот::11.1.": [
        "ey"
    ],
    "Навоийазот::11.2.": [
        "ey"
    ],
    "Навоийуран::1.1.": [
        "mckinsey"
    ],
    "Навоийуран::1.2.": [
        "mckinsey"
    ],
    "Навоийуран::1.3.": [
        "mckinsey"
    ],
    "Навоийуран::3.1.": [
        "pwc"
    ],
    "Навоийуран::4.1.": [
        "kpmg"
    ],
    "Навоийуран::5.1.": [
        "pwc"
    ],
    "Навоийуран::7.1.": [
        "pwc"
    ],
    "Навоийуран::7.2.": [
        "pwc"
    ],
    "НЭС::1.1.": [
        "bcg"
    ],
    "НЭС::3.1.": [
        "pwc"
    ],
    "НЭС::3.2.": [
        "pwc"
    ],
    "НЭС::6.1.": [
        "pwc"
    ],
    "НЭС::7.1.": [
        "pwc"
    ],
    "РЭС::1.1.": [
        "kpmg"
    ],
    "РЭС::1.2.": [
        "kpmg"
    ],
    "РЭС::6.1.": [
        "pwc"
    ],
    "РЭС::6.3.": [
        "kpmg"
    ],
    "РЭС::7.1.": [
        "pwc"
    ],
    "ТЭС::2.1.": [
        "kpmg"
    ],
    "ТЭС::3.1.": [
        "kpmg"
    ],
    "ТЭС::4.1.": [
        "kpmg"
    ],
    "ТЭС::4.4.": [
        "kpmg"
    ],
    "ТЭС::5.1.": [
        "kpmg"
    ],
    "ТЭС::6.1.": [
        "kpmg"
    ],
    "ТЭС::6.2.": [
        "kpmg"
    ],
    "ТЭС::7.1.": [
        "pwc"
    ],
    "ТЭС::12.1.": [
        "kpmg"
    ],
    "Узбекгидроэнерго::3.1.": [
        "pwc"
    ],
    "Узбекгидроэнерго::4.1.": [
        "pwc"
    ],
    "Узбекгидроэнерго::5.1.": [
        "pwc"
    ],
    "Узбекгидроэнерго::6.1.": [
        "pwc"
    ],
    "Узбекнефтегаз::1.2.": [
        "bcg",
        "mckinsey"
    ],
    "Узбекнефтегаз::2.1.": [
        "techenergy"
    ],
    "Узбекнефтегаз::4.1.": [
        "degolyer"
    ],
    "Узбекнефтегаз::5.1.": [
        "kpmg"
    ],
    "Узбекнефтегаз::5.3.": [
        "kpmg"
    ],
    "Узбекнефтегаз::8.2.": [
        "techenergy"
    ],
    "Узбекнефтегаз::9.2.": [
        "kpmg"
    ],
    "Узбекнефтегаз::9.3.": [
        "ey"
    ],
    "Узбекнефтегаз::9.4.": [
        "hpbs"
    ],
    "Узбекнефтегаз::9.5.": [
        "kpmg"
    ],
    "Узбекуголь::3.1.": [
        "ey"
    ],
    "Узбекуголь::4.1.": [
        "ey"
    ],
    "Узбекуголь::5.1.": [
        "ey"
    ],
    "Узбекуголь::5.3.": [
        "ey"
    ],
    "Узбекуголь::6.1.": [
        "kpmg"
    ],
    "Узметкомбинат::1.1.": [
        "kpmg"
    ],
    "Узметкомбинат::2.1.": [
        "ey"
    ],
    "Узтрансгаз::1.1.": [
        "deloitte"
    ],
    "Узтрансгаз::2.1.": [
        "bcg"
    ],
    "Узтрансгаз::3.4.": [
        "rothschild"
    ],
    "Узтрансгаз::3.5.": [
        "rothschild"
    ],
    "Узтрансгаз::3.6.": [
        "rothschild"
    ],
    "Узтрансгаз::3.7.": [
        "rothschild"
    ],
    "Узтрансгаз::4.1.": [
        "ey"
    ],
    "Узтрансгаз::4.2.": [
        "ey"
    ],
    "Узтрансгаз::4.3.": [
        "ey"
    ],
    "Узтрансгаз::7.2.": [
        "vema",
        "worldbank"
    ],
    "Узтрансгаз::7.3.": [
        "vema",
        "worldbank"
    ],
    "Узтрансгаз::7.4.": [
        "worldbank"
    ],
    "Узтрансгаз::7.5.": [
        "worldbank"
    ],
    "Узтрансгаз::8.1.": [
        "kpmg"
    ],
    "Узтрансгаз::8.2.": [
        "kpmg"
    ],
    "Худудгазтаъминот::2.2.": [
        "bcg"
    ],
    "Худудгазтаъминот::5.5.": [
        "pwc"
    ],
    "Худудгазтаъминот::6.2.": [
        "deloitte"
    ],
    "Худудгазтаъминот::6.3.": [
        "deloitte"
    ],
    "Худудгазтаъминот::6.4.": [
        "deloitte"
    ],
    "Худудгазтаъминот::9.3.": [
        "kpmg"
    ],
    "Худудгазтаъминот::9.4.": [
        "kpmg"
    ],
    "Худудгазтаъминот::9.5.": [
        "kpmg"
    ],
    "УзАвто Саноат::1.1.": [
        "bcg"
    ],
    "УзАвто Саноат::1.2.": [
        "bcg"
    ],
    "УзАвто Саноат::1.3.": [
        "bcg"
    ],
    "УзАвто Саноат::1.4.": [
        "bcg"
    ],
    "УзАвто Саноат::5.1.": [
        "kpmg"
    ],
    "УзАвто Саноат::7.1.": [
        "kpmg"
    ]
}

LOOKUP_YEAR = 2025


# =====================================================================
# Migrator 1: Consultants master list
# =====================================================================

class ConsultantsMigrator(Migrator):
    name = "consultants"
    firebase_path = "<embedded CONSULTANTS seed>"

    async def fetch(self, ctx: MigrationContext) -> Any:
        return list(CONSULTANTS_SEED)

    async def apply(self, ctx: MigrationContext) -> None:
        seed = await self.fetch(ctx)
        if not seed:
            ctx.report.add_error("consultants: empty seed")
            return

        # Idempotent: clear existing master list and reinsert
        # (assignments cascade-delete via FK, but we run before assignments
        # migrator anyway, so this is safe)
        if not ctx.dry_run:
            await ctx.db.execute(delete(Consultant))
            await ctx.db.flush()

        created = 0
        for idx, row in enumerate(seed):
            code = (row.get("id") or "").strip().lower()
            name = row.get("name") or ""
            if not code or not name:
                continue

            if not ctx.dry_run:
                co = Consultant(
                    code=code,
                    name_ru=name,
                    abbr=(row.get("abbr") or "").strip()[:32] or None,
                    color_hex=(row.get("color") or "").strip()[:9] or None,
                    is_big4=(code in BIG4),
                    is_active=True,
                    sort_order=idx * 10,
                )
                ctx.db.add(co)
            created += 1
            ctx.report.add_create("consultants")

        if not ctx.dry_run:
            await ctx.db.flush()
            await ctx.db.commit()

        msg = f"  ✓ consultants: {created} firms seeded "
        msg += "(DRY)" if ctx.dry_run else f"({sum(1 for r in seed if (r.get('id','').strip().lower() in BIG4))} Big4)"
        log.info(msg)
        print(msg)


# =====================================================================
# Migrator 2: ConsultantAssignments
# =====================================================================

class ConsultantAssignmentsMigrator(Migrator):
    name = "consultant_assignments"
    firebase_path = "/pf/tasks"

    async def fetch(self, ctx: MigrationContext) -> Any:
        return ctx.fb.get(self.firebase_path)

    async def apply(self, ctx: MigrationContext) -> None:
        # 1. Build code → Consultant.id lookup
        cons_q = await ctx.db.execute(select(Consultant))
        cons_rows = cons_q.scalars().all()
        code_to_id: dict[str, Any] = {c.code: c.id for c in cons_rows}
        if not code_to_id:
            ctx.report.add_error(
                "consultant_assignments: consultants table empty — run "
                "consultants migrator first"
            )
            return

        # 2. Build (board_name, task_num) → task_id lookup for portfolio_year=2025
        # We need this for CONSULTANT_LOOKUP application
        bn_q = await ctx.db.execute(
            select(Task.id, Task.num, Board.name, Task.portfolio_year)
            .join(Board, Board.id == Task.board_id)
        )
        rows = bn_q.all()
        boardnum_to_taskid: dict[tuple, Any] = {}
        for tid, num, bname, year in rows:
            if not bname:
                continue
            key = (bname.strip(), str(num or "").strip(), year or 0)
            boardnum_to_taskid[key] = tid

        # 3. Build legacy_id → task_id lookup for FB task processing
        # Tasks were imported with legacy_id from FB
        leg_q = await ctx.db.execute(
            select(Task.id, Task.legacy_id, Task.extra)
            .where(Task.legacy_id.is_not(None))
        )
        legacy_to_id: dict[str, Any] = {}
        # Also extract the FB consultant field from extra if available
        extra_consultants: dict[Any, Any] = {}
        for tid, legacy, extra in leg_q.all():
            if legacy:
                legacy_to_id[legacy] = tid
            if extra and isinstance(extra, dict):
                c = extra.get("consultant")
                if c:
                    extra_consultants[tid] = c

        # 4. Process FB tasks (extra.consultant should have all assignments)
        fb_tasks = await self.fetch(ctx)
        if not fb_tasks:
            log.warning("consultant_assignments: /pf/tasks returned empty")
            fb_tasks = {}

        # FB tasks may be dict-of-dicts {"task_id": {...}} or list
        if isinstance(fb_tasks, dict):
            fb_iter = fb_tasks.values()
        elif isinstance(fb_tasks, list):
            fb_iter = fb_tasks
        else:
            fb_iter = []

        # Idempotent: drop existing 'task' and 'lookup' source rows
        if not ctx.dry_run:
            await ctx.db.execute(
                delete(ConsultantAssignment).where(
                    ConsultantAssignment.source.in_(["task", "lookup"])
                )
            )
            await ctx.db.flush()

        # 4a. From task.consultant (FB)
        pairs: set[tuple] = set()
        unknown_codes: set[str] = set()

        for fb_t in fb_iter:
            if not isinstance(fb_t, dict):
                continue
            t_legacy = fb_t.get("id") or fb_t.get("legacyId")
            if not t_legacy:
                continue
            task_id = legacy_to_id.get(str(t_legacy))
            if task_id is None:
                continue

            consultant_field = fb_t.get("consultant")
            if not consultant_field:
                continue

            # consultant can be string or array
            cids: list[str] = []
            if isinstance(consultant_field, str):
                cids = [consultant_field.strip().lower()]
            elif isinstance(consultant_field, list):
                cids = [str(x).strip().lower() for x in consultant_field if x]
            else:
                arr = normalize_array(consultant_field)
                cids = [str(x).strip().lower() for x in arr if x]

            for cid in cids:
                if cid == "other" or not cid:
                    continue
                cons_id = code_to_id.get(cid)
                if cons_id is None:
                    unknown_codes.add(cid)
                    continue
                pairs.add((task_id, cons_id, "task"))

        task_pair_count = len(pairs)

        # 4b. Apply CONSULTANT_LOOKUP — only to year=2025 tasks
        lookup_added = 0
        for key, cids in CONSULTANT_LOOKUP_SEED.items():
            if "::" not in key:
                continue
            board_name, task_num = key.split("::", 1)
            board_name = board_name.strip()
            task_num = task_num.strip()
            tid = boardnum_to_taskid.get((board_name, task_num, LOOKUP_YEAR))
            if tid is None:
                continue
            for cid in cids:
                cid = (cid or "").strip().lower()
                if cid == "other" or not cid:
                    continue
                cons_id = code_to_id.get(cid)
                if cons_id is None:
                    unknown_codes.add(cid)
                    continue
                pair = (tid, cons_id, "lookup")
                if pair not in pairs:
                    pairs.add(pair)
                    lookup_added += 1

        # 5. Bulk insert with ON CONFLICT DO NOTHING (UniqueConstraint
        # on (task_id, consultant_id) will dedupe across both sources)
        inserted = 0
        if pairs and not ctx.dry_run:
            stmt = pg_insert(ConsultantAssignment).values([
                {"task_id": tid, "consultant_id": cid, "source": src}
                for tid, cid, src in pairs
            ]).on_conflict_do_nothing(index_elements=["task_id", "consultant_id"])
            res = await ctx.db.execute(stmt)
            inserted = res.rowcount or 0
            await ctx.db.commit()

        for _ in pairs:
            ctx.report.add_create("consultant_assignments")

        if unknown_codes:
            ctx.report.add_warning(
                f"consultant_assignments: unknown codes ignored: "
                f"{sorted(unknown_codes)}"
            )

        msg = (f"  ✓ consultant_assignments: "
               f"{task_pair_count} from task.consultant + "
               f"{lookup_added} from CONSULTANT_LOOKUP = "
               f"{len(pairs)} pairs total ({inserted} inserted)")
        log.info(msg)
        print(msg)
