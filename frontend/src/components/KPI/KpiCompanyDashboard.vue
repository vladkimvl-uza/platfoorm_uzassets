<script setup lang="ts">
/**
 *
 * Структура:
 *  1. Status bar (4 cells: Общий прогресс / На цели ≥95% / Критичных / Всего KPI)
 *  2. Manager cards (horizontal scroll) с beads, top stripe, shimmer, bar fill
 *  3. Split row: Attention + Achievements
 *  4. Comment block (editable, → bpKpi API → PostgreSQL)
 *  5. Details ОФР (indicators table для active manager) с status icons
 *
 * Все save (комментарий) через kpiApi → backend → PostgreSQL.
 * Attention + comment загружаются здесь же при mount/period change.
 */
import { computed, onMounted, ref, watch } from "vue";
import {
  kpiApi,
  kpiStatusColor,
  num,
  type KpiAttentionIssue,
  type KpiComment,
  type KpiIndicator,
  type KpiManager,
  type KpiStatus,
} from "@/api/bpKpi";
import { useFormatters } from "@/composables/useFormatters";
import { useToast } from "@/composables/useToast";

const fmt = useFormatters();

const props = defineProps<{
  managers: KpiManager[];
  activeManagerIdx: number;
  period: "annual" | "q1" | "q2" | "q3" | "q4";
  companyId: string;
  companyName: string;
  year: number;
  canEdit: boolean;
}>();

const emit = defineEmits<{
  (e: "set-manager", idx: number): void;
  (e: "open-indicator", id: string): void;
}>();

// ──────────────────────────────────────────────────────────────────
//   Period helpers
// ──────────────────────────────────────────────────────────────────

function periodKey(): "year" | "q1" | "q2" | "q3" | "q4" {
  return props.period === "annual" ? "year" : props.period;
}

function planValue(ind: KpiIndicator, p: string): number | null {
  const k = p === "annual" ? "year" : p;
  if (k === "year") return ind.plan_year != null ? num(ind.plan_year) : null;
  const v = (ind as unknown as Record<string, unknown>)[`${k}_plan`];
  return v != null ? num(v as string | number) : null;
}

function factValue(ind: KpiIndicator, p: string): number | null {
  const k = p === "annual" ? "year" : p;
  if (k === "year") return ind.fact_year != null ? num(ind.fact_year) : null;
  const v = (ind as unknown as Record<string, unknown>)[`${k}_fact`];
  return v != null ? num(v as string | number) : null;
}

function weightValue(ind: KpiIndicator, p: string): number {
  const k = p === "annual" ? "year" : p;
  if (k === "year") return num(ind.weight);
  const v = (ind as unknown as Record<string, unknown>)[`${k}_weight`];
  return v != null ? num(v as string | number) : 0;
}

function indCompletion(ind: KpiIndicator, p: string): number | null {
  const plan = planValue(ind, p);
  const fact = factValue(ind, p);
  if (plan == null || plan === 0 || fact == null) return null;
  return fact / plan;
}

function indStatus(ind: KpiIndicator, p: string): KpiStatus | null {
  const r = indCompletion(ind, p);
  if (r == null) return null;
  if (r >= 1.0) return "over";
  if (r >= 0.95) return "hit";
  if (r >= 0.75) return "risk";
  if (r >= 0.5) return "crit";
  return "fail";
}

function mgrOverallPct(m: KpiManager, p: string): number | null {
  let sumW = 0, sumWtd = 0;
  for (const ind of m.indicators) {
    const w = weightValue(ind, p);
    if (w === 0) continue;
    const r = indCompletion(ind, p);
    if (r == null) continue;
    sumW += w;
    sumWtd += Math.min(r, 1.5) * w;
  }
  return sumW > 0 ? sumWtd / sumW : null;
}

// ──────────────────────────────────────────────────────────────────
//   Status bar (4 cells)
// ──────────────────────────────────────────────────────────────────

interface StatCell {
  id: string;
  severity: "ok" | "warn" | "bad" | "neutral";
  label: string;
  value: string;
  sub: string;
  accent: string;
  delay: number;
}

const statBand = computed<StatCell[]>(() => {
  const period = props.period;
  let sumP = 0, cntP = 0, okMgrs = 0, critKpis = 0, totalKpis = 0;
  for (const mgr of props.managers) {
    const p = mgrOverallPct(mgr, period);
    if (p != null) { sumP += p; cntP++; if (p >= 0.95) okMgrs++; }
    for (const ind of mgr.indicators) {
      totalKpis++;
      const r = indCompletion(ind, period);
      if (r != null && r < 0.70) critKpis++;
    }
  }

  const avg = cntP > 0 ? sumP / cntP : null;
  const overallSev = avg == null ? "neutral" : avg >= 0.95 ? "ok" : avg >= 0.80 ? "warn" : "bad";
  const overallVal = avg == null ? "—" : Math.round(avg * 100) + "%";
  const overallSub = avg == null ? "нет данных" : `среднее · ${cntP} руководит.`;

  const ontrackSev = cntP === 0 ? "neutral" : okMgrs / cntP >= 0.7 ? "ok" : okMgrs / cntP >= 0.4 ? "warn" : "bad";
  const ontrackVal = cntP === 0 ? "—" : `${okMgrs} из ${cntP}`;
  const ontrackSub = cntP === 0 ? "нет данных" : "руководителей";

  const critSev = critKpis === 0 ? "ok" : critKpis <= 2 ? "warn" : "bad";

  const totalSev = totalKpis === 0 ? "neutral" : "ok";

  return [
    { id: "overall", severity: overallSev as StatCell["severity"], label: "Общий прогресс", value: overallVal, sub: overallSub, accent: "#7F77DD", delay: 40 },
    { id: "ontrack", severity: ontrackSev as StatCell["severity"], label: "На цели (≥95%)", value: ontrackVal, sub: ontrackSub, accent: "#1D9E75", delay: 90 },
    { id: "crit",    severity: critSev as StatCell["severity"],    label: "Критичных KPI", value: String(critKpis), sub: critKpis === 0 ? "всё в норме" : "<70% плана", accent: "#E24B4A", delay: 140 },
    { id: "total",   severity: totalSev as StatCell["severity"],   label: "Всего KPI", value: String(totalKpis), sub: "отслеживается", accent: "#378ADD", delay: 190 },
  ];
});

