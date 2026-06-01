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
        for i, line in enumerate(lines):
            m_tbl = re.search(r'__tablename__\s*=\s*[\'"]([^\'"]+)[\'"]', line)
            if m_tbl:
                cur_table = m_tbl.group(1)
            if "ForeignKey" not in line:
                continue
            if "mapped_column" not in line:
                continue
            total_fk += 1
            col_name = "?"
            for j in range(i, max(-1, i - 4), -1):
                m = re.match(r'\s+([a-z_][a-z0-9_]*)\s*:\s*Mapped', lines[j])
                if m:
                    col_name = m.group(1)
                    break
            snippet = line
            depth = line.count("(") - line.count(")")
            k = i + 1
            while depth > 0 and k < len(lines):
                snippet += lines[k]
                depth += lines[k].count("(") - lines[k].count(")")
                k += 1
            if "index=True" in snippet or "primary_key=True" in snippet or "unique=True" in snippet:
                continue
            missing.append((cur_table or "?", col_name))

print(f"Total FK: {total_fk}")
print(f"Missing index: {len(missing)}")
by_table = {}
for tbl, col in missing:
    by_table.setdefault(tbl, []).append(col)
for tbl in sorted(by_table):
    print(f"  {tbl}: {by_table[tbl]}")
