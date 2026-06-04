<script setup lang="ts">
/**
 * CustomApiBuilder — «Конструктор API»: собрать read-only data-endpoint из
 * источника (KPI/финансы/проекты/задачи/рейтинги) + фильтры/колонки → живой
 * превью → сохранение. Endpoint доступен по /api/v1/custom/{slug}.
 */
import { ref, computed, onMounted } from "vue";
import { customApi, type ApiSource, type CustomEndpoint, type PreviewResult } from "@/api/customApi";
import BIcon from "@/components/broadcasts/BIcon.vue";

const sources = ref<ApiSource[]>([]);
const endpoints = ref<CustomEndpoint[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const building = ref(false);
const editId = ref<string | null>(null);
const form = ref({ title: "", slug: "", description: "", source: "", columns: [] as string[], year: "" as string | number, standard: "", limit: 2000 });

const preview = ref<PreviewResult | null>(null);
const previewing = ref(false);
const saving = ref(false);
const copied = ref<string | null>(null);

const origin = window.location.origin;
const activeSource = computed(() => sources.value.find(s => s.key === form.value.source) || null);

async function loadAll() {
  loading.value = true; error.value = null;
  try {
    const [s, e] = await Promise.all([customApi.sources(), customApi.list()]);
    sources.value = s; endpoints.value = e;
  } catch (e: any) { error.value = e?.response?.data?.detail || "Не удалось загрузить"; }
  finally { loading.value = false; }
}
onMounted(loadAll);

function slugify(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64);
}
function onTitleInput() { if (!editId.value) form.value.slug = slugify(form.value.title); }

function pickSource(key: string) {
  form.value.source = key;
  const s = sources.value.find(x => x.key === key);
  form.value.columns = s ? [...s.columns] : [];
  preview.value = null;
}
function toggleColumn(c: string) {
  const i = form.value.columns.indexOf(c);
  if (i >= 0) form.value.columns.splice(i, 1); else form.value.columns.push(c);
}

function startNew() {
  building.value = true; editId.value = null; preview.value = null;
  form.value = { title: "", slug: "", description: "", source: "", columns: [], year: "", standard: "", limit: 2000 };
}
function startEdit(ep: CustomEndpoint) {
  building.value = true; editId.value = ep.id; preview.value = null;
  form.value = {
    title: ep.title, slug: ep.slug, description: ep.description || "", source: ep.source,
    columns: ep.config.columns?.length ? [...ep.config.columns] : (sources.value.find(s => s.key === ep.source)?.columns || []),
    year: ep.config.year ?? "", standard: ep.config.standard ?? "", limit: ep.config.limit ?? 2000,
  };
}
function cancel() { building.value = false; editId.value = null; preview.value = null; error.value = null; }

function buildConfig() {
  return {
    columns: form.value.columns,
    year: form.value.year === "" ? null : Number(form.value.year),
    standard: form.value.standard || null,
    limit: Number(form.value.limit) || 2000,
  };
}

async function runPreview() {
  if (!form.value.source) { error.value = "Выберите источник"; return; }
  previewing.value = true; error.value = null;
  try { preview.value = await customApi.preview(form.value.source, buildConfig()); }
  catch (e: any) { error.value = e?.response?.data?.detail || "Ошибка превью"; }
  finally { previewing.value = false; }
}

async function save() {
  if (!form.value.source) { error.value = "Выберите источник"; return; }
  if (!form.value.title.trim()) { error.value = "Введите название"; return; }
  saving.value = true; error.value = null;
  try {
    if (editId.value) {
      await customApi.update(editId.value, { title: form.value.title, description: form.value.description || null, config: buildConfig() });
    } else {
      await customApi.create({ slug: form.value.slug, title: form.value.title, description: form.value.description || null, source: form.value.source, config: buildConfig(), is_active: true });
    }
    await loadAll(); cancel();
  } catch (e: any) { error.value = e?.response?.data?.detail || "Не удалось сохранить"; }
  finally { saving.value = false; }
}

async function toggleActive(ep: CustomEndpoint) {
  try { await customApi.update(ep.id, { is_active: !ep.is_active }); await loadAll(); }
  catch (e: any) { error.value = e?.response?.data?.detail || "Ошибка"; }
}
async function remove(ep: CustomEndpoint) {
  if (!confirm(`Удалить endpoint «${ep.title}» (${ep.slug})?`)) return;
  try { await customApi.remove(ep.id); await loadAll(); }
  catch (e: any) { error.value = e?.response?.data?.detail || "Ошибка"; }
}
function copy(text: string, key: string) {
  navigator.clipboard.writeText(text).then(() => { copied.value = key; setTimeout(() => (copied.value = null), 1600); });
}
function srcLabel(key: string) { return sources.value.find(s => s.key === key)?.label || key; }
</script>

