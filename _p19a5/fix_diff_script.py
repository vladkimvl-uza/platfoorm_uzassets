"""Patch the broken diff_all_financials.py script.

Removes the broken line 127 that calls grade() with no args, which crashes
the script before printing per-company results.

Run inside backend container:
    docker compose exec backend python /tmp/fix_diff_script.py
"""
from pathlib import Path
import re

target = Path("/app/app/scripts/firebase_migration/diff_all_financials.py")
text = target.read_text()

# The broken lines look like:
#     ifrs_g = grade(*[totals.get(k, 0) for k in []])  # noqa
# Several variants exist — strip any line invoking grade() with empty unpack
broken_pattern = re.compile(
    r"^\s*\w+_g\s*=\s*grade\(\*\[totals\.get\([^)]+\) for k in \[\]\]\).*$",
    re.MULTILINE,
)

matches = broken_pattern.findall(text)
if not matches:
    print("No broken grade() lines found — script may be already patched")
    raise SystemExit(0)

print(f"Found {len(matches)} broken lines:")
for m in matches:
    print(f"  {m.strip()}")

text2 = broken_pattern.sub("    # removed broken grade() call", text)
target.write_text(text2)
print(f"\nPatched. Now run:")
print(f"  docker compose exec backend python -m app.scripts.firebase_migration.diff_all_financials --details")
