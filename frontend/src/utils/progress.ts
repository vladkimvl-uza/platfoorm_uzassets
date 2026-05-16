/**
 * `_taskWeight` and `computeProgress` from index.html ~line 7044/7064.
 *
 * Used everywhere a project/task percentage is shown:
 *   - Project list (avg progress across direct tasks)
 *   - Dashboard KPIs (project-level vs task-level totals)
 *   - Kanban board headers
 *   - Task editor's quarterly badge
 *
 * Keeping this single source of truth means Vue's UI cannot drift from the
 */

export type TaskStatus =
  | "init" | "new" | "active" | "review" | "done"
  | "quarterly" | "monthly" | "ongoing";

export interface QuartersObject {
  q1?: { weight?: number; plan?: number; fact?: number | null } | boolean;
  q2?: { weight?: number; plan?: number; fact?: number | null } | boolean;
  q3?: { weight?: number; plan?: number; fact?: number | null } | boolean;
  q4?: { weight?: number; plan?: number; fact?: number | null } | boolean;
}

export interface TaskWithStatus {
  status?: string | null;
  quarters?: QuartersObject | null;
}

/** Status codes that are EXCLUDED from progress percentage entirely
 *  (no end point — recurring/perpetual work). */
export const EXCLUDED_FROM_PCT = new Set(["monthly", "ongoing"]);

/**
 * Returns task weight 0..1 for progress calculation. `null` means "exclude".
 *
 *   - new/init/active/review → 0
 *   - done → 1
 *   - quarterly → 1 if all 4 quarters closed, else 0
 *   - monthly/ongoing → null (excluded)
 */
export function taskWeight(t: TaskWithStatus | null | undefined): number | null {
  if (!t || !t.status) return 0;
  const s = t.status;

  if (s === "monthly" || s === "ongoing") return null;

  if (s === "quarterly") {
    const q = t.quarters || {};
    return (q.q1 && q.q2 && q.q3 && q.q4) ? 1 : 0;
  }

  return s === "done" ? 1 : 0;
}

/** How many of 4 quarters are closed for a quarterly-status task. */
export function quarterlyDoneCount(t: TaskWithStatus | null | undefined): number {
  if (!t || t.status !== "quarterly") return 0;
  const q = t.quarters || {};
  let n = 0;
  if (q.q1) n++;
  if (q.q2) n++;
  if (q.q3) n++;
  if (q.q4) n++;
  return n;
}

/** True iff task is quarterly AND all 4 quarters closed (= auto-done). */
export function isQuarterlyAllDone(t: TaskWithStatus | null | undefined): boolean {
  if (!t || t.status !== "quarterly") return false;
  const q = t.quarters || {};
  return !!(q.q1 && q.q2 && q.q3 && q.q4);
}

/** Quarterly badge label — "✓ Все кварталы закрыты" or "Ежеквартально · N/4". */
export function quarterlyBadgeText(t: TaskWithStatus | null | undefined): string {
  const n = quarterlyDoneCount(t);
  if (n === 4) return "✓ Все кварталы закрыты";
  return `Ежеквартально · ${n}/4`;
}

export interface ProgressResult {
  done: number;       // count of fully-closed tasks (weight === 1)
  total: number;      // count of weighted tasks (excluding monthly/ongoing)
  pct: number;        // 0..100 rounded; sum(weights)/total * 100
  excluded: number;   // count of monthly/ongoing tasks dropped from calc
}

/**
 * Computes progress over a set of tasks.
 *
 * not just done/total. quarterly with 1-3 closed quarters contributes 0
 * (not partial) — only ALL FOUR closed count as 1.
 */
export function computeProgress(tasks: TaskWithStatus[] | null | undefined): ProgressResult {
  if (!Array.isArray(tasks)) return { done: 0, total: 0, pct: 0, excluded: 0 };

  let excluded = 0;
  let done = 0;
  let total = 0;
  let sum = 0;

  for (const t of tasks) {
    if (!t) continue;
    const w = taskWeight(t);
    if (w === null) {
      excluded++;
      continue;
    }
    total++;
    if (w === 1) done++;
    sum += w;
  }

  return {
    done, total, excluded,
    pct: total ? Math.round((sum / total) * 100) : 0,
  };
}

export function progressColor(pct: number): string {
  if (pct >= 70) return "#1D9E75";
  if (pct >= 35) return "#D97706";
  return "#E24B4A";
}

export const STATUS_ORDER: TaskStatus[] = [
  "new", "init", "active", "review", "done",
  "quarterly", "monthly", "ongoing",
];

export const STATUS_LABELS: Record<string, string> = {
  new:       "Не начато",
  init:      "Инициирование",
  active:    "В процессе",
  review:    "На согласовании",
  done:      "Завершено",
  quarterly: "Ежеквартально",
  monthly:   "Ежемесячно",
  ongoing:   "Постоянно",
};

export const STATUS_COLORS: Record<string, string> = {
  new:       "#CBD5E1",   // light slate
  init:      "#7F77DD",   // platform purple
  active:    "#378ADD",   // azure blue
  review:    "#EF9F27",   // amber
  done:      "#1D9E75",   // teal
  quarterly: "#A855F7",   // purple
  monthly:   "#6366F1",   // indigo
  ongoing:   "#06B6D4",   // cyan
};

/** Status background tints (for chip backgrounds — semi-transparent). */
export const STATUS_BG: Record<string, string> = {
  new:       "#F1F5F9",
  init:      "rgba(127,119,221,.13)",
  active:    "rgba(55,138,221,.13)",
  review:    "rgba(239,159,39,.13)",
  done:      "rgba(29,158,117,.13)",
  quarterly: "rgba(168,85,247,.13)",
  monthly:   "rgba(99,102,241,.13)",
  ongoing:   "rgba(6,182,212,.13)",
};
