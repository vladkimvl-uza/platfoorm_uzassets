"""Find ForeignKey columns missing index=True (single-pass, multi-line aware).

Run: python backend/scripts/audit_fk_indexes.py
"""
import os
import re
import sys


def main():
    root_dir = os.path.join(os.path.dirname(__file__), "..", "app", "models")
    root_dir = os.path.abspath(root_dir)

    total_fk = 0
    missing = []  # list of (file, line_num, column_name, table_inferred)

    for root, _dirs, files in os.walk(root_dir):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            with open(path, encoding="utf-8") as f:
                src = f.read()
            lines = src.split("\n")

            # Walk: find each "ForeignKey" mention, then gather the enclosing
            # `mapped_column(...)` (multi-line) and check for index=True.
            in_class_table = None
            for i, line in enumerate(lines):
                m_tbl = re.search(r'__tablename__\s*=\s*[\'"]([^\'"]+)[\'"]', line)
                if m_tbl:
                    in_class_table = m_tbl.group(1)
                if "ForeignKey" not in line:
                    continue
                if "mapped_column" not in line:
                    # Could be a forward-string reference inside relationship; skip
                    continue
                total_fk += 1
                # Find column name from preceding line: "    column_name: Mapped[...]"
                col_name = None
                for j in range(i, max(-1, i - 4), -1):
                    m = re.match(r"\s+([a-z_][a-z0-9_]*)\s*:\s*Mapped", lines[j])
                    if m:
                        col_name = m.group(1)
                        break

                # Gather multi-line statement until parens balanced
                snippet = line
                depth = line.count("(") - line.count(")")
                k = i + 1
                while depth > 0 and k < len(lines):
                    snippet += lines[k]
                    depth += lines[k].count("(") - lines[k].count(")")
                    k += 1
                if "index=True" in snippet:
                    continue
                if "primary_key=True" in snippet:
                    continue  # PKs are indexed implicitly
                if "unique=True" in snippet:
                    continue  # unique constraints create indexes
                missing.append((path, i + 1, col_name or "?", in_class_table or "?"))

    print(f"Total FK columns: {total_fk}")
    print(f"Missing index=True: {len(missing)}")
    print()
    by_table = {}
    for path, ln, col, tbl in missing:
        by_table.setdefault(tbl, []).append((col, path, ln))
    for tbl in sorted(by_table):
        cols = by_table[tbl]
        print(f"  {tbl}: {len(cols)} column(s)")
        for col, path, ln in cols:
            short = os.path.relpath(path, root_dir)
            print(f"     - {col}  ({short}:{ln})")
    return missing


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
