<script setup lang="ts">
/**
 * ProjectBuilder.vue — конструктор массового заведения проектов и задач.
 *
 * Автоматизация: мультивыбор компаний (одно заведение → во все), общие
 * настройки (год/направление/дедлайн на всё), вставка списком (строка =
 * задача), вложенные задачи под проектами + отдельные задачи. Один вызов
 * /builder/bulk создаёт всё.
 */
import { ref, computed, onMounted } from "vue";
import { api } from "@/api/client";
import { useToast } from "@/composables/useToast";
import EptLogo from "@/components/EptLogo.vue";

interface Co { id: string; code: string; name: string; }
interface Dir { id: string; code: string; name: string; }
interface BTask { title: string; status: string; priority: string; due_date: string; assignee_email: string; }
interface BProject { title: string; status: string; priority: string; due_date: string; direction_id: string; tasks: BTask[]; }

const toast = useToast();
const companies = ref<Co[]>([]);
const directions = ref<Dir[]>([]);
const selected = ref<Set<string>>(new Set());
const submitting = ref(false);

const common = ref({ portfolio_year: new Date().getFullYear(), direction_id: "", due_date: "" });

const STATUSES = [
  { v: "new", l: "Не начато" }, { v: "init", l: "Инициирование" }, { v: "active", l: "В процессе" },
  { v: "quarterly", l: "Ежеквартально" }, { v: "monthly", l: "Ежемесячно" }, { v: "ongoing", l: "Постоянно" },
];
const PRIOS = [{ v: "high", l: "Высокий" }, { v: "medium", l: "Средний" }, { v: "low", l: "Низкий" }];

const projects = ref<BProject[]>([]);
const standalone = ref<BTask[]>([]);

function newTask(): BTask { return { title: "", status: "new", priority: "medium", due_date: "", assignee_email: "" }; }
function newProject(): BProject { return { title: "", status: "new", priority: "medium", due_date: "", direction_id: "", tasks: [] }; }

function addProject() { projects.value.push(newProject()); }
function rmProject(i: number) { projects.value.splice(i, 1); }
function addTask(p: BProject) { p.tasks.push(newTask()); }
function rmTask(p: BProject, i: number) { p.tasks.splice(i, 1); }
function addStandalone() { standalone.value.push(newTask()); }
function rmStandalone(i: number) { standalone.value.splice(i, 1); }

// вставка списком: каждая непустая строка → задача
const pasteFor = ref<{ kind: "project" | "standalone"; idx: number } | null>(null);
const pasteText = ref("");
function openPaste(kind: "project" | "standalone", idx: number) { pasteFor.value = { kind, idx }; pasteText.value = ""; }
function applyPaste() {
  const lines = pasteText.value.split("\n").map((l) => l.trim()).filter(Boolean);
  if (!lines.length || !pasteFor.value) { pasteFor.value = null; return; }
  const tasks = lines.map((l) => ({ ...newTask(), title: l }));
  if (pasteFor.value.kind === "project") projects.value[pasteFor.value.idx].tasks.push(...tasks);
  else standalone.value.push(...tasks);
  toast.success(`Добавлено задач: ${tasks.length}`);
  pasteFor.value = null;
}

function toggleCo(id: string) { selected.value.has(id) ? selected.value.delete(id) : selected.value.add(id); selected.value = new Set(selected.value); }
function selectAll() { selected.value = new Set(companies.value.map((c) => c.id)); }
function clearCo() { selected.value = new Set(); }

const totalTasks = computed(() => projects.value.reduce((s, p) => s + p.tasks.length, 0) + standalone.value.length);
const totalProjects = computed(() => projects.value.length);
const perCompany = computed(() => `${totalProjects.value} проектов · ${totalTasks.value} задач`);
const canSubmit = computed(() => (totalProjects.value > 0 || totalTasks.value > 0) &&
  projects.value.every((p) => p.title.trim()) && standalone.value.every((t) => t.title.trim()) &&
  projects.value.every((p) => p.tasks.every((t) => t.title.trim())));

async function load() {
  const [c, d] = await Promise.all([api.get("/builder/companies"), api.get("/builder/directions")]);
  companies.value = c.data.items || [];
  directions.value = d.data.items || [];
}
onMounted(load);

