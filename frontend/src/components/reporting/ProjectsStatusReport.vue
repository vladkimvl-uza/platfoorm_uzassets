<script setup lang="ts">
/**
 * ProjectsStatusReport — «Отчёт по проектам, задачам и статусам».
 * Премиум-отчёт уровня министра/совета: фирменный хедер, сводка со сегментными
 * барами, групп-заголовки направлений, статус-pill, health-индикатор «хода».
 *
 * Автозаполняется из данных воркспейса (проекты + задачи + последний «ход» из
 * status-updates: текст + health). Группировка направление → проект (1..N) →
 * задачи (N.M). Любую ячейку (срок/статус/комментарий) можно отредактировать —
 * правки сохраняются оверрайдами в report_wizard config (исходные задачи не
 * меняются). Экспорт в Word (.doc) в формате шаблона.
 */
import { ref, computed, watch, onMounted } from "vue";
import { statusUpdatesApi, HEALTH_META, type StatusHealth } from "@/api/statusUpdates";
import { reportWizardApi } from "@/api/reportWizard";
import { useToast } from "@/composables/useToast";
import EptLogo from "@/components/EptLogo.vue";
import UzaSkeleton from "@/components/UZA/UzaSkeleton.vue";

const props = defineProps<{
  companyName: string;
  companyCode: string;
  sectorName?: string | null;
  year: number;
  projects: any[];
  tasks: any[];
}>();

const toast = useToast();

// ─── Мета направлений (label + бренд-цвет) ───────────────────────
const DIR_META: Record<string, { label: string; color: string }> = {
  strategy:    { label: "Стратегическое управление",  color: "#1e2787" },
  finance:     { label: "Финансы / риски / аудит",    color: "#D97706" },
  procurement: { label: "Система закупок",            color: "#3B6D11" },
  orgdev:      { label: "Организационное развитие",   color: "#534AB7" },
  digital:     { label: "Цифровизация",               color: "#1D9E75" },
  operations:  { label: "Операционная эффективность", color: "#EF4444" },
  governance:  { label: "Корпоративное управление",   color: "#72243E" },
  esg:         { label: "ESG",                        color: "#0F8A6B" },
  pr:          { label: "Связи с общественностью",    color: "#D4537E" },
  pmo:         { label: "PMO",                        color: "#2563EB" },
  analytics:   { label: "Сводный отдел",              color: "#7C3AED" },
};
const STATUS_META: Record<string, { label: string; color: string }> = {
  new:       { label: "Не начато",       color: "#94A3B8" },
  init:      { label: "Инициирование",   color: "#7F77DD" },
  active:    { label: "В процессе",      color: "#378ADD" },
  review:    { label: "На согласовании", color: "#EF9F27" },
  done:      { label: "Завершено",       color: "#1D9E75" },
  quarterly: { label: "Ежеквартально",   color: "#A855F7" },
  monthly:   { label: "Ежемесячно",      color: "#A855F7" },
  ongoing:   { label: "Постоянно",       color: "#A855F7" },
  deferred:  { label: "Отложено",        color: "#94A3B8" },
};
const STATUS_OPTIONS = ["new", "init", "active", "review", "done", "quarterly", "monthly", "ongoing", "deferred"];
function statusLabel(s: string) { return STATUS_META[s]?.label || s || "—"; }
function statusColor(s: string) { return STATUS_META[s]?.color || "#94A3B8"; }
function dirMeta(code: string | null | undefined) {
  return DIR_META[String(code || "").toLowerCase()] || { label: "Без направления", color: "#8A8A8A" };
}

const ROMAN = ["", "I", "II", "III", "IV"];
function quarterOf(due: string | null | undefined): string {
  if (!due) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(due));
  if (!m) return String(due);
  return `${ROMAN[Math.ceil(Number(m[2]) / 3)] || ""} кв. ${m[1]}`;
}

