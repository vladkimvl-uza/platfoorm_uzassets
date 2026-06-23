<script setup lang="ts">
/**
 * MatrixEditor — ручная настройка квартальной матрицы «Сводного обзора» по
 * компании+году: выбор проектов (вкл/выкл), переопределение названия/даты/квартала
 * и свои пункты. Сохраняется в БД (overview-matrix), применяется в матрице/печати.
 */
import { computed, onMounted, reactive, ref } from "vue";
import ModalShell from "@/components/ModalShell.vue";
import { useToast } from "@/composables/useToast";
import {
  overviewMatrixApi,
  type MatrixConfig,
  type MatrixCustomItem,
} from "@/api/overviewMatrix";

interface Proj {
  id: string;
  title: string;
  due_date: string | null;
  direction_id?: string | null;
  direction?: string | null;
}

const props = defineProps<{
  companyId: string;
  companyName: string;
  year: number;
  projects: Proj[];
  directions: Array<{ id: string; name: string }>;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "saved", companyId: string, config: MatrixConfig): void;
}>();

const toast = useToast();
const loading = ref(true);
const saving = ref(false);

const QOPTS: { v: number | null; l: string }[] = [
  { v: null, l: "авто" },
  { v: 0, l: "Q1" },
  { v: 1, l: "Q2" },
  { v: 2, l: "Q3" },
  { v: 3, l: "Q4" },
];
// Конец-квартал (Гант-растяжка): «— один» = один квартал; иначе тянем до Qn.
const QEND_OPTS: { v: number | null; l: string }[] = [
  { v: null, l: "— один" },
  { v: 0, l: "до Q1" },
  { v: 1, l: "до Q2" },
  { v: 2, l: "до Q3" },
  { v: 3, l: "до Q4" },
];

// Рабочее состояние
const hidden = reactive(new Set<string>());
interface OvState { title: string; due_date: string; quarter: number | null; quarter_end: number | null }
const ov = reactive<Record<string, OvState>>({});
const custom = ref<MatrixCustomItem[]>([]);
let customSeq = 0;

function dstr(d: string | null | undefined): string {
  return (d || "").slice(0, 10);
}

function ensureOv(p: Proj): OvState {
  if (!ov[p.id]) ov[p.id] = { title: "", due_date: dstr(p.due_date), quarter: null, quarter_end: null };
  return ov[p.id];
}

const groups = computed(() => {
  const order = new Map(props.directions.map((d, i) => [d.id, i]));
  const map = new Map<string, { id: string | null; name: string; projects: Proj[] }>();
  for (const p of props.projects) {
    const key = p.direction_id || "__none__";
    let g = map.get(key);
    if (!g) { g = { id: p.direction_id || null, name: p.direction || "Без направления", projects: [] }; map.set(key, g); }
    g.projects.push(p);
  }
  // добавим направления без проектов (чтобы в них можно было класть свои пункты)
  for (const d of props.directions) {
    if (!map.has(d.id)) map.set(d.id, { id: d.id, name: d.name, projects: [] });
  }
  return Array.from(map.values()).sort((a, b) => {
    const oa = a.id ? (order.get(a.id) ?? 900) : 1000;
    const ob = b.id ? (order.get(b.id) ?? 900) : 1000;
    return oa - ob;
  });
});

function customFor(dirId: string | null): MatrixCustomItem[] {
  return custom.value.filter(c => (c.direction_id || null) === dirId);
}

