"""
AI service — Anthropic API client + streaming helpers.

Pack 7.5 additions:
  • stream_chat_with_tools — multi-turn loop with tool execution
    Yields SSE-format frames; injects custom 'tool_use_start',
    'tool_use_end', 'tool_result' events between AI engine turns
    so frontend can show "AI is using tool X..." badges.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any, AsyncGenerator, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Model tiers — UI/config используют нейтральные алиасы; реальные provider-id
# берутся из окружения (вне VCS). Неизвестная строка считается готовым id
# (legacy-значения из БД проходят как есть).
_MODEL_TIER_ENV = {
    "ai-balanced": "AI_MODEL_BALANCED",
    "ai-deep": "AI_MODEL_DEEP",
    "ai-fast": "AI_MODEL_FAST",
}


def _resolve_model(m: Optional[str]) -> str:
    key = _MODEL_TIER_ENV.get(m or "")
    if key:
        return os.environ.get(key) or os.environ.get("AI_MODEL_BALANCED") or (m or "")
    return m or DEFAULT_MODEL


DEFAULT_MODEL = os.environ.get("AI_MODEL_DEFAULT", "ai-balanced")
DEFAULT_MAX_TURNS = 12  # safety cap for tool_use loop — bumped 6→12 for chained verify_count flows


def get_api_key() -> str:
    return os.environ.get("ANTHROPIC_API_KEY", "")


def is_enabled() -> bool:
    return bool(get_api_key())


# ──────────────────────────── Single-turn (legacy, no tools) ────────────────────────────

async def stream_chat(
    *,
    system: str,
    messages: list[dict[str, Any]],
    model: Optional[str] = None,
    max_tokens: int = 16000,
    temperature: float = 0.25,
) -> AsyncGenerator[bytes, None]:
    """Stream chat completion from Anthropic. Yields raw SSE chunks."""
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    payload = {
        "model": _resolve_model(model),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": messages,
        "stream": True,
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        async with client.stream("POST", ANTHROPIC_API_URL, json=payload, headers=headers) as resp:
            if resp.status_code != 200:
                err_text = await resp.aread()
                err = {
                    "type": "error",
                    "error": {
                        "status": resp.status_code,
                        "message": err_text.decode("utf-8", errors="replace"),
                    },
                }
                yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n".encode("utf-8")
                return

            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk


async def complete_once(
    *,
    system: str,
    prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 1800,
    temperature: float = 0.3,
    tools: Optional[list] = None,
    timeout: float = 120.0,
) -> str:
    """Однократный (нестриминговый) вызов AI engine → собранный текст ответа.

    Используется для генерации детерминированных артефактов (executive-бриф).
    """
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")
    payload = {
        "model": _resolve_model(model),
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    if tools:
        payload["tools"] = tools
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(ANTHROPIC_API_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()


def extract_text_and_stats(events: list[dict]) -> tuple[str, int | None, int | None, str | None]:
    """Walk parsed SSE events, return (full_text, tokens_in, tokens_out, stop_reason)."""
    text_parts: list[str] = []
    tin: int | None = None
    tout: int | None = None
    stop: str | None = None
    for ev in events:
        et = ev.get("type")
        if et == "content_block_delta":
            d = ev.get("delta") or {}
            if d.get("type") == "text_delta":
                t = d.get("text", "")
                if t:
                    text_parts.append(t)
        elif et == "message_start":
            usage = (ev.get("message") or {}).get("usage") or {}
            if "input_tokens" in usage:
                tin = usage["input_tokens"]
            if "output_tokens" in usage:
                tout = usage["output_tokens"]
        elif et == "message_delta":
            d = ev.get("delta") or {}
            if d.get("stop_reason"):
                stop = d["stop_reason"]
            usage = ev.get("usage") or {}
            if "output_tokens" in usage:
                tout = usage["output_tokens"]
    return "".join(text_parts), tin, tout, stop


# ──────────────────────────── Multi-turn with tools ────────────────────────────

async def stream_chat_with_tools(
    *,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict],
    db: AsyncSession,
    tool_dispatcher,                       # async callable: (name, args, db) -> dict
    model: Optional[str] = None,
    max_tokens: int = 16000,
    temperature: float = 0.25,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> AsyncGenerator[bytes, None]:
    """
    Multi-turn streaming chat with tool execution.

    Flow:
      1. Send messages + tools to Anthropic
      2. Stream response. If we see content_blocks of type 'tool_use' with
         stop_reason == 'tool_use', collect them.
      3. For each tool_use, run dispatcher(name, args, db) and append a
         'tool_result' user message.
      4. Loop with augmented messages until model returns stop_reason='end_turn'.

    Yields:
      - All raw Anthropic SSE chunks (so frontend sees text deltas in real-time)
      - Plus custom events:
          event: tool_use_start
          data: {name, args, id}
          event: tool_use_end
          data: {id, ok, result_summary}
    """
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    # Working copy of messages (we'll append assistant + tool_result rounds)
    convo: list[dict[str, Any]] = [dict(m) for m in messages]

    for turn in range(max_turns):
        payload = {
            "model": _resolve_model(model),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": convo,
            "tools": tools,
            "stream": True,
        }

        # Accumulate response: text parts, tool_use blocks
        assistant_blocks: list[dict] = []  # for sending back as assistant turn
        current_block: Optional[dict] = None  # in-progress block being streamed
        current_block_input_str = ""
        stop_reason: Optional[str] = None

        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("POST", ANTHROPIC_API_URL, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    err_text = await resp.aread()
                    err = {
                        "type": "error",
                        "error": {
                            "status": resp.status_code,
                            "message": err_text.decode("utf-8", errors="replace"),
                        },
                    }
                    yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n".encode("utf-8")
                    return

                # We need to BOTH yield raw bytes (so frontend sees text) AND
                # parse them to discover tool_use. So we re-serialize parsed
                # events; simpler: parse line-by-line, yield the raw line, and
                # also accumulate.
                buf = b""
                async for chunk in resp.aiter_bytes():
                    if not chunk:
                        continue
                    yield chunk  # forward to frontend immediately
                    buf += chunk

                    # Parse complete SSE frames separated by \n\n
                    while b"\n\n" in buf:
                        frame_bytes, _, buf = buf.partition(b"\n\n")
                        frame_text = frame_bytes.decode("utf-8", errors="replace")
                        data_str = ""
                        for ln in frame_text.split("\n"):
                            if ln.startswith("data:"):
                                data_str += ln[5:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            ev = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        et = ev.get("type")
                        if et == "content_block_start":
                            cb = ev.get("content_block") or {}
                            current_block = {
                                "type": cb.get("type"),
                                "id": cb.get("id"),
                                "name": cb.get("name"),
                                "input": cb.get("input") or {},
                                "text": "",
                            }
                            current_block_input_str = ""
                        elif et == "content_block_delta":
                            d = ev.get("delta") or {}
                            if current_block is None:
                                continue
                            if d.get("type") == "text_delta":
                                current_block["text"] += d.get("text", "")
                            elif d.get("type") == "input_json_delta":
                                current_block_input_str += d.get("partial_json", "")
                        elif et == "content_block_stop":
                            if current_block is not None:
                                if current_block.get("type") == "tool_use":
                                    if current_block_input_str:
                                        try:
                                            current_block["input"] = json.loads(current_block_input_str)
                                        except json.JSONDecodeError:
                                            pass
                                    assistant_blocks.append({
                                        "type": "tool_use",
                                        "id": current_block.get("id"),
                                        "name": current_block.get("name"),
                                        "input": current_block.get("input") or {},
                                    })
                                elif current_block.get("type") == "text":
                                    txt = current_block.get("text", "")
                                    if txt:
                                        assistant_blocks.append({"type": "text", "text": txt})
                                current_block = None
                                current_block_input_str = ""
                        elif et == "message_delta":
                            d = ev.get("delta") or {}
                            if d.get("stop_reason"):
                                stop_reason = d["stop_reason"]

        # End of streaming for this turn. Decide what to do.
        if stop_reason != "tool_use":
            # Model finished — done.
            return

        # Tool execution required.
        # Append assistant turn (with tool_use blocks) and tool_result user turn.
        tool_use_blocks = [b for b in assistant_blocks if b.get("type") == "tool_use"]
        if not tool_use_blocks:
            # Anomaly — no tool blocks but stop_reason says tool_use
            return

        convo.append({"role": "assistant", "content": assistant_blocks})

        tool_result_blocks: list[dict] = []
        for tb in tool_use_blocks:
            tool_id = tb.get("id")
            tool_name = tb.get("name") or ""
            tool_args = tb.get("input") or {}

            # Emit custom 'tool_use_start' for frontend
            start_evt = {
                "type": "tool_use_start",
                "id": tool_id,
                "name": tool_name,
                "args": tool_args,
            }
            yield f"event: tool_use_start\ndata: {json.dumps(start_evt, ensure_ascii=False)}\n\n".encode("utf-8")

            # Execute
            try:
                result = await tool_dispatcher(tool_name, tool_args, db)
                ok = "error" not in (result if isinstance(result, dict) else {})
            except Exception as e:
                logger.exception("Tool execution failed")
                result = {"error": f"Tool execution failed: {e}"}
                ok = False

            # Build summary for UI (tiny)
            summary = ""
            if isinstance(result, dict):
                if "error" in result:
                    summary = result["error"][:200]
                elif "count" in result and "table" in result:  # verify_count
                    summary = f"{result['table']}: {result['count']}"
                elif "by_year" in result:  # compare_years
                    summary = f"{result.get('metric','')}: {result.get('by_year',{})}"
                elif "tasks" in result:
                    summary = f"найдено {len(result.get('tasks', []))} задач"
                elif "results" in result:
                    summary = f"сравнение {len(result.get('results', []))} компаний"
                elif "loans" in result:
                    summary = f"{len(result.get('loans', []))} займов"
                elif "consultants" in result:
                    summary = f"{len(result.get('consultants', []))} консультантов"
                elif "comments" in result:
                    summary = f"{len(result.get('comments', []))} комментариев"
                elif "name_ru" in result or "name_en" in result:
                    summary = result.get("name_ru") or result.get("name_en") or ""
                else:
                    summary = "готово"

            # include full result for UI inspection (capped to 50KB)
            try:
                result_json = json.dumps(result, ensure_ascii=False, default=str)
                if len(result_json) > 50_000:
                    result_json = result_json[:50_000] + '..."[truncated]"'
            except Exception:
                result_json = '{"error":"failed to serialize result"}'

            end_evt = {
                "type": "tool_use_end",
                "id": tool_id,
                "name": tool_name,
                "ok": ok,
                "summary": summary,
                "result_json": result_json,
            }
            yield f"event: tool_use_end\ndata: {json.dumps(end_evt, ensure_ascii=False)}\n\n".encode("utf-8")

            # Append to tool_result blocks for next turn
            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

        convo.append({"role": "user", "content": tool_result_blocks})

    # Loop exhausted
    err = {
        "type": "error",
        "error": {"message": f"Max tool turns ({max_turns}) exhausted"},
    }
    yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n".encode("utf-8")
