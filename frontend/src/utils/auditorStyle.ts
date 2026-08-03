/**
 * Стиль аудитора/консультанта — ОДИН источник правды.
 *
 * Раньше цвет «Big 4» жил в трёх местах и в трёх разных палитрах:
 * CompanyWorkspace (`_AUDITOR_COLORS`: KPMG #378ADD), ForensicAudit
 * (`AUDITOR_COLORS`: KPMG #0033A0) и BadgeConsultant (#0091DA) — одна и та же
 * компания на трёх экранах была трёх разных цветов, а бейдж «Big 4» в форензике
 * рисовался вообще любому аудитору, включая не входящих в четвёрку.
 *
 * Теперь и цвет, и признак Big 4 берутся из справочника консультантов (тот же
 * список, что рисует `/consultants`), а имя аудитора сопоставляется со
 * справочником по названию/коду/аббревиатуре. Нет совпадения — нейтральный
 * серый и без бейджа: выдумывать принадлежность к четвёрке нельзя.
 */
import { consultantsApi, type ConsultantBrief } from "@/api/consultants";

export interface AuditorStyle {
  /** Отображаемое имя (без легаси-хвостов вида «до 31.12.2026»). */
  name: string;
  /** Короткая метка для аватара-бейджа. */
  abbr: string;
  /** Фирменный цвет из справочника; нейтральный серый, если не опознан. */
  color: string;
  /** Входит ли в «большую четвёрку» — по данным справочника, а не по имени. */
  isBig4: boolean;
  /** Нашли ли запись в справочнике. */
  matched: boolean;
}

const NEUTRAL = "#64748B";

let _cache: ConsultantBrief[] | null = null;
let _inflight: Promise<ConsultantBrief[]> | null = null;

/** Справочник консультантов с кэшем на вкладку. */
export async function ensureConsultants(): Promise<ConsultantBrief[]> {
  if (_cache) return _cache;
  if (!_inflight) {
    _inflight = consultantsApi.list()
      .then((rows) => { _cache = rows; return rows; })
      .catch(() => [])          // список не критичен: упадём в нейтральный стиль
      .finally(() => { _inflight = null; });
  }
  return _inflight;
}

/** Убрать легаси-хвост срока, который попадал в поле имени аудитора. */
export function cleanAuditorName(raw: string | null | undefined): string {
  return (raw || "").replace(/\s*до\s+\d{2}\.\d{2}\.\d{4}/, "").trim();
}

function norm(s: string): string {
  return s.toLowerCase().replace(/[^a-zа-яё0-9]/gi, "");
}

/** Сопоставить строку с записью справочника: по коду, аббревиатуре или имени. */
export function matchConsultant(
  raw: string | null | undefined,
  list: ConsultantBrief[],
): ConsultantBrief | null {
  const cleaned = cleanAuditorName(raw);
  if (!cleaned) return null;
  const key = norm(cleaned);
  if (!key) return null;

  const rows = list.map((c) => ({
    c,
    keys: [c.code, c.abbr, c.name_ru, c.name_en]
      .filter(Boolean).map((x) => norm(x as string)).filter(Boolean),
  }));

  // 1) точное совпадение
  for (const r of rows) if (r.keys.includes(key)) return r.c;

  // 2) имя из форензика начинается с названия консультанта: «KPMG Uzbekistan»,
  //    «PwC (аудит 2025)». Обратное вхождение НЕ используем: короткий ключ «ey»
  //    оказался бы внутри «mckinsey» и EY получил бы чужой цвет.
  let best: { c: ConsultantBrief; len: number } | null = null;
  for (const r of rows) {
    for (const n of r.keys) {
      if (n.length >= 2 && key.startsWith(n) && (!best || n.length > best.len)) {
        best = { c: r.c, len: n.length };
      }
    }
  }
  return best?.c ?? null;
}

/** Готовый стиль для отрисовки аудитора. */
export function auditorStyle(
  raw: string | null | undefined,
  list: ConsultantBrief[],
): AuditorStyle {
  const name = cleanAuditorName(raw);
  const hit = matchConsultant(raw, list);
  return {
    name: name || "—",
    abbr: (hit?.abbr || hit?.code || name || "—").slice(0, 8),
    color: hit?.color_hex || NEUTRAL,
    isBig4: !!hit?.is_big4,
    matched: !!hit,
  };
}

/** Инлайновый стиль бейджа «Big 4» — тот же рецепт, что на /consultants. */
export function big4ChipStyle(color: string): Record<string, string> {
  return { background: color + "15", color, borderColor: color + "25" };
}
