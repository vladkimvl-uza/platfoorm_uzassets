// ============================================================================
// Forecasting engine for financial series — pure, testable functions.
//
// Все модели работают на годовом ряду факта (HistPoint[]) и дают прогноз на
// целевые годы (targetYears). Пользователь выбирает модель и заполняет её
// входные параметры (ForecastParams). Прогноз ВСЕГДА помечается как прогнозный
// на UI — это не факт.
// ============================================================================

export type ForecastModel = "runrate" | "cagr" | "linear" | "manual" | "flat";

export interface ForecastModelMeta {
  id: ForecastModel;
  label: string;
  desc: string;
  /** какие поля ввода нужны пользователю для этой модели */
  inputs: Array<"cagrRange" | "growthPct" | "linearWindow">;
}

export const FORECAST_MODELS: ForecastModelMeta[] = [
  {
    id: "runrate", label: "Run-rate",
    desc: "Проекция по последнему годовому темпу роста (YoY последнего факта). Доп. данные не нужны.",
    inputs: [],
  },
  {
    id: "cagr", label: "CAGR",
    desc: "Среднегодовой темп роста за выбранный базовый период. Укажите базовые годы.",
    inputs: ["cagrRange"],
  },
  {
    id: "linear", label: "Линейный тренд",
    desc: "Экстраполяция по методу наименьших квадратов. Укажите глубину истории.",
    inputs: ["linearWindow"],
  },
  {
    id: "manual", label: "Ручные допущения",
    desc: "Вы задаёте процент роста выручки на каждый прогнозный год.",
    inputs: ["growthPct"],
  },
  {
    id: "flat", label: "Без изменений",
    desc: "Удержание последнего факта без роста. Доп. данные не нужны.",
    inputs: [],
  },
];

export interface HistPoint { year: number; value: number | null; }
export interface ForecastPoint { year: number; value: number; }

export interface ForecastParams {
  cagrFrom?: number;
  cagrTo?: number;
  growthPct?: number[];   // manual: % роста на каждый targetYear (по индексу)
  linearWindow?: number;  // сколько последних лет факта брать в тренд
}

function actuals(history: HistPoint[]): Array<{ year: number; value: number }> {
  // 0 в модуле = «нет данных» → исключаем из базы прогноза
  return history
    .filter((h) => h.value != null && h.value !== 0)
    .map((h) => ({ year: h.year, value: h.value as number }))
    .sort((a, b) => a.year - b.year);
}

/** Главная функция: прогноз ряда по выбранной модели. */
export function runForecast(
  model: ForecastModel,
  history: HistPoint[],
  targetYears: number[],
  params: ForecastParams = {},
): ForecastPoint[] {
  const acts = actuals(history);
  if (!acts.length) return [];
  const last = acts[acts.length - 1];
  const out: ForecastPoint[] = [];

  switch (model) {
    case "flat": {
      for (const y of targetYears) out.push({ year: y, value: last.value });
      break;
    }
    case "manual": {
      let prev = last.value;
      targetYears.forEach((y, i) => {
        const g = (params.growthPct?.[i] ?? 0) / 100;
        prev = prev * (1 + g);
        out.push({ year: y, value: prev });
      });
      break;
    }
    case "runrate": {
      let g = 0;
      if (acts.length >= 2) {
        const a = acts[acts.length - 2].value;
        if (a !== 0) g = last.value / a - 1;
      }
      let prev = last.value;
      for (const y of targetYears) { prev = prev * (1 + g); out.push({ year: y, value: prev }); }
      break;
    }
    case "cagr": {
      const from = acts.find((a) => a.year === params.cagrFrom) ?? acts[0];
      const to = acts.find((a) => a.year === params.cagrTo) ?? last;
      let g = 0;
      const n = to.year - from.year;
      if (n > 0 && from.value > 0) g = Math.pow(to.value / from.value, 1 / n) - 1;
      let prev = last.value;
      for (const y of targetYears) { prev = prev * (1 + g); out.push({ year: y, value: prev }); }
      break;
    }
    case "linear": {
      const win = params.linearWindow && params.linearWindow > 1 ? params.linearWindow : acts.length;
      const pts = acts.slice(-win);
      const n = pts.length;
      const sx = pts.reduce((s, p) => s + p.year, 0);
      const sy = pts.reduce((s, p) => s + p.value, 0);
      const sxx = pts.reduce((s, p) => s + p.year * p.year, 0);
      const sxy = pts.reduce((s, p) => s + p.year * p.value, 0);
      const denom = n * sxx - sx * sx;
      const b = denom !== 0 ? (n * sxy - sx * sy) / denom : 0;
      const a = (sy - b * sx) / n;
      for (const y of targetYears) out.push({ year: y, value: Math.max(0, a + b * y) });
      break;
    }
  }
  return out;
}

/** Реализованный темп роста последнего факта (для подсказки в UI). */
export function lastYoY(history: HistPoint[]): number | null {
  const acts = actuals(history);
  if (acts.length < 2) return null;
  const a = acts[acts.length - 2].value;
  const b = acts[acts.length - 1].value;
  return a !== 0 ? (b / a - 1) * 100 : null;
}
