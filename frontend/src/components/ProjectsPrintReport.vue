<script setup lang="ts">
/**
 * ProjectsPrintReport — печатный документ «сводный обзор» по проектам/задачам
 * компании. Группировка: направление → проект → задачи под ним, справа «ход
 * проекта» (последний статус из status-трекера).
 *
 * Шапка — таблица (министерство · ЕДИНАЯ ПЛАТФОРМА ТРАНСФОРМАЦИИ · UzAssets,
 * ниже название компании и «сектор · сводный обзор»). Компонент презентационный:
 * вся подготовка данных (группы, метки/цвета статусов, последний «ход») — в
 * родителе CompanyWorkspace.vue.
 */
import minfinLogoUrl from "@/assets/minfin-logo.png";
import uzassetsLogoUrl from "@/assets/uzassets-logo-wide.png";
import { HEALTH_META, type StatusUpdate } from "@/api/statusUpdates";
import { companyDisplayName } from "@/utils/displayNames";

interface PReportTask {
  task: any;
  statusLabel: string;
  statusColor: string;
}
interface PReportProject {
  project: any;
  statusLabel: string;
  statusColor: string;
  tasks: PReportTask[];
  status: StatusUpdate | null;
}
interface PReportGroup {
  key: string;
  label: string;
  color: string;
  projects: PReportProject[];
}

const props = defineProps<{
  company: any;
  sectorName: string;
  year: number;
  groups: PReportGroup[];
  totals: { projects: number; tasks: number };
}>();

function companyName(): string {
  return props.company?.name_ru || props.company?.name || companyDisplayName(props.company || {}) || "—";
}

function plural(n: number, one: string, few: string, many: string): string {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return one;
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return few;
  return many;
}

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
}

function stampToday(): string {
  return new Date().toLocaleDateString("ru-RU", { day: "2-digit", month: "long", year: "numeric" });
}

function healthMeta(h: StatusUpdate["health"]): { label: string; color: string } {
  if (h && HEALTH_META[h]) return HEALTH_META[h];
  return { label: "Без оценки", color: "#8A8A8A" };
}