// ──────────────────────────────────────────────────────────────────
//   Manager cards (beads, %, total, bar fill, footer)
// ──────────────────────────────────────────────────────────────────

interface ManagerCard {
  idx: number;
  short_title: string;
  role: string;
  accent: string;
  beads: ("ok" | "warn" | "bad" | "none")[];
  pct: number | null;
  pctColor: string;
  barColor: string;
  totalCount: number;
  okCount: number;
  warnCount: number;
  badCount: number;
  footL: string;
  active: boolean;
  delay: number;
}

const COLOR_MAP = ["#7F77DD", "#1D9E75", "#378ADD", "#EF9F27"];

const managerCards = computed<ManagerCard[]>(() => {
  return props.managers.map((mgr, idx) => {
    const accent = COLOR_MAP[idx % COLOR_MAP.length];
    const p = mgrOverallPct(mgr, props.period);
    const pct = p != null ? Math.round(p * 100) : null;
    const barColor = p == null ? "#94A3B8" : (p >= 0.95 ? "#1D9E75" : p >= 0.80 ? "#EF9F27" : "#E24B4A");
    const pctColor = p == null ? "#888780" : (p >= 0.95 ? "#0F6E56" : p >= 0.80 ? "#8A5F15" : "#933632");

    const beads: ManagerCard["beads"] = [];
    let okCount = 0, warnCount = 0, badCount = 0;
    for (const ind of mgr.indicators) {
      const r = indCompletion(ind, props.period);
      if (r == null) { beads.push("none"); continue; }
      if (r >= 0.95) { beads.push("ok"); okCount++; }
      else if (r >= 0.80) { beads.push("warn"); warnCount++; }
      else { beads.push("bad"); badCount++; }
    }

    const totalCount = mgr.indicators.length;
    let footL: string;
    if (totalCount === 0) footL = "— · нет KPI";
    else if (badCount > 0) footL = `<span class="ok">${okCount} на цели</span> · <span class="bad">${badCount} крит.</span>`;
    else if (warnCount > 0) footL = `<span class="ok">${okCount} на цели</span> · <span class="warn">${warnCount} внимание</span>`;
    else footL = `<span class="ok">${okCount} на цели</span>`;

    return {
      idx,
      short_title: mgr.short_title || `Руководитель ${idx + 1}`,
      role: mgr.role || "",
      accent,
      beads,
      pct,
      pctColor,
      barColor,
      totalCount,
      okCount,
      warnCount,
      badCount,
      footL,
      active: idx === props.activeManagerIdx,
      delay: 120 + idx * 60,
    };
  });
});

function beadColor(s: ManagerCard["beads"][number]): string {
  if (s === "ok") return "#1D9E75";
  if (s === "warn") return "#EF9F27";
  if (s === "bad") return "#E24B4A";
  return "#E2E8F0";
}

// ──────────────────────────────────────────────────────────────────
//   Attention + Achievements
// ──────────────────────────────────────────────────────────────────

const attention = ref<KpiAttentionIssue[]>([]);

async function loadAttention() {
  try {
    const p = periodKey();
    attention.value = await kpiApi.getAttention(props.companyId, props.year, p);
  } catch {
    attention.value = [];
  }
}

interface Achievement {
  title: string;
  meta: string;
  ratio: number;
}

const achievements = computed<Achievement[]>(() => {
  const res: Achievement[] = [];
  for (const mgr of props.managers) {
    for (const ind of mgr.indicators) {
      const r = indCompletion(ind, props.period);
      if (r == null || r < 1.05) continue;
      const fact = factValue(ind, props.period);
      const plan = planValue(ind, props.period);
      res.push({
        title: ind.name,
        meta: `${mgr.short_title || mgr.title} · факт ${fmtNum(fact)} · план ${fmtNum(plan)}`,
        ratio: r,
      });
    }
  }
  return res.sort((a, b) => b.ratio - a.ratio).slice(0, 5);
});

const attentionDotColor = computed(() => {
  if (!attention.value.length) return "#1D9E75";
  return attention.value[0].severity === "high" ? "#A32D2D" : "#BA7517";
});

// ──────────────────────────────────────────────────────────────────
//   Comment
// ──────────────────────────────────────────────────────────────────

