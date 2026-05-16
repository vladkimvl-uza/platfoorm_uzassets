"""Probe Firebase RTDB to see what financial data exists for the 6 problem
companies that are missing NSBU 2025 data in Postgres.

Run inside backend container:
    docker compose exec backend python /tmp/probe_firebase.py
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

FB_URL = "https://uza-projectsflow-default-rtdb.europe-west1.firebasedatabase.app"

# Map Postgres code → all known Firebase keys (russian + legacy aliases)
PROBES = {
    "utc": ["UzTelecom", "Узбектелеком"],
    "uty": ["Узбекистон Темир Йуллари", "UTY", "Uzbekistan Railways"],
    "uap": ["Uzbekistan Airports", "UAP"],
    "uks": ["Узкимёсаноат", "Uzkimyosanoat"],
    "ung": ["Узбекнефтегаз", "Uzbekneftegaz"],
    "upt": ["Узбекистон Почтаси", "UzPost", "Узбекистан Почтаси"],
}


def fetch_json(url: str):
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
            return json.loads(r.read())
    except Exception:
        return None


def describe(rec):
    """Summarize a Firebase financial record."""
    if rec is None:
        return "MISSING"
    if not isinstance(rec, dict):
        return f"{type(rec).__name__}: {repr(rec)[:60]}"

    # Years
    years = rec.get("years")
    if isinstance(years, dict):
        years = list(years.values())
    years = sorted(set(int(y) for y in (years or []) if y is not None))

    # How many actual data fields (excluding meta)
    META = {"years", "source", "_meta", "createdAt", "updatedAt", "lastEdit", "editedBy"}
    data_fields = [k for k in rec.keys() if k not in META and not k.startswith("_")]

    # Check if revenue 2025 has a non-null value
    rev = rec.get("revenue")
    if isinstance(rev, dict):
        rev = list(rev.values())
    rev_has_2025 = False
    if isinstance(rev, list) and 2025 in years:
        idx = years.index(2025) if 2025 in years else -1
        if idx >= 0 and idx < len(rev) and rev[idx] not in (None, ""):
            rev_has_2025 = True

    return (
        f"years={years} | "
        f"{len(data_fields)} fields | "
        f"revenue_2025={'YES' if rev_has_2025 else 'no'}"
    )


def main():
    print(f"{'='*100}")
    print(f"Firebase probe for 6 companies missing NSBU 2025 in Postgres")
    print(f"URL: {FB_URL}/pf/financials")
    print(f"{'='*100}\n")

    for code, candidates in PROBES.items():
        print(f"━━━ {code.upper()} ━━━")
        for k in candidates:
            enc = urllib.parse.quote(k)
            for prefix in ("", "__nsbu_"):
                url = f"{FB_URL}/pf/financials/{prefix}{enc}.json"
                rec = fetch_json(url)
                std_label = "NSBU" if prefix else "IFRS"
                key_display = f"{prefix}{k}"
                print(f"  [{std_label}] {key_display:45s} → {describe(rec)}")
        print()


if __name__ == "__main__":
    main()