function pct(v: number | null | undefined): number {
  const n = Number(v ?? 0);
  if (isNaN(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}
</script>

<template>
  <div class="pdoc-sheet">
    <!-- ШАПКА (таблица) -->
    <table class="pdoc-head">
      <tbody>
        <tr class="ph-logos">
          <td class="ph-left">
            <img :src="minfinLogoUrl" alt="Иқтисодиёт ва молия вазирлиги" class="ph-minfin" />
          </td>
          <td class="ph-center">
            <div class="ph-ept">
              <svg class="ph-ept-mark" viewBox="0 0 28 28" aria-hidden="true">
                <path d="M5 4.2c0-1 1.1-1.6 1.95-1.06l14.2 9.05a1.25 1.25 0 0 1 0 2.12L6.95 23.4C6.1 23.94 5 23.34 5 22.34V4.2z" fill="#4B4A9A" />
                <circle cx="23.4" cy="20.4" r="2.2" fill="#9C97E0" />
              </svg>
              <div class="ph-ept-text">ЕДИНАЯ ПЛАТФОРМА<br />ТРАНСФОРМАЦИИ</div>
            </div>
          </td>
          <td class="ph-right">
            <img :src="uzassetsLogoUrl" alt="UzAssets" class="ph-uza" />
          </td>
        </tr>
        <tr class="ph-titlerow">
          <td colspan="2" class="ph-company">{{ companyName() }}</td>
          <td class="ph-sector">{{ sectorName || "—" }} · сводный обзор</td>
        </tr>
      </tbody>
    </table>

    <!-- Сводная строка -->
    <div class="pdoc-summary">
      <span class="ps-strong">{{ totals.projects }} {{ plural(totals.projects, "проект", "проекта", "проектов") }}</span>
      <span class="ps-dot">·</span>
      <span>{{ totals.tasks }} {{ plural(totals.tasks, "задача", "задачи", "задач") }}</span>
      <span class="ps-dot">·</span>
      <span>FY {{ year }}</span>
      <span class="ps-spacer" />
      <span class="ps-stamp">по состоянию на {{ stampToday() }}</span>
    </div>

    <!-- ТЕЛО: направление → проекты → задачи + ход -->
    <div v-if="!groups.length" class="pdoc-empty">Нет проектов за FY {{ year }}.</div>

    <section v-for="g in groups" :key="g.key" class="pdoc-dirsec">
      <div class="pdoc-dirhdr" :style="{ '--c': g.color }">
        <span class="pd-bar" />
        <span class="pd-label">{{ g.label }}</span>
        <span class="pd-count">{{ g.projects.length }} {{ plural(g.projects.length, "проект", "проекта", "проектов") }}</span>
      </div>

      <div v-for="(row, i) in g.projects" :key="row.project.id" class="pdoc-proj">
        <!-- Левая колонка: проект + задачи -->
        <div class="pp-main">
          <div class="pp-head">
            <span class="pp-num">{{ i + 1 }}</span>
            <span class="pp-title">{{ row.project.title }}</span>
            <span class="pp-badge" :style="{ color: row.statusColor, borderColor: row.statusColor }">{{ row.statusLabel }}</span>
          </div>

          <div class="pp-progress">
            <div class="pp-bar"><div class="pp-bar-fill" :style="{ width: pct(row.project.progress_percent) + '%' }" /></div>
            <span class="pp-pct">{{ pct(row.project.progress_percent) }}%</span>
            <span class="pp-meta">
              задач {{ row.project.tasks_done ?? 0 }}/{{ row.project.tasks_total ?? row.tasks.length }}
              <template v-if="row.project.due_date"> · срок {{ fmtDate(row.project.due_date) }}</template>
              <template v-if="row.project.assignee_name"> · {{ row.project.assignee_name }}</template>
            </span>
          </div>

          <table v-if="row.tasks.length" class="pp-tasks">
            <tbody>
              <tr v-for="rt in row.tasks" :key="rt.task.id">
                <td class="pt-dot"><span :style="{ background: rt.statusColor }" /></td>
                <td class="pt-title">{{ rt.task.title }}</td>
                <td class="pt-status" :style="{ color: rt.statusColor }">{{ rt.statusLabel }}</td>
                <td class="pt-due">{{ rt.task.due_date ? fmtDate(rt.task.due_date) : "—" }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="pp-notasks">Задач нет</div>
        </div>

        <!-- Правая колонка: ход проекта (последний статус) -->
        <div class="pp-flow">
          <div class="pf-title">Ход проекта</div>
          <template v-if="row.status">
            <div class="pf-health" :style="{ color: healthMeta(row.status.health).color }">
              <span class="pf-hdot" :style="{ background: healthMeta(row.status.health).color }" />
              {{ healthMeta(row.status.health).label }}
            </div>
            <div class="pf-body">{{ row.status.body }}</div>
            <div class="pf-meta">{{ fmtDate(row.status.created_at) }}<template v-if="row.status.author_name"> · {{ row.status.author_name }}</template></div>
          </template>
          <div v-else class="pf-empty">нет записей</div>
        </div>
      </div>
    </section>

    <div class="pdoc-foot">
      Единая платформа трансформации · UzAssets — сформировано {{ stampToday() }}
    </div>
  </div>
</template>

<style scoped>
.pdoc-sheet {
  background: #fff;
  color: #14171F;
  font-family: var(--font, "Geist Variable", system-ui, sans-serif);
  width: 210mm;
  max-width: 100%;
  margin: 0 auto;
  padding: 16mm 14mm;
  box-sizing: border-box;
  font-size: 12px;
  line-height: 1.4;
}

/* ── Шапка-таблица ── */
.pdoc-head {
  width: 100%;
  border-collapse: collapse;
  border-bottom: 2px solid #4B4A9A;
  table-layout: fixed;
}
.pdoc-head td { vertical-align: middle; padding: 0; }
.ph-logos td { padding-bottom: 12px; }
.ph-left { width: 33%; text-align: left; }
.ph-center { width: 34%; text-align: center; }
.ph-right { width: 33%; text-align: right; }
.ph-minfin { height: 46px; width: auto; object-fit: contain; }
.ph-uza { height: 30px; width: auto; object-fit: contain; }

.ph-ept { display: inline-flex; align-items: center; gap: 8px; }
.ph-ept-mark { width: 22px; height: 22px; flex-shrink: 0; }
.ph-ept-text {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
  color: #4B4A9A;
  text-align: left;
  line-height: 1.18;
}

.ph-titlerow td { padding-top: 10px; padding-bottom: 8px; }
.ph-company {
  font-size: 19px;
  font-weight: 800;
  color: #14171F;
  letter-spacing: -0.01em;
}
.ph-sector {
  text-align: right;
  font-size: 11px;
  font-weight: 600;
  color: #8A8C99;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  white-space: nowrap;
}

/* ── Сводная строка ── */
.pdoc-summary {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 10px 0 18px;
  font-size: 12px;
  color: #4A4D5C;
}
.ps-strong { font-weight: 700; color: #14171F; }
.ps-dot { color: #B9BBC6; }
.ps-spacer { flex: 1; }
.ps-stamp { color: #8A8C99; font-size: 11px; }

/* ── Направление ── */
.pdoc-dirsec { margin-bottom: 14px; break-inside: avoid; }
.pdoc-dirhdr {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 0 6px;
  border-bottom: 1px solid #E6E7EE;
  margin-bottom: 8px;
}
.pd-bar { width: 4px; height: 15px; border-radius: 2px; background: var(--c, #8A8A8A); flex-shrink: 0; }
.pd-label {
  font-size: 13px;
  font-weight: 800;
  color: var(--c, #14171F);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.pd-count { font-size: 11px; color: #9698A4; margin-left: auto; }

/* ── Проект (2 колонки: проект+задачи | ход) ── */
.pdoc-proj {
  display: grid;
  grid-template-columns: 1fr 200px;
  gap: 12px;
  padding: 8px 0 10px;
  border-bottom: 1px solid #F0F1F5;
  break-inside: avoid;
  page-break-inside: avoid;
}
.pp-main { min-width: 0; }
.pp-head { display: flex; align-items: baseline; gap: 7px; }
.pp-num {
  font-size: 11px;
  font-weight: 800;
  color: #fff;
  background: #4B4A9A;
  border-radius: 4px;
  min-width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
  flex-shrink: 0;
}
.pp-title { font-size: 13.5px; font-weight: 700; color: #14171F; }
.pp-badge {
  margin-left: auto;
  font-size: 10px;
  font-weight: 700;
  border: 1px solid;
  border-radius: 999px;
  padding: 1px 8px;
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.pp-progress { display: flex; align-items: center; gap: 8px; margin: 5px 0 7px; }
.pp-bar { width: 110px; height: 5px; background: #ECEDF2; border-radius: 4px; overflow: hidden; flex-shrink: 0; }
.pp-bar-fill { height: 5px; background: #4B4A9A; border-radius: 4px; }
.pp-pct { font-size: 11px; font-weight: 700; color: #14171F; min-width: 30px; }
.pp-meta { font-size: 11px; color: #7C7F8C; }

.pp-tasks { width: 100%; border-collapse: collapse; }
.pp-tasks td { padding: 2.5px 6px 2.5px 0; vertical-align: top; font-size: 11.5px; }
.pt-dot { width: 12px; padding-top: 6px !important; }
.pt-dot span { display: inline-block; width: 6px; height: 6px; border-radius: 50%; }
.pt-title { color: #2A2D38; }
.pt-status { width: 92px; font-weight: 600; white-space: nowrap; }
.pt-due { width: 72px; color: #9698A4; text-align: right; white-space: nowrap; }
.pp-notasks { font-size: 11px; color: #A9ABB5; font-style: italic; }

/* ── Ход проекта (правая колонка) ── */
.pp-flow {
  border-left: 1px solid #E6E7EE;
  padding-left: 12px;
  min-width: 0;
}
.pf-title {
  font-size: 9.5px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #A1A3AE;
  margin-bottom: 5px;
}
.pf-health { display: flex; align-items: center; gap: 5px; font-size: 11.5px; font-weight: 700; margin-bottom: 3px; }
.pf-hdot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.pf-body { font-size: 11px; color: #3A3D48; line-height: 1.35; }
.pf-meta { font-size: 10px; color: #A1A3AE; margin-top: 4px; }
.pf-empty { font-size: 11px; color: #BCBEC7; font-style: italic; }

.pdoc-empty { padding: 40px 0; text-align: center; color: #9698A4; }

.pdoc-foot {
  margin-top: 18px;
  padding-top: 8px;
  border-top: 1px solid #E6E7EE;
  font-size: 10px;
  color: #A1A3AE;
  text-align: center;
}

/* ── Печать ── */
@media print {
  .pdoc-sheet {
    width: auto;
    margin: 0;
    padding: 0;
    font-size: 11px;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
  .pdoc-proj { break-inside: avoid; page-break-inside: avoid; }
  .pdoc-dirhdr { break-after: avoid; page-break-after: avoid; }
}
</style>