const comment = ref<KpiComment | null>(null);
const editingComment = ref(false);
const commentDraft = ref("");
const savingComment = ref(false);

async function loadComment() {
  try {
    comment.value = await kpiApi.getComment(props.companyId, props.year, periodKey());
    commentDraft.value = comment.value?.body ?? "";
  } catch {
    comment.value = null;
    commentDraft.value = "";
  }
}

async function saveComment() {
  if (savingComment.value) return;
  savingComment.value = true;
  try {
    const saved = await kpiApi.upsertComment(
      props.companyId,
      props.year,
      periodKey(),
      commentDraft.value.trim(),
    );
    comment.value = saved;
    editingComment.value = false;
  } catch (e) {
    console.error("[KPI] comment save failed:", e);
    useToast().error("Не удалось сохранить комментарий");
  } finally {
    savingComment.value = false;
  }
}

function cancelEdit() {
  editingComment.value = false;
  commentDraft.value = comment.value?.body ?? "";
}

// ──────────────────────────────────────────────────────────────────
//   Details (active manager indicators)
// ──────────────────────────────────────────────────────────────────

const activeManager = computed<KpiManager | null>(() =>
  props.managers[props.activeManagerIdx] || null,
);

interface DetailsRow {
  ind: KpiIndicator;
  pct: number | null;
  pctClass: "" | "ok" | "warn" | "bad";
  icnClass: "ok" | "warn" | "bad" | "";
  icnKind: "check" | "dot" | "cross" | "dash";
  plan: number | null;
  fact: number | null;
  unit: string;
  weight: number;
  trClass: "" | "alert-high" | "alert-med";
}

const detailsRows = computed<DetailsRow[]>(() => {
  if (!activeManager.value) return [];
  return activeManager.value.indicators.map(ind => {
    const r = indCompletion(ind, props.period);
    const pct = r != null ? r * 100 : null;
    const pctClass: DetailsRow["pctClass"] = r == null ? "" : r >= 0.95 ? "ok" : r >= 0.80 ? "warn" : "bad";
    const icnKind: DetailsRow["icnKind"] = r == null ? "dash" : r >= 0.95 ? "check" : r >= 0.80 ? "dot" : "cross";
    const icnClass: DetailsRow["icnClass"] = r == null ? "" : r >= 0.95 ? "ok" : r >= 0.80 ? "warn" : "bad";
    const trClass: DetailsRow["trClass"] = r == null ? "" : r < 0.70 ? "alert-high" : r < 0.90 ? "alert-med" : "";
    return {
      ind,
      pct,
      pctClass,
      icnClass,
      icnKind,
      plan: planValue(ind, props.period),
      fact: factValue(ind, props.period),
      unit: ind.unit || "",
      weight: weightValue(ind, props.period),
      trClass,
    };
  });
});

const detailsMeta = computed(() => {
  const m = activeManager.value;
  if (!m) return null;
  const p = mgrOverallPct(m, props.period);
  return {
    title: m.short_title || m.title,
    sub: `${m.indicators.length} KPI · взвешенно ${p != null ? Math.round(p * 100) + "%" : "—"} · ${props.period === "annual" ? "итог года" : "квартал " + props.period.toUpperCase()}`,
  };
});

// ──────────────────────────────────────────────────────────────────
//   Lifecycle
// ──────────────────────────────────────────────────────────────────

onMounted(() => {
  loadAttention();
  loadComment();
});

watch(
  () => [props.companyId, props.year, props.period],
  () => {
    loadAttention();
    loadComment();
  },
);

// ──────────────────────────────────────────────────────────────────
//   Helpers
// ──────────────────────────────────────────────────────────────────

function fmtNum(v: number | null): string {
  if (v == null) return "—";
  if (Math.abs(v) >= 1000) return fmt.fmtNumber(Math.round(v));
  if (Math.abs(v) >= 10) return fmt.fmtNumber(v, { decimals: 1 });
  return fmt.fmtNumber(v, { decimals: 2 });
}
</script>

