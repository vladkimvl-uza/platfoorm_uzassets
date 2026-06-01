"""Bulk replace Decimal type annotations with MoneyDecimal in schemas/.

Safe substitution:
  - `: Decimal\b` → `: MoneyDecimal`  (type annotations only)
  - `Optional[Decimal]` → `Optional[MoneyDecimal]`
  - `List[Decimal]` → `List[MoneyDecimal]`
  - keeps `Decimal(...)` constructor calls untouched
  - keeps existing `from decimal import Decimal` (still needed for defaults)
  - injects `from app.schemas._types import MoneyDecimal` if missing
"""
import os
import re

SCHEMAS_DIR = "/app/app/schemas"

# Files to skip (already migrated, base type, etc.)
SKIP = {"_types.py", "__init__.py", "procurement_analysis.py"}


def migrate(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    original = src

    if "Decimal" not in src:
        return False

    # Match `: Decimal` followed by space, comma, newline, =, ), ]
    # Not preceded by `(` (so `Decimal(...)` constructor stays).
    # Pattern: `: Decimal\b` where context is type annotation.
    new = re.sub(r":\s*Decimal\b", ": MoneyDecimal", src)
    new = re.sub(r"Optional\[Decimal\]", "Optional[MoneyDecimal]", new)
    new = re.sub(r"List\[Decimal\]", "List[MoneyDecimal]", new)
    new = re.sub(r"Dict\[([^,\]]+),\s*Decimal\]", r"Dict[\1, MoneyDecimal]", new)

    if new == original:
        return False

    # Add MoneyDecimal import if not present
    if "from app.schemas._types import MoneyDecimal" not in new:
        # Insert after "from decimal import Decimal" if exists
        m = re.search(r"^(from\s+decimal\s+import\s+Decimal.*?)$", new, re.MULTILINE)
        if m:
            insertion = m.group(1) + "\n\nfrom app.schemas._types import MoneyDecimal"
            new = new.replace(m.group(1), insertion, 1)
        else:
            # Insert at top after first blank line
            new = "from app.schemas._types import MoneyDecimal\n" + new

    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return True


changed = []
for fn in sorted(os.listdir(SCHEMAS_DIR)):
    if not fn.endswith(".py") or fn in SKIP:
        continue
    path = os.path.join(SCHEMAS_DIR, fn)
    if migrate(path):
        changed.append(fn)

print(f"Migrated {len(changed)} files:")
for fn in changed:
    print(f"  {fn}")
