<script setup lang="ts">
/**
 * ErpRecords.vue — generic-рендерер ERP-конструктора (Фаза 0).
 *
 * ОДИН компонент рисует список + форму для ЛЮБОЙ сущности метамодели по её
 * определению (mm_fields). 14 типов полей → переиспользуемые инпуты.
 * Данные: /erp/entities, /erp/entities/{code}, /erp/companies, /erp/records.
 */
import { ref, computed, onMounted, watch } from "vue";
import { api } from "@/api/client";
import { useToast } from "@/composables/useToast";
import EptLogo from "@/components/EptLogo.vue";

interface FieldDef {
  code: string; label: string; type: string; group: string | null;
  required: boolean; unique_scoped: boolean; options: any[] | null;
  ref_entity_code: string | null; unit: string | null; validation: any;
  help: string | null; show_in_list: boolean; sort: number;
}
interface EntityDef { code: string; name: string; name_plural: string; icon: string | null; module: string | null; is_company_scoped: boolean; title_field: string | null; }
interface Rec { id: string; company_id: string | null; data: Record<string, any>; state: string | null; created_at: string; updated_at: string; }
interface Co { id: string; code: string; name: string; }

const toast = useToast();
const entities = ref<EntityDef[]>([]);
const activeCode = ref("");
const entityDef = ref<EntityDef | null>(null);
const fields = ref<FieldDef[]>([]);
const companies = ref<Co[]>([]);
const companyId = ref("");
const records = ref<Rec[]>([]);
const search = ref("");
const loading = ref(false);

const listFields = computed(() => fields.value.filter((f) => f.show_in_list));
const activeEntity = computed(() => entities.value.find((e) => e.code === activeCode.value));

async function loadEntities() {
  const { data } = await api.get("/erp/entities");
  entities.value = data.items || [];
  if (!activeCode.value && entities.value.length) activeCode.value = entities.value[0].code;
}
async function loadCompanies() {
  const { data } = await api.get("/erp/companies");
  companies.value = data.items || [];
  if (!companyId.value && companies.value.length) companyId.value = companies.value[0].id;
}
async function loadEntity() {
  if (!activeCode.value) return;
  const { data } = await api.get(`/erp/entities/${activeCode.value}`);
  entityDef.value = data.entity;
  fields.value = (data.fields || []).sort((a: FieldDef, b: FieldDef) => a.sort - b.sort);
}
async function loadRecords() {
  if (!activeCode.value) return;
  loading.value = true;
  try {
    const params: any = {};
    if (entityDef.value?.is_company_scoped && companyId.value) params.company_id = companyId.value;
    if (search.value.trim()) params.search = search.value.trim();
    const { data } = await api.get(`/erp/records/${activeCode.value}`, { params });
    records.value = data.items || [];
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Ошибка загрузки");
  } finally { loading.value = false; }
}

onMounted(async () => { await Promise.all([loadEntities(), loadCompanies()]); await loadEntity(); await loadRecords(); });
watch(activeCode, async () => { await loadEntity(); await loadRecords(); });
watch(companyId, loadRecords);
let st: any = null;
watch(search, () => { clearTimeout(st); st = setTimeout(loadRecords, 250); });

// ─── рендер значения в ячейке ──────────────────────────────────
function optOf(f: FieldDef, v: any) { return (f.options || []).find((o: any) => o.value === v); }
function cell(f: FieldDef, v: any): { text: string; color?: string; chip?: boolean } {
  if (v === null || v === undefined || v === "") return { text: "—" };
  if (f.type === "select") { const o = optOf(f, v); return { text: o?.label || v, color: o?.color, chip: true }; }
  if (f.type === "bool") return { text: v ? "✓" : "✗", color: v ? "#1D9E75" : "#94A3B8" };
  if (f.type === "money") return { text: new Intl.NumberFormat("ru-RU").format(Number(v)) + (f.unit ? " " + f.unit : "") };
  if (f.type === "number") return { text: new Intl.NumberFormat("ru-RU").format(Number(v)) + (f.unit ? " " + f.unit : "") };
  if (f.type === "date") return { text: String(v).slice(0, 10).split("-").reverse().join(".") };
  return { text: String(v) };
}

// ─── модалка создания/редактирования ───────────────────────────
const formOpen = ref(false);
const editing = ref<Rec | null>(null);
const form = ref<Record<string, any>>({});
const saving = ref(false);

