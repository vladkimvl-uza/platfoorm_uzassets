"""Find UPDATE schemas missing fields that exist as columns on the model.

For each `class FooUpdate(BaseModel)` schema, infer the model name (`Foo`),
locate the model class, gather its columns (mapped_column lines), and
report any column NOT in the Update schema (with sensible exclusions like
id, created_at, updated_at, server-managed fields).
"""
import os
import re

SCHEMAS_DIR = "/app/app/schemas"
MODELS_DIR = "/app/app/models"

# Columns to ignore (server-managed, system fields)
IGNORE = {
    "id", "created_at", "updated_at", "creator_id", "updated_by", "updated_by_id",
    "created_by_id", "deleted_at", "is_archived",  # archive has separate endpoint
    "extra",  # JSONB, usually wrapped
    "password_hash", "password_history", "password_history_enc",
    "mfa_secret_encrypted", "mfa_recovery_codes",
    "telegram_chat_id_encrypted", "telegram_username", "telegram_linked_at",
    "telegram_link_token_hashed", "telegram_link_token_expires_at",
    "failed_login_attempts", "locked_until", "last_login_at", "last_login_ip",
    "tokens_invalid_before",
    "must_change_password", "password_changed_at",
    "password_reset_token_hashed", "password_reset_code_hashed",
    "password_reset_expires_at", "password_reset_attempts",
    "completed_at", "result_at",  # mutation through dedicated endpoint
    "legacy_id",
    "is_owner", "is_active",  # toggled via separate admin endpoint
    "is_external", "is_admin",
    "ground_number", "recurring_period", "consultant_id",  # known to be EXTRA-stored (project)
}


def parse_model_columns(model_path):
    """Return dict: classname -> set of column names."""
    with open(model_path, encoding="utf-8") as f:
        src = f.read()
    lines = src.split("\n")
    classes = {}
    cur_class = None
    for _i, line in enumerate(lines):
        m_cls = re.match(r"class\s+(\w+)\s*\(", line)
        if m_cls and ("Base" in line or "Mixin" in line):
            cur_class = m_cls.group(1)
            classes[cur_class] = set()
            continue
        if cur_class and "mapped_column" in line:
            m_col = re.match(r"\s+([a-z_][a-z0-9_]*)\s*:\s*Mapped", line)
            if m_col:
                classes[cur_class].add(m_col.group(1))
    return classes


def parse_update_fields(schema_path):
    """Return dict: classname -> set of field names (only *Update classes)."""
    with open(schema_path, encoding="utf-8") as f:
        src = f.read()
    lines = src.split("\n")
    classes = {}
    cur_class = None
    for line in lines:
        m_cls = re.match(r"class\s+(\w+Update)\s*\(", line)
        if m_cls:
            cur_class = m_cls.group(1)
            classes[cur_class] = set()
            continue
        if not line.startswith("class ") and cur_class is None:
            continue
        if line.startswith("class "):
            cur_class = None  # left the Update class
            continue
        if cur_class:
            m_field = re.match(r"\s+([a-z_][a-z0-9_]*)\s*:", line)
            if m_field:
                classes[cur_class].add(m_field.group(1))
    return classes


# Build model column index
all_model_classes = {}
for root, _dirs, files in os.walk(MODELS_DIR):
    for fn in files:
        if not fn.endswith(".py"):
            continue
        for cname, cols in parse_model_columns(os.path.join(root, fn)).items():
            all_model_classes[cname] = cols


# For each Update schema, locate corresponding model and compare
issues = []
for root, _dirs, files in os.walk(SCHEMAS_DIR):
    for fn in files:
        if not fn.endswith(".py"):
            continue
        upd_classes = parse_update_fields(os.path.join(root, fn))
        for upd_name, upd_fields in upd_classes.items():
            # FooUpdate → look for "Foo" model
            base = upd_name[:-6]  # strip "Update"
            model_cols = all_model_classes.get(base)
            if model_cols is None:
                # Try plural/variant
                continue
            missing_in_update = model_cols - upd_fields - IGNORE
            if missing_in_update:
                issues.append((fn, upd_name, base, sorted(missing_in_update)))


print(f"Suspect Update schemas: {len(issues)}")
print()
for fn, upd, model, missing in issues:
    print(f"  {fn}:{upd}  (model={model})")
    for col in missing:
        print(f"     - {col}")