async function loadCfg() {
  loading.value = true;
  try {
    const r = await overviewMatrixApi.get(props.companyId, props.year);
    const cfg = r.config;
    hidden.clear();
    for (const id of (cfg.hidden || [])) hidden.add(id);
    // overrides
    for (const p of props.projects) ensureOv(p);
    for (const [id, o] of Object.entries(cfg.overrides || {})) {
      ensureOv({ id, title: "", due_date: null });
      ov[id].title = o.title || "";
      if (o.due_date != null) ov[id].due_date = dstr(o.due_date);
      ov[id].quarter = (o.quarter ?? null);
      ov[id].quarter_end = (o.quarter_end ?? null);
    }
    custom.value = (cfg.custom || []).map(c => ({ ...c, due_date: dstr(c.due_date) }));
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не удалось загрузить настройку: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally {
    loading.value = false;
  }
}
onMounted(loadCfg);

function included(id: string): boolean { return !hidden.has(id); }
function toggleIncluded(id: string) { if (hidden.has(id)) hidden.delete(id); else hidden.add(id); }

function addCustom(dirId: string | null, dirName: string) {
  custom.value.push({
    id: `custom_${Date.now()}_${customSeq++}`,
    direction_id: dirId,
    direction_name: dirName,
    title: "",
    due_date: "",
    quarter: null,
  });
}
function removeCustom(id: string) { custom.value = custom.value.filter(c => c.id !== id); }

function buildConfig(): MatrixConfig {
  const overrides: MatrixConfig["overrides"] = {};
  for (const p of props.projects) {
    const o = ov[p.id];
    if (!o) continue;
    const out: { title?: string; due_date?: string | null; quarter?: number | null; quarter_end?: number | null } = {};
    const t = o.title.trim();
    if (t && t !== p.title) out.title = t;
    if (o.due_date && o.due_date !== dstr(p.due_date)) out.due_date = o.due_date;
    if (o.quarter != null) out.quarter = o.quarter;
    if (o.quarter_end != null) out.quarter_end = o.quarter_end;
    if (Object.keys(out).length) overrides[p.id] = out;
  }
  return {
    hidden: Array.from(hidden),
    overrides,
    custom: custom.value
      .filter(c => c.title.trim())
      .map(c => ({
        id: c.id,
        direction_id: c.direction_id || null,
        direction_name: c.direction_name || null,
        title: c.title.trim(),
        due_date: c.due_date || null,
        quarter: c.quarter ?? null,
        quarter_end: c.quarter_end ?? null,
      })),
  };
}

async function save() {
  if (saving.value) return;
  saving.value = true;
  try {
    const cfg = buildConfig();
    const r = await overviewMatrixApi.save(props.companyId, props.year, cfg);
    toast.success("Настройка матрицы сохранена");
    emit("saved", props.companyId, r.config);
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    toast.error("Не удалось сохранить: " + (err?.response?.data?.detail || err?.message || "ошибка"));
  } finally {
    saving.value = false;
  }
}

const totalIncluded = computed(() =>
  props.projects.filter(p => included(p.id)).length + custom.value.filter(c => c.title.trim()).length,
);
</script>

<template>
  <ModalShell :open="true" size="full" @close="emit('close')">
    <template #header>
      <div class="mx-head">
        <div class="mx-head-t">Матрица «Сводного обзора» — {{ companyName }}</div>
        <div class="mx-head-s">FY {{ year }} · отметь проекты, поправь название/дату/квартал, добавь свои пункты · в печати: {{ totalIncluded }}</div>
      </div>
    </template>

    <div v-if="loading" class="mx-state">Загрузка настройки…</div>

    <div v-else class="mx">
      <div v-for="g in groups" :key="g.id || '__none__'" class="mx-dir">
        <div class="mx-dir-head">
          <span class="mx-dir-name">{{ g.name }}</span>
          <button class="mx-add" type="button" @click="addCustom(g.id, g.name)">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
            свой пункт
          </button>
        </div>

        <div v-if="!g.projects.length && !customFor(g.id).length" class="mx-empty">нет проектов</div>

        <!-- реальные проекты -->
        <div v-for="p in g.projects" :key="p.id" class="mx-row" :class="{ off: !included(p.id) }">
          <label class="mx-chk" :title="included(p.id) ? 'Показывать' : 'Скрыто'">
            <input type="checkbox" :checked="included(p.id)" @change="toggleIncluded(p.id)" />
          </label>
          <input v-model="ov[p.id].title" class="mx-in mx-in-title" :placeholder="p.title" :disabled="!included(p.id)" />
          <input v-model="ov[p.id].due_date" type="date" class="mx-in mx-in-date" :disabled="!included(p.id)" />
          <select v-model="ov[p.id].quarter" class="mx-in mx-in-q" :disabled="!included(p.id)" title="Квартал (старт)">
            <option v-for="o in QOPTS" :key="String(o.v)" :value="o.v">{{ o.l }}</option>
          </select>
          <select v-model="ov[p.id].quarter_end" class="mx-in mx-in-q" :disabled="!included(p.id)" title="Растянуть до квартала (Гант)">
            <option v-for="o in QEND_OPTS" :key="'e' + String(o.v)" :value="o.v">{{ o.l }}</option>
          </select>
        </div>

        <!-- свои пункты -->
        <div v-for="c in customFor(g.id)" :key="c.id" class="mx-row mx-row-custom">
          <span class="mx-chk mx-custom-tag" title="Свой пункт">+</span>
          <input v-model="c.title" class="mx-in mx-in-title" placeholder="Название своего пункта" />
          <input v-model="c.due_date" type="date" class="mx-in mx-in-date" />
          <select v-model="c.quarter" class="mx-in mx-in-q" title="Квартал (старт)">
            <option v-for="o in QOPTS" :key="String(o.v)" :value="o.v">{{ o.l }}</option>
          </select>
          <select v-model="c.quarter_end" class="mx-in mx-in-q" title="Растянуть до квартала (Гант)">
            <option v-for="o in QEND_OPTS" :key="'e' + String(o.v)" :value="o.v">{{ o.l }}</option>
          </select>
          <button class="mx-del" type="button" title="Удалить пункт" @click="removeCustom(c.id)">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
          </button>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="mx-foot">
        <span class="mx-foot-note">Квартал «авто» — по дате; задай вручную, чтобы перенести в другой квартал</span>
        <div class="mx-foot-btns">
          <button class="mx-btn-cancel" type="button" :disabled="saving" @click="emit('close')">Отмена</button>
          <button class="mx-btn-save" type="button" :disabled="saving || loading" @click="save">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
        </div>
      </div>
    </template>
  </ModalShell>
</template>

<style scoped>
.mx-head-t { font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A); }
.mx-head-s { font-size: 11.5px; color: var(--t3, var(--t-muted)); margin-top: 2px; }
.mx-state { text-align: center; padding: 40px; color: var(--t3, var(--t-muted)); font-size: 13px; }