function openCreate() {
  editing.value = null; form.value = {};
  for (const f of fields.value) if (f.type === "bool") form.value[f.code] = false;
  formOpen.value = true;
}
function openEdit(r: Rec) { editing.value = r; form.value = { ...r.data }; formOpen.value = true; }
function closeForm() { formOpen.value = false; }

async function save() {
  saving.value = true;
  try {
    if (editing.value) {
      await api.patch(`/erp/records/${editing.value.id}`, { data: form.value });
      toast.success("Сохранено");
    } else {
      const body: any = { data: form.value };
      if (entityDef.value?.is_company_scoped) body.company_id = companyId.value;
      await api.post(`/erp/records/${activeCode.value}`, body);
      toast.success("Запись создана");
    }
    formOpen.value = false;
    await loadRecords();
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Ошибка сохранения");
  } finally { saving.value = false; }
}
async function del(r: Rec) {
  if (!confirm("Удалить запись?")) return;
  try { await api.delete(`/erp/records/${r.id}`); toast.success("Удалено"); await loadRecords(); }
  catch (e: any) { toast.error(e?.response?.data?.detail || "Ошибка"); }
}
function titleOf(r: Rec): string {
  const tf = entityDef.value?.title_field;
  return (tf && r.data[tf]) || Object.values(r.data).find((v) => typeof v === "string" && v) || "—";
}
</script>

