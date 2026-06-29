<script setup lang="ts">
/**
 * ProjectsStatusReport — «Отчёт по проектам, задачам и статусам».
 * Премиум-отчёт уровня министра/совета: официальная тройная шапка
 * (Минэкономфин · Единая платформа трансформации · UzAssets), сводка со
 * сегментными барами, статус-pill, «ход проекта». Печать в АЛЬБОМНОЙ
 * ориентации через teleport-оверлей; печатный лист — строго в фирменной
 * монохромной палитре (без «светофора»).
 *
 * Порядок и состав строк — 1:1 как в /workspace?tab=work (CompanyBoardList):
 *   проекты по (sort_order, num) → вложенные задачи по (sort_order, num) →
 *   задачи без проекта в конце. «Ход проекта» берётся из поля current_status
 *   (последний статус-апдейт), как колонка «Ход проекта» в work-табе.
 * Любую ячейку (срок/статус/комментарий) можно отредактировать вручную —
 * правки сохраняются оверрайдами в report_wizard config. Экспорт в Word (.doc).
 */
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from "vue";
import { HEALTH_META, type StatusHealth } from "@/api/statusUpdates";
import { reportWizardApi } from "@/api/reportWizard";
import { useToast } from "@/composables/useToast";
import { useDirectionsStore } from "@/stores/directions";
import UzaSkeleton from "@/components/UZA/UzaSkeleton.vue";
import minfinLogoUrl from "@/assets/minfin-logo.png";
import uzassetsLogoUrl from "@/assets/uzassets-logo-wide.png";

const props = defineProps<{
  companyName: string;
  companyCode: string;
  sectorName?: string | null;
  year: number;
  projects: any[];
  tasks: any[];
}>();

const toast = useToast();
const directionsStore = useDirectionsStore();

// ─── Статусы: палитра 1:1 c work-табом (экран) ───────────────────
const STATUS_META: Record<string, { label: string; color: string }> = {
  init:      { label: "Инициировано",   color: "#7F77DD" },
  new:       { label: "Не начато",       color: "#94A3B8" },
  active:    { label: "В процессе",      color: "#378ADD" },
  review:    { label: "На согласовании", color: "#EF9F27" },
  done:      { label: "Завершено",       color: "#1D9E75" },
  quarterly: { label: "Ежеквартально",   color: "#A855F7" },
  monthly:   { label: "Ежемесячно",      color: "#6366F1" },
  ongoing:   { label: "Постоянно",       color: "#06B6D4" },
  deferred:  { label: "Отложено",        color: "#94A3B8" },
};
const STATUS_OPTIONS = ["new", "init", "active", "review", "done", "quarterly", "monthly", "ongoing", "deferred"];
function statusLabel(s: string) { return STATUS_META[s]?.label || s || "—"; }
function statusColor(s: string) { return STATUS_META[s]?.color || "#94A3B8"; }

// ─── Печать: СТРОГО фирменная монохромная палитра (без «светофора») ──
//   done       → насыщенный бренд-индиго (плашка)
//   в процессе → бренд-фиолет (init/active/review)
//   повторяющ. → бренд-пурпур (quarterly/monthly/ongoing)
//   не начато  → нейтральный графит (new/deferred)
function printStatusStyle(s: string): { bg: string; color: string; weight: number } {
  if (s === "done") return { bg: "#1e2787", color: "#FFFFFF", weight: 700 };
  if (s === "new" || s === "deferred") return { bg: "#EFF0F5", color: "#7C8198", weight: 600 };
  if (s === "quarterly" || s === "monthly" || s === "ongoing")
    return { bg: "rgba(83,74,183,.10)", color: "#5B53B8", weight: 600 };
  return { bg: "rgba(67,56,202,.12)", color: "#4338CA", weight: 600 }; // init/active/review
}

