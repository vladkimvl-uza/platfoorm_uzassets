# `backend/scripts/` — one-shot tooling

## What lives here

- **`audit_fk_v3.py`** — scan models/ for ForeignKey columns missing `index=True`. Used to generate `alembic/versions/9aZ_fk_indexes.py`.
- **`audit_update_schemas.py`** — find UPDATE Pydantic schemas missing model columns (silent-drop bug pattern).
- **`probes/`** — accumulated debug/probe scripts (one-shot DB queries, audits, recon). Created during incident investigations or migrations. **Not part of CI; not imported by app.** Keep around for forensic reference; delete when an investigation is closed and the question no longer matters.
- **`sql/`** — ad-hoc SQL snippets used during migrations or hotfixes (e.g. `_bp_nsbu_backfill.sql`). Same lifecycle as `probes/`.

## Guidelines

1. **New probe?** Drop it in `probes/` with a comment at top explaining what bug/question prompted it.
2. **Becomes durable?** Promote to `app/services/...` or a proper alembic migration.
3. **Stale?** Delete. We don't want a museum.
4. **Never import from `app/`** in probes — they should be standalone with their own DB connection if needed (most just use `docker exec uza-postgres psql`).
