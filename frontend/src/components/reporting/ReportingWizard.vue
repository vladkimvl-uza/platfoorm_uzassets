<script setup lang="ts">
/**
 * ReportingWizard — мастер управленческого отчёта по компании на A4 (альбом).
 *
 * Поток: пользователь добавляет лист на КАЖДОЕ направление, отмечает ключевые
 * проекты, словами описывает «Текущий статус» и «Предложения по дальнейшим шагам».
 * Печать — фирменная шапка (ЕПТ + эмблема Минфина), как в Сводном обзоре, ниже —
 * полоса ключевых проектов и две колонки «Статус | Шаги».
 *
 * Хранения нет (печать-онли). Всё гибкое: textarea авто-растут, на печати текст
 * переносится (pre-wrap, break-word) и при необходимости перетекает на доп. лист —
 * ничего не обрезается. Глобальное скрытие #app на печати гейтится классом
 * body.rw-printing — чтобы не ломать другие печати в приложении.
 */
import { ref, computed, onMounted, nextTick } from "vue";
import minfinLogoUrl from "@/assets/minfin-logo.png";
import uzassetsLogoUrl from "@/assets/uzassets-logo-wide.png";
import { directionsApi, type DirectionBrief } from "@/api/directions";
import type { ProjectBrief } from "@/api/projects";

const props = defineProps<{
  companyName: string;
  sectorName?: string | null;
  year?: number | null;
  projects: ProjectBrief[];
}>();

const directions = ref<DirectionBrief[]>([]);
onMounted(async () => {
  try { directions.value = await directionsApi.list(); } catch { /* каталог опционален */ }
});

interface ReportPage {
  id: number;
  directionName: string;    // имя направления (как в ProjectBrief.direction)
  keyProjectIds: string[];  // id выбранных ключевых проектов
  status: string;
  nextSteps: string;
}
let _seq = 1;
function blankPage(): ReportPage {
  return { id: _seq++, directionName: "", keyProjectIds: [], status: "", nextSteps: "" };
}
const pages = ref<ReportPage[]>([blankPage()]);
function addPage() { pages.value.push(blankPage()); }
function removePage(id: number) {
  pages.value = pages.value.filter(p => p.id !== id);
  if (!pages.value.length) pages.value = [blankPage()];
}

function projectsForDir(name: string): ProjectBrief[] {
  if (!name) return [];
  return props.projects.filter(p => (p.direction || "") === name);
}
function toggleProject(page: ReportPage, pid: string) {
  const i = page.keyProjectIds.indexOf(pid);
  if (i >= 0) page.keyProjectIds.splice(i, 1); else page.keyProjectIds.push(pid);
}
function selectedProjects(page: ReportPage): ProjectBrief[] {
  const set = new Set(page.keyProjectIds);
  // сохраняем порядок выбора
  return page.keyProjectIds.map(id => props.projects.find(p => p.id === id)).filter(Boolean) as ProjectBrief[];
}

function fmtDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleDateString("ru-RU", { day: "2-digit", month: "short", year: "2-digit" });
}
const todayStr = new Date().toLocaleDateString("ru-RU");
const fy = computed(() => props.year || new Date().getFullYear());

// печатаем только содержательные листы
const printablePages = computed(() =>
  pages.value.filter(p => p.directionName || p.status.trim() || p.nextSteps.trim() || p.keyProjectIds.length)
);

function autoGrow(e: Event) {
  const el = e.target as HTMLTextAreaElement;
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}

function printReport() {
  if (!printablePages.value.length) return;
  document.body.classList.add("rw-printing");
  const cleanup = () => {
    document.body.classList.remove("rw-printing");
    window.removeEventListener("afterprint", cleanup);
  };
  window.addEventListener("afterprint", cleanup);
  nextTick(() => window.print());
}
</script>