<template>
  <div class="cab">
    <div class="cab-head">
      <div>
        <div class="cab-eyebrow">Интеграции · собственные API</div>
        <div class="cab-title">Конструктор API</div>
        <div class="cab-sub">Соберите read-only endpoint из любого источника — данные тянутся вживую, новые записи отражаются автоматически.</div>
      </div>
      <button v-if="!building" class="cab-btn cab-btn-p" @click="startNew"><BIcon name="plus" :size="14" /> Новый endpoint</button>
    </div>

    <div v-if="error" class="cab-err">{{ error }} <button @click="error = null">×</button></div>

    <!-- ───────── BUILDER ───────── -->
    <div v-if="building" class="cab-builder">
      <div class="cab-form">
        <div class="cab-grid2">
          <label class="cab-fld"><span>Название *</span><input v-model="form.title" @input="onTitleInput" placeholder="KPI всех компаний" /></label>
          <label class="cab-fld"><span>Slug (в URL)</span><input v-model="form.slug" :disabled="!!editId" placeholder="kpi-all" /></label>
        </div>
        <label class="cab-fld"><span>Описание</span><input v-model="form.description" placeholder="для внешней интеграции…" /></label>

        <div class="cab-fld">
          <span>Источник данных *</span>
          <div class="cab-chips">
            <button v-for="s in sources" :key="s.key" type="button" class="cab-chip" :class="{ on: form.source === s.key }" :disabled="!!editId" @click="pickSource(s.key)">{{ s.label }}</button>
          </div>
        </div>

        <div v-if="activeSource" class="cab-fld">
          <span>Колонки ({{ form.columns.length }}/{{ activeSource.columns.length }})</span>
          <div class="cab-cols">
            <label v-for="c in activeSource.columns" :key="c" class="cab-col" :class="{ on: form.columns.includes(c) }">
              <input type="checkbox" :checked="form.columns.includes(c)" @change="toggleColumn(c)" /> {{ c }}
            </label>
          </div>
        </div>

        <div v-if="activeSource" class="cab-grid3">
          <label v-if="activeSource.filters.includes('year')" class="cab-fld"><span>Год (фикс.)</span><input v-model="form.year" type="number" placeholder="все" /></label>
          <label v-if="activeSource.filters.includes('standard')" class="cab-fld"><span>Стандарт</span>
            <select v-model="form.standard"><option value="">любой</option><option value="IFRS">IFRS</option><option value="NSBU">NSBU</option></select>
          </label>
          <label class="cab-fld"><span>Лимит строк</span><input v-model="form.limit" type="number" /></label>
        </div>

        <div class="cab-actions">
          <button class="cab-btn cab-btn-g" @click="cancel">Отмена</button>
          <div style="flex:1"></div>
          <button class="cab-btn cab-btn-g" :disabled="previewing || !form.source" @click="runPreview"><BIcon name="player-play" :size="13" /> {{ previewing ? "…" : "Превью" }}</button>
          <button class="cab-btn cab-btn-p" :disabled="saving" @click="save">{{ saving ? "…" : (editId ? "Сохранить" : "Создать endpoint") }}</button>
        </div>
      </div>

      <!-- preview -->
      <div class="cab-preview">
        <div class="cab-pv-h">Превью данных <span v-if="preview" class="cab-pv-c">{{ preview.count }} строк</span></div>
        <div v-if="!preview" class="cab-pv-empty"><BIcon name="terminal-2" :size="22" /><span>Нажмите «Превью» — здесь появятся живые данные</span></div>
        <div v-else-if="!preview.sample.length" class="cab-pv-empty">Нет данных по фильтрам</div>
        <div v-else class="cab-pv-tbl-wrap">
          <table class="cab-pv-tbl">
            <thead><tr><th v-for="c in (form.columns.length ? form.columns : preview.columns)" :key="c">{{ c }}</th></tr></thead>
            <tbody>
              <tr v-for="(row, i) in preview.sample.slice(0, 20)" :key="i">
                <td v-for="c in (form.columns.length ? form.columns : preview.columns)" :key="c">{{ row[c] ?? "—" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ───────── SAVED ENDPOINTS ───────── -->
    <div v-else>
      <div v-if="loading" class="cab-state">Загрузка…</div>
      <div v-else-if="!endpoints.length" class="cab-state">
        <BIcon name="api" :size="26" /><div>Пользовательских API ещё нет</div>
        <div class="cab-state-sub">Соберите первый — он станет доступен внешним системам по API-ключу.</div>
      </div>
      <div v-else class="cab-list">
        <div v-for="ep in endpoints" :key="ep.id" class="cab-card" :class="{ off: !ep.is_active }">
          <div class="cab-card-top">
            <div class="cab-card-titlewrap">
              <span class="cab-card-title">{{ ep.title }}</span>
              <span class="cab-card-src">{{ srcLabel(ep.source) }}</span>
              <span v-if="!ep.is_active" class="cab-card-off">отключён</span>
            </div>
            <div class="cab-card-acts">
              <button class="cab-ibtn" :title="ep.is_active ? 'Отключить' : 'Включить'" @click="toggleActive(ep)"><BIcon name="power" :size="14" /></button>
              <button class="cab-ibtn" title="Редактировать" @click="startEdit(ep)"><BIcon name="edit" :size="14" /></button>
              <button class="cab-ibtn cab-ibtn-d" title="Удалить" @click="remove(ep)"><BIcon name="trash" :size="14" /></button>
            </div>
          </div>
          <p v-if="ep.description" class="cab-card-desc">{{ ep.description }}</p>
          <div class="cab-card-url">
            <span class="cab-mverb">GET</span>
            <code>{{ origin }}{{ ep.url }}</code>
            <button class="cab-copy" @click="copy(origin + ep.url, ep.id)"><BIcon :name="copied === ep.id ? 'check' : 'copy'" :size="13" /></button>
          </div>
          <div class="cab-card-meta">
            <span>scope: <code>{{ ep.required_permission }}</code></span>
            <span v-if="ep.config.columns?.length">· {{ ep.config.columns.length }} колонок</span>
            <span v-if="ep.config.year">· FY{{ ep.config.year }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cab { display: flex; flex-direction: column; gap: 14px; }
.cab-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.cab-eyebrow { font-size: 10px; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; color: var(--p-deep, #534AB7); }
.cab-title { font-size: 18px; font-weight: 500; letter-spacing: -.01em; color: var(--t1, #1E2A4A); margin-top: 3px; }
.cab-sub { font-size: 12px; color: var(--t3, #94A3B8); margin-top: 4px; max-width: 620px; line-height: 1.5; }
.cab-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 9px; font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; border: none; }
.cab-btn:disabled { opacity: .55; cursor: default; }
.cab-btn-p { background: linear-gradient(135deg, #8B7FFF, #6C5CE7); color: #fff; box-shadow: 0 3px 12px rgba(108,92,231,.3); }
.cab-btn-g { background: #fff; border: 1px solid var(--border-hard, #E5E7EB); color: var(--t2, #334155); }
.cab-btn-g:hover:not(:disabled) { background: #F7F8FB; }
.cab-err { background: rgba(226,75,74,.08); border: 0.5px solid rgba(226,75,74,.3); color: #A82C2B; padding: 8px 12px; border-radius: 8px; font-size: 11.5px; display: flex; justify-content: space-between; }
.cab-err button { background: none; border: none; color: #A82C2B; cursor: pointer; font-size: 16px; }

.cab-builder { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.cab-form, .cab-preview { background: #fff; border: 0.5px solid var(--border-hard, #E5E7EB); border-radius: 12px; padding: 16px; }
.cab-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.cab-grid3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
.cab-fld { display: flex; flex-direction: column; gap: 4px; margin-bottom: 11px; }
.cab-fld > span { font-size: 9.5px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; color: var(--t3, #94A3B8); }
.cab-fld input, .cab-fld select { padding: 8px 10px; border: 1px solid var(--border-input, #E2E8F0); border-radius: 8px; font-size: 12.5px; font-family: inherit; color: #1E2A4A; outline: none; background: #fff; }
.cab-fld input:focus, .cab-fld select:focus { border-color: #7C6FF7; box-shadow: 0 0 0 3px rgba(124,111,247,.12); }
.cab-fld input:disabled { background: #F3F4F8; color: #94A3B8; }
.cab-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.cab-chip { padding: 5px 12px; border-radius: 8px; border: 1px solid var(--border-hard, #E5E7EB); background: #F7F8FB; color: var(--t2, #334155); font-size: 11.5px; font-weight: 500; cursor: pointer; font-family: inherit; }
.cab-chip.on { background: #7F77DD; border-color: #7F77DD; color: #fff; }
.cab-chip:disabled { opacity: .5; cursor: default; }
.cab-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; max-height: 180px; overflow-y: auto; padding: 2px; }
.cab-col { display: flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: 6px; font-size: 11.5px; color: var(--t2, #334155); cursor: pointer; font-family: ui-monospace, 'SF Mono', Menlo, monospace; }
.cab-col.on { background: rgba(124,111,247,.08); color: var(--p-deep, #534AB7); }
.cab-col input { accent-color: #7C6FF7; }
.cab-actions { display: flex; align-items: center; gap: 8px; margin-top: 6px; }

.cab-preview { display: flex; flex-direction: column; }
.cab-pv-h { font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t3, #94A3B8); margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
.cab-pv-c { font-size: 10px; color: var(--p-deep, #534AB7); background: rgba(124,111,247,.12); padding: 1px 8px; border-radius: 8px; }
.cab-pv-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; color: var(--t3, #94A3B8); font-size: 12px; padding: 30px; text-align: center; }
.cab-pv-tbl-wrap { overflow: auto; max-height: 380px; border: 0.5px solid var(--border-hard, #E5E7EB); border-radius: 8px; }
.cab-pv-tbl { width: 100%; border-collapse: collapse; font-size: 11px; }
.cab-pv-tbl th { position: sticky; top: 0; background: #F7F8FB; text-align: left; padding: 6px 9px; color: var(--t3, #64748B); font-weight: 600; white-space: nowrap; border-bottom: 1px solid var(--border-hard, #E5E7EB); }
.cab-pv-tbl td { padding: 5px 9px; border-bottom: 0.5px solid #F0F1F6; color: #1E2A4A; white-space: nowrap; max-width: 200px; overflow: hidden; text-overflow: ellipsis; }

.cab-state { padding: 50px; text-align: center; color: var(--t3, #94A3B8); font-size: 13px; display: flex; flex-direction: column; align-items: center; gap: 8px; }
.cab-state-sub { font-size: 11px; color: var(--t3, #94A3B8); }
.cab-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 12px; }
.cab-card { background: #fff; border: 0.5px solid var(--border-hard, #E5E7EB); border-radius: 12px; padding: 14px; box-shadow: 0 1px 2px rgba(15,23,60,.04); }
.cab-card.off { opacity: .65; }
.cab-card-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
.cab-card-titlewrap { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; }
.cab-card-title { font-size: 13.5px; font-weight: 600; color: #1E2A4A; }
.cab-card-src { font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--p-deep, #534AB7); background: rgba(124,111,247,.1); padding: 2px 7px; border-radius: 6px; }
.cab-card-off { font-size: 9.5px; color: #94A3B8; background: #F3F4F8; padding: 2px 7px; border-radius: 6px; }
.cab-card-acts { display: flex; gap: 4px; flex-shrink: 0; }
.cab-ibtn { width: 28px; height: 28px; display: inline-flex; align-items: center; justify-content: center; background: transparent; border: 0.5px solid var(--border-hard, #E5E7EB); border-radius: 7px; color: var(--t3, #64748B); cursor: pointer; }
.cab-ibtn:hover { border-color: #7F77DD; color: var(--p-deep, #534AB7); }
.cab-ibtn-d:hover { border-color: #E24B4A; color: #B91C1C; background: rgba(226,75,74,.06); }
.cab-card-desc { font-size: 11.5px; color: var(--t3, #64748B); margin: 8px 0; line-height: 1.4; }
.cab-card-url { display: flex; align-items: center; gap: 6px; margin-top: 8px; background: #0C1230; border-radius: 8px; padding: 7px 9px; }
.cab-mverb { font-size: 9px; font-weight: 700; color: #5DCAA5; letter-spacing: .04em; }
.cab-card-url code { flex: 1; min-width: 0; font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: 10.5px; color: #C8CEE8; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cab-copy { background: rgba(255,255,255,.08); border: none; color: #C8CEE8; width: 24px; height: 24px; border-radius: 6px; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; }
.cab-copy:hover { background: rgba(255,255,255,.16); color: #fff; }
.cab-card-meta { font-size: 10.5px; color: var(--t3, #94A3B8); margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
.cab-card-meta code { font-size: 10px; background: #F3F4F8; padding: 1px 5px; border-radius: 4px; }

@media (max-width: 880px) { .cab-builder { grid-template-columns: 1fr; } .cab-grid2, .cab-grid3, .cab-cols { grid-template-columns: 1fr; } }
</style>
