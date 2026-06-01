"""Audit Vue files for action buttons (write/delete) without permission gates.

Heuristic — count write-related @click handlers, flag files that lack
either `usePermissions` import or `can(` checks in template.
"""
import os
import re

# Run from project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ROOT = os.path.join(ROOT, 'frontend', 'src')

# Walk vue files
results_no_guard = []
results_with_guard = []
files_with_action = 0

for dirpath, _, filenames in os.walk(SRC_ROOT):
    for fname in filenames:
        if not fname.endswith('.vue'):
            continue
        fp = os.path.join(dirpath, fname)
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                src = f.read()
        except Exception:
            continue
        # button @click handlers
        action_buttons = re.findall(r'<button[^>]*@click=\"([^\"]+)\"', src)
        if not action_buttons:
            continue
        files_with_action += 1
        # Filter write-like handlers
        write_handlers = [
            h for h in action_buttons
            if any(kw in h.lower() for kw in
                   ['delete', 'remove', 'save', 'create', 'submit',
                    'edit', 'add', 'archive', 'update'])
        ]
        if not write_handlers:
            continue
        # Permission usage
        has_perms = (
            'usePermissions' in src
            or re.search(r'\bcan\(', src) is not None
            or re.search(r'\bhasPermission\(', src) is not None
        )
        rel = os.path.relpath(fp, SRC_ROOT).replace(os.sep, '/')
        if not has_perms:
            results_no_guard.append((rel, len(write_handlers), write_handlers[:5]))
        else:
            results_with_guard.append((rel, len(write_handlers)))

print(f"Files with action buttons:           {files_with_action}")
print(f"Files using permissions (OK):        {len(results_with_guard)}")
print(f"Files WITHOUT permission guards:     {len(results_no_guard)}")
print()
print("=" * 80)
print("Top 30 files with WRITE actions but no perm guards (potential UI leaks):")
print("=" * 80)
for rel, n, samples in sorted(results_no_guard, key=lambda x: -x[1])[:30]:
    print(f"  {n:3d}  {rel}")
    for s in samples[:3]:
        print(f"         click → {s[:80]}")