<template>
  <div class="erp">
    <div class="erp-top">
      <div class="erp-brand">
        <div class="erp-logo"><EptLogo :size="22" /></div>
        <div><div class="erp-eyebrow">ERP-КОНСТРУКТОР · ФАЗА 0</div><div class="erp-tt">Операционные данные</div></div>
      </div>
      <select v-if="activeEntity?.is_company_scoped" v-model="companyId" class="erp-sel">
        <option v-for="c in companies" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
    </div>

    <div class="erp-page">
      <!-- сущности -->
      <div class="erp-ent-tabs">
        <button v-for="e in entities" :key="e.code" class="erp-ent" :class="{ on: e.code === activeCode }" @click="activeCode = e.code">
          {{ e.name_plural }}
        </button>
        <span class="erp-ent-soon">+ скоро: конструктор сущностей</span>
      </div>

      <div class="erp-panel">
        <div class="erp-ph">
          <div>
            <div class="erp-ph-t">{{ entityDef?.name || '—' }}</div>
            <div class="erp-ph-cap">{{ records.length }} записей<template v-if="activeEntity?.module"> · {{ activeEntity.module }}</template></div>
          </div>
          <div class="erp-ph-r">
            <input v-model="search" class="erp-search" placeholder="Поиск…" />
            <button class="erp-add" @click="openCreate">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
              Добавить
            </button>
          </div>
        </div>

        <div v-if="loading" class="erp-state">Загрузка…</div>
        <table v-else class="erp-table">
          <thead><tr>
            <th v-for="f in listFields" :key="f.code">{{ f.label }}<span v-if="f.unit" class="erp-unit"> · {{ f.unit }}</span></th>
            <th class="erp-act-col"></th>
          </tr></thead>
          <tbody>
            <tr v-for="r in records" :key="r.id" @click="openEdit(r)">
              <td v-for="f in listFields" :key="f.code">
                <template v-if="cell(f, r.data[f.code]).chip">
                  <span class="erp-chip" :style="{ background: (cell(f, r.data[f.code]).color || '#888') + '1f', color: cell(f, r.data[f.code]).color }">{{ cell(f, r.data[f.code]).text }}</span>
                </template>
                <span v-else :style="{ color: cell(f, r.data[f.code]).color }">{{ cell(f, r.data[f.code]).text }}</span>
              </td>
              <td class="erp-act-col">
                <button class="erp-del" @click.stop="del(r)" title="Удалить">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/></svg>
                </button>
              </td>
            </tr>
            <tr v-if="!records.length"><td :colspan="listFields.length + 1" class="erp-empty">Записей нет. Нажмите «Добавить».</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ФОРМА -->
    <Teleport to="body">
      <Transition name="erp-modal">
        <div v-if="formOpen" class="erp-back" @click.self="closeForm">
          <div class="erp-mod">
            <div class="erp-mod-head">
              <div><div class="erp-mod-eyebrow">{{ entityDef?.name }}</div><div class="erp-mod-title">{{ editing ? titleOf(editing) : 'Новая запись' }}</div></div>
              <button class="erp-x" @click="closeForm"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
            </div>
            <div class="erp-mod-body">
              <div v-for="f in fields" :key="f.code" class="erp-fld" :class="{ wide: f.type === 'textarea' }">
                <label class="erp-fld-l">{{ f.label }}<span v-if="f.required" class="erp-req">*</span><span v-if="f.unit" class="erp-fld-u">{{ f.unit }}</span></label>
                <!-- по типу -->
                <textarea v-if="f.type === 'textarea'" v-model="form[f.code]" rows="3" class="erp-in" />
                <select v-else-if="f.type === 'select'" v-model="form[f.code]" class="erp-in">
                  <option :value="undefined">—</option>
                  <option v-for="o in (f.options || [])" :key="o.value" :value="o.value">{{ o.label }}</option>
                </select>
                <label v-else-if="f.type === 'bool'" class="erp-switch">
                  <input type="checkbox" v-model="form[f.code]" /> <span>{{ form[f.code] ? 'Да' : 'Нет' }}</span>
                </label>
                <input v-else-if="f.type === 'number' || f.type === 'money'" type="number" step="any" v-model.number="form[f.code]" class="erp-in" />
                <input v-else-if="f.type === 'date'" type="date" v-model="form[f.code]" class="erp-in" />
                <input v-else-if="f.type === 'datetime'" type="datetime-local" v-model="form[f.code]" class="erp-in" />
                <input v-else v-model="form[f.code]" class="erp-in" />
                <div v-if="f.help" class="erp-fld-help">{{ f.help }}</div>
              </div>
            </div>
            <div class="erp-mod-foot">
              <button class="erp-cancel" @click="closeForm">Отмена</button>
              <button class="erp-save" @click="save" :disabled="saving">{{ saving ? 'Сохранение…' : 'Сохранить' }}</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.erp { --p:#7C6FF7; --p-deep:#534AB7; --navy:#0C1230; --navy2:#141C42; --t3:#64748B; --t4:#94A3B8; --bd:#EAEBF2; --line:#F0F1F6; --ease:cubic-bezier(.34,1.2,.64,1); color:#0F172A; }
.erp-top { height: 62px; background: linear-gradient(120deg,var(--navy),var(--navy2) 70%,#1C2550); display: flex; align-items: center; padding: 0 24px; }
.erp-brand { display: flex; align-items: center; gap: 12px; }
.erp-logo { width: 34px; height: 34px; border-radius: 10px; background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.12); display: grid; place-items: center; }
.erp-eyebrow { font-size: 9px; font-weight: 600; letter-spacing: .1em; color: #9A8FFF; }
.erp-tt { color: #fff; font-size: 15px; font-weight: 600; margin-top: 2px; }
.erp-sel { margin-left: auto; background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.09); color: rgba(255,255,255,.82); font: 600 12px inherit; padding: 8px 13px; border-radius: 10px; cursor: pointer; outline: none; }
.erp-sel option { color: #1E2A4A; }
.erp-page { padding: 18px 24px 80px; max-width: 1280px; margin: 0 auto; }

.erp-ent-tabs { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
.erp-ent { border: 1px solid var(--bd); background: #fff; color: #475569; font: 600 12.5px inherit; padding: 8px 16px; border-radius: 10px; cursor: pointer; transition: all .15s var(--ease); }
.erp-ent.on { background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; border-color: transparent; box-shadow: 0 4px 14px rgba(108,92,231,.3); }
.erp-ent-soon { font-size: 11px; color: var(--t4); margin-left: 6px; }

.erp-panel { background: #fff; border: 1px solid var(--bd); border-radius: 16px; box-shadow: 0 1px 2px rgba(15,23,60,.05),0 12px 32px rgba(15,23,60,.06); overflow: hidden; }
.erp-ph { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--line); }
.erp-ph-t { font-size: 14px; font-weight: 600; color: #1E2A4A; }
.erp-ph-cap { font-size: 11px; color: var(--t4); margin-top: 2px; }
.erp-ph-r { display: flex; gap: 9px; align-items: center; }
.erp-search { border: 1px solid var(--bd); border-radius: 9px; padding: 8px 12px; font-size: 12.5px; outline: none; width: 200px; }
.erp-search:focus { border-color: var(--p); box-shadow: 0 0 0 3px rgba(124,111,247,.12); }
.erp-add { display: inline-flex; align-items: center; gap: 7px; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; border: none; font: 600 12px inherit; padding: 9px 15px; border-radius: 10px; cursor: pointer; box-shadow: 0 4px 14px rgba(108,92,231,.3); }
.erp-state { padding: 50px; text-align: center; color: var(--t3); }
.erp-table { width: 100%; border-collapse: collapse; }
.erp-table thead th { font-size: 9.5px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: var(--t4); padding: 12px 16px; background: #FBFBFE; text-align: left; }
.erp-unit { color: #C7C9D1; text-transform: none; }
.erp-table tbody tr { border-top: 1px solid var(--line); cursor: pointer; transition: background .12s; }
.erp-table tbody tr:hover { background: #FAFAFF; }
.erp-table tbody td { padding: 11px 16px; font-size: 12.5px; color: #1E2A4A; font-variant-numeric: tabular-nums; }
.erp-chip { display: inline-block; padding: 3px 10px; border-radius: 8px; font-size: 11.5px; font-weight: 600; }
.erp-act-col { width: 44px; text-align: right; }
.erp-del { border: 0; background: transparent; color: var(--t4); cursor: pointer; padding: 5px; border-radius: 7px; }
.erp-del:hover { color: #E24B4A; background: #FCE7E7; }
.erp-empty { text-align: center; color: var(--t4); padding: 36px; font-size: 12.5px; }

.erp-back { position: fixed; inset: 0; background: rgba(15,18,40,.5); -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); z-index: 9999; display: grid; place-items: center; padding: 24px; }
.erp-mod { width: min(620px,100%); max-height: calc(100vh - 48px); background: #fff; border-radius: 18px; box-shadow: 0 24px 64px rgba(15,23,60,.22); display: flex; flex-direction: column; overflow: hidden; }
.erp-mod-head { display: flex; align-items: center; justify-content: space-between; padding: 18px 22px; border-bottom: 1px solid var(--line); }
.erp-mod-eyebrow { font-size: 10px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--p-deep); }
.erp-mod-title { font-size: 16px; font-weight: 600; color: #1E2A4A; margin-top: 2px; }
.erp-x { border: 0; background: rgba(15,23,60,.04); cursor: pointer; color: #64748B; width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center; }
.erp-x:hover { background: rgba(127,119,221,.12); color: var(--p-deep); }
.erp-mod-body { overflow-y: auto; padding: 18px 22px; display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.erp-fld { display: flex; flex-direction: column; gap: 6px; } .erp-fld.wide { grid-column: 1 / -1; }
.erp-fld-l { font-size: 11px; font-weight: 500; color: var(--t3); display: flex; align-items: center; gap: 5px; }
.erp-req { color: #E24B4A; } .erp-fld-u { margin-left: auto; color: var(--t4); font-size: 10px; }
.erp-in { border: 1px solid var(--bd); border-radius: 9px; padding: 9px 12px; font-size: 13px; font-family: inherit; color: #1E2A4A; outline: none; background: #fff; width: 100%; }
.erp-in:focus { border-color: var(--p); box-shadow: 0 0 0 3px rgba(124,111,247,.12); }
.erp-switch { display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: #1E2A4A; cursor: pointer; padding: 8px 0; }
.erp-fld-help { font-size: 10.5px; color: var(--t4); }
.erp-mod-foot { display: flex; justify-content: flex-end; gap: 10px; padding: 14px 22px; border-top: 1px solid var(--line); background: #FAFAFD; }
.erp-cancel { border: 1px solid var(--bd); background: #fff; color: var(--t3); font: 600 12.5px inherit; padding: 9px 18px; border-radius: 10px; cursor: pointer; }
.erp-save { border: 0; background: linear-gradient(135deg,#8B7FFF,#6C5CE7); color: #fff; font: 600 12.5px inherit; padding: 9px 22px; border-radius: 10px; cursor: pointer; box-shadow: 0 4px 14px rgba(108,92,231,.3); }
.erp-save:disabled { opacity: .65; cursor: default; }
.erp-modal-enter-active,.erp-modal-leave-active { transition: opacity .22s ease; } .erp-modal-enter-from,.erp-modal-leave-to { opacity: 0; }
.erp-modal-enter-active .erp-mod { transition: transform .4s var(--ease); } .erp-modal-enter-from .erp-mod { transform: scale(.94) translateY(12px); }

@media (max-width: 720px) { .erp-mod-body { grid-template-columns: 1fr; } }
</style>
