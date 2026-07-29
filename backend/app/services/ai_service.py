"""
AI service — LLM API client + streaming helpers.

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

from app.core.i18n import ai_language_instruction

logger = logging.getLogger(__name__)

# Endpoint и имя версии-заголовка внешнего LLM-провайдера — ТОЛЬКО из окружения
# (вне VCS), чтобы провайдер не светился в коде; задаются в .env на каждом
# окружении. Версия-дата нейтральна — допустим литерал-fallback.
_API_URL = os.environ.get("LLM_API_URL", "")
_API_VERSION = os.environ.get("LLM_API_VERSION") or "2023-06-01"
_VERSION_HEADER = os.environ.get("LLM_VERSION_HEADER", "")

# Model tiers — UI/config используют нейтральные алиасы; реальные provider-id
# берутся из окружения (вне VCS). Неизвестная строка считается готовым id
# (legacy-значения из БД проходят как есть).
_MODEL_TIER_ENV = {
    "ai-balanced": "AI_MODEL_BALANCED",
    "ai-deep": "AI_MODEL_DEEP",
    "ai-fast": "AI_MODEL_FAST",
}


def _resolve_model(m: Optional[str]) -> str:
    # m=None → дефолтный тир; алиас (в т.ч. DEFAULT_MODEL) обязательно мапим в
    # реальный provider-id из окружения, иначе уходит литерал «ai-balanced» → 404.
    name = m or DEFAULT_MODEL
    key = _MODEL_TIER_ENV.get(name)
    if key:
        return os.environ.get(key) or os.environ.get("AI_MODEL_BALANCED") or name
    return name


DEFAULT_MODEL = os.environ.get("AI_MODEL_DEFAULT", "ai-balanced")
DEFAULT_MAX_TURNS = 12  # safety cap for tool_use loop — bumped 6→12 for chained verify_count flows

# P1 аудита ИИ (июль 2026): результат инструмента уходил модели БЕЗ усечения
# (лимит 50 КБ применялся только к копии для UI) и оставался в контексте на все
# последующие турны → лавинообразный рост стоимости. Кап на блок, уходящий в
# диалог; пользователю в UI по-прежнему отдаётся более полная копия.
_TOOL_RESULT_CAP = 24_000

# Ниже какого размера кэшировать префикс бессмысленно (провайдер требует
# минимальную длину блока; для коротких промптов только накладные расходы).
_CACHE_MIN_CHARS = 4_000


def _cacheable_system(system: str):
    """Системный промпт как кэшируемый блок (prompt caching).

    Возвращает исходную строку, если промпт короткий — тогда кэш не нужен.
    """
    if not system or len(system) < _CACHE_MIN_CHARS:
        return system
    return [{
        "type": "text",
        "text": system,
        "cache_control": {"type": "ephemeral"},
    }]


def _cacheable_tools(tools: Optional[list]) -> Optional[list]:
    """Пометить последнюю схему инструмента как границу кэша.

    Схемы инструментов идут в префиксе запроса сразу за system и в рамках одного
    диалога неизменны — кэшируем их вместе с системным промптом.
    """
    if not tools:
        return tools
    out = [dict(t) for t in tools]
    out[-1]["cache_control"] = {"type": "ephemeral"}
    return out


def get_api_key() -> str:
    # Дженерик-имя приоритетно; старое имя оставлено как fallback (на проде .env
    # пока задаёт его) — даёт миграцию без простоя ИИ.
    return (os.environ.get("AI_API_KEY")
            or os.environ.get("LLM_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY", ""))


def is_enabled() -> bool:
    # Требуем и ключ, и endpoint, и имя версии-заголовка (всё из .env) — иначе ИИ
    # просто выключен, без обращений к незаданному провайдеру.
    return bool(get_api_key()) and bool(_API_URL) and bool(_VERSION_HEADER)


async def complete_once(
    *,
    system: str,
    prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 1800,
    temperature: Optional[float] = 0.3,
    tools: Optional[list] = None,
    timeout: float = 120.0,
) -> str:
    """Однократный (нестриминговый) вызов AI engine → собранный текст ответа.

    Используется для генерации детерминированных артефактов (executive-бриф).
    """
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("LLM API key not configured")
    system = f"{system}\n\n{ai_language_instruction()}"
    payload = {
        "model": _resolve_model(model),
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    # `temperature` депрекейтнут у новых моделей (напр. Opus 4.8) → 400, если слать.
    # Не включаем при None; ниже есть авто-лечение на случай явного значения.
    if temperature is not None:
        payload["temperature"] = temperature
    if tools:
        payload["tools"] = tools
    headers = {
        "x-api-key": api_key,
        _VERSION_HEADER: _API_VERSION,
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(_API_URL, json=payload, headers=headers)
        # Авто-лечение депрекейта `temperature` у новых моделей: убрать и повторить.
        if resp.status_code == 400 and "temperature" in payload and "temperature" in resp.text:
            payload.pop("temperature", None)
            resp = await client.post(_API_URL, json=payload, headers=headers)
        if resp.status_code >= 400:
            # Тело ответа LLM несёт реальную причину — раньше оно терялось
            # в raise_for_status() и любой 400 был «слепым».
            logger.warning("LLM %s: %s", resp.status_code, resp.text[:500])
        resp.raise_for_status()
        data = resp.json()
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()


def extract_text_and_stats(events: list[dict]) -> tuple[str, int | None, int | None, str | None]:
    """Walk parsed SSE events, return (full_text, tokens_in, tokens_out, stop_reason).

    P1 аудита: счётчики ПЕРЕЗАПИСЫВАЛИСЬ на каждом `message_start`, а список
    событий — общий на весь мультитурновый цикл (до 12 турнов). В БД уходил
    расход ПОСЛЕДНЕГО турна вместо суммы, и понять источник счёта провайдера по
    журналу было невозможно. Теперь усилия суммируются по турнам; output
    последнего турна корректируется из `message_delta` (там финальное значение).
    """
    text_parts: list[str] = []
    tin_total = 0
    tout_total = 0
    seen_usage = False
    cur_turn_out = 0          # output последнего начатого турна
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
            # закрываем предыдущий турн
            tout_total += cur_turn_out
            cur_turn_out = 0
            if "input_tokens" in usage:
                tin_total += usage["input_tokens"] or 0
                seen_usage = True
            if "output_tokens" in usage:
                cur_turn_out = usage["output_tokens"] or 0
                seen_usage = True
        elif et == "message_delta":
            d = ev.get("delta") or {}
            if d.get("stop_reason"):
                stop = d["stop_reason"]
            usage = ev.get("usage") or {}
            if "output_tokens" in usage:
                cur_turn_out = usage["output_tokens"] or 0
                seen_usage = True
    tout_total += cur_turn_out
    tin = tin_total if seen_usage else None
    tout = tout_total if seen_usage else None
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
    temperature: Optional[float] = 0.25,
    max_turns: int = DEFAULT_MAX_TURNS,
) -> AsyncGenerator[bytes, None]:
    """
    Multi-turn streaming chat with tool execution.

    Flow:
      1. Send messages + tools to LLM
      2. Stream response. If we see content_blocks of type 'tool_use' with
         stop_reason == 'tool_use', collect them.
      3. For each tool_use, run dispatcher(name, args, db) and append a
         'tool_result' user message.
      4. Loop with augmented messages until model returns stop_reason='end_turn'.

    Yields:
      - All raw LLM SSE chunks (so frontend sees text deltas in real-time)
      - Plus custom events:
          event: tool_use_start
          data: {name, args, id}
          event: tool_use_end
          data: {id, ok, result_summary}
    """
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError("LLM API key not configured")

    system = f"{system}\n\n{ai_language_instruction()}"
    headers = {
        "x-api-key": api_key,
        _VERSION_HEADER: _API_VERSION,
        "content-type": "application/json",
    }

    # Working copy of messages (we'll append assistant + tool_result rounds)
    convo: list[dict[str, Any]] = [dict(m) for m in messages]

    # `temperature` депрекейтнут у новых моделей (Opus 4.8) → 400. Держим значение
    # в локале: авто-лечение (ниже) убирает его и повторяет ТОТ ЖЕ турн, а снятие
    # сохраняется на все последующие турны. Зеркалит complete_once (там же 400-heal).
    send_temperature = temperature
    turn = 0
    while turn < max_turns:
        payload = {
            "model": _resolve_model(model),
            "max_tokens": max_tokens,
            # P2 аудита: prompt caching. Системный промпт + схемы инструментов —
            # ~90 КБ КОНСТАНТНОГО префикса, который оплачивался заново в каждом
            # из до 12 турнов одного вопроса. cache_control на последнем блоке
            # префикса кэширует его целиком (system + tools) между турнами.
            "system": _cacheable_system(system),
            "messages": convo,
            "tools": _cacheable_tools(tools),
            "stream": True,
        }
        if send_temperature is not None:
            payload["temperature"] = send_temperature

        # Accumulate response: text parts, tool_use blocks
        assistant_blocks: list[dict] = []  # for sending back as assistant turn
        current_block: Optional[dict] = None  # in-progress block being streamed
        current_block_input_str = ""
        stop_reason: Optional[str] = None

        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("POST", _API_URL, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    err_text = await resp.aread()
                    # Авто-лечение депрекейта `temperature` у новых моделей (Opus 4.8):
                    # убрать параметр и повторить ТОТ ЖЕ турн один раз, без event: error.
                    # (send_temperature=None → повторный 400 сюда уже не попадёт.)
                    if (resp.status_code == 400 and send_temperature is not None
                            and b"temperature" in err_text):
                        send_temperature = None
                        continue
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

            # Append to tool_result blocks for next turn.
            # P1 аудита: усечение (50 КБ) применялось ТОЛЬКО к копии для UI, а в
            # диалог с моделью уходил полный дамп — и оставался там навсегда,
            # пересылаясь на каждом следующем турне (до 12). Контекст рос
            # лавинообразно. Теперь режем и то, что уходит модели, с ЧЕСТНОЙ
            # пометкой — чтобы она понимала неполноту и уточнила фильтр,
            # а не выдумывала полноту.
            try:
                content_for_model = json.dumps(result, ensure_ascii=False, default=str)
            except Exception:
                content_for_model = '{"error":"failed to serialize result"}'
            if len(content_for_model) > _TOOL_RESULT_CAP:
                content_for_model = (
                    content_for_model[:_TOOL_RESULT_CAP]
                    + '..."[ДАННЫЕ УСЕЧЕНЫ: показана только часть результата. '
                      'Уточни фильтр (компания/год/лимит) и вызови инструмент '
                      'повторно; не додумывай пропущенное]"'
                )
            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": content_for_model,
            })

        convo.append({"role": "user", "content": tool_result_blocks})
        turn += 1

    # Loop exhausted
    err = {
        "type": "error",
        "error": {"message": f"Max tool turns ({max_turns}) exhausted"},
    }
    yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n".encode("utf-8")