// ─── Последний «ход» (текст + health) проекта/задачи ─────────────
const latestMap = ref<Record<string, { body: string; health: StatusHealth | null; at: string | null }>>({});
const loadingFlow = ref(false);
async function loadFlow() {
  loadingFlow.value = true;
  try {
    const map: Record<string, { body: string; health: StatusHealth | null; at: string | null }> = {};
    const jobs: Promise<void>[] = [];
    const pull = (type: "project" | "task", id: string) => jobs.push(
      statusUpdatesApi.list(type, id).then(list => {
        if (list?.length) {
          const l = [...list].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))[0];
          if (l) map[id] = { body: l.body || "", health: l.health, at: l.created_at || null };
        }
      }).catch(() => {}),
    );
    for (const p of props.projects) pull("project", p.id);
    for (const t of props.tasks) pull("task", t.id);
    await Promise.allSettled(jobs);
    latestMap.value = map;
  } finally { loadingFlow.value = false; }
}

// ─── Оверрайды + сохранение в report_wizard config ──────────────
type Override = { srok?: string; status?: string; comment?: string };
const overrides = ref<Record<string, Override>>({});
const baseConfig = ref<Record<string, unknown>>({});
const CFG_KEY = "projects_status_report";
const loadingCfg = ref(false);
const saving = ref(false);
let saveTimer: ReturnType<typeof setTimeout> | null = null;

async function loadConfig() {
  loadingCfg.value = true;
  try {
    const r = await reportWizardApi.get(props.companyCode, props.year);
    baseConfig.value = r.config || {};
    const ov = (r.config as any)?.[CFG_KEY]?.overrides;
    overrides.value = (ov && typeof ov === "object") ? ov : {};
  } catch { overrides.value = {}; } finally { loadingCfg.value = false; }
}
function scheduleSave() { if (saveTimer) clearTimeout(saveTimer); saveTimer = setTimeout(doSave, 800); }
async function doSave() {
  saving.value = true;
  try {
    const cfg = { ...baseConfig.value, [CFG_KEY]: { overrides: overrides.value } };
    const r = await reportWizardApi.save(props.companyCode, props.year, cfg);
    baseConfig.value = r.config || cfg;
  } catch (e: any) {
    toast.error("Не удалось сохранить: " + (e?.response?.data?.detail || e?.message || ""));
  } finally { saving.value = false; }
}
function setOverride(id: string, field: keyof Override, value: string) {
  overrides.value = { ...overrides.value, [id]: { ...(overrides.value[id] || {}), [field]: value } };
  scheduleSave();
}
function resetOverrides() {
  overrides.value = {}; scheduleSave();
  toast.info("Ручные правки сброшены — данные снова из системы");
}

// ─── Сборка строк, сгруппированных по направлениям ───────────────
interface Row {
  id: string; kind: "project" | "task"; num: string; title: string;
  srok: string; status: string; comment: string; health: StatusHealth | null;
}
interface Group { key: string; label: string; color: string; rows: Row[] }

const grouped = computed<Group[]>(() => {
  const tasksByProj = new Map<string, any[]>();
  for (const t of props.tasks) {
    if (!t.project_id) continue;
    (tasksByProj.get(t.project_id) || tasksByProj.set(t.project_id, []).get(t.project_id)!).push(t);
  }
  const byDir = new Map<string, any[]>();
  for (const p of props.projects) {
    const k = String(p.direction || "").toLowerCase() || "__none__";
    (byDir.get(k) || byDir.set(k, []).get(k)!).push(p);
  }
  const keys = [...byDir.keys()].sort((a, b) => {
    if (a === "__none__") return 1; if (b === "__none__") return -1;
    return dirMeta(a).label.localeCompare(dirMeta(b).label, "ru");
  });
  let pNo = 0;
  const groups: Group[] = [];
  for (const dk of keys) {
    const meta = dk === "__none__" ? { label: "Без направления", color: "#8A8A8A" } : dirMeta(dk);
    const rows: Row[] = [];
    const ps = byDir.get(dk)!.slice().sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
    for (const p of ps) {
      pNo++;
      const pf = latestMap.value[p.id];
      rows.push({ id: p.id, kind: "project", num: String(pNo), title: p.title || "—",
        srok: quarterOf(p.due_date), status: p.status || "new", comment: pf?.body || "", health: pf?.health ?? null });
      const ts = (tasksByProj.get(p.id) || []).slice().sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
      ts.forEach((t, i) => {
        const tf = latestMap.value[t.id];
        rows.push({ id: t.id, kind: "task", num: `${pNo}.${i + 1}`, title: t.title || "—",
          srok: quarterOf(t.due_date), status: t.status || "new", comment: tf?.body || "", health: tf?.health ?? null });
      });
    }
    groups.push({ key: dk, label: meta.label, color: meta.color, rows });
  }
  return groups;
});

