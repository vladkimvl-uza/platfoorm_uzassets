"""Scan all mapped_column blocks containing ForeignKey for missing index=True.
Handles multi-line declarations."""
import os
import re

ROOT = "/app/app/models"
total_fk = 0
missing = []

for root, _dirs, files in os.walk(ROOT):
    for fn in files:
        if not fn.endswith(".py"):
            continue
        path = os.path.join(root, fn)
        with open(path, encoding="utf-8") as f:
            src = f.read()
        lines = src.split("\n")
        cur_table = None
        i = 0
        while i < len(lines):
            line = lines[i]
            m_tbl = re.search(r'__tablename__\s*=\s*[\'"]([^\'"]+)[\'"]', line)
            if m_tbl:
                cur_table = m_tbl.group(1)
            # Detect mapped_column( opening
            if "mapped_column(" in line:
                # Find column name from this or prev line
                col_name = "?"
                m = re.search(r'^\s*([a-z_][a-z0-9_]*)\s*:\s*Mapped', line)
                if m:
                    col_name = m.group(1)
                # Gather block until parens balanced
                block = line
                depth = line.count("(") - line.count(")")
                k = i
                while depth > 0 and k + 1 < len(lines):
                    k += 1
                    block += "\n" + lines[k]
                    depth += lines[k].count("(") - lines[k].count(")")
                # Is FK?
                if "ForeignKey" in block:
                    total_fk += 1
                    if (
                        "index=True" not in block
                        and "primary_key=True" not in block
                        and "unique=True" not in block
                    ):
                        missing.append((cur_table or "?", col_name, os.path.basename(path), i + 1))
                i = max(k + 1, i + 1)
                continue
            i += 1

print(f"Total FK: {total_fk}")
print(f"Missing index: {len(missing)}")
by_table = {}
for tbl, col, fn, ln in missing:
    by_table.setdefault(tbl, []).append((col, fn, ln))
for tbl in sorted(by_table):
    print(f"  {tbl}:")
    for col, fn, ln in by_table[tbl]:
        print(f"     - {col}  ({fn}:{ln})")
