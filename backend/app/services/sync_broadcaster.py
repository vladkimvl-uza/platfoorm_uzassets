"""Sync broadcaster (Pack 9aJ · Company Library — Phase 1.5).

Maintains in-memory map of WebSocket connections per scope and broadcasts
field-update messages so all open library / detail tabs auto-refresh.

Scope keys:
  * "global"         — receive every company field update
  * "{company_id}"   — receive updates for a specific company only

Message envelope:
{
  "type": "field_update",
  "company_id": "<uuid>",
  "field_code": "ebitda",
  "value": 30000.0,
  "source_module": "finmodel",
  "actor_id": "<uuid|null>",
  "ts": 1700000000.123
}

Best-effort delivery: dead sockets are pruned silently. Never raises.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any, Optional

from fastapi import WebSocket

log = logging.getLogger(__name__)

GLOBAL_SCOPE = "global"


class SyncBroadcaster:
    def __init__(self) -> None:
        self.connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, scope: str) -> None:
        await ws.accept()
        async with self._lock:
            self.connections[scope].add(ws)
        log.info("ws connect scope=%s total=%s", scope, len(self.connections[scope]))

    async def disconnect(self, ws: WebSocket, scope: str) -> None:
        async with self._lock:
            self.connections[scope].discard(ws)

    async def broadcast_field_update(
        self,
        *,
        company_id: str,
        field_code: str,
        value: Any,
        source_module: Optional[str],
        actor_id: Optional[str] = None,
    ) -> int:
        """Push a field_update to every subscriber of GLOBAL_SCOPE and the
        specific company_id scope. Returns the count of successful pushes.
        """
        message = {
            "type": "field_update",
            "company_id": company_id,
            "field_code": field_code,
            "value": value,
            "source_module": source_module,
            "actor_id": actor_id,
            "ts": time.time(),
        }
        payload = json.dumps(message, default=str, ensure_ascii=False)

        sent = 0
        dead: list[tuple[str, WebSocket]] = []
        for scope in (GLOBAL_SCOPE, company_id):
            for ws in list(self.connections.get(scope, ())):
                try:
                    await ws.send_text(payload)
                    sent += 1
                except Exception as e:
                    log.debug("ws send failed scope=%s err=%s", scope, e)
                    dead.append((scope, ws))

        if dead:
            async with self._lock:
                for scope, ws in dead:
                    self.connections[scope].discard(ws)
        return sent

    async def broadcast_raw(self, scope: str, message: dict) -> int:
        """Send an arbitrary JSON message to a single scope."""
        payload = json.dumps(message, default=str, ensure_ascii=False)
        sent = 0
        dead: list[WebSocket] = []
        for ws in list(self.connections.get(scope, ())):
            try:
                await ws.send_text(payload)
                sent += 1
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self.connections[scope].discard(ws)
        return sent


# Module-level singleton — import everywhere as `from app.services.sync_broadcaster import broadcaster`
broadcaster = SyncBroadcaster()