function effSrok(r: Row) { return overrides.value[r.id]?.srok ?? r.srok; }
function effStatus(r: Row) { return overrides.value[r.id]?.status ?? r.status; }
function effComment(r: Row) { return overrides.value[r.id]?.comment ?? r.comment; }
function isEdited(r: Row) {
  const o = overrides.value[r.id];
  return !!(o && (o.srok !== undefined || o.status !== undefined || o.comment !== undefined));
}

// ─── Сводка ──────────────────────────────────────────────────────
function bucket(s: string): "done" | "notstarted" | "inprogress" {
  if (s === "done") return "done"; if (s === "new") return "notstarted"; return "inprogress";
}
const allRows = computed(() => grouped.value.flatMap(g => g.rows));
function tally(list: Row[]) {
  const t = { total: list.length, done: 0, inprogress: 0, notstarted: 0 };
  for (const r of list) t[bucket(effStatus(r))]++;
  return t;
}
const summary = computed(() => ({
  projects: tally(allRows.value.filter(r => r.kind === "project")),
  tasks: tally(allRows.value.filter(r => r.kind === "task")),
}));
function pct(n: number, total: number) { return total > 0 ? Math.round(n / total * 100) : 0; }
function autoGrow(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = "auto"; el.style.height = el.scrollHeight + "px";
}