<template>
  <div class="kpv-scroll">
    <div class="kpv-body">

      <!-- ═══ 1. Status bar (4 cells) ═══ -->
      <div class="kpv-stat-bar">
        <div
          v-for="s in statBand"
          :key="s.id"
          class="kpi2 fin-shimmer kpv-stat-cell"
          :class="s.severity"
          :style="{ '--kpi2-accent': s.accent, '--kpi2-d': s.delay + 'ms', '--d': s.delay + 'ms' }"
        >
          <div class="kpi2-lbl kpv-stat-lbl">{{ s.label }}</div>
          <div class="kpi2-val kpv-stat-val">{{ s.value }}</div>
          <div class="kpi2-sub kpv-stat-sub">{{ s.sub }}</div>
        </div>
      </div>

      <!-- ═══ 2. Manager cards (horizontal scroll) ═══ -->
      <div v-if="!managers.length" class="kpv-empty">
        <div class="kpv-empty-ttl">Данные KPI не заполнены</div>
        <div class="kpv-empty-sub">Импортируйте шаблон или введите показатели вручную<br>для всех руководителей (обычно 20-30 KPI на каждого)</div>
      </div>

      <div v-else class="kpv-mgrs">
        <div
          v-for="card in managerCards"
          :key="card.idx"
          class="kpi2 fin-shimmer kpv-mgr"
          :class="{ active: card.active }"
          :style="{ '--kpi2-accent': card.accent, '--kpi2-d': card.delay + 'ms', '--d': card.delay + 'ms' }"
          @click="emit('set-manager', card.idx)"
        >
          <div class="kpv-mgr-head">
            <div class="kpi2-lbl kpv-mgr-t1">{{ card.short_title }}</div>
            <div class="kpv-mgr-t2">{{ card.role }}</div>
          </div>

          <div class="kpv-mgr-beads">
            <div v-for="(b, bi) in card.beads" :key="bi" class="kpv-mgr-bead" :style="{ background: beadColor(b) }"></div>
          </div>

          <div class="kpv-mgr-pct-row">
            <div class="kpv-mgr-pct-main">
              <span class="kpi2-val kpv-mgr-pct-v" :style="{ color: card.pctColor }">{{ card.pct != null ? card.pct : "—" }}</span>
              <span v-if="card.pct != null" class="kpv-mgr-pct-suffix" :style="{ color: card.pctColor }">%</span>
            </div>
            <div class="kpv-mgr-pct-side">
              <span class="kpv-mgr-total-lbl">всего</span>
              <span class="kpv-mgr-total-v">{{ card.totalCount }}</span>
            </div>
          </div>

          <div class="kpv-mgr-bar">
            <div class="kpv-mgr-bar-fill" :style="{ width: (card.pct != null ? Math.min(card.pct, 100) : 0) + '%', background: card.barColor, '--w': (card.pct != null ? Math.min(card.pct, 100) : 0) + '%' }"></div>
          </div>

          <div class="kpv-mgr-foot">
            <span v-html="card.footL"></span>
          </div>
        </div>
      </div>

      <!-- ═══ 3. Split row: Attention + Achievements ═══ -->
      <div class="kpv-split">
        <div class="kpv-card" style="--d:260ms">
          <div class="kpv-card-ttl">
            <span><span class="kpv-att-dot" :style="{ background: attentionDotColor }"></span>Требуют решения</span>
          </div>
          <div v-if="!attention.length" class="kpv-att-empty">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="#1D9E75" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-right:6px"><path d="M3 7l3 3 5-6"/></svg>
            Критических отклонений нет
          </div>
          <div v-else>
            <div
              v-for="(iss, i) in attention"
              :key="i"
              class="kpv-att-row"
              :class="iss.severity === 'high' ? 'high' : 'medium'"
              :style="{ '--d': (i * 40) + 'ms' }"
            >
              <div>
                <div class="kpv-att-ttl">{{ iss.title }}</div>
                <div class="kpv-att-d">{{ iss.detail || '' }}</div>
              </div>
              <div class="kpv-att-val">{{ iss.value }}</div>
            </div>
          </div>
        </div>

        <div class="kpv-card" style="--d:300ms">
          <div class="kpv-card-ttl">
            <span><span class="kpv-att-dot" style="background:#1D9E75"></span>Достижения периода</span>
          </div>
          <div v-if="!achievements.length" class="kpv-ach-empty">Нет показателей ≥105% плана</div>
          <div v-else>
            <div
              v-for="(a, i) in achievements"
              :key="a.title + i"
              class="kpv-ach-row"
              :style="{ '--d': (i * 40) + 'ms' }"
            >
              <div>
                <div class="kpv-ach-ttl">{{ a.title }}</div>
                <div class="kpv-ach-d">{{ a.meta }}</div>
              </div>
              <div class="kpv-ach-val">{{ Math.round(a.ratio * 100) }}%</div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ 4. Comment ═══ -->
      <div class="kpv-cmt" style="--d:340ms">
        <div class="kpv-cmt-hd">
          <span class="kpv-cmt-ttl">Комментарий руководителя</span>
          <span style="display:flex;align-items:center;gap:10px">
            <span class="kpv-cmt-meta">{{ comment?.body ? 'обновлено' : '' }}</span>
            <button v-if="canEdit && !editingComment" class="kpv-cmt-edit" @click="editingComment = true">
              {{ comment?.body ? 'Редактировать' : 'Добавить' }}
            </button>
          </span>
        </div>
        <div v-if="!editingComment">
          <div v-if="comment?.body" class="kpv-cmt-text">{{ comment.body }}</div>
          <div v-else class="kpv-cmt-text empty">Комментарий не задан. Нажмите «{{ canEdit ? 'Добавить' : '—' }}» чтобы добавить пояснение для НС.</div>
        </div>
        <div v-else>
          <textarea
            v-model="commentDraft"
            class="kpv-cmt-textarea"
            placeholder="Например: В Q1 все 4 руководителя достигли целевых показателей. Отставание по IPO-направлению компенсируется опережением по инвестпрограмме..."
          ></textarea>
          <div class="kpv-cmt-btns">
            <button class="kpv-cmt-cancel" @click="cancelEdit">Отмена</button>
            <button class="kpv-cmt-save" @click="saveComment" :disabled="savingComment">
              {{ savingComment ? 'Сохранение...' : 'Сохранить' }}
            </button>
          </div>
        </div>
      </div>

      <!-- ═══ 5. Details ОФР ═══ -->
      <div class="kpv-card" style="--d:380ms">
        <div class="kpv-card-ttl">
          <span>Детализация KPI</span>
        </div>
        <div v-if="!activeManager" class="kpv-empty">
          <div class="kpv-empty-ttl">Выберите руководителя</div>
          <div class="kpv-empty-sub">Нажмите на карточку выше чтобы увидеть детализацию по всем KPI</div>
        </div>
        <template v-else>
          <div v-if="detailsMeta" class="kpv-det-head">
            <div class="kpv-det-info">
              <div class="lt">{{ detailsMeta.title }}</div>
              <div class="ls">{{ detailsMeta.sub }}</div>
            </div>
          </div>
          <div v-if="!detailsRows.length" class="kpv-empty">
            <div class="kpv-empty-ttl">У руководителя ещё нет KPI</div>
            <div class="kpv-empty-sub">Добавьте показатели через «Редактировать»</div>
          </div>
          <div v-else class="kpv-det-body">
            <table class="kpv-det-tbl">
              <thead>
                <tr>
                  <th>KPI</th>
                  <th>Вес</th>
                  <th>План</th>
                  <th>Факт</th>
                  <th>Ед. изм.</th>
                  <th>%</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in detailsRows" :key="row.ind.id" :class="row.trClass" @click="emit('open-indicator', row.ind.id)">
                  <td>{{ row.ind.name }}</td>
                  <td class="r">{{ row.weight || 0 }}</td>
                  <td class="r">{{ fmtNum(row.plan) }}</td>
                  <td class="r">{{ fmtNum(row.fact) }}</td>
                  <td class="r" style="color: var(--t3, #888780);font-size:11px">{{ row.unit }}</td>
                  <td class="r"><span class="kpv-det-pct" :class="row.pctClass">{{ row.pct != null ? Math.round(row.pct) + '%' : '—' }}</span></td>
                  <td>
                    <span class="kpv-icn" :class="row.icnClass">
                      <svg v-if="row.icnKind === 'check'" width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 6.5l2.5 2.5L9.5 3.5"/></svg>
                      <svg v-else-if="row.icnKind === 'dot'" width="11" height="11" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="3" fill="currentColor"/></svg>
                      <svg v-else-if="row.icnKind === 'cross'" width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 3l6 6M9 3l-6 6"/></svg>
                      <span v-else>—</span>
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>

    </div>
  </div>
