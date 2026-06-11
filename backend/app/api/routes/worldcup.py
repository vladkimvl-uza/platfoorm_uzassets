"""World Cup 2026 · Группа K — live-данные для виджета на /home.

Источник: football-data.org v4 (ключ из env FOOTBALL_API_KEY). Если ключа нет
или API недоступен — отдаём статический фолбэк (расписание известно заранее).
Кеш в памяти на 5 минут, чтобы не выходить за лимиты free-tier.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/worldcup", tags=["worldcup"])

_API = "https://api.football-data.org/v4/competitions/WC"
_CACHE: dict = {"ts": 0.0, "data": None}
_TTL = 300  # 5 мин

# Название (англ.) → (RU, ISO-2 страны)
_TEAM = {
    "portugal": ("Португалия", "pt"),
    "colombia": ("Колумбия", "co"),
    "uzbekistan": ("Узбекистан", "uz"),
    "dr congo": ("ДР Конго", "cd"),
    "congo dr": ("ДР Конго", "cd"),
    "democratic republic of congo": ("ДР Конго", "cd"),
}
_MONTHS = ["", "января", "февраля", "марта", "апреля", "мая", "июня",
           "июля", "августа", "сентября", "октября", "ноября", "декабря"]

# Статический фолбэк (расписание Группы K, счёта пустые до старта 17 июня).
_STATIC = {
    "live": False,
    "standings": [
        {"code": "POR", "cc": "pt", "name": "Португалия", "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0},
        {"code": "COL", "cc": "co", "name": "Колумбия",   "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0},
        {"code": "UZB", "cc": "uz", "name": "Узбекистан", "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0},
        {"code": "COD", "cc": "cd", "name": "ДР Конго",   "p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0},
    ],
    "uz_matches": [
        {"date": "18 июня · 07:00", "h": "Узбекистан", "hcc": "uz", "a": "Колумбия",   "acc": "co", "score": "— : —"},
        {"date": "23 июня · 22:00", "h": "Португалия", "hcc": "pt", "a": "Узбекистан", "acc": "uz", "score": "— : —"},
        {"date": "28 июня · 04:30", "h": "ДР Конго",   "hcc": "cd", "a": "Узбекистан", "acc": "uz", "score": "— : —"},
    ],
}


def _team(name: str):
    return _TEAM.get((name or "").strip().lower(), (name, "un"))


def _code(cc: str) -> str:
    return {"pt": "POR", "co": "COL", "uz": "UZB", "cd": "COD"}.get(cc, cc.upper())


def _tashkent_label(utc_iso: str) -> str:
    try:
        dt = datetime.fromisoformat(utc_iso.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=5)))
        return f"{dt.day} {_MONTHS[dt.month]} · {dt.strftime('%H:%M')}"
    except Exception:
        return ""


async def _fetch_live(key: str) -> dict | None:
    headers = {"X-Auth-Token": key}
    try:
        async with httpx.AsyncClient(timeout=8.0) as c:
            st = (await c.get(f"{_API}/standings", headers=headers)).json()
            mt = (await c.get(f"{_API}/matches", headers=headers)).json()
    except Exception:
        return None

    # — таблица Группы K —
    standings = []
    for s in st.get("standings", []):
        grp = (s.get("group") or "")
        if s.get("type") == "TOTAL" and grp.upper().endswith("K"):
            for row in s.get("table", []):
                ru, cc = _team(row.get("team", {}).get("name", ""))
                standings.append({
                    "code": _code(cc), "cc": cc, "name": ru,
                    "p": row.get("playedGames", 0), "w": row.get("won", 0),
                    "d": row.get("draw", 0), "l": row.get("lost", 0),
                    "gf": row.get("goalsFor", 0), "ga": row.get("goalsAgainst", 0),
                    "pts": row.get("points", 0),
                })
            break
    if not standings:
        return None

    # — матчи Узбекистана —
    uz_matches = []
    for m in mt.get("matches", []):
        h = m.get("homeTeam", {}).get("name", "")
        a = m.get("awayTeam", {}).get("name", "")
        hru, hcc = _team(h)
        aru, acc = _team(a)
        if "Узбекистан" not in (hru, aru):
            continue
        ft = (m.get("score") or {}).get("fullTime") or {}
        hs, as_ = ft.get("home"), ft.get("away")
        score = f"{hs} : {as_}" if hs is not None and as_ is not None else "— : —"
        uz_matches.append({
            "date": _tashkent_label(m.get("utcDate", "")) or "—",
            "h": hru, "hcc": hcc, "a": aru, "acc": acc, "score": score,
        })

    return {"live": True, "standings": standings,
            "uz_matches": uz_matches or _STATIC["uz_matches"]}


@router.get("/groupk")
async def groupk(user: User = Depends(get_current_user)):
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _TTL:
        return _CACHE["data"]

    key = os.environ.get("FOOTBALL_API_KEY", "").strip()
    data = None
    if key:
        data = await _fetch_live(key)
    if data is None:
        data = _STATIC
    _CACHE["ts"] = now
    _CACHE["data"] = data
    return data