const ROMAN = ["", "I", "II", "III", "IV"];
function quarterOf(due: string | null | undefined): string {
  if (!due) return "—";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(due));
  if (!m) return String(due);
  return `${ROMAN[Math.ceil(Number(m[2]) / 3)] || ""} кв. ${m[1]}`;
}
function stampToday(): string {
  try { return new Date().toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" }); }
  catch { return ""; }
}

// ─── Направления (label + цвет) из store — 1:1 с work-табом ──────
function dirLabel(code: string | null | undefined): string {
  return code ? directionsStore.labelFor(code) : "Без направления";
}
function dirColor(code: string | null | undefined): string {
  return code ? directionsStore.colorFor(code) : "#8A8FA3";
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

// ─── Строки: порядок 1:1 c work-табом (CompanyBoardList.groups) ──
interface Row {
  id: string; kind: "project" | "task"; num: string; title: string;
  dirCode: string | null; srok: string; status: string;
  comment: string; health: StatusHealth | null;
}
function _ord(x: any): number { return Number(x?.sort_order) || 0; }
function _bySortThenNum(a: any, b: any): number {
  const d = _ord(a) - _ord(b);
  if (d !== 0) return d;
  return String(a?.num || "").localeCompare(String(b?.num || ""), "en", { numeric: true });
}
const normNum = (n: any) => String(n || "").replace(/\.+$/, "").trim();

const rows = computed<Row[]>(() => {
  const projs = [...props.projects].filter(p => !p.is_archived).sort(_bySortThenNum);
  const allTasks = [...props.tasks].filter(t => !t.is_archived);
  const claimed = new Set<string>();
  const out: Row[] = [];
  let pNo = 0;
  for (const p of projs) {
    pNo++;
    const pId = String(p.id || "");
    const pNum = normNum(p.num);
    const nested = allTasks.filter(t => {
      const tPid = String(t.project_id || "");
      if (tPid && pId && tPid === pId) return true;
      const tNum = normNum(t.num);
      if (!pNum || !tNum) return false;
      return tNum.startsWith(pNum + ".");
    }).sort(_bySortThenNum);
    nested.forEach(t => claimed.add(String(t.id)));
    out.push({ id: p.id, kind: "project", num: String(pNo), title: p.title || "—",
      dirCode: p.direction || null, srok: quarterOf(p.due_date), status: p.status || "new",
      comment: p.current_status || "", health: (p.current_health as StatusHealth) || null });
    nested.forEach((t, i) => out.push({ id: t.id, kind: "task", num: `${pNo}.${i + 1}`, title: t.title || "—",
      dirCode: t.direction || null, srok: quarterOf(t.due_date), status: t.status || "new",
      comment: t.current_status || "", health: (t.current_health as StatusHealth) || null }));
  }
  const orphans = allTasks.filter(t => !claimed.has(String(t.id))).sort(_bySortThenNum);
  orphans.forEach(t => {
    pNo++;
    out.push({ id: t.id, kind: "task", num: String(pNo), title: t.title || "—",
      dirCode: t.direction || null, srok: quarterOf(t.due_date), status: t.status || "new",
      comment: t.current_status || "", health: (t.current_health as StatusHealth) || null });
  });
  return out;
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
  if (s === "done") return "done";
  if (s === "new" || s === "deferred") return "notstarted";
  return "inprogress";
}
function tally(list: Row[]) {
  const t = { total: list.length, done: 0, inprogress: 0, notstarted: 0 };
  for (const r of list) t[bucket(effStatus(r))]++;
  return t;
}
const summary = computed(() => ({
  projects: tally(rows.value.filter(r => r.kind === "project")),
  tasks: tally(rows.value.filter(r => r.kind === "task")),
}));
function pct(n: number, total: number) { return total > 0 ? Math.round(n / total * 100) : 0; }
function autoGrow(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = "auto"; el.style.height = el.scrollHeight + "px";
}

// ─── Печать (альбомная ориентация, teleport-оверлей) ─────────────
const printOpen = ref(false);
function ensureLandscapeStyle() {
  let st = document.getElementById("psr-landscape") as HTMLStyleElement | null;
  if (!st) { st = document.createElement("style"); st.id = "psr-landscape"; document.head.appendChild(st); }
  st.textContent = "@media print { @page { size: A4 landscape; margin: 9mm; } }";
}
function removeLandscapeStyle() { document.getElementById("psr-landscape")?.remove(); }
function openPrint() { printOpen.value = true; document.body.classList.add("pdoc-open"); ensureLandscapeStyle(); }
function closePrint() { printOpen.value = false; document.body.classList.remove("pdoc-open"); removeLandscapeStyle(); }
async function doPrint() { ensureLandscapeStyle(); await nextTick(); window.print(); }
onUnmounted(() => { document.body.classList.remove("pdoc-open"); removeLandscapeStyle(); });

// ─── Экспорт .doc (печатный формат, фирменная палитра) ──────────
function esc(s: string) { return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
function exportDoc() {
  const s = summary.value;
  const sumLine = (t: typeof s.projects) =>
    `завершено ${t.done} (${pct(t.done, t.total)}%) · в процессе ${t.inprogress} (${pct(t.inprogress, t.total)}%) · не начато ${t.notstarted} (${pct(t.notstarted, t.total)}%)`;
  const head = `
    <div style="border-bottom:2.5px solid #4B4A9A;padding-bottom:8px;margin-bottom:12px">
      <div style="font:800 18px Arial;color:#14171F;margin:0">${esc(props.companyName)}</div>
      <div style="font:11px Arial;color:#8A8C99;margin-top:3px;text-transform:uppercase;letter-spacing:.04em">${props.sectorName ? esc(props.sectorName) + " · " : ""}отчёт по проектам · FY ${props.year}</div>
    </div>
    <div style="font:11px Arial;color:#3A3D48;margin:0 0 12px;line-height:1.5">
      <b>Проекты:</b> ${s.projects.total} — ${sumLine(s.projects)}<br/>
      <b>Задачи:</b> ${s.tasks.total} — ${sumLine(s.tasks)}
    </div>`;
  const th = (x: string) => `<th style="border:1px solid #2a375a;background:#1e2a4a;color:#fff;font:700 10px Arial;padding:6px;text-align:left">${x}</th>`;
  const td = (x: string, b = false) => `<td style="border:1px solid #d7d9e0;font:${b ? "700" : "400"} 10.5px Arial;padding:5px;vertical-align:top">${esc(x)}</td>`;
  const body = rows.value.map(r => {
    const proj = r.kind === "project";
    const bg = proj ? ' style="background:#f3f2fb"' : "";
    const st = printStatusStyle(effStatus(r));
    return `<tr${bg}>${td(r.num, proj)}${td(dirLabel(r.dirCode))}${td(r.title, proj)}${td(effSrok(r))}
      <td style="border:1px solid #d7d9e0;font:${st.weight} 10.5px Arial;padding:5px;color:${st.color};background:${st.bg}">${esc(statusLabel(effStatus(r)))}</td>
      ${td(effComment(r))}</tr>`;
  }).join("");
  const html = `<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word'>
    <head><meta charset="utf-8"><!--[if gte mso 9]><xml><w:WordDocument><w:View>Print</w:View></w:WordDocument>
    <o:OfficeDocumentSettings/></xml><![endif]-->
    <style>@page{size:A4 landscape;margin:1cm}</style></head><body>${head}
    <table style="border-collapse:collapse;width:100%">
      <thead><tr>${["№", "Направление", "Проект / Задача", "Срок", "Статус", "Комментарий / статус"].map(th).join("")}</tr></thead>
      <tbody>${body}</tbody></table></body></html>`;
  const blob = new Blob(["﻿", html], { type: "application/msword" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = `Отчёт по проектам — ${props.companyName} — FY${props.year}.doc`;
  document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}

onMounted(() => { directionsStore.ensureLoaded(); loadConfig(); });
watch(() => [props.year, props.companyCode], loadConfig);
</script>

<template>
  <div class="psr">
    <!-- ── Официальная тройная шапка ── -->
    <table class="psr-lh">
      <tbody>
        <tr class="lh-logos">
          <td class="lh-left"><img :src="minfinLogoUrl" alt="Иқтисодиёт ва молия вазирлиги" class="lh-minfin" /></td>
          <td class="lh-center">
            <div class="lh-ept">
              <svg class="lh-ept-mark" viewBox="0 0 28 28" aria-hidden="true">
                <path d="M5 4.2c0-1 1.1-1.6 1.95-1.06l14.2 9.05a1.25 1.25 0 0 1 0 2.12L6.95 23.4C6.1 23.94 5 23.34 5 22.34V4.2z" fill="#4B4A9A" />
                <circle cx="23.4" cy="20.4" r="2.2" fill="#9C97E0" />
              </svg>
              <div class="lh-ept-t">ЕДИНАЯ ПЛАТФОРМА<br />ТРАНСФОРМАЦИИ</div>
            </div>
          </td>
          <td class="lh-right"><img :src="uzassetsLogoUrl" alt="UzAssets" class="lh-uza" /></td>
        </tr>
        <tr class="lh-titlerow">
          <td colspan="2" class="lh-company">{{ companyName }}</td>
          <td class="lh-sector">{{ sectorName || "—" }} · отчёт по проектам</td>
        </tr>
      </tbody>
    </table>

    <!-- ── Тулбар (вне печати) ── -->
    <div class="psr-toolbar">
      <span class="psr-tb-sub">Реализация мероприятий трансформации · FY {{ year }}</span>
      <span class="psr-tb-sp" />
      <transition name="psr-fade"><span v-if="saving" class="psr-saving">● сохранение</span></transition>
      <button class="psr-btn ghost" @click="resetOverrides" title="Вернуть данные из системы">Сбросить правки</button>
      <button class="psr-btn ghost" @click="exportDoc">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
        Экспорт в Word
      </button>
      <button class="psr-btn" @click="openPrint">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v8H6z"/></svg>
        Печать
      </button>
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

    <!-- ── Таблица (порядок как в work-табе) ── -->
    <div class="psr-table-wrap">
      <UzaSkeleton v-if="loadingCfg" variant="rows" :rows="8" rowHeight="34px" />
      <table v-else class="psr-table">
        <thead>
          <tr>
            <th class="c-num">№</th>
            <th class="c-dir">Направление</th>
            <th class="c-title">Проект / Задача</th>
            <th class="c-srok">Срок</th>
            <th class="c-status">Статус</th>
            <th class="c-com">Комментарий / статус</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id" :class="{ 'is-project': r.kind === 'project', 'is-edited': isEdited(r) }">
            <td class="c-num">{{ r.num }}</td>
            <td class="c-dir">
              <span class="psr-dir-dot" :style="{ background: dirColor(r.dirCode) }" />
              <span class="psr-dir-l" :style="{ color: dirColor(r.dirCode) }">{{ dirLabel(r.dirCode) }}</span>
            </td>
            <td class="c-title"><span class="psr-title-txt" :class="{ proj: r.kind === 'project' }">{{ r.title }}</span></td>
            <td class="c-srok"><input class="psr-in" :value="effSrok(r)" @change="setOverride(r.id, 'srok', ($event.target as HTMLInputElement).value)" /></td>
            <td class="c-status">
              <span class="psr-pill" :style="{ color: statusColor(effStatus(r)), background: statusColor(effStatus(r)) + '1a' }">
                {{ statusLabel(effStatus(r)) }}
                <select class="psr-pill-sel" :value="effStatus(r)" @change="setOverride(r.id, 'status', ($event.target as HTMLSelectElement).value)">
                  <option v-for="o in STATUS_OPTIONS" :key="o" :value="o">{{ statusLabel(o) }}</option>
                </select>
              </span>
            </td>
            <td class="c-com">
              <div class="psr-com">
                <span v-if="r.health" class="psr-health" :title="HEALTH_META[r.health].label" :style="{ background: HEALTH_META[r.health].color }" />
                <textarea class="psr-ta" :value="effComment(r)" rows="1" placeholder="—"
                          @focus="autoGrow" @input="autoGrow"
                          @change="setOverride(r.id, 'comment', ($event.target as HTMLTextAreaElement).value)"></textarea>
              </div>
            </td>
          </tr>
          <tr v-if="!rows.length"><td colspan="6" class="psr-empty">Нет проектов и задач за {{ year }} год.</td></tr>
        </tbody>
      </table>
    </div>

    <!-- ── ПЕЧАТНЫЙ ОВЕРЛЕЙ (альбомный, фирменная палитра) ── -->
    <Teleport to="body">
      <div v-if="printOpen" class="pdoc-overlay">
        <div class="pdoc-toolbar">
          <span class="pdt-title">Предпросмотр печати · альбомная ориентация</span>
          <span class="pdt-sp" />
          <button class="pdt-btn" @click="doPrint">Печать</button>
          <button class="pdt-btn ghost" @click="closePrint">Закрыть</button>
        </div>
        <div class="pdoc-scroll">
          <div class="pdoc-sheet psr-print">
            <table class="psr-lh">
              <tbody>
                <tr class="lh-logos">
                  <td class="lh-left"><img :src="minfinLogoUrl" alt="" class="lh-minfin" /></td>
                  <td class="lh-center">
                    <div class="lh-ept">
                      <svg class="lh-ept-mark" viewBox="0 0 28 28"><path d="M5 4.2c0-1 1.1-1.6 1.95-1.06l14.2 9.05a1.25 1.25 0 0 1 0 2.12L6.95 23.4C6.1 23.94 5 23.34 5 22.34V4.2z" fill="#4B4A9A" /><circle cx="23.4" cy="20.4" r="2.2" fill="#9C97E0" /></svg>
                      <div class="lh-ept-t">ЕДИНАЯ ПЛАТФОРМА<br />ТРАНСФОРМАЦИИ</div>
                    </div>
                  </td>
                  <td class="lh-right"><img :src="uzassetsLogoUrl" alt="" class="lh-uza" /></td>
                </tr>
                <tr class="lh-titlerow">
                  <td colspan="2" class="lh-company">{{ companyName }}</td>
                  <td class="lh-sector">{{ sectorName || "—" }} · отчёт по проектам</td>
                </tr>
              </tbody>
            </table>
            <div class="psr-print-sum">
              <b>Проекты:</b> {{ summary.projects.total }} — завершено {{ summary.projects.done }} ({{ pct(summary.projects.done, summary.projects.total) }}%) · в процессе {{ summary.projects.inprogress }} ({{ pct(summary.projects.inprogress, summary.projects.total) }}%) · не начато {{ summary.projects.notstarted }} ({{ pct(summary.projects.notstarted, summary.projects.total) }}%)<br />
              <b>Задачи:</b> {{ summary.tasks.total }} — завершено {{ summary.tasks.done }} ({{ pct(summary.tasks.done, summary.tasks.total) }}%) · в процессе {{ summary.tasks.inprogress }} ({{ pct(summary.tasks.inprogress, summary.tasks.total) }}%) · не начато {{ summary.tasks.notstarted }} ({{ pct(summary.tasks.notstarted, summary.tasks.total) }}%)
              <span class="psr-print-stamp">по состоянию на {{ stampToday() }}</span>
            </div>
            <table class="psr-print-tbl">
              <thead>
                <tr><th>№</th><th>Направление</th><th>Проект / Задача</th><th>Срок</th><th>Статус</th><th>Комментарий / статус</th></tr>
              </thead>
              <tbody>
                <tr v-for="r in rows" :key="r.id" :class="{ proj: r.kind === 'project' }">
                  <td class="pn">{{ r.num }}</td>
                  <td class="pd">{{ dirLabel(r.dirCode) }}</td>
                  <td :class="{ pt: r.kind === 'project' }">{{ r.title }}</td>
                  <td class="ps">{{ effSrok(r) }}</td>
                  <td class="pst">
                    <span class="psr-print-pill" :style="{ background: printStatusStyle(effStatus(r)).bg, color: printStatusStyle(effStatus(r)).color, fontWeight: printStatusStyle(effStatus(r)).weight }">{{ statusLabel(effStatus(r)) }}</span>
                  </td>
                  <td class="pc">{{ effComment(r) }}</td>
                </tr>
              </tbody>
            </table>
            <div class="psr-print-foot">Единая платформа трансформации · UzAssets — сформировано {{ stampToday() }}</div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.psr { display: flex; flex-direction: column; gap: 14px; }

/* ── Официальная тройная шапка ── */
.psr-lh { width: 100%; border-collapse: collapse; border-bottom: 2px solid #4B4A9A; table-layout: fixed; }
.psr-lh td { vertical-align: middle; padding: 0; }
.lh-logos td { padding-bottom: 10px; }
.lh-left { width: 33%; text-align: left; }
.lh-center { width: 34%; text-align: center; }
.lh-right { width: 33%; text-align: right; }
.lh-minfin { height: 44px; width: auto; object-fit: contain; }
.lh-uza { height: 28px; width: auto; object-fit: contain; }
.lh-ept { display: inline-flex; align-items: center; gap: 8px; }
.lh-ept-mark { width: 22px; height: 22px; flex-shrink: 0; }
.lh-ept-t { font-size: 11px; font-weight: 800; letter-spacing: .12em; color: #4B4A9A; text-align: left; line-height: 1.18; }
.lh-titlerow td { padding-top: 9px; padding-bottom: 7px; }
.lh-company { font-size: 19px; font-weight: 800; color: var(--t1, #14171F); letter-spacing: -.01em; }
.lh-sector { text-align: right; font-size: 11px; font-weight: 600; color: #8A8C99; text-transform: uppercase; letter-spacing: .04em; white-space: nowrap; }

/* ── Тулбар ── */
.psr-toolbar { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
.psr-tb-sub { font-size: 11.5px; color: var(--t3, #64748B); }
.psr-tb-sp { flex: 1; }
.psr-saving { font-size: 11px; color: #7F77DD; }
.psr-btn { display: inline-flex; align-items: center; gap: 7px; background: linear-gradient(135deg, #8B7FFF, #6C5CE7); color: #fff; border: none; font: 600 12px inherit; padding: 8px 14px; border-radius: 10px; cursor: pointer; box-shadow: 0 4px 14px rgba(108,92,231,.28); transition: transform .15s; }
.psr-btn:hover { transform: translateY(-1px); }
.psr-btn.ghost { background: transparent; color: var(--t3, #64748B); border: 1px solid rgba(99,102,180,.22); box-shadow: none; }
.psr-btn.ghost:hover { color: #6C5CE7; border-color: #6C5CE7; transform: none; }
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

/* ── Таблица (экран) ── */
.psr-table-wrap { overflow-x: auto; border: 1px solid rgba(99,102,180,.14); border-radius: 14px; background: #fff; box-shadow: 0 4px 14px rgba(15,23,60,.05); }
.psr-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.psr-table thead th { background: #1e2a4a; color: #fff; font-size: 10px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; text-align: left; padding: 10px 12px; position: sticky; top: 0; z-index: 2; white-space: nowrap; }
.psr-table td { border-bottom: 1px solid rgba(15,23,60,.05); padding: 5px 12px; vertical-align: top; color: var(--t1, #1e2a4a); }
.psr-table tr.is-project { background: rgba(127,119,221,.05); }
.psr-table tr.is-project:hover, .psr-table tbody tr:hover { background: rgba(127,119,221,.09); }
.psr-table tr.is-edited td.c-num { box-shadow: inset 3px 0 0 #EF9F27; }
.c-num { width: 46px; font-variant-numeric: tabular-nums; color: var(--t3, #8A90A6); font-size: 11px; }
.c-dir { width: 168px; }
.psr-dir-dot { display: inline-block; width: 7px; height: 7px; border-radius: 2px; vertical-align: middle; margin-right: 6px; }
.psr-dir-l { font-size: 11px; font-weight: 500; }
.c-title { min-width: 260px; }
.psr-title-txt { line-height: 1.4; }
.psr-title-txt.proj { font-weight: 600; }
.c-srok { width: 108px; }
.c-status { width: 156px; }
.c-com { min-width: 300px; }
.psr-in { width: 100%; border: 1px solid transparent; background: transparent; font: inherit; color: inherit; border-radius: 6px; padding: 3px 6px; }
.psr-in:hover { background: rgba(127,119,221,.06); }
.psr-in:focus { outline: none; border-color: #7F77DD; background: #fff; }
.psr-pill { position: relative; display: inline-flex; align-items: center; font-size: 11px; font-weight: 600; padding: 3px 10px; border-radius: 999px; white-space: nowrap; cursor: pointer; }
.psr-pill::after { content: "▾"; font-size: 8px; margin-left: 5px; opacity: .55; }
.psr-pill-sel { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; }
.psr-com { display: flex; align-items: flex-start; gap: 7px; }
.psr-health { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; margin-top: 7px; box-shadow: 0 0 0 2px rgba(255,255,255,.7); }
.psr-ta { width: 100%; border: 1px solid transparent; background: transparent; font: inherit; color: inherit; border-radius: 6px; padding: 3px 6px; resize: none; min-height: 26px; line-height: 1.45; font-size: 11.5px; overflow: hidden; }
.psr-ta:hover { background: rgba(127,119,221,.06); }
.psr-ta:focus { outline: none; border-color: #7F77DD; background: #fff; }
.psr-empty { text-align: center; padding: 30px; color: var(--t3, #64748B); font-style: italic; }

/* ── Печатный оверлей ── */
.pdoc-overlay { position: fixed; inset: 0; z-index: 9000; background: #5b5e72; display: flex; flex-direction: column; }
.pdoc-toolbar { display: flex; align-items: center; gap: 10px; padding: 10px 16px; background: #1e2a4a; color: #fff; }
.pdt-title { font-size: 12.5px; font-weight: 600; }
.pdt-sp { flex: 1; }
.pdt-btn { background: #7F77DD; color: #fff; border: none; font: 600 12px inherit; padding: 7px 16px; border-radius: 8px; cursor: pointer; }
.pdt-btn.ghost { background: transparent; border: 1px solid rgba(255,255,255,.3); }
.pdoc-scroll { flex: 1; overflow: auto; padding: 22px; display: flex; justify-content: center; }
.pdoc-sheet.psr-print {
  background: #fff; color: #14171F; width: 297mm; max-width: 100%; min-height: 210mm;
  padding: 9mm 10mm; box-sizing: border-box; box-shadow: 0 10px 40px rgba(0,0,0,.3);
  font-family: var(--font, "Geist Variable", system-ui, sans-serif); font-size: 11px; align-self: flex-start;
}
.psr-print-sum { display: block; margin: 10px 0 12px; font-size: 11px; color: #3A3D48; line-height: 1.5; }
.psr-print-stamp { display: block; color: #8A8C99; font-size: 10px; margin-top: 3px; }
.psr-print-tbl { width: 100%; border-collapse: collapse; }
.psr-print-tbl th { background: #1e2a4a; color: #fff; font-size: 9.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; text-align: left; padding: 6px 7px; border: 1px solid #2a375a; }
.psr-print-tbl td { border: 1px solid #d7d9e0; padding: 4px 7px; vertical-align: top; font-size: 10.5px; line-height: 1.35; }
.psr-print-tbl tr.proj { background: #f3f2fb; }
.psr-print-tbl tr.proj .pt { font-weight: 700; }
.psr-print-tbl .pn { width: 34px; font-variant-numeric: tabular-nums; color: #6A6D7C; }
.psr-print-tbl .pd { width: 132px; color: #5F6270; }
.psr-print-tbl .ps { width: 78px; white-space: nowrap; }
.psr-print-tbl .pst { width: 118px; white-space: nowrap; }
.psr-print-pill { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 9.5px; letter-spacing: .01em; }
.psr-print-tbl .pc { color: #3A3D48; }
.psr-print-foot { margin-top: 12px; padding-top: 7px; border-top: 1px solid #E6E7EE; font-size: 9.5px; color: #A1A3AE; text-align: center; }

@media print {
  .pdoc-sheet.psr-print { width: auto; min-height: 0; padding: 0; box-shadow: none; font-size: 10px; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .psr-print-tbl tr { break-inside: avoid; page-break-inside: avoid; }
  .psr-print-tbl thead { display: table-header-group; }
}
@media (prefers-reduced-motion: reduce) { .psr-seg-p, .psr-btn { transition: none; } }
</style>