</template>

<style scoped>
.kpv-scroll { background: #F4F3F9; min-height: 100%; padding: 0; }
.kpv-body { padding: 20px 22px 28px; }

@keyframes kpvCardIn {
  0% { opacity: 0; transform: translateY(12px) scale(.98); }
  60% { opacity: 1; transform: translateY(-2px) scale(1); }
  100% { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes kpvStripeIn {
  0% { transform: scaleX(0); }
  100% { transform: scaleX(1); }
}
@keyframes kpvBarFill {
  0% { width: 0; }
  100% { width: var(--w, 100%); }
}
@keyframes kpvShimmer {
  0% { left: -60%; }
  100% { left: 160%; }
}
@keyframes kpvNumIn {
  0% { opacity: 0; transform: translateY(6px); }
  100% { opacity: 1; transform: translateY(0); }
}
@keyframes kpvSlideIn {
  0% { opacity: 0; transform: translateX(-6px); }
  100% { opacity: 1; transform: translateX(0); }
}

/* ═══ Status bar (4 cells) ═══ */
.kpv-stat-bar {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;
  margin-bottom: 14px;
}
.kpv-stat-cell {
  background: rgba(255, 255, 255, .92);
  border: 1px solid rgba(255, 255, 255, .7);
  border-radius: 12px;
  padding: 14px 16px 12px;
  position: relative; overflow: hidden;
  animation: kpvCardIn .5s cubic-bezier(0.34, 1.2, 0.64, 1) var(--d, 0ms) both;
  transition: background .25s, border-color .25s;
  box-shadow: 0 2px 8px rgba(15, 23, 60, .06);
}
.kpv-stat-cell::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--kpi2-accent, #7F77DD);
  transform-origin: left;
  animation: kpvStripeIn .8s cubic-bezier(0.34, 1.2, 0.64, 1) var(--kpi2-d, 0ms) both;
  transition: background .3s;
}
.kpv-stat-cell.fin-shimmer::after {
  content: ""; position: absolute; top: 0; left: -60%;
  width: 60%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(127, 119, 221, .07), transparent);
  animation: kpvShimmer 1.1s ease-out calc(var(--d, 0ms) + 200ms) forwards;
  pointer-events: none; z-index: 2;
}
.kpv-stat-cell.ok      { --kpi2-accent: #1D9E75; }
.kpv-stat-cell.warn    { --kpi2-accent: #EF9F27; }
.kpv-stat-cell.bad     { --kpi2-accent: #E24B4A; }
.kpv-stat-cell.neutral { --kpi2-accent: #94A3B8; }
.kpv-stat-lbl {
  font-size: 11px; color: var(--t3, #888780); text-transform: uppercase;
  letter-spacing: .06em; font-weight: 500; margin-bottom: 8px;
  animation: kpvNumIn .4s ease calc(var(--d, 0ms) + 50ms) both;
}
.kpv-stat-val {
  font-size: 36px; font-weight: 400;
  color: var(--kpi2-accent, #1E2A4A);
  letter-spacing: -.035em; line-height: 1;
  font-feature-settings: "tnum"; margin: 0;
  transition: color .3s;
  animation: kpvNumIn .5s ease calc(var(--d, 0ms) + 200ms) both;
}
.kpv-stat-sub {
  font-size: 11.5px; color: var(--t3, #888780);
  margin-top: 6px; font-weight: 500;
  animation: kpvNumIn .4s ease calc(var(--d, 0ms) + 300ms) both;
}

/* ═══ Manager cards (horizontal scroll) ═══ */
.kpv-mgrs {
  display: grid; grid-auto-flow: column;
  grid-auto-columns: minmax(220px, 1fr); gap: 12px;
  margin-bottom: 14px; overflow-x: auto;
  scroll-snap-type: x proximity;
  padding-bottom: 2px;
  scrollbar-width: thin;
}
.kpv-mgrs::-webkit-scrollbar { height: 6px; }
.kpv-mgrs::-webkit-scrollbar-track { background: transparent; }
.kpv-mgrs::-webkit-scrollbar-thumb { background: rgba(127, 119, 221, .25); border-radius: 3px; }
.kpv-mgrs::-webkit-scrollbar-thumb:hover { background: rgba(127, 119, 221, .4); }

.kpv-mgr {
  background: rgba(255, 255, 255, .92);
  border: 1px solid rgba(255, 255, 255, .7);
  border-radius: 12px; padding: 14px 16px 12px;
  cursor: pointer; scroll-snap-align: start; min-width: 0;
  position: relative; overflow: hidden;
  animation: kpvCardIn .5s cubic-bezier(0.34, 1.2, 0.64, 1) var(--d, 0ms) both;
  transition: box-shadow .2s;
  box-shadow: 0 2px 8px rgba(15, 23, 60, .06);
}
.kpv-mgr::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--kpi2-accent, #7F77DD);
  transform-origin: left;
  animation: kpvStripeIn .8s cubic-bezier(0.34, 1.2, 0.64, 1) var(--kpi2-d, 0ms) both;
}
.kpv-mgr.fin-shimmer::after {
  content: ""; position: absolute; top: 0; left: -60%;
  width: 60%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(127, 119, 221, .07), transparent);
  animation: kpvShimmer 1.1s ease-out calc(var(--d, 0ms) + 200ms) forwards;
  pointer-events: none; z-index: 2;
}
.kpv-mgr.active {
  box-shadow: 0 0 0 2px var(--kpi2-accent, #7F77DD), 0 4px 16px rgba(15, 23, 60, .08);
}
.kpv-mgr-head { margin-bottom: 8px; min-height: 36px; }
.kpv-mgr-t1 {
  font-size: 10px; color: var(--t3, #888780); letter-spacing: .06em;
  text-transform: uppercase; font-weight: 500;
  line-height: 1.2; margin-bottom: 3px;
  animation: kpvNumIn .4s ease calc(var(--d, 0ms) + 50ms) both;
}
.kpv-mgr-t2 {
  font-size: 12.5px; font-weight: 500; color: var(--t1, #1E2A4A);
  line-height: 1.3; overflow: hidden;
  text-overflow: ellipsis; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.kpv-mgr-beads {
  display: flex; gap: 3px; margin-top: 12px; margin-bottom: 10px;
  animation: kpvNumIn .45s ease calc(var(--d, 0ms) + 300ms) both;
}
.kpv-mgr-bead {
  flex: 1; height: 6px; border-radius: 2px;
  min-width: 4px; transition: background .25s;
}
.kpv-mgr-pct-row {
  display: flex; justify-content: space-between;
  align-items: flex-end; margin-top: 2px;
}
.kpv-mgr-pct-main { display: flex; align-items: baseline; gap: 1px; }
.kpv-mgr-pct-v {
  font-feature-settings: "tnum"; transition: color .25s;
  font-size: 22px; margin: 0; line-height: 1; font-weight: 500;
  letter-spacing: -.02em;
  animation: kpvNumIn .5s ease calc(var(--d, 0ms) + 180ms) both;
}
.kpv-mgr-pct-suffix {
  font-size: 14px; font-weight: 500; margin-left: 1px;
}
.kpv-mgr-pct-side {
  display: flex; flex-direction: column; align-items: flex-end; line-height: 1;
  animation: kpvNumIn .4s ease calc(var(--d, 0ms) + 260ms) both;
}
.kpv-mgr-total-lbl { font-size: 10px; color: var(--t3, #888780); margin-bottom: 2px; }
.kpv-mgr-total-v {
  font-size: 16px; font-weight: 500; color: var(--t3, #64748B);
  font-feature-settings: "tnum";
}
.kpv-mgr-bar {
  height: 5px; background: rgba(0, 0, 0, .05);
  border-radius: 3px; margin-top: 8px; overflow: hidden;
  animation: kpvNumIn .45s ease calc(var(--d, 0ms) + 300ms) both;
}
.kpv-mgr-bar-fill {
  height: 100%; border-radius: 3px;
  animation: kpvBarFill .8s cubic-bezier(.22,.61,.36,1) calc(var(--d, 0ms) + 450ms) both;
}
.kpv-mgr-foot {
  margin-top: 10px; padding-top: 8px;
  border-top: 0.5px solid rgba(0, 0, 0, .05);
  font-size: 10.5px; color: var(--t3, #888780);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  animation: kpvNumIn .4s ease calc(var(--d, 0ms) + 380ms) both;
}
.kpv-mgr-foot :deep(.ok)   { color: #0F6E56; font-weight: 500; }
.kpv-mgr-foot :deep(.warn) { color: #A36500; font-weight: 500; }
.kpv-mgr-foot :deep(.bad)  { color: #933632; font-weight: 500; }

/* ═══ Split: Attention + Achievements ═══ */
.kpv-split {
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 12px; margin-bottom: 14px;
}
.kpv-card {
  background: var(--bg1, #fff); border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, .05);
  padding: 16px 18px; position: relative;
  animation: kpvCardIn .65s cubic-bezier(0.34, 1.2, 0.64, 1) var(--d, 0ms) both;
}
.kpv-card-ttl {
  font-size: 11px; font-weight: 500; color: var(--t3, #888780);
  text-transform: uppercase; letter-spacing: .07em;
  margin: 0 0 12px;
  display: flex; justify-content: space-between; align-items: center;
  animation: kpvNumIn .45s ease var(--d, 0ms) both;
}
.kpv-att-dot {
  display: inline-block; width: 6px; height: 6px;
  border-radius: 50%; margin-right: 6px; vertical-align: middle;
}
.kpv-att-empty, .kpv-ach-empty {
  padding: 20px 8px; text-align: center;
  color: var(--t3, #888780); font-size: 12px; font-weight: 500;
}
.kpv-att-row {
  padding: 8px 11px; border-radius: 8px;
  margin-bottom: 6px;
  display: flex; justify-content: space-between;
  align-items: flex-start; gap: 10px;
  animation: kpvSlideIn .35s cubic-bezier(.22,.61,.36,1) var(--d, 0ms) both;
  /* top-stripe via .kpv-att-row::before — colour via --kpv-accent */
  position: relative; overflow: hidden;
  --kpv-accent: transparent;
}
.kpv-att-row::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: var(--kpv-accent);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .5s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  pointer-events: none;
}
.kpv-att-row:last-child { margin-bottom: 0; }
.kpv-att-row.high   { background: #FEF2F2; --kpv-accent: #E24B4A; }
.kpv-att-row.medium { background: #FFFBEB; --kpv-accent: #EF9F27; }
.kpv-att-ttl { font-size: 12px; font-weight: 500; color: var(--t1, #1E2A4A); margin-bottom: 2px; }
.kpv-att-d   { font-size: 10.5px; color: var(--t3, #5F5E5A); line-height: 1.4; }
.kpv-att-val {
  font-size: 11px; font-weight: 600; font-feature-settings: "tnum";
  white-space: nowrap; flex-shrink: 0;
}
.kpv-att-row.high .kpv-att-val   { color: #A32D2D; }
.kpv-att-row.medium .kpv-att-val { color: #8A5F15; }

.kpv-ach-row {
  padding: 7px 11px; border-radius: 8px;
  margin-bottom: 6px;
  background: rgba(29, 158, 117, .06);
  display: flex; justify-content: space-between;
  align-items: flex-start; gap: 10px;
  animation: kpvSlideIn .35s cubic-bezier(.22,.61,.36,1) var(--d, 0ms) both;
  position: relative; overflow: hidden;
}
.kpv-ach-row::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #1D9E75;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .5s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  pointer-events: none;
}
.kpv-ach-row:last-child { margin-bottom: 0; }
.kpv-ach-ttl { font-size: 12px; font-weight: 500; color: var(--t1, #1E2A4A); margin-bottom: 2px; }
.kpv-ach-d   { font-size: 10.5px; color: var(--t3, #5F5E5A); line-height: 1.4; }
.kpv-ach-val {
  font-size: 11px; font-weight: 600; color: #0F6E56;
  font-feature-settings: "tnum"; white-space: nowrap; flex-shrink: 0;
}

/* ═══ Comment ═══ */
.kpv-cmt {
  padding: 14px 18px; background: var(--bg1, #fff);
  border: 1px solid rgba(0, 0, 0, .05);
  border-radius: 12px; margin-bottom: 14px;
  animation: kpvCardIn .55s cubic-bezier(0.34, 1.2, 0.64, 1) var(--d, 0ms) both;
}
.kpv-cmt-hd {
  display: flex; justify-content: space-between;
  align-items: center; margin-bottom: 10px;
}
.kpv-cmt-ttl {
  font-size: 11px; font-weight: 500; color: var(--t3, #888780);
  text-transform: uppercase; letter-spacing: .07em;
}
.kpv-cmt-meta { font-size: 10.5px; color: var(--t3, #888780); font-weight: 500; }
.kpv-cmt-text {
  font-size: 13px; line-height: 1.6; color: var(--t1, #1E2A4A);
  white-space: pre-wrap; min-height: 20px;
}
.kpv-cmt-text.empty { color: var(--t3, #888780); font-style: italic; }
.kpv-cmt-edit {
  padding: 4px 12px; font-size: 11px;
  border: 1px solid rgba(0, 0, 0, .08); border-radius: 6px;
  background: var(--bg1, #fff); color: var(--t3, #888780); cursor: pointer;
  font-family: inherit; transition: all .15s;
}
.kpv-cmt-edit:hover { background: #fafafa; color: var(--t1, #1E2A4A); border-color: rgba(0, 0, 0, .15); }
.kpv-cmt-textarea {
  width: 100%; min-height: 80px;
  padding: 10px 12px;
  border: 1px solid rgba(127, 119, 221, .3);
  border-radius: 8px;
  font-size: 13px; line-height: 1.55;
  font-family: inherit; color: var(--t1, #1E2A4A);
  resize: vertical; outline: none; box-sizing: border-box;
}
.kpv-cmt-textarea:focus {
  border-color: #7F77DD;
  box-shadow: 0 0 0 2px rgba(127, 119, 221, .15);
}
.kpv-cmt-btns { display: flex; gap: 6px; justify-content: flex-end; margin-top: 8px; }
.kpv-cmt-btns button {
  padding: 5px 14px; font-size: 11px;
  border-radius: 6px; cursor: pointer;
  font-family: inherit; font-weight: 500; transition: all .15s;
}
.kpv-cmt-save { background: #7F77DD; color: #fff; border: none; }
.kpv-cmt-save:hover:not(:disabled) { background: #6B63D4; }
.kpv-cmt-save:disabled { opacity: .6; cursor: not-allowed; }
.kpv-cmt-cancel {
  background: var(--bg1, #fff); color: var(--t3, #888780);
  border: 1px solid rgba(0, 0, 0, .08);
}
.kpv-cmt-cancel:hover { background: #fafafa; color: var(--t1, #1E2A4A); }

/* ═══ Details table ═══ */
.kpv-det-head {
  display: flex; justify-content: space-between;
  align-items: center; margin-bottom: 12px;
}
.kpv-det-info { display: flex; flex-direction: column; gap: 2px; }
.kpv-det-info .lt { font-size: 13px; font-weight: 500; color: var(--t1, #1E2A4A); }
.kpv-det-info .ls { font-size: 11px; color: var(--t3, #888780); }

.kpv-det-tbl {
  width: 100%; border-collapse: collapse;
  font-size: 12px;
}
.kpv-det-tbl thead th {
  padding: 8px 10px; text-align: right;
  font-size: 10px; font-weight: 500; color: var(--t3, #888780);
  text-transform: uppercase; letter-spacing: .06em;
  border-bottom: 1.5px solid rgba(0, 0, 0, .08);
  white-space: nowrap;
}
.kpv-det-tbl thead th:first-child { text-align: left; padding-left: 0; }
.kpv-det-tbl thead th:last-child { padding-right: 0; text-align: center; width: 30px; }
.kpv-det-tbl tbody td {
  padding: 8px 10px;
  font-feature-settings: "tnum";
  border-bottom: 1px solid rgba(0, 0, 0, .03);
  vertical-align: top;
}
.kpv-det-tbl tbody tr:last-child td { border-bottom: none; }
.kpv-det-tbl tbody td:first-child {
  padding-left: 0; text-align: left;
  color: var(--t1, #1E2A4A); font-size: 12px; line-height: 1.35;
}
.kpv-det-tbl tbody td:last-child { padding-right: 0; text-align: center; }
.kpv-det-tbl tbody td.r { text-align: right; }
.kpv-det-tbl tbody tr {
  cursor: pointer;
  transition: background .15s;
}
.kpv-det-tbl tbody tr:hover { background: rgba(127, 119, 221, .04); }
.kpv-det-tbl tbody tr.alert-high td:first-child {
  position: relative; padding-left: 8px;
}
.kpv-det-tbl tbody tr.alert-high td:first-child::before {
  content: ""; position: absolute; left: 0; top: 8px; bottom: 8px;
  width: 2px; background: #E24B4A; border-radius: 1px;
}
.kpv-det-tbl tbody tr.alert-med td:first-child {
  position: relative; padding-left: 8px;
}
.kpv-det-tbl tbody tr.alert-med td:first-child::before {
  content: ""; position: absolute; left: 0; top: 8px; bottom: 8px;
  width: 2px; background: #EF9F27; border-radius: 1px;
}
.kpv-det-pct { font-weight: 500; }
.kpv-det-pct.ok   { color: #0F6E56; }
.kpv-det-pct.warn { color: #8A5F15; }
.kpv-det-pct.bad  { color: #933632; }

.kpv-icn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 50%;
  font-size: 10px; font-weight: 500;
}
.kpv-icn.ok   { background: rgba(29, 158, 117, .12); color: #0F6E56; }
.kpv-icn.warn { background: rgba(239, 159, 39, .12); color: #8A5F15; }
.kpv-icn.bad  { background: rgba(226, 75, 74, .12); color: #933632; }

/* ═══ Empty state ═══ */
.kpv-empty {
  text-align: center; padding: 40px 20px; color: var(--t3, #888780);
}
.kpv-empty-ttl { font-size: 14px; font-weight: 500; color: var(--t3, #5F5E5A); margin-bottom: 6px; }
.kpv-empty-sub { font-size: 12px; color: var(--t3, #888780); margin-bottom: 14px; line-height: 1.55; }

/* ═══ Responsive ═══ */
@media (max-width: 1100px) {
  .kpv-stat-bar { grid-template-columns: repeat(2, 1fr); }
  .kpv-split { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .kpv-body { padding: 14px 12px; }
  .kpv-stat-bar { grid-template-columns: 1fr; }
}
</style>