// ─── Экспорт .doc (формат шаблона: с колонкой «Направление») ─────
function esc(s: string) { return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function exportDoc() {
  const s = summary.value;
  const sumLine = (t: typeof s.projects) =>
    `завершено ${t.done} (${pct(t.done, t.total)}%) · в процессе ${t.inprogress} (${pct(t.inprogress, t.total)}%) · не начато ${t.notstarted} (${pct(t.notstarted, t.total)}%)`;
  const head = `
    <div style="border-bottom:3px solid #7F77DD;padding-bottom:8px;margin-bottom:12px">
      <div style="font:700 19px Arial;color:#1e2a4a;margin:0">ОТЧЁТ ПО ПРОЕКТАМ, ЗАДАЧАМ И СТАТУСАМ</div>
      <div style="font:12px Arial;color:#555;margin-top:3px">${esc(props.companyName)}${props.sectorName ? " · " + esc(props.sectorName) : ""} · FY ${props.year}</div>
    </div>
    <div style="font:12px Arial;color:#333;margin:0 0 12px">
      <b>Проекты:</b> ${s.projects.total} — ${sumLine(s.projects)}<br/>
      <b>Задачи:</b> ${s.tasks.total} — ${sumLine(s.tasks)}
    </div>`;
  const th = (x: string) => `<th style="border:1px solid #888;background:#1e2a4a;color:#fff;font:700 11px Arial;padding:6px;text-align:left">${x}</th>`;
  const td = (x: string, b = false) => `<td style="border:1px solid #cfcfcf;font:${b ? "700" : "400"} 11px Arial;padding:5px;vertical-align:top">${esc(x)}</td>`;
  const body = grouped.value.map(g => g.rows.map(r => {
    const proj = r.kind === "project";
    const bg = proj ? ' style="background:#f3f2fb"' : "";
    return `<tr${bg}>${td(r.num, proj)}${td(g.label)}${td(r.title, proj)}${td(effSrok(r))}
      <td style="border:1px solid #cfcfcf;font:700 11px Arial;padding:5px;color:${statusColor(effStatus(r))}">${esc(statusLabel(effStatus(r)))}</td>
      ${td(effComment(r))}</tr>`;
  }).join("")).join("");
  const html = `<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word'>
    <head><meta charset="utf-8"></head><body>${head}
    <table style="border-collapse:collapse;width:100%">
      <thead><tr>${["№", "Направление", "Проект / Задача", "Срок", "Статус", "Комментарий / статус"].map(th).join("")}</tr></thead>
      <tbody>${body}</tbody></table></body></html>`;
  const blob = new Blob(["﻿", html], { type: "application/msword" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `Отчёт по проектам — ${props.companyName} — FY${props.year}.doc`;
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}

onMounted(() => { loadFlow(); loadConfig(); });
watch(() => [props.year, props.companyCode], () => { loadFlow(); loadConfig(); });
</script>

<template>
  <div class="psr">
    <!-- ── Фирменный хедер ── -->
    <div class="psr-hero">
      <div class="psr-hero-l">
        <div class="psr-logo"><EptLogo :size="24" /></div>
        <div>
          <div class="psr-eyebrow">ОТЧЁТ ПО ПРОЕКТАМ, ЗАДАЧАМ И СТАТУСАМ</div>
          <div class="psr-co">{{ companyName }}<span v-if="sectorName" class="psr-sec"> · {{ sectorName }}</span></div>
        </div>
      </div>
      <div class="psr-hero-r">
        <span class="psr-fy">FY {{ year }}</span>
        <transition name="psr-fade"><span v-if="saving" class="psr-saving">● сохранение</span></transition>
        <button class="psr-btn ghost" @click="resetOverrides" title="Вернуть данные из системы">Сбросить правки</button>
        <button class="psr-btn" @click="exportDoc">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
          Экспорт в Word
        </button>
      </div>
    </div>

    <!-- ── Сводка: сегментные бары ── -->
    <div class="psr-stats">
      <div v-for="(t, key) in { projects: summary.projects, tasks: summary.tasks }" :key="key" class="psr-stat">
        <div class="psr-stat-top">
          <span class="psr-stat-h">{{ key === 'projects' ? 'Проекты' : 'Задачи' }}</span>
          <span class="psr-stat-n">{{ t.total }}</span>
        </div>
        <div class="psr-seg">
          <span class="psr-seg-p done" :style="{ width: pct(t.done, t.total) + '%' }" />
          <span class="psr-seg-p ip" :style="{ width: pct(t.inprogress, t.total) + '%' }" />
          <span class="psr-seg-p ns" :style="{ width: pct(t.notstarted, t.total) + '%' }" />
        </div>
        <div class="psr-leg">
          <span class="psr-leg-i"><i class="done" />Завершено <b>{{ t.done }}</b> ({{ pct(t.done, t.total) }}%)</span>
          <span class="psr-leg-i"><i class="ip" />В процессе <b>{{ t.inprogress }}</b> ({{ pct(t.inprogress, t.total) }}%)</span>
          <span class="psr-leg-i"><i class="ns" />Не начато <b>{{ t.notstarted }}</b> ({{ pct(t.notstarted, t.total) }}%)</span>
        </div>
      </div>
    </div>

    <!-- ── Таблица с групп-заголовками направлений ── -->
    <div class="psr-table-wrap">
      <UzaSkeleton v-if="loadingFlow || loadingCfg" variant="rows" :rows="8" rowHeight="34px" />
      <table v-else class="psr-table">
        <thead>
          <tr>
            <th class="c-num">№</th>
            <th class="c-title">Проект / Задача</th>
            <th class="c-srok">Срок</th>
            <th class="c-status">Статус</th>
            <th class="c-com">Комментарий / статус</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="g in grouped" :key="g.key">
            <tr class="psr-dir">
              <td colspan="5">
                <span class="psr-dir-dot" :style="{ background: g.color }" />
                <span class="psr-dir-name">{{ g.label }}</span>
                <span class="psr-dir-cnt">{{ g.rows.filter(r => r.kind === 'project').length }} проектов · {{ g.rows.filter(r => r.kind === 'task').length }} задач</span>
              </td>
            </tr>
            <tr v-for="r in g.rows" :key="r.id"
                :class="{ 'is-project': r.kind === 'project', 'is-edited': isEdited(r) }">
              <td class="c-num">{{ r.num }}</td>
              <td class="c-title">
                <span class="psr-title-txt" :class="{ proj: r.kind === 'project' }">{{ r.title }}</span>
              </td>
              <td class="c-srok">
                <input class="psr-in" :value="effSrok(r)" @change="setOverride(r.id, 'srok', ($event.target as HTMLInputElement).value)" />
              </td>
              <td class="c-status">
                <span class="psr-pill" :style="{ color: statusColor(effStatus(r)), background: statusColor(effStatus(r)) + '1a' }">
                  {{ statusLabel(effStatus(r)) }}
                  <select class="psr-pill-sel" :value="effStatus(r)"
                          @change="setOverride(r.id, 'status', ($event.target as HTMLSelectElement).value)">
                    <option v-for="o in STATUS_OPTIONS" :key="o" :value="o">{{ statusLabel(o) }}</option>
                  </select>
                </span>
              </td>
              <td class="c-com">
                <div class="psr-com">
                  <span v-if="r.health" class="psr-health" :title="HEALTH_META[r.health].label"
                        :style="{ background: HEALTH_META[r.health].color }" />
                  <textarea class="psr-ta" :value="effComment(r)" rows="1" placeholder="—"
                            @focus="autoGrow" @input="autoGrow"
                            @change="setOverride(r.id, 'comment', ($event.target as HTMLTextAreaElement).value)"></textarea>
                </div>
              </td>
            </tr>
          </template>
          <tr v-if="!grouped.length"><td colspan="5" class="psr-empty">Нет проектов и задач за {{ year }} год.</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.psr { display: flex; flex-direction: column; gap: 16px; }

/* ── Hero ── */
.psr-hero {
  display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;
  background: linear-gradient(120deg, #0C1230, #141C42 70%, #1C2550);
  border-radius: 16px; padding: 16px 22px; box-shadow: 0 12px 32px rgba(15,23,60,.14);
}
.psr-hero-l { display: flex; align-items: center; gap: 14px; min-width: 0; }
.psr-logo { width: 38px; height: 38px; border-radius: 11px; background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.14); display: grid; place-items: center; flex: 0 0 auto; }
.psr-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .12em; color: #9A8FFF; }
.psr-co { color: #fff; font-size: 16px; font-weight: 600; margin-top: 3px; letter-spacing: -.01em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.psr-sec { color: rgba(255,255,255,.6); font-weight: 400; }
.psr-hero-r { display: flex; align-items: center; gap: 9px; flex: 0 0 auto; }
.psr-fy { font: 600 12px inherit; color: rgba(255,255,255,.85); background: rgba(255,255,255,.08); border: 1px solid rgba(255,255,255,.12); padding: 6px 12px; border-radius: 9px; }
.psr-saving { font-size: 11px; color: #9A8FFF; }
.psr-btn { display: inline-flex; align-items: center; gap: 7px; background: linear-gradient(135deg, #8B7FFF, #6C5CE7); color: #fff; border: none; font: 600 12px inherit; padding: 8px 14px; border-radius: 10px; cursor: pointer; box-shadow: 0 4px 14px rgba(108,92,231,.3); transition: transform .15s; }
.psr-btn:hover { transform: translateY(-1px); }
.psr-btn.ghost { background: rgba(255,255,255,.06); color: rgba(255,255,255,.8); border: 1px solid rgba(255,255,255,.14); box-shadow: none; }
.psr-btn.ghost:hover { background: rgba(255,255,255,.12); transform: none; }
.psr-fade-enter-active, .psr-fade-leave-active { transition: opacity .25s; }
.psr-fade-enter-from, .psr-fade-leave-to { opacity: 0; }

/* ── Сводка ── */
.psr-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
@media (max-width: 760px) { .psr-stats { grid-template-columns: 1fr; } }
.psr-stat { background: #fff; border: 1px solid rgba(99,102,180,.12); border-radius: 14px; padding: 14px 18px; position: relative; overflow: hidden; box-shadow: 0 4px 14px rgba(15,23,60,.05); }
.psr-stat::before { content: ""; position: absolute; left: 0; top: 0; right: 0; height: 3px; background: linear-gradient(90deg, #9D97E6, #7F77DD); }
.psr-stat-top { display: flex; align-items: baseline; justify-content: space-between; }
.psr-stat-h { font-size: 10.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--t3, #64748B); }
.psr-stat-n { font-size: 30px; font-weight: 400; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; line-height: 1; letter-spacing: -.02em; }
.psr-seg { display: flex; height: 9px; border-radius: 5px; overflow: hidden; background: #EEF0F6; margin: 11px 0 9px; }
.psr-seg-p { height: 100%; transition: width .7s cubic-bezier(.22,1,.36,1); }
.psr-seg-p.done { background: linear-gradient(90deg, #34C088, #1D9E75); }
.psr-seg-p.ip { background: linear-gradient(90deg, #5BA3F0, #2563EB); }
.psr-seg-p.ns { background: #CBD2DE; }
.psr-leg { display: flex; flex-wrap: wrap; gap: 5px 16px; font-size: 11.5px; color: var(--t3, #5F6B80); }
.psr-leg-i { display: inline-flex; align-items: center; gap: 5px; }
.psr-leg-i b { color: var(--t1, #1e2a4a); font-weight: 600; font-variant-numeric: tabular-nums; }
.psr-leg-i i { width: 8px; height: 8px; border-radius: 2px; }
.psr-leg-i i.done { background: #1D9E75; } .psr-leg-i i.ip { background: #2563EB; } .psr-leg-i i.ns { background: #CBD2DE; }

/* ── Таблица ── */
.psr-table-wrap { overflow-x: auto; border: 1px solid rgba(99,102,180,.14); border-radius: 14px; background: #fff; box-shadow: 0 4px 14px rgba(15,23,60,.05); }
.psr-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.psr-table thead th {
  background: #1e2a4a; color: #fff; font-size: 10px; font-weight: 600; letter-spacing: .05em;
  text-transform: uppercase; text-align: left; padding: 10px 12px; position: sticky; top: 0; z-index: 2; white-space: nowrap;
}
.psr-table td { border-bottom: 1px solid rgba(15,23,60,.05); padding: 5px 12px; vertical-align: top; color: var(--t1, #1e2a4a); }

.psr-dir td { background: linear-gradient(90deg, rgba(127,119,221,.08), transparent 70%); padding: 9px 12px; }
.psr-dir-dot { display: inline-block; width: 9px; height: 9px; border-radius: 3px; vertical-align: middle; margin-right: 8px; }
.psr-dir-name { font-size: 12px; font-weight: 700; color: var(--t1, #1e2a4a); letter-spacing: .01em; }
.psr-dir-cnt { font-size: 10.5px; color: var(--t3, #8A90A6); margin-left: 10px; font-weight: 500; }

.psr-table tr.is-project { background: rgba(127,119,221,.045); }
.psr-table tr.is-project:hover, .psr-table tbody tr:hover:not(.psr-dir) { background: rgba(127,119,221,.08); }
.psr-table tr.is-edited td.c-num { box-shadow: inset 3px 0 0 #EF9F27; }
.c-num { width: 46px; font-variant-numeric: tabular-nums; color: var(--t3, #8A90A6); font-size: 11px; }
.c-title { min-width: 300px; }
.psr-title-txt { line-height: 1.4; }
.psr-title-txt.proj { font-weight: 600; }
.c-srok { width: 108px; }
.c-status { width: 156px; }
.c-com { min-width: 340px; }

.psr-in { width: 100%; border: 1px solid transparent; background: transparent; font: inherit; color: inherit; border-radius: 6px; padding: 3px 6px; }
.psr-in:hover { background: rgba(127,119,221,.06); }
.psr-in:focus { outline: none; border-color: #7F77DD; background: #fff; }

/* статус как pill, поверх него прозрачный select для правки */
.psr-pill { position: relative; display: inline-flex; align-items: center; font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 999px; white-space: nowrap; cursor: pointer; }
.psr-pill::after { content: "▾"; font-size: 8px; margin-left: 5px; opacity: .55; }
.psr-pill-sel { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; }

.psr-com { display: flex; align-items: flex-start; gap: 7px; }
.psr-health { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; margin-top: 7px; box-shadow: 0 0 0 2px rgba(255,255,255,.7); }
.psr-ta { width: 100%; border: 1px solid transparent; background: transparent; font: inherit; color: inherit; border-radius: 6px; padding: 3px 6px; resize: none; min-height: 26px; line-height: 1.45; font-size: 11.5px; overflow: hidden; }
.psr-ta:hover { background: rgba(127,119,221,.06); }
.psr-ta:focus { outline: none; border-color: #7F77DD; background: #fff; }

.psr-empty { text-align: center; padding: 30px; color: var(--t3, #64748B); font-style: italic; }

@media (prefers-reduced-motion: reduce) { .psr-seg-p, .psr-btn { transition: none; } }
</style>