<template>
  <div class="rw">
    <div class="rw-head">
      <div class="rw-head-t">
        <h2 class="rw-title">Мастер отчёта</h2>
        <p class="rw-desc">Соберите управленческий отчёт по компании: одно направление — один лист A4. Заполните и распечатайте с фирменной шапкой.</p>
      </div>
      <div class="rw-head-actions">
        <button class="rw-btn" @click="addPage">+ Направление</button>
        <button class="rw-btn rw-btn-print" :disabled="!printablePages.length" @click="printReport">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
          Печать отчёта<template v-if="printablePages.length"> ({{ printablePages.length }})</template>
        </button>
      </div>
    </div>

    <TransitionGroup tag="div" name="rwpage" class="rw-pages" appear>
      <div v-for="(page, i) in pages" :key="page.id" class="rw-pg" :style="{ '--d': i * 50 + 'ms' }">
        <div class="rw-pg-top">
          <span class="rw-pg-n">Лист {{ i + 1 }}</span>
          <select v-model="page.directionName" class="rw-select">
            <option value="" disabled>Выберите направление…</option>
            <option v-for="d in directions" :key="d.id" :value="d.label">{{ d.label }}</option>
          </select>
          <button v-if="pages.length > 1" class="rw-rm" @click="removePage(page.id)">Удалить лист</button>
        </div>

        <div v-if="page.directionName" class="rw-field">
          <label class="rw-label">Ключевые проекты</label>
          <div class="rw-picks">
            <button v-for="p in projectsForDir(page.directionName)" :key="p.id"
              class="rw-pick" :class="{ on: page.keyProjectIds.includes(p.id) }"
              @click="toggleProject(page, p.id)">
              <span class="rw-pick-ck"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg></span>
              <span class="rw-pick-t">{{ p.title }}</span>
              <span class="rw-pick-d">{{ fmtDate(p.due_date) }}</span>
            </button>
            <span v-if="!projectsForDir(page.directionName).length" class="rw-empty">В этом направлении пока нет проектов</span>
          </div>
        </div>

        <div class="rw-two">
          <div class="rw-field">
            <label class="rw-label">Текущий статус</label>
            <textarea v-model="page.status" class="rw-ta" rows="5" @input="autoGrow"
              placeholder="Опишите словами текущее положение по направлению…"></textarea>
          </div>
          <div class="rw-field">
            <label class="rw-label">Предложения по дальнейшим шагам</label>
            <textarea v-model="page.nextSteps" class="rw-ta" rows="5" @input="autoGrow"
              placeholder="Опишите предлагаемые следующие шаги…"></textarea>
          </div>
        </div>
      </div>
    </TransitionGroup>

    <!-- ── Печатный портал: один лист A4 (альбом) на направление ── -->
    <Teleport to="body">
      <div class="rw-print-portal">
        <section v-for="page in printablePages" :key="'rwpp_' + page.id" class="rw-pp-page">
          <div class="rw-pp-head">
            <div class="rw-pp-toprow">
              <img :src="minfinLogoUrl" class="rw-pp-imv-img" alt="Иқтисодиёт ва молия вазирлиги" />
              <div class="rw-pp-brand">
                <svg class="rw-pp-logo" viewBox="0 0 240 220" width="26" height="24" aria-hidden="true">
                  <path d="M 80 30 L 210 110 L 80 190 L 115 110 Z" fill="#534AB7" />
                  <g fill="#7F77DD"><rect x="56" y="50" width="8" height="8" /><rect x="42" y="64" width="7" height="7" /><rect x="50" y="96" width="7" height="7" /><rect x="36" y="116" width="7" height="7" /><rect x="48" y="150" width="7" height="7" /></g>
                </svg>
                <span class="rw-pp-brand-txt">Единая платформа<br />трансформации</span>
              </div>
              <img :src="uzassetsLogoUrl" class="rw-pp-uza-img" alt="UzAssets" />
            </div>
            <div class="rw-pp-titlerow">
              <h2>{{ companyName }}</h2>
              <span class="rw-pp-doc">{{ page.directionName || '—' }} · отчёт о ходе</span>
            </div>
            <div class="rw-pp-sub">FY {{ fy }}<template v-if="sectorName"> · {{ sectorName }}</template> · на {{ todayStr }}</div>
          </div>

          <div v-if="selectedProjects(page).length" class="rw-pp-keys">
            <span class="rw-pp-keys-l">Ключевые проекты</span>
            <span v-for="p in selectedProjects(page)" :key="'k_' + p.id" class="rw-pp-key">{{ p.title }}<span class="rw-pp-key-d"> — {{ fmtDate(p.due_date) }}</span></span>
          </div>

          <div class="rw-pp-cols">
            <div class="rw-pp-col">
              <div class="rw-pp-col-h">Текущий статус</div>
              <div class="rw-pp-col-b">{{ page.status || '—' }}</div>
            </div>
            <div class="rw-pp-col">
              <div class="rw-pp-col-h">Предложения по дальнейшим шагам</div>
              <div class="rw-pp-col-b">{{ page.nextSteps || '—' }}</div>
            </div>
          </div>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.rw { animation: rwIn .35s var(--ease-out, cubic-bezier(.16,1,.3,1)) both; }