.mx { display: flex; flex-direction: column; gap: 16px; }
.mx-dir {
  border: 1px solid var(--border1, rgba(0, 0, 0, .06)); border-radius: 12px;
  overflow: hidden;
}
.mx-dir-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 9px 14px; background: var(--bg2, #FAFBFC);
  border-bottom: 1px solid var(--border1, rgba(0, 0, 0, .06));
}
.mx-dir-name { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--p-deep, #5B53B8); }
.mx-add {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 4px 11px; border-radius: 7px; font-size: 11px; font-weight: 500;
  font-family: inherit; cursor: pointer;
  background: rgba(127, 119, 221, .08); border: 1px solid rgba(127, 119, 221, .22);
  color: var(--p-deep, #5B53B8); transition: all .15s;
}
.mx-add:hover { background: #7F77DD; color: #fff; border-color: #7F77DD; }
.mx-empty { padding: 14px; text-align: center; color: var(--t3, var(--t-muted)); font-size: 11.5px; }

.mx-row {
  display: grid; grid-template-columns: 30px 1fr 128px 76px 86px auto; gap: 8px;
  align-items: center; padding: 7px 14px;
  border-bottom: 1px solid rgba(0, 0, 0, .035);
}
.mx-row:last-child { border-bottom: none; }
.mx-row.off { opacity: .5; }
.mx-row-custom { background: rgba(127, 119, 221, .035); }
.mx-chk { display: flex; align-items: center; justify-content: center; }
.mx-chk input { width: 16px; height: 16px; cursor: pointer; accent-color: #7F77DD; }
.mx-custom-tag { font-weight: 700; color: #7F77DD; font-size: 14px; }
.mx-in {
  padding: 6px 9px; border-radius: 7px; border: 1px solid rgba(0, 0, 0, .12);
  font-size: 12px; font-family: inherit; color: var(--t1, #1E2A4A);
  background: var(--bg1, #fff); outline: none; min-width: 0; box-sizing: border-box; width: 100%;
}
.mx-in:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127, 119, 221, .15); }
.mx-in:disabled { background: #f6f6f9; color: var(--t3, #9aa0b0); }
.mx-in-q { cursor: pointer; }
.mx-del {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: 6px; cursor: pointer;
  background: transparent; border: 1px solid transparent; color: var(--t3, var(--t-muted)); transition: all .15s;
}
.mx-del:hover { background: rgba(226, 75, 74, .1); color: #C53030; border-color: rgba(226, 75, 74, .25); }

.mx-foot { display: flex; align-items: center; justify-content: space-between; width: 100%; gap: 14px; flex-wrap: wrap; }
.mx-foot-note { font-size: 11px; color: var(--t3, var(--t-muted)); font-style: italic; }
.mx-foot-btns { display: flex; gap: 8px; }
.mx-btn-cancel, .mx-btn-save { padding: 7px 18px; font-size: 12px; font-weight: 500; border-radius: 7px; cursor: pointer; font-family: inherit; transition: all .15s; }
.mx-btn-cancel { background: var(--bg1, #fff); color: var(--t3, var(--t-muted)); border: 1px solid rgba(0, 0, 0, .1); }
.mx-btn-cancel:hover:not(:disabled) { color: var(--t1, #1E2A4A); }
.mx-btn-save { background: #7F77DD; color: #fff; border: none; }
.mx-btn-save:hover:not(:disabled) { background: #6B63D4; }
.mx-btn-cancel:disabled, .mx-btn-save:disabled { opacity: .6; cursor: not-allowed; }

@media (max-width: 760px) {
  .mx-row { grid-template-columns: 26px 1fr auto; grid-auto-rows: auto; }
  .mx-in-date { grid-column: 2 / 4; }
  .mx-in-q { grid-column: 2 / 4; }
}
</style>
