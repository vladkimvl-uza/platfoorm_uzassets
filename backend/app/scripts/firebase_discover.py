"""Firebase structure discovery — produces a privacy-preserving "shape report".

Reads the Firebase Realtime Database structure WITHOUT outputting any actual
values. Only field names, types, magnitudes and counts are written to the
report. Safe to share with developers for migration mapping.

Usage:
    docker compose exec -e PYTHONPATH=/app backend python -m app.scripts.firebase_discover

Reads:
    /app/firebase-service-account.json   (mounted from backend/firebase-service-account.json)
Writes:
    /app/firebase-discovery-report.json  (mounted to backend/firebase-discovery-report.json)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials, db


# =====================================================================
# Configuration
# =====================================================================

SERVICE_ACCOUNT = Path("/app/firebase-service-account.json")
DATABASE_URL    = "https://uza-projectsflow-default-rtdb.europe-west1.firebasedatabase.app/"
OUTPUT          = Path("/app/firebase-discovery-report.json")

# Limits to keep the report small and safe
MAX_SAMPLES_PER_NODE = 2     # how many children to sample at each container
MAX_DEPTH            = 4     # how deep to descend into nested objects
MAX_FIELDS_REPORTED  = 30    # cap field count per object to keep report readable


# =====================================================================
# Privacy-preserving shape inspection
# =====================================================================

def magnitude(n: float) -> str:
    """Bucket a number by order of magnitude — never reveal exact value."""
    a = abs(n)
    if a == 0:           return "zero"
    if a < 10:           return "<10"
    if a < 100:          return "<100"
    if a < 10_000:       return "<10k"
    if a < 1_000_000:    return "<1M"
    if a < 1_000_000_000: return "<1B"
    return ">=1B"


def looks_like(s: str) -> str | None:
    """Detect well-known string formats — never report the value."""
    if not s:
        return None
    if "@" in s and "." in s and " " not in s:
        return "email"
    if len(s) == 36 and s.count("-") == 4:
        return "uuid"
    if len(s) >= 16 and (s.startswith("http://") or s.startswith("https://")):
        return "url"
    if s.startswith("$2") and len(s) == 60:
        return "bcrypt_hash"
    # ISO date
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return "iso_datetime"
    return None


def shape_of(value: Any, depth: int = 0) -> dict:
    """Describe a value without disclosing its content."""
    if value is None:
        return {"type": "null"}

    if isinstance(value, bool):
        return {"type": "bool"}

    if isinstance(value, int):
        return {"type": "int", "magnitude": magnitude(value)}

    if isinstance(value, float):
        return {"type": "float", "magnitude": magnitude(value)}

    if isinstance(value, str):
        out = {"type": "string", "len": len(value)}
        f = looks_like(value)
        if f:
            out["format"] = f
        return out

    if isinstance(value, list):
        out = {"type": "list", "len": len(value)}
        if value and depth < MAX_DEPTH:
            # Sample types of first few elements
            child_shapes = [shape_of(v, depth + 1) for v in value[:3]]
            out["element_shapes"] = child_shapes
        return out

    if isinstance(value, dict):
        keys = list(value.keys())
        # Detect "array as object" — Firebase stores lists as {0: ..., 1: ..., 2: ...}
        all_numeric = bool(keys) and all(str(k).lstrip("-").isdigit() for k in keys)

        if all_numeric:
            out = {"type": "array_as_object", "len": len(keys)}
            if depth < MAX_DEPTH and keys:
                first_val = value[keys[0]]
                out["element_shape"] = shape_of(first_val, depth + 1)
            return out

        # Regular object: describe its fields
        if depth >= MAX_DEPTH:
            return {"type": "object", "field_count": len(keys), "fields": "<truncated_by_depth>"}

        sorted_keys = sorted(keys)
        truncated = sorted_keys[:MAX_FIELDS_REPORTED]
        more = len(sorted_keys) - len(truncated)
        fields = {k: shape_of(value[k], depth + 1) for k in truncated}
        out = {"type": "object", "field_count": len(sorted_keys), "fields": fields}
        if more > 0:
            out["fields_omitted"] = more
        return out

    # Fallback for unexpected types (Firebase usually returns only the above)
    return {"type": type(value).__name__}


# =====================================================================
# Firebase exploration
# =====================================================================

def init_firebase() -> None:
    if not SERVICE_ACCOUNT.is_file():
        print(
            f"❌ Service-account ключ не найден: {SERVICE_ACCOUNT}\n"
            f"\n"
            f"Скачай его так:\n"
            f"  1. Открой Firebase Console (https://console.firebase.google.com)\n"
            f"  2. Проект uza-projectsflow → ⚙ Settings → Service Accounts\n"
            f"  3. Generate new private key → скачается JSON\n"
            f"  4. Положи файл в:  backend/firebase-service-account.json\n",
            file=sys.stderr,
        )
        sys.exit(1)

    cred = credentials.Certificate(str(SERVICE_ACCOUNT))
    firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})


def explore(path: str, samples_per_node: int = MAX_SAMPLES_PER_NODE) -> dict:
    """Explore a Firebase path: count children, sample shape of a few of them."""
    ref = db.reference(path)

    # Try a shallow read to avoid downloading huge subtrees
    try:
        shallow = ref.get(shallow=True)
    except Exception as e:
        return {"path": path, "error": f"shallow_failed: {type(e).__name__}: {e}"}

    if shallow is None:
        return {"path": path, "type": "null"}

    # If shallow is a leaf (not a dict), download it directly — should be small
    if not isinstance(shallow, dict):
        try:
            value = ref.get()
            return {"path": path, **shape_of(value)}
        except Exception as e:
            return {"path": path, "error": f"leaf_read_failed: {type(e).__name__}"}

    # It's a parent — sample N children
    keys = list(shallow.keys())
    report: dict[str, Any] = {
        "path": path,
        "type": "container",
        "child_count": len(keys),
    }

    sampled_shapes = []
    for i, key in enumerate(keys[:samples_per_node]):
        child_path = f"{path}/{key}".replace("//", "/")
        try:
            child_value = db.reference(child_path).get()
            sampled_shapes.append({
                "sample_index": i,
                "shape": shape_of(child_value),
            })
        except Exception as e:
            sampled_shapes.append({
                "sample_index": i,
                "error": f"{type(e).__name__}: {e}",
            })

    report["sampled_children"] = sampled_shapes
    return report


# =====================================================================
# Main
# =====================================================================

def main() -> int:
    init_firebase()
    print(f"Подключаюсь к Firebase: {DATABASE_URL}")
    print()

    # Top-level keys
    try:
        root_shallow = db.reference("/").get(shallow=True)
    except Exception as e:
        print(f"❌ Не могу прочитать корень: {e}", file=sys.stderr)
        return 1

    if not root_shallow or not isinstance(root_shallow, dict):
        print("⚠ База пустая или невозможно прочитать.")
        return 1

    top_keys = sorted(root_shallow.keys())
    print(f"Найдено {len(top_keys)} разделов: {top_keys}")
    print()

    report: dict[str, Any] = {
        "database_url": DATABASE_URL,
        "top_level_keys": top_keys,
        "sections": {},
        "limits": {
            "max_samples_per_node": MAX_SAMPLES_PER_NODE,
            "max_depth": MAX_DEPTH,
            "max_fields_reported": MAX_FIELDS_REPORTED,
        },
    }

    for section in top_keys:
        print(f"  Изучаю /{section} ...", end="", flush=True)
        section_report = explore(f"/{section}")
        report["sections"][section] = section_report
        cc = section_report.get("child_count")
        if cc is not None:
            print(f"  ({cc} child{'ren' if cc != 1 else ''})")
        else:
            print(f"  ({section_report.get('type', '?')})")

    # Save report
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print()
    print(f"✅ Отчёт сохранён: {OUTPUT}")
    print(f"   На хосте этот файл лежит по пути:")
    print(f"   backend/firebase-discovery-report.json")
    print()
    print(f"   Размер: {OUTPUT.stat().st_size} байт")
    print()
    print(f"Этот файл содержит ТОЛЬКО структуру (имена полей, типы, размерности).")
    print(f"Никаких реальных значений (имён, паролей, сумм) — только их форма.")
    print(f"Можно безопасно отправить разработчику для написания мигратора.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