.rw-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 18px; }
.rw-title { font-size: 17px; font-weight: 600; color: var(--t1, #1e2a4a); margin: 0; letter-spacing: -.01em; }
.rw-desc { font-size: 12.5px; color: var(--t3, #94a3b8); margin: 4px 0 0; max-width: 560px; line-height: 1.45; }
.rw-head-actions { display: flex; gap: 8px; flex-shrink: 0; }
.rw-btn { display: inline-flex; align-items: center; gap: 7px; height: 34px; padding: 0 14px; border: 1px solid var(--border, rgba(99,102,180,.18)); border-radius: 9px; background: var(--bg1, #fff); color: var(--t2, #475569); font-size: 12.5px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all .14s; }
.rw-btn:hover { border-color: var(--p, #7f77dd); color: var(--p-deep, #534ab7); }
.rw-btn-print { background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; border-color: transparent; box-shadow: 0 2px 8px rgba(127,119,221,.28); }
.rw-btn-print:hover { color: #fff; transform: translateY(-1px); }
.rw-btn-print:disabled { opacity: .5; cursor: default; transform: none; box-shadow: none; }

.rw-pages { display: flex; flex-direction: column; gap: 14px; position: relative; }
.rw-pg { position: relative; overflow: hidden; border: 1px solid var(--border, rgba(99,102,180,.14)); border-radius: 14px; background: var(--bg1, #fff); padding: 16px 18px; box-shadow: 0 1px 3px rgba(15,23,60,.03); transition: box-shadow .22s, border-color .22s, transform .22s; }
.rw-pg::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, #7f77dd, #6b62cc); transform: scaleX(0); transform-origin: left; transition: transform .3s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.rw-pg:hover { box-shadow: 0 6px 20px -8px rgba(15,23,60,.12); }
.rw-pg:focus-within { box-shadow: 0 10px 30px -10px rgba(127,119,221,.3); border-color: rgba(127,119,221,.4); }
.rw-pg:focus-within::before { transform: scaleX(1); }
/* добавление / удаление / перестановка листов — плавно */
.rwpage-enter-active { transition: all .42s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.rwpage-leave-active { transition: all .3s cubic-bezier(.4,0,1,1); position: absolute; left: 0; right: 0; }
.rwpage-enter-from { opacity: 0; transform: translateY(-14px) scale(.98); }
.rwpage-leave-to { opacity: 0; transform: translateX(-18px) scale(.97); }
.rwpage-move { transition: transform .42s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.rw-pg-top { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.rw-pg-n { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94a3b8); background: rgba(127,119,221,.1); border-radius: 7px; padding: 3px 9px; flex-shrink: 0; }
.rw-select { flex: 1; min-width: 220px; height: 36px; padding: 0 12px; border: 1px solid var(--border, rgba(99,102,180,.2)); border-radius: 9px; background: var(--bg1, #fff); font-size: 13px; font-weight: 500; color: var(--t1, #1e2a4a); font-family: inherit; cursor: pointer; }
.rw-rm { height: 32px; padding: 0 12px; border: 1px solid var(--border, rgba(99,102,180,.18)); border-radius: 8px; background: var(--bg1, #fff); color: var(--t3, #94a3b8); font-size: 12px; cursor: pointer; font-family: inherit; flex-shrink: 0; transition: all .14s; }
.rw-rm:hover { border-color: #E24B4A; color: #E24B4A; }

.rw-field { margin-top: 14px; }
.rw-label { display: block; font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: var(--p-deep, #534ab7); margin-bottom: 7px; }
.rw-picks { display: flex; flex-wrap: wrap; gap: 7px; }
.rw-pick { display: inline-flex; align-items: center; gap: 8px; max-width: 100%; padding: 6px 11px; border: 1px solid var(--border, rgba(99,102,180,.2)); border-radius: 9px; background: var(--bg1, #fff); cursor: pointer; font-family: inherit; transition: all .14s; text-align: left; }
.rw-pick:hover { border-color: var(--p, #7f77dd); }
.rw-pick.on { background: rgba(127,119,221,.1); border-color: var(--p, #7f77dd); }
.rw-pick:active { transform: scale(.96); }
.rw-pick-ck { width: 0; height: 15px; overflow: hidden; display: inline-flex; align-items: center; justify-content: center; color: var(--p-deep, #534ab7); transition: width .22s var(--ease-out, cubic-bezier(.16,1,.3,1)); flex-shrink: 0; }
.rw-pick-ck svg { width: 13px; height: 13px; transform: scale(0); transition: transform .28s var(--bounce, cubic-bezier(.34,1.56,.64,1)); }
.rw-pick.on .rw-pick-ck { width: 16px; }
.rw-pick.on .rw-pick-ck svg { transform: scale(1); }
.rw-pick-t { font-size: 12.5px; color: var(--t1, #1e2a4a); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 320px; }
.rw-pick.on .rw-pick-t { color: var(--p-deep, #534ab7); }
.rw-pick-d { font-size: 10.5px; color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; flex-shrink: 0; }
.rw-empty { font-size: 12px; color: var(--t3, #94a3b8); padding: 4px 2px; }

.rw-two { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 760px) { .rw-two { grid-template-columns: 1fr; } }
.rw-ta { width: 100%; min-height: 96px; padding: 11px 13px; border: 1px solid var(--border, rgba(99,102,180,.2)); border-radius: 10px; background: var(--bg2, #fafafc); font-size: 13px; line-height: 1.5; color: var(--t1, #1e2a4a); font-family: inherit; resize: vertical; box-sizing: border-box; transition: border-color .14s, background .14s; }
.rw-ta:focus { outline: none; border-color: var(--p, #7f77dd); background: #fff; box-shadow: 0 0 0 3px rgba(127,119,221,.1); }
.rw-ta::placeholder { color: var(--t3, #b4b7c9); }

@keyframes rwIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
</style>

<!-- Глобальные стили печати: фирменный лист A4 (альбом), вне scoped (Teleport в body). -->
<style>
.rw-print-portal { display: none; }

@media print {
  /* скрываем приложение и показываем портал ТОЛЬКО во время печати отчёта */
  body.rw-printing #app { display: none !important; }
  body.rw-printing .rw-print-portal { display: block !important; }

  @page { size: A4 landscape; margin: 0; }

  .rw-print-portal {
    font-family: -apple-system, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    color: #1a1f3c;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  .rw-pp-page { padding: 11mm 13mm; box-sizing: border-box; break-after: page; page-break-after: always; }
  .rw-pp-page:last-child { break-after: auto; page-break-after: auto; }

  /* фирменная шапка — идентична Сводному обзору */
  .rw-pp-head { border-bottom: 1.5pt solid #534AB7; padding-bottom: 9px; margin-bottom: 12px; }
  .rw-pp-toprow { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 9px; }
  .rw-pp-brand { display: flex; align-items: center; gap: 9px; }
  .rw-pp-logo { display: block; flex-shrink: 0; }
  .rw-pp-brand-txt { font-size: 8.5pt; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; color: #534AB7; line-height: 1.25; }
  .rw-pp-imv-img { height: 42px; width: auto; flex-shrink: 0; }
  .rw-pp-uza-img { height: 27px; width: auto; flex-shrink: 0; }
  .rw-pp-titlerow { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
  .rw-pp-head h2 { font-size: 18pt; font-weight: 600; margin: 0; letter-spacing: -.01em; color: #161b33; }
  .rw-pp-doc { font-size: 8.5pt; color: #8A90A8; font-weight: 500; white-space: nowrap; }
  .rw-pp-sub { font-size: 8.5pt; color: #6b7088; margin-top: 4px; font-variant-numeric: tabular-nums; }

  /* полоса ключевых проектов */
  .rw-pp-keys { font-size: 8.5pt; color: #1a1f3c; line-height: 1.55; margin-bottom: 11px; }
  .rw-pp-keys-l { font-weight: 700; color: #534AB7; text-transform: uppercase; font-size: 8pt; letter-spacing: .04em; margin-right: 8px; }
  .rw-pp-key { display: inline; }
  .rw-pp-key:not(:last-child)::after { content: " · "; color: #c9c5e6; }
  .rw-pp-key-d { color: #6b7088; white-space: nowrap; font-variant-numeric: tabular-nums; }

  /* две колонки «Статус | Шаги» — равные, текст гибкий, ничего не обрезается */
  .rw-pp-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; align-items: start; }
  .rw-pp-col-h { font-size: 9pt; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #534AB7; background: rgba(127,119,221,.1); padding: 3px 8px; border-radius: 3px; margin-bottom: 6px; }
  .rw-pp-col-b { font-size: 9.5pt; line-height: 1.5; color: #1a1f3c; white-space: pre-wrap; word-break: break-word; overflow-wrap: anywhere; }
}
</style>