async function submit() {
  if (!canSubmit.value) { toast.error("Заполните названия проектов/задач"); return; }
  submitting.value = true;
  try {
    const clean = (t: BTask) => ({ title: t.title, status: t.status, priority: t.priority, due_date: t.due_date || null, assignee_email: t.assignee_email || null });
    const body = {
      company_ids: [...selected.value],
      common: { portfolio_year: common.value.portfolio_year, direction_id: common.value.direction_id || null, due_date: common.value.due_date || null },
      projects: projects.value.map((p) => ({ title: p.title, status: p.status, priority: p.priority, due_date: p.due_date || null, direction_id: p.direction_id || null, tasks: p.tasks.map(clean) })),
      standalone_tasks: standalone.value.map(clean),
    };
    const { data } = await api.post("/builder/bulk", body);
    toast.success(`Создано: ${data.projects_created} проектов · ${data.tasks_created} задач в ${data.companies} компаниях`, 5000);
    projects.value = []; standalone.value = [];
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Ошибка создания");
  } finally { submitting.value = false; }
}
</script>

<template>
  <div class="pb">
    <div class="pb-top">
      <div class="pb-brand">
        <div class="pb-logo"><EptLogo :size="22" /></div>
        <div><div class="pb-eyebrow">МАССОВОЕ ЗАВЕДЕНИЕ</div><div class="pb-tt">Конструктор проектов и задач</div></div>
      </div>
      <button class="pb-create" :disabled="!canSubmit || submitting || !selected.size" @click="submit">
        {{ submitting ? "Создаю…" : `Создать всё → ${selected.size || 0} комп.` }}
      </button>
    </div>

    <div class="pb-page">
      <!-- 1. КОМПАНИИ -->
      <div class="pb-card">
        <div class="pb-card-h">
          <span class="pb-step">1</span><span class="pb-card-t">Компании</span>
          <span class="pb-card-cap">{{ selected.size }} выбрано</span>
          <div class="pb-card-r"><button class="pb-mini" @click="selectAll">Все</button><button class="pb-mini" @click="clearCo">Сброс</button></div>
        </div>
        <div class="pb-cos">
          <button v-for="c in companies" :key="c.id" class="pb-co" :class="{ on: selected.has(c.id) }" @click="toggleCo(c.id)">{{ c.name }}</button>
        </div>
      </div>

      <!-- 2. ОБЩИЕ НАСТРОЙКИ -->
      <div class="pb-card">
        <div class="pb-card-h"><span class="pb-step">2</span><span class="pb-card-t">Общие настройки</span><span class="pb-card-cap">применяются ко всему</span></div>
        <div class="pb-common">
          <div class="pb-fld"><label>Год портфеля</label><input type="number" v-model.number="common.portfolio_year" class="pb-in" /></div>
          <div class="pb-fld"><label>Направление (по умолч.)</label>
            <select v-model="common.direction_id" class="pb-in"><option value="">—</option><option v-for="d in directions" :key="d.id" :value="d.id">{{ d.name }}</option></select>
          </div>
          <div class="pb-fld"><label>Дедлайн (по умолч.)</label><input type="date" v-model="common.due_date" class="pb-in" /></div>
        </div>
      </div>

      <!-- 3. ПРОЕКТЫ -->
      <div class="pb-card">
        <div class="pb-card-h"><span class="pb-step">3</span><span class="pb-card-t">Проекты</span><span class="pb-card-cap">{{ projects.length }}</span>
          <div class="pb-card-r"><button class="pb-add" @click="addProject">＋ Проект</button></div>
        </div>
        <div v-if="!projects.length" class="pb-empty">Проектов нет. Добавьте проект или сразу отдельные задачи ниже.</div>
        <div v-for="(p, pi) in projects" :key="pi" class="pb-proj">
          <div class="pb-proj-head">
            <input v-model="p.title" class="pb-in title" placeholder="Название проекта" />
            <select v-model="p.status" class="pb-in sm"><option v-for="s in STATUSES" :key="s.v" :value="s.v">{{ s.l }}</option></select>
            <select v-model="p.direction_id" class="pb-in sm"><option value="">направление…</option><option v-for="d in directions" :key="d.id" :value="d.id">{{ d.name }}</option></select>
            <input type="date" v-model="p.due_date" class="pb-in sm" />
            <button class="pb-del" @click="rmProject(pi)"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg></button>
          </div>
          <div class="pb-tasks">
            <div v-for="(t, ti) in p.tasks" :key="ti" class="pb-task">
              <span class="pb-task-dot" />
              <input v-model="t.title" class="pb-in" placeholder="Задача" />
              <select v-model="t.status" class="pb-in sm"><option v-for="s in STATUSES" :key="s.v" :value="s.v">{{ s.l }}</option></select>
              <input type="date" v-model="t.due_date" class="pb-in sm" />
              <button class="pb-del" @click="rmTask(p, ti)"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/></svg></button>
            </div>
            <div class="pb-task-actions">
              <button class="pb-add sm" @click="addTask(p)">＋ Задача</button>
              <button class="pb-paste" @click="openPaste('project', pi)">⤓ Вставить списком</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 4. ОТДЕЛЬНЫЕ ЗАДАЧИ -->
      <div class="pb-card">
        <div class="pb-card-h"><span class="pb-step">4</span><span class="pb-card-t">Отдельные задачи</span><span class="pb-card-cap">{{ standalone.length }}</span>
          <div class="pb-card-r"><button class="pb-add" @click="addStandalone">＋ Задача</button><button class="pb-paste" @click="openPaste('standalone', 0)">⤓ Вставить списком</button></div>
        </div>
        <div v-for="(t, ti) in standalone" :key="ti" class="pb-task">
          <span class="pb-task-dot" />
          <input v-model="t.title" class="pb-in" placeholder="Задача" />
          <select v-model="t.status" class="pb-in sm"><option v-for="s in STATUSES" :key="s.v" :value="s.v">{{ s.l }}</option></select>
          <select v-model="t.priority" class="pb-in sm"><option v-for="p in PRIOS" :key="p.v" :value="p.v">{{ p.l }}</option></select>
          <input type="date" v-model="t.due_date" class="pb-in sm" />
          <button class="pb-del" @click="rmStandalone(ti)"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/></svg></button>
        </div>
      </div>

      <div class="pb-summary">
        Итого на <b>{{ selected.size }}</b> компаний: <b>{{ perCompany }}</b> ·
        всего будет создано <b>{{ totalProjects * (selected.size||1) }}</b> проектов и <b>{{ totalTasks * (selected.size||1) }}</b> задач
      </div>
    </div>

    <!-- PASTE -->
    <Teleport to="body">
      <Transition name="pb-modal">
        <div v-if="pasteFor" class="pb-back" @click.self="pasteFor = null">
          <div class="pb-mod">
            <div class="pb-mod-h"><div class="pb-mod-t">Вставить списком</div><button class="pb-x" @click="pasteFor = null"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg></button></div>
            <div class="pb-mod-b">
              <p class="pb-mod-hint">Каждая строка станет отдельной задачей.</p>
              <textarea v-model="pasteText" rows="10" class="pb-area" placeholder="Разработать стратегию&#10;Привлечь консультанта&#10;Провести инвентаризацию&#10;…"></textarea>
            </div>
            <div class="pb-mod-f"><button class="pb-cancel" @click="pasteFor = null">Отмена</button><button class="pb-save" @click="applyPaste">Добавить</button></div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.pb { --p:#7C6FF7; --p-deep:#534AB7; --navy:#0C1230; --navy2:#141C42; --t3:#64748B; --t4:#94A3B8; --bd:#EAEBF2; --line:#F0F1F6; --ease:cubic-bezier(.34,1.2,.64,1); color:#0F172A; }
.pb-top { height: 62px; background: linear-gradient(120deg,var(--navy),var(--navy2) 70%,#1C2550); display: flex; align-items: center; padding: 0 24px; }
.pb-brand { display: flex; align-items: center; gap: 12px; }
.pb-logo { width: 34px; height: 34px; border-radius: 10px; background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.12); display: grid; place-items: center; }
.pb-eyebrow { font-size: 9px; font-weight: 600; letter-spacing: .1em; color: #9A8FFF; }
.pb-tt { color: #fff; font-size: 15px; font-weight: 600; margin-top: 2px; }
.pb-create { margin-left: auto; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; border: none; font: 600 12.5px inherit; padding: 10px 18px; border-radius: 10px; cursor: pointer; box-shadow: 0 4px 16px rgba(108,92,231,.3); }
.pb-create:disabled { opacity: .5; cursor: default; }
.pb-page { padding: 18px 24px 80px; max-width: 1100px; margin: 0 auto; }

.pb-card { background: #fff; border: 1px solid var(--bd); border-radius: 16px; box-shadow: 0 1px 2px rgba(15,23,60,.05),0 12px 32px rgba(15,23,60,.06); margin-bottom: 16px; overflow: hidden; }
.pb-card-h { display: flex; align-items: center; gap: 10px; padding: 14px 18px; border-bottom: 1px solid var(--line); }
.pb-step { width: 22px; height: 22px; border-radius: 7px; background: #F0EEFF; color: var(--p-deep); font-weight: 700; font-size: 12px; display: grid; place-items: center; }
.pb-card-t { font-size: 13.5px; font-weight: 600; color: #1E2A4A; }
.pb-card-cap { font-size: 11px; color: var(--t4); }
.pb-card-r { margin-left: auto; display: flex; gap: 8px; }
.pb-mini { border: 1px solid var(--bd); background: #fff; color: var(--t3); font: 600 11px inherit; padding: 5px 11px; border-radius: 8px; cursor: pointer; }
.pb-add { border: 1px solid rgba(124,111,247,.3); background: rgba(124,111,247,.06); color: var(--p-deep); font: 600 11.5px inherit; padding: 6px 12px; border-radius: 8px; cursor: pointer; }
.pb-add.sm { font-size: 11px; padding: 5px 10px; }
.pb-paste { border: 1px solid var(--bd); background: #fff; color: var(--t3); font: 600 11.5px inherit; padding: 6px 12px; border-radius: 8px; cursor: pointer; }

.pb-cos { display: flex; flex-wrap: wrap; gap: 7px; padding: 16px 18px; }
.pb-co { border: 1px solid var(--bd); background: #fff; color: #475569; font: 500 12px inherit; padding: 7px 13px; border-radius: 9px; cursor: pointer; transition: all .12s; }
.pb-co.on { background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; border-color: transparent; }

.pb-common { display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; padding: 16px 18px; }
.pb-fld { display: flex; flex-direction: column; gap: 5px; } .pb-fld label { font-size: 11px; color: var(--t3); font-weight: 500; }
.pb-in { border: 1px solid var(--bd); border-radius: 9px; padding: 8px 11px; font-size: 12.5px; font-family: inherit; color: #1E2A4A; outline: none; background: #fff; }
.pb-in:focus { border-color: var(--p); box-shadow: 0 0 0 3px rgba(124,111,247,.12); }
.pb-in.sm { padding: 7px 9px; font-size: 12px; flex-shrink: 0; } .pb-in.title { flex: 1; font-weight: 500; }

.pb-empty { padding: 20px; text-align: center; color: var(--t4); font-size: 12.5px; }
.pb-proj { border-bottom: 1px solid var(--line); padding: 14px 18px; }
.pb-proj-head { display: flex; gap: 8px; align-items: center; }
.pb-tasks { margin: 10px 0 0 22px; padding-left: 14px; border-left: 2px solid var(--line); }
.pb-task { display: flex; gap: 8px; align-items: center; margin-bottom: 7px; }
.pb-task .pb-in:not(.sm) { flex: 1; }
.pb-task-dot { width: 6px; height: 6px; border-radius: 50%; background: #C7C9D1; flex-shrink: 0; }
.pb-task-actions { display: flex; gap: 8px; margin-top: 4px; }
.pb-del { border: 0; background: transparent; color: var(--t4); cursor: pointer; padding: 5px; border-radius: 7px; flex-shrink: 0; }
.pb-del:hover { color: #E24B4A; background: #FCE7E7; }
.pb-summary { margin-top: 4px; padding: 14px 18px; background: rgba(124,111,247,.05); border: 1px solid rgba(124,111,247,.16); border-radius: 12px; font-size: 12.5px; color: var(--t3); }
.pb-summary b { color: #1E2A4A; }

.pb-back { position: fixed; inset: 0; background: rgba(15,18,40,.5); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); z-index: 9999; display: grid; place-items: center; padding: 24px; }
.pb-mod { width: min(520px,100%); background: #fff; border-radius: 18px; box-shadow: 0 24px 64px rgba(15,23,60,.22); overflow: hidden; }
.pb-mod-h { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--line); }
.pb-mod-t { font-size: 14px; font-weight: 600; color: #1E2A4A; }
.pb-x { border: 0; background: rgba(15,23,60,.04); cursor: pointer; color: #64748B; width: 30px; height: 30px; border-radius: 8px; display: grid; place-items: center; }
.pb-mod-b { padding: 16px 20px; } .pb-mod-hint { font-size: 12px; color: var(--t3); margin: 0 0 10px; }
.pb-area { width: 100%; border: 1px solid var(--bd); border-radius: 10px; padding: 11px; font: 13px inherit; outline: none; resize: vertical; }
.pb-area:focus { border-color: var(--p); }
.pb-mod-f { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 20px; border-top: 1px solid var(--line); background: #FAFAFD; }
.pb-cancel { border: 1px solid var(--bd); background: #fff; color: var(--t3); font: 600 12.5px inherit; padding: 9px 18px; border-radius: 10px; cursor: pointer; }
.pb-save { border: 0; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; font: 600 12.5px inherit; padding: 9px 22px; border-radius: 10px; cursor: pointer; }
.pb-modal-enter-active,.pb-modal-leave-active { transition: opacity .2s; } .pb-modal-enter-from,.pb-modal-leave-to { opacity: 0; }

@media (max-width: 760px) { .pb-common { grid-template-columns: 1fr; } }
</style>
