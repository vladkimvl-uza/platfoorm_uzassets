"""Diagnostic: inspect what's actually in Firebase /pf/tasks.

Usage:
    docker compose exec -e PYTHONPATH=/app backend \\
        python -m app.scripts.firebase_inspect_tasks

Output: structure type, item count, sample of first 3 items.
This is a READ-ONLY script — never writes anything anywhere.
"""
from __future__ import annotations

import json
import sys

from app.scripts.firebase_migration.base import FirebaseClient, normalize_array


def _summarize(name: str, value) -> None:
    print(f"\n=== {name} ===")
    if value is None:
        print("  type: NULL  (path doesn't exist or is empty)")
        return

    print(f"  python type: {type(value).__name__}")

    if isinstance(value, list):
        print(f"  list length: {len(value)}")
    elif isinstance(value, dict):
        keys = list(value.keys())
        print(f"  dict keys: {len(keys)}")
        # Are keys numeric (Firebase array)?
        all_numeric = bool(keys) and all(
            isinstance(k, str) and k.isdigit() for k in keys
        )
        print(f"  numeric keys (Firebase array): {all_numeric}")
        print(f"  first 5 keys: {keys[:5]}")

    # Try normalize_array
    try:
        norm = normalize_array(value)
        print(f"  normalize_array → list of length: {len(norm)}")
        if norm:
            sample = norm[0]
            if isinstance(sample, dict):
                print(f"  first item keys: {list(sample.keys())[:15]}")
                print(f"  first item title:    {sample.get('title')!r}")
                print(f"  first item status:   {sample.get('status')!r}")
                print(f"  first item boardId:  {sample.get('boardId')!r}")
            else:
                print(f"  first item type: {type(sample).__name__}  value: {sample!r:.200}")
    except Exception as e:
        print(f"  normalize_array EXCEPTION: {type(e).__name__}: {e}")


def main() -> int:
    print("Connecting to Firebase…")
    fb = FirebaseClient()

    # 1. Top-level /pf shallow
    print("\n=== /pf shallow (top-level keys) ===")
    pf_keys = fb.shallow_keys("/pf")
    print(f"  keys count: {len(pf_keys)}")
    print(f"  has 'tasks': {'tasks' in pf_keys}")
    print(f"  has 'boards': {'boards' in pf_keys}")
    print(f"  all keys: {sorted(pf_keys)[:30]}")

    # 2. /pf/tasks shallow — to see if it's hierarchical or flat
    print("\n=== /pf/tasks shallow ===")
    try:
        task_keys = fb.shallow_keys("/pf/tasks")
        print(f"  keys count: {len(task_keys)}")
        print(f"  first 10 keys: {task_keys[:10]}")
        all_numeric = bool(task_keys) and all(k.isdigit() for k in task_keys)
        print(f"  all numeric (= flat array): {all_numeric}")
    except Exception as e:
        print(f"  EXCEPTION: {type(e).__name__}: {e}")

    # 3. /pf/tasks full (what we read in TasksMigrator)
    raw_tasks = fb.get("/pf/tasks")
    _summarize("/pf/tasks (full payload)", raw_tasks)

    # 4. /pf/boards for comparison
    raw_boards = fb.get("/pf/boards")
    _summarize("/pf/boards (full payload)", raw_boards)

    # 5. Also try /pf/tasks/{firstKey} just in case it's hierarchical
    try:
        first_key = fb.shallow_keys("/pf/tasks")[:1]
        if first_key:
            sub_path = f"/pf/tasks/{first_key[0]}"
            sub_data = fb.get(sub_path)
            _summarize(f"{sub_path}", sub_data)
    except Exception as e:
        print(f"\n  Could not fetch first sub-key: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
