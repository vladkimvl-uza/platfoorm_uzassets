<script setup lang="ts">
/**
 * Companies admin tab inside RBAC v2 (Pack 9.2).
 *
 * Tabs structure: список слева + детальный редактор справа.
 * Detail имеет суб-табы: Основное · Цвет+бейдж · По годам · Модули · Идентификаторы · Иерархия · Теги
 */
import { computed, onMounted, ref, watch } from "vue";
import {
  companiesAdminV2Api,
  sectorsAdminV2Api,
  COLOR_PALETTE, STATUS_LABELS, EXCLUSION_REASONS, MODULE_FLAGS,
  statusBadge,
  type CompanyAdmin,
  type SectorAdmin,
  type CompanyYearOverride,
  type CompanyYearOverrideUpsert,
  type Badge,
} from "@/api/companiesAdminV2";
import { useCompaniesStore } from "@/stores/companies";

const companiesStore = useCompaniesStore();

const companies = ref<CompanyAdmin[]>([]);
const sectors = ref<SectorAdmin[]>([]);
const selectedCode = ref<string | null>(null);
const detail = ref<CompanyAdmin | null>(null);
const overrides = ref<CompanyYearOverride[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const search = ref("");
const filterSector = ref("");
const filterStatus = ref("");
const showCreate = ref(false);
const dirty = ref(false);

type SubTab = "basic" | "design" | "years" | "modules" | "ids" | "hierarchy" | "tags";
const subTab = ref<SubTab>("design");

// Year range — last 6 years
const YEARS = [2021, 2022, 2023, 2024, 2025, 2026];

// ─── Load ──────────────────────────────────────────────────
async function loadAll() {
  loading.value = true;
  try {
    [companies.value, sectors.value] = await Promise.all([
      companiesAdminV2Api.list(),
      sectorsAdminV2Api.list(),
    ]);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  } finally {
    loading.value = false;
  }
}

async function selectCompany(code: string) {
  selectedCode.value = code;
  dirty.value = false;
  try {
    [detail.value, overrides.value] = await Promise.all([
      companiesAdminV2Api.get(code),
      companiesAdminV2Api.listYearOverrides(code),
    ]);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  }
}

onMounted(loadAll);

// ─── Filtering ─────────────────────────────────────────────
const filteredCompanies = computed(() => {
  let list = companies.value;
  if (filterSector.value) list = list.filter(c => c.sector_code === filterSector.value);
  if (filterStatus.value) list = list.filter(c => c.status === filterStatus.value);
  const q = search.value.trim().toLowerCase();
  if (q) {
    list = list.filter(c =>
      (c.code || "").toLowerCase().includes(q) ||
      (c.name_ru || "").toLowerCase().includes(q) ||
      (c.name_short || "").toLowerCase().includes(q)
    );
  }
  return [...list].sort((a, b) =>
    Number(b.is_pinned) - Number(a.is_pinned) ||
    (a.sort_order || 0) - (b.sort_order || 0) ||
    a.name_ru.localeCompare(b.name_ru)
  );
});

// ─── Helpers ───────────────────────────────────────────────
function initials(c: CompanyAdmin): string {
  const s = c.name_short || c.name_ru;
  return s.replace(/[«»"']/g, "").slice(0, 2).toUpperCase();
}

function getColor(c: CompanyAdmin): string {
  return c.primary_color || sectors.value.find(s => s.code === c.sector_code)?.color_hex || "#7F77DD";
}

function getOverrideForYear(year: number): CompanyYearOverride | undefined {
  return overrides.value.find(o => o.year === year);
}

// ─── Update single field ───────────────────────────────────
async function updateField<K extends keyof CompanyAdmin>(key: K, value: CompanyAdmin[K]) {
  if (!detail.value) return;
  try {
    detail.value = await companiesAdminV2Api.update(detail.value.code, { [key]: value } as any);
    const idx = companies.value.findIndex(c => c.code === detail.value!.code);
    if (idx >= 0) companies.value[idx] = detail.value;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  }
}

// Color / badges editing
const draftPrimary = ref<string>("");
const draftSecondary = ref<string>("");
const draftHasGradient = ref(false);
const draftBadges = ref<Badge[]>([]);

watch(detail, (d) => {
  if (!d) return;
  draftPrimary.value = d.primary_color || getColor(d);
  draftSecondary.value = d.secondary_color || "";
  draftHasGradient.value = !!d.secondary_color;
  draftBadges.value = [...(d.badges || [])];
});

async function saveDesign() {
  if (!detail.value) return;
  await updateField("primary_color", draftPrimary.value || null as any);
  await updateField("secondary_color", draftHasGradient.value ? (draftSecondary.value || null as any) : null as any);
  await updateField("badges", draftBadges.value.length ? draftBadges.value as any : null as any);
}

function addBadge() {
  if (draftBadges.value.length >= 3) return;
  draftBadges.value.push({ text: "NEW", color: COLOR_PALETTE[draftBadges.value.length % COLOR_PALETTE.length] });
}
function removeBadge(i: number) { draftBadges.value.splice(i, 1); }

// Year overrides
const draftOverrides = ref<Record<number, CompanyYearOverrideUpsert>>({});
watch(detail, () => {
  draftOverrides.value = {};
  for (const o of overrides.value) {
    draftOverrides.value[o.year] = {
      year: o.year, is_hidden: o.is_hidden,
      name_override: o.name_override,
      sector_override_code: o.sector_override_code,
      exclusion_reason: o.exclusion_reason,
      notes: o.notes,
    };
  }
});

function toggleYearVisibility(year: number) {
  const cur = draftOverrides.value[year] || { year, is_hidden: false };
  cur.is_hidden = !cur.is_hidden;
  draftOverrides.value = { ...draftOverrides.value, [year]: cur };
}

function setYearField(year: number, key: string, value: any) {
  const cur = draftOverrides.value[year] || { year, is_hidden: false };
  (cur as any)[key] = value;
  draftOverrides.value = { ...draftOverrides.value, [year]: cur };
}

async function saveYearOverrides() {
  if (!detail.value) return;
  const arr = Object.values(draftOverrides.value).filter(o =>
    o.is_hidden || o.name_override || o.sector_override_code || o.exclusion_reason || o.notes
  );
  try {
    overrides.value = await companiesAdminV2Api.setYearOverrides(detail.value.code, arr);
    detail.value = await companiesAdminV2Api.get(detail.value.code);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  }
}

// Module flags
async function toggleModule(flag: string) {
  if (!detail.value) return;
  const m = { ...(detail.value.module_flags || {}) };
  m[flag] = !(m[flag] !== false);
  await updateField("module_flags", m as any);
}

function moduleEnabled(flag: string): boolean {
  if (!detail.value) return true;
  return detail.value.module_flags?.[flag] !== false;
}

// Tags
const newTagInput = ref("");
async function addTag() {
  if (!newTagInput.value.trim() || !detail.value) return;
  const tags = [...(detail.value.tags || []), newTagInput.value.trim()];
  newTagInput.value = "";
  await updateField("tags", tags as any);
}
async function removeTag(t: string) {
  if (!detail.value) return;
  await updateField("tags", (detail.value.tags || []).filter(x => x !== t) as any);
}

// Create
const createForm = ref<{ code: string; name_ru: string; name_short: string; sector_code: string; legal_form: string }>({
  code: "", name_ru: "", name_short: "", sector_code: "", legal_form: "АО",
});
async function createCompany() {
  if (!createForm.value.code || !createForm.value.name_ru) return;
  try {
    const c = await companiesAdminV2Api.create(createForm.value as any);
    await loadAll();
    // Pack 148 D: surface the new company everywhere it's cached
    // (sidebar, KPI picker, FinModel companies dropdown, etc.)
    await companiesStore.reload();
    showCreate.value = false;
    createForm.value = { code: "", name_ru: "", name_short: "", sector_code: "", legal_form: "АО" };
    await selectCompany(c.code);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  }
}

async function deleteCompany() {
  if (!detail.value) return;
  if (!confirm(`Удалить компанию "${detail.value.name_ru}" безвозвратно?`)) return;
  try {
    await companiesAdminV2Api.remove(detail.value.code);
    detail.value = null;
    selectedCode.value = null;
    await loadAll();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  }
}

// Preview for design tab
const gradientCss = computed(() => {
  if (draftHasGradient.value && draftSecondary.value) {
    return `linear-gradient(135deg, ${draftPrimary.value}, ${draftSecondary.value})`;
  }
  return draftPrimary.value;
});

// Status options
const STATUS_OPTIONS = Object.entries(STATUS_LABELS).map(([k, v]) => ({ value: k, label: v.label }));
const EXCLUSION_OPTIONS = Object.entries(EXCLUSION_REASONS).map(([k, v]) => ({ value: k, label: v }));
</script>

<template>
  <div class="ca-wrap">
    <div v-if="error" class="ca-error">{{ error }} <button @click="error = null">×</button></div>

    <div class="ca-grid">

      <!-- LEFT: company list -->
      <div class="ca-card">
        <div class="ca-card-hd">
          <input v-model="search" placeholder="Поиск компании..." class="ca-search"/>
          <button class="ca-btn ca-btn-primary" @click="showCreate = !showCreate">
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M8 3v10M3 8h10"/></svg>
            {{ showCreate ? "Скрыть" : "Новая" }}
          </button>
        </div>

        <!-- Pack 148 D: inline minimal add-company form above the list. -->
        <div v-if="showCreate" class="ca-inline-add">
          <div class="ca-inline-row">
            <input v-model="createForm.code" placeholder="code (latin), напр. uzbekugol" class="ca-mono ca-inline-i"/>
            <input v-model="createForm.name_ru" placeholder="Название (RU)*" class="ca-inline-i"/>
          </div>
          <div class="ca-inline-row">
            <input v-model="createForm.name_short" placeholder="Короткое имя" class="ca-inline-i"/>
            <select v-model="createForm.sector_code" class="ca-inline-i">
              <option value="">— сектор —</option>
              <option v-for="s in sectors" :key="s.code" :value="s.code">{{ s.name_ru }}</option>
            </select>
            <select v-model="createForm.legal_form" class="ca-inline-i" style="max-width:80px">
              <option>АО</option><option>ООО</option><option>ГП</option>
            </select>
          </div>
          <div class="ca-inline-row" style="justify-content:flex-end">
            <button class="ca-btn ca-btn-ghost" @click="showCreate = false">Отмена</button>
            <button class="ca-btn ca-btn-primary" @click="createCompany" :disabled="!createForm.code || !createForm.name_ru">
              Создать (с группой)
            </button>
          </div>
          <div class="ca-inline-hint">
            При создании автоматически появится группа RBAC v3 с тем же
            кодом — её можно сразу использовать для добавления пользователей.
          </div>
        </div>
        <div class="ca-filter-row">
          <select v-model="filterSector" class="ca-fl">
            <option value="">Все сектора</option>
            <option v-for="s in sectors" :key="s.code" :value="s.code">{{ s.name_ru }} ({{ s.companies_count }})</option>
          </select>
          <select v-model="filterStatus" class="ca-fl">
            <option value="">Все статусы</option>
            <option v-for="s in STATUS_OPTIONS" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>
        </div>
        <div class="ca-list">
          <div v-if="!filteredCompanies.length" class="ca-empty">Нет компаний</div>
          <div v-for="c in filteredCompanies" :key="c.code"
               class="ca-row"
               :class="{ active: c.code === selectedCode, hidden: !c.is_active }"
               @click="selectCompany(c.code)">
            <span class="ca-icn" :style="{ background: getColor(c), color: '#fff' }">{{ initials(c) }}</span>
            <div class="ca-info">
              <div class="ca-name">{{ c.name_short || c.name_ru }}</div>
              <div class="ca-sub">{{ c.sector_code || "—" }} <span v-if="c.children_count">· {{ c.children_count }} sub</span></div>
            </div>
            <div class="ca-badges">
              <span v-for="b in (c.badges || []).slice(0, 1)" :key="b.text" class="ca-bdg" :style="{ background: b.color, color: '#fff' }">{{ b.text }}</span>
              <span v-if="c.year_overrides_count" class="ca-bdg" style="background: rgba(239,159,39,.15); color: #A36500">⚠</span>
            </div>
          </div>
        </div>
      </div>

      <!-- RIGHT: detail editor -->
      <div class="ca-card">
        <div v-if="!detail" class="ca-empty-detail">Выберите компанию слева</div>
        <div v-else>

          <!-- Header -->
          <div class="ca-detail-hd">
            <span class="ca-icn-lg" :style="{ background: gradientCss, color: '#fff' }">{{ initials(detail) }}</span>
            <div class="ca-detail-info">
              <div class="ca-detail-name">
                {{ detail.name_ru }}
                <span v-for="b in (detail.badges || [])" :key="b.text" class="ca-bdg-inline" :style="{ background: b.color, color: '#fff' }">{{ b.text }}</span>
              </div>
              <div class="ca-detail-sub">
                <code>{{ detail.code }}</code> · {{ detail.sector_name || "—" }} ·
                {{ detail.founded_year || "—" }} · {{ detail.employees_count ? detail.employees_count.toLocaleString() + " сотр." : "—" }}
                <span v-if="detail.status" :style="{ color: statusBadge(detail.status).color }" style="margin-left: 6px; font-weight: 500;">
                  · {{ statusBadge(detail.status).label }}
                </span>
              </div>
            </div>
            <div class="ca-detail-actions">
              <button class="ca-btn ca-btn-ghost" :class="{ active: detail.is_pinned }" @click="updateField('is_pinned', !detail.is_pinned as any)">
                <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 1l2 5 5 1-4 4 1 5-5-3-4 3 1-5-4-4 5-1z"/></svg>
                {{ detail.is_pinned ? "Закреплено" : "Закрепить" }}
              </button>
              <button class="ca-btn ca-btn-red" @click="deleteCompany">Удалить</button>
            </div>
          </div>

          <!-- Sub-tabs -->
          <div class="ca-subtabs">
            <button :class="{ active: subTab === 'basic' }"     @click="subTab = 'basic'">Основное</button>
            <button :class="{ active: subTab === 'design' }"    @click="subTab = 'design'">Цвет + бейдж</button>
            <button :class="{ active: subTab === 'years' }"     @click="subTab = 'years'">По годам</button>
            <button :class="{ active: subTab === 'modules' }"   @click="subTab = 'modules'">Модули</button>
            <button :class="{ active: subTab === 'ids' }"       @click="subTab = 'ids'">Идентификаторы</button>
            <button :class="{ active: subTab === 'hierarchy' }" @click="subTab = 'hierarchy'">Иерархия</button>
            <button :class="{ active: subTab === 'tags' }"      @click="subTab = 'tags'">Теги</button>
          </div>

          <!-- ─── BASIC ─── -->
          <div v-if="subTab === 'basic'" class="ca-section">
            <div class="ca-grid-2">
              <div class="ca-f">
                <label>Название (RU)</label>
                <input :value="detail.name_ru" @change="updateField('name_ru', ($event.target as HTMLInputElement).value as any)"/>
              </div>
              <div class="ca-f">
                <label>Короткое имя</label>
                <input :value="detail.name_short || ''" @change="updateField('name_short', ($event.target as HTMLInputElement).value as any)"/>
              </div>
              <div class="ca-f">
                <label>Название (UZ)</label>
                <input :value="detail.name_uz || ''" @change="updateField('name_uz', ($event.target as HTMLInputElement).value as any)"/>
              </div>
              <div class="ca-f">
                <label>Название (EN)</label>
                <input :value="detail.name_en || ''" @change="updateField('name_en', ($event.target as HTMLInputElement).value as any)"/>
              </div>
              <div class="ca-f">
                <label>Сектор</label>
                <select :value="detail.sector_code || ''" @change="updateField('sector_code' as any, ($event.target as HTMLSelectElement).value as any)">
                  <option value="">— нет —</option>
                  <option v-for="s in sectors" :key="s.code" :value="s.code">{{ s.name_ru }}</option>
                </select>
              </div>
              <div class="ca-f">
                <label>Статус</label>
                <select :value="detail.status || 'active'" @change="updateField('status', ($event.target as HTMLSelectElement).value as any)">
                  <option v-for="s in STATUS_OPTIONS" :key="s.value" :value="s.value">{{ s.label }}</option>
                </select>
              </div>
              <div class="ca-f">
                <label>Год основания</label>
                <input type="number" :value="detail.founded_year || ''" @change="updateField('founded_year', Number(($event.target as HTMLInputElement).value) as any)"/>
              </div>
              <div class="ca-f">
                <label>Сотрудников</label>
                <input type="number" :value="detail.employees_count || ''" @change="updateField('employees_count', Number(($event.target as HTMLInputElement).value) as any)"/>
              </div>
              <div class="ca-f">
                <label>Юр. форма</label>
                <select :value="detail.legal_form || ''" @change="updateField('legal_form', ($event.target as HTMLSelectElement).value as any)">
                  <option value="">—</option>
                  <option>АО</option><option>ООО</option><option>ГП</option>
                </select>
              </div>
              <div class="ca-f">
                <label>CEO</label>
                <input :value="detail.ceo_name || ''" @change="updateField('ceo_name', ($event.target as HTMLInputElement).value as any)"/>
              </div>
            </div>
            <div class="ca-f">
              <label>Описание</label>
              <textarea :value="detail.description || ''" @change="updateField('description', ($event.target as HTMLTextAreaElement).value as any)" rows="3"></textarea>
            </div>
          </div>

          <!-- ─── DESIGN: color + badges ─── -->
          <div v-if="subTab === 'design'" class="ca-section">
            <div class="ca-grid-2-fixed">
              <div>
                <div class="ca-section-l">Цвет компании (override сектора)</div>
                <div class="ca-swatches">
                  <button v-for="col in COLOR_PALETTE" :key="col"
                          class="ca-swatch"
                          :class="{ active: draftPrimary === col }"
                          :style="{ background: col }"
                          @click="draftPrimary = col"></button>
                  <input type="color" :value="draftPrimary" @input="draftPrimary = ($event.target as HTMLInputElement).value" class="ca-color-picker"/>
                </div>
                <div class="ca-row-flex">
                  <input :value="draftPrimary" @input="draftPrimary = ($event.target as HTMLInputElement).value" class="ca-hex"/>
                  <label class="ca-cb">
                    <input type="checkbox" v-model="draftHasGradient"/> Gradient
                  </label>
                  <input v-if="draftHasGradient" :value="draftSecondary" @input="draftSecondary = ($event.target as HTMLInputElement).value" class="ca-hex" placeholder="#534AB7"/>
                </div>
              </div>

              <div>
                <div class="ca-section-l">Бейджи (до 3)</div>
                <div class="ca-badge-list">
                  <div v-for="(b, i) in draftBadges" :key="i" class="ca-badge-edit">
                    <span class="ca-bdg-preview" :style="{ background: b.color, color: '#fff' }">{{ b.text }}</span>
                    <input v-model="b.text" maxlength="8" class="ca-bdg-text"/>
                    <input type="color" :value="b.color" @input="b.color = ($event.target as HTMLInputElement).value" class="ca-bdg-color"/>
                    <button class="ca-x" @click="removeBadge(i)">×</button>
                  </div>
                  <button v-if="draftBadges.length < 3" class="ca-add-btn" @click="addBadge">+ Добавить бейдж</button>
                </div>
              </div>
            </div>

            <div class="ca-section-l" style="margin-top: 14px">Превью</div>
            <div class="ca-preview-row">
              <div class="ca-prev-card" :style="{ '--c1': draftPrimary, '--c2': draftSecondary || draftPrimary } as any">
                <div class="ca-prev-stripe"></div>
                <span class="ca-prev-icn" :style="{ background: gradientCss }">{{ initials(detail) }}</span>
                <div class="ca-prev-info">
                  <div class="ca-prev-name">{{ detail.name_short || detail.name_ru }}</div>
                  <div class="ca-prev-sec">{{ detail.sector_code }}</div>
                </div>
                <div class="ca-prev-bdgs">
                  <span v-for="b in draftBadges" :key="b.text" :style="{ background: b.color, color: '#fff' }" class="ca-bdg-inline">{{ b.text }}</span>
                </div>
              </div>
            </div>

            <button class="ca-btn ca-btn-primary" style="margin-top: 14px" @click="saveDesign">Сохранить цвет и бейджи</button>
          </div>

          <!-- ─── YEARS ─── -->
          <div v-if="subTab === 'years'" class="ca-section">
            <div class="ca-section-l">Видимость по годам</div>
            <div class="ca-years-grid">
              <div v-for="year in YEARS" :key="year" class="ca-year-cell">
                <div class="ca-year-label">{{ year }}</div>
                <label class="ca-switch">
                  <input type="checkbox" :checked="!(draftOverrides[year]?.is_hidden ?? false)" @change="toggleYearVisibility(year)"/>
                  <span class="ca-switch-tr"></span>
                </label>
                <div v-if="draftOverrides[year]?.is_hidden" class="ca-year-hidden">скрыта</div>
              </div>
            </div>

            <div v-for="year in YEARS.filter(y => draftOverrides[y]?.is_hidden || draftOverrides[y]?.name_override)" :key="year" class="ca-year-detail">
              <div class="ca-section-l" style="margin-top: 12px">Настройки {{ year }} год</div>
              <div class="ca-grid-2">
                <div class="ca-f" v-if="draftOverrides[year]?.is_hidden">
                  <label>Причина исключения</label>
                  <select :value="draftOverrides[year]?.exclusion_reason || ''" @change="setYearField(year, 'exclusion_reason', ($event.target as HTMLSelectElement).value || null)">
                    <option value="">— выбрать —</option>
                    <option v-for="opt in EXCLUSION_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                  </select>
                </div>
                <div class="ca-f">
                  <label>Override названия</label>
                  <input :value="draftOverrides[year]?.name_override || ''" @input="setYearField(year, 'name_override', ($event.target as HTMLInputElement).value || null)" placeholder="напр. Navoi Mining Co."/>
                </div>
                <div class="ca-f">
                  <label>Override сектора</label>
                  <select :value="draftOverrides[year]?.sector_override_code || ''" @change="setYearField(year, 'sector_override_code', ($event.target as HTMLSelectElement).value || null)">
                    <option value="">— как обычно —</option>
                    <option v-for="s in sectors" :key="s.code" :value="s.code">{{ s.name_ru }}</option>
                  </select>
                </div>
                <div class="ca-f">
                  <label>Примечание</label>
                  <input :value="draftOverrides[year]?.notes || ''" @input="setYearField(year, 'notes', ($event.target as HTMLInputElement).value || null)"/>
                </div>
              </div>
            </div>

            <button class="ca-btn ca-btn-primary" style="margin-top: 14px" @click="saveYearOverrides">Сохранить overrides</button>
          </div>

          <!-- ─── MODULES ─── -->
          <div v-if="subTab === 'modules'" class="ca-section">
            <div class="ca-grid-2-fixed">
              <div>
                <div class="ca-section-l">Модули per компания</div>
                <div class="ca-tg-list">
                  <label v-for="m in MODULE_FLAGS" :key="m.code" class="ca-tg-row">
                    <span>{{ m.label }}</span>
                    <span class="ca-switch">
                      <input type="checkbox" :checked="moduleEnabled(m.code)" @change="toggleModule(m.code)"/>
                      <span class="ca-switch-tr"></span>
                    </span>
                  </label>
                  <label class="ca-tg-row">
                    <span>Включать в KPI rollups</span>
                    <span class="ca-switch">
                      <input type="checkbox" :checked="detail.include_in_rollups" @change="updateField('include_in_rollups', !detail.include_in_rollups as any)"/>
                      <span class="ca-switch-tr"></span>
                    </span>
                  </label>
                </div>
              </div>

              <div>
                <div class="ca-section-l">Currency &amp; FY</div>
                <div class="ca-curr-block">
                  <div class="ca-f">
                    <label>Primary currency</label>
                    <div class="ca-curr-tabs">
                      <button v-for="curr in ['UZS','USD','EUR']" :key="curr"
                              class="ca-curr-tab"
                              :class="{ active: detail.primary_currency === curr }"
                              @click="updateField('primary_currency', curr as any)">{{ curr }}</button>
                    </div>
                  </div>
                  <div class="ca-f">
                    <label>FY start month</label>
                    <select :value="detail.fy_start_month" @change="updateField('fy_start_month', Number(($event.target as HTMLSelectElement).value) as any)">
                      <option :value="1">Январь (по умолчанию)</option>
                      <option :value="4">Апрель</option>
                      <option :value="7">Июль</option>
                      <option :value="10">Октябрь</option>
                    </select>
                  </div>
                  <label class="ca-tg-row" style="margin-top: 4px">
                    <span>Корректировка на инфляцию</span>
                    <span class="ca-switch">
                      <input type="checkbox" :checked="detail.track_inflation" @change="updateField('track_inflation', !detail.track_inflation as any)"/>
                      <span class="ca-switch-tr"></span>
                    </span>
                  </label>
                </div>
              </div>
            </div>
          </div>

          <!-- ─── IDS ─── -->
          <div v-if="subTab === 'ids'" class="ca-section">
            <div class="ca-grid-2">
              <div class="ca-f">
                <label>ИНН</label>
                <input :value="detail.inn || ''" @change="updateField('inn', ($event.target as HTMLInputElement).value as any)" class="ca-mono"/>
              </div>
              <div class="ca-f">
                <label>Bloomberg ticker</label>
                <input :value="detail.bloomberg_ticker || ''" @change="updateField('bloomberg_ticker', ($event.target as HTMLInputElement).value as any)" placeholder="UZUG UZ" class="ca-mono"/>
              </div>
              <div class="ca-f">
                <label>ISIN</label>
                <input :value="detail.isin || ''" @change="updateField('isin', ($event.target as HTMLInputElement).value as any)" placeholder="UZ4801070000" class="ca-mono"/>
              </div>
              <div class="ca-f">
                <label>LEI</label>
                <input :value="detail.lei || ''" @change="updateField('lei', ($event.target as HTMLInputElement).value as any)" class="ca-mono"/>
              </div>
            </div>
            <div class="ca-f">
              <label>Aliases / former names</label>
              <div class="ca-tag-chips">
                <span v-for="a in (detail.aliases || [])" :key="a" class="ca-chip">{{ a }} <button @click="updateField('aliases', (detail.aliases || []).filter(x => x !== a) as any)">×</button></span>
                <input placeholder="+ alias" class="ca-chip-input" @change="updateField('aliases', [...(detail.aliases || []), ($event.target as HTMLInputElement).value] as any); ($event.target as HTMLInputElement).value = ''"/>
              </div>
            </div>
          </div>

          <!-- ─── HIERARCHY ─── -->
          <div v-if="subTab === 'hierarchy'" class="ca-section">
            <div class="ca-f">
              <label>Parent company</label>
              <select :value="detail.parent_code || ''" @change="updateField('parent_code' as any, ($event.target as HTMLSelectElement).value as any)">
                <option value="">— нет (standalone) —</option>
                <option v-for="c in companies.filter(x => x.code !== detail!.code)" :key="c.code" :value="c.code">{{ c.name_short || c.name_ru }}</option>
              </select>
            </div>
            <div v-if="detail.parent_code" class="ca-hint">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 2v12M3 10l5-5 5 5"/></svg>
              Subsidiary под <b>{{ companies.find(c => c.code === detail.parent_code)?.name_short || detail.parent_code }}</b>
            </div>
            <div v-if="detail.children_count" class="ca-hint">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 14V2M3 6l5 5 5-5"/></svg>
              Имеет <b>{{ detail.children_count }}</b> подкомпаний
            </div>
            <div class="ca-f">
              <label>Portfolio start year</label>
              <input type="number" :value="detail.portfolio_start_year || ''" @change="updateField('portfolio_start_year', Number(($event.target as HTMLInputElement).value) as any)"/>
            </div>
          </div>

          <!-- ─── TAGS ─── -->
          <div v-if="subTab === 'tags'" class="ca-section">
            <div class="ca-section-l">Свободные теги</div>
            <div class="ca-tag-chips">
              <span v-for="t in (detail.tags || [])" :key="t" class="ca-chip">
                {{ t }} <button @click="removeTag(t)">×</button>
              </span>
              <input v-model="newTagInput" @keydown.enter="addTag" placeholder="+ добавить тег" class="ca-chip-input"/>
            </div>
            <div class="ca-section-l" style="margin-top: 14px">Примеры тегов</div>
            <div class="ca-tag-chips">
              <span v-for="t in ['pilot_2026','esg_focus','high_priority','m&a_target','digitalization']" :key="t"
                    class="ca-chip dimmed" @click="newTagInput = t; addTag()">+ {{ t }}</span>
            </div>
          </div>

        </div>
      </div>

    </div>

  </div>
</template>

<style scoped>
.ca-wrap { padding: 0; }
.ca-error { background: rgba(226,75,74,.08); color: #A32D2D; padding: 8px 14px; border-radius: 6px; margin-bottom: 10px; display: flex; justify-content: space-between; font-size: 12px; }
.ca-error button { background: transparent; border: 0; color: inherit; cursor: pointer; font-size: 16px; }
.ca-grid { display: grid; grid-template-columns: 300px 1fr; gap: 12px; }
.ca-card { background: var(--bg1, #fff); border: 0.5px solid rgba(0,0,0,.06); border-radius: 12px; overflow: hidden; }
.ca-card-hd { padding: 10px 12px; border-bottom: 0.5px solid rgba(0,0,0,.06); background: var(--bg2, #FAFAFC); display: flex; gap: 6px; align-items: center; }
.ca-search { border: 0; background: transparent; flex: 1; font-size: 12px; outline: none; font-family: inherit; color: var(--t1, #1E2A4A); }
.ca-filter-row { padding: 8px 12px; display: flex; gap: 6px; border-bottom: 0.5px solid rgba(0,0,0,.05); }
.ca-fl { flex: 1; padding: 4px 8px; border: 0.5px solid rgba(0,0,0,.1); border-radius: 6px; font-size: 11px; background: var(--bg1, #fff); font-family: inherit; color: var(--t1, #1E2A4A); }

.ca-btn { border: 0; padding: 5px 10px; border-radius: 6px; font-size: 11px; font-family: inherit; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; }
.ca-btn-primary { background: #7F77DD; color: #fff; }
.ca-btn-primary:hover { background: #6E66CC; }
.ca-btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.ca-btn-ghost { background: transparent; border: 0.5px solid rgba(0,0,0,.12); color: var(--t3, #5F5E5A); }
.ca-btn-ghost.active { background: rgba(127,119,221,.1); color: #534AB7; border-color: rgba(127,119,221,.3); }
.ca-btn-red { background: rgba(226,75,74,.12); color: #A32D2D; }

.ca-list { max-height: 560px; overflow-y: auto; }
.ca-empty { padding: 24px; text-align: center; color: var(--t3, #888780); font-size: 11px; font-style: italic; }
.ca-empty-detail { padding: 80px 20px; text-align: center; color: var(--t3, #888780); font-size: 12px; }

.ca-row { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 0.5px solid rgba(0,0,0,.04); cursor: pointer; transition: background .15s; position: relative; overflow: hidden; }
.ca-row:hover { background: rgba(127,119,221,.04); }
.ca-row.active { background: rgba(127,119,221,.08); }
.ca-row.active::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 2px; background: #7F77DD;
  animation: uzaStripeDrawIn .4s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  transform-origin: left center;
  pointer-events: none;
}
.ca-row.hidden { opacity: .5; }
.ca-icn { width: 24px; height: 24px; border-radius: 5px; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 500; flex-shrink: 0; }
.ca-icn-lg { width: 42px; height: 42px; border-radius: 7px; display: flex; align-items: center; justify-content: center; font-size: 14px; font-weight: 500; flex-shrink: 0; }
.ca-info { flex: 1; min-width: 0; }
.ca-name { font-size: 12px; color: var(--t1, #1E2A4A); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ca-sub { font-size: 10px; color: var(--t3, #888780); }
.ca-badges { display: flex; flex-direction: column; gap: 2px; align-items: flex-end; }
.ca-bdg { padding: 1px 5px; border-radius: 3px; font-size: 8.5px; font-weight: 600; letter-spacing: .04em; }

.ca-detail-hd { display: flex; align-items: center; gap: 12px; padding: 14px 18px; border-bottom: 0.5px solid rgba(0,0,0,.06); background: var(--bg2, #FAFAFC); }
.ca-detail-info { flex: 1; }
.ca-detail-name { font-size: 15px; color: var(--t1, #1E2A4A); font-weight: 500; display: flex; align-items: center; gap: 6px; }
.ca-detail-sub { font-size: 11px; color: var(--t3, #888780); margin-top: 2px; }
.ca-detail-sub code { font-family: monospace; color: #534AB7; }
.ca-detail-actions { display: flex; gap: 6px; }
.ca-bdg-inline { padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 500; letter-spacing: .04em; }

.ca-subtabs { display: flex; gap: 2px; padding: 12px 18px; border-bottom: 0.5px solid rgba(0,0,0,.06); overflow-x: auto; }
.ca-subtabs button { background: transparent; border: 0; color: var(--t3, #888780); padding: 5px 12px; border-radius: 6px; font-size: 11px; cursor: pointer; font-family: inherit; white-space: nowrap; }
.ca-subtabs button.active { background: rgba(127,119,221,.1); color: #534AB7; font-weight: 500; }
.ca-section { padding: 14px 18px; }
.ca-section-l { font-size: 9.5px; color: var(--t3, #888780); text-transform: uppercase; letter-spacing: .07em; font-weight: 500; margin-bottom: 8px; }

.ca-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
.ca-grid-2-fixed { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.ca-f { display: flex; flex-direction: column; gap: 3px; margin-bottom: 8px; }
.ca-f label { font-size: 9.5px; color: var(--t3, #888780); text-transform: uppercase; letter-spacing: .06em; }
.ca-f input, .ca-f select, .ca-f textarea { padding: 5px 9px; border: 0.5px solid rgba(0,0,0,.12); border-radius: 5px; font-size: 11.5px; outline: none; font-family: inherit; background: var(--bg1, #fff); color: var(--t1, #1E2A4A); }
.ca-f input:focus, .ca-f select:focus { border-color: #7F77DD; }
.ca-mono { font-family: monospace !important; }

.ca-swatches { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 8px; }
.ca-swatch { width: 24px; height: 24px; border-radius: 5px; border: 0; cursor: pointer; transition: transform .12s; }
.ca-swatch:hover { transform: scale(1.1); }
.ca-swatch.active { border: 2px solid #1E2A4A; }
.ca-color-picker { width: 24px; height: 24px; border: 0.5px dashed rgba(0,0,0,.2); border-radius: 5px; cursor: pointer; padding: 0; background: transparent; }
.ca-row-flex { display: flex; gap: 6px; align-items: center; }
.ca-hex { font-family: monospace; padding: 4px 8px; border: 0.5px solid rgba(0,0,0,.1); border-radius: 5px; font-size: 11px; width: 90px; }
.ca-cb { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--t3, #5F5E5A); cursor: pointer; }

.ca-badge-list { display: flex; flex-direction: column; gap: 5px; }
.ca-badge-edit { display: flex; align-items: center; gap: 6px; padding: 5px 8px; background: var(--bg2, #FAFAFC); border-radius: 6px; }
.ca-bdg-preview { padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 500; letter-spacing: .04em; min-width: 36px; text-align: center; }
.ca-bdg-text { border: 0; background: transparent; flex: 1; font-size: 11px; outline: none; font-family: inherit; }
.ca-bdg-color { width: 16px; height: 16px; border: 0; border-radius: 3px; cursor: pointer; padding: 0; }
.ca-x { background: transparent; border: 0; color: var(--t3, #888780); cursor: pointer; font-size: 14px; }
.ca-add-btn { background: transparent; border: 0.5px dashed rgba(0,0,0,.2); color: var(--t3, #888780); padding: 5px 8px; border-radius: 6px; font-size: 11px; cursor: pointer; font-family: inherit; }

.ca-preview-row { padding: 12px; background: var(--bg2, #FAFAFC); border-radius: 8px; display: flex; gap: 10px; align-items: center; }
.ca-prev-card { flex: 1; background: var(--bg1, #fff); border: 0.5px solid rgba(0,0,0,.06); border-radius: 8px; padding: 10px 12px; position: relative; display: flex; align-items: center; gap: 8px; }
.ca-prev-stripe { position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, var(--c1), var(--c2)); border-radius: 8px 8px 0 0; }
.ca-prev-icn { width: 28px; height: 28px; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 11px; font-weight: 500; }
.ca-prev-info { flex: 1; min-width: 0; }
.ca-prev-name { font-size: 12px; font-weight: 500; color: var(--t1, #1E2A4A); }
.ca-prev-sec { font-size: 10px; color: var(--t3, #888780); }
.ca-prev-bdgs { display: flex; flex-direction: column; gap: 2px; align-items: flex-end; }

.ca-years-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; padding: 12px; background: var(--bg2, #FAFAFC); border-radius: 8px; }
.ca-year-cell { text-align: center; }
.ca-year-label { font-size: 10.5px; color: var(--t3, #888780); margin-bottom: 4px; font-weight: 500; }
.ca-year-hidden { font-size: 9px; color: #A36500; margin-top: 3px; }
.ca-year-detail { padding: 8px 12px; background: rgba(239,159,39,.04); border-radius: 6px; margin-top: 10px; }

.ca-switch { position: relative; display: inline-block; width: 28px; height: 16px; cursor: pointer; }
.ca-switch input { opacity: 0; width: 0; height: 0; position: absolute; }
.ca-switch-tr { position: absolute; inset: 0; background: #D3D1C7; border-radius: 9px; transition: background .2s; }
.ca-switch-tr::before { content: ""; position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; background: var(--bg1, #fff); border-radius: 50%; transition: left .2s; }
.ca-switch input:checked + .ca-switch-tr { background: #1D9E75; }
.ca-switch input:checked + .ca-switch-tr::before { left: 14px; }

.ca-tg-list { background: var(--bg2, #FAFAFC); border-radius: 8px; padding: 8px 10px; display: flex; flex-direction: column; gap: 6px; }
.ca-tg-row { display: flex; justify-content: space-between; align-items: center; font-size: 11.5px; color: var(--t1, #1E2A4A); cursor: pointer; }
.ca-curr-block { background: var(--bg2, #FAFAFC); border-radius: 8px; padding: 10px; }
.ca-curr-tabs { display: flex; gap: 4px; }
.ca-curr-tab { background: transparent; border: 0.5px solid rgba(0,0,0,.12); padding: 4px 10px; border-radius: 5px; font-size: 11px; cursor: pointer; color: var(--t3, #5F5E5A); font-family: inherit; }
.ca-curr-tab.active { background: #7F77DD; color: #fff; border-color: #7F77DD; }

.ca-tag-chips { display: flex; gap: 5px; flex-wrap: wrap; }
.ca-chip { background: rgba(55,138,221,.1); color: #185FA5; padding: 3px 9px; border-radius: 5px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; }
.ca-chip button { background: transparent; border: 0; color: inherit; cursor: pointer; font-size: 12px; }
.ca-chip.dimmed { background: rgba(0,0,0,.04); color: var(--t3, #888780); cursor: pointer; }
.ca-chip-input { border: 0.5px dashed rgba(0,0,0,.2); background: transparent; padding: 3px 9px; border-radius: 5px; font-size: 11px; outline: none; }

.ca-hint { display: flex; align-items: center; gap: 6px; padding: 8px 10px; background: rgba(127,119,221,.06); color: #534AB7; border-radius: 6px; font-size: 11.5px; margin-bottom: 8px; }

.ca-inline-add { padding: 10px 12px; background: rgba(127,119,221,.04); border-bottom: 0.5px solid rgba(127,119,221,.18); display: flex; flex-direction: column; gap: 6px; }
.ca-inline-row { display: flex; gap: 6px; align-items: center; }
.ca-inline-i { flex: 1; padding: 5px 9px; border: 0.5px solid rgba(0,0,0,.12); border-radius: 5px; font-size: 11.5px; outline: none; font-family: inherit; background: var(--bg1, #fff); color: var(--t1, #1E2A4A); min-width: 0; }
.ca-inline-i:focus { border-color: #7F77DD; }
.ca-inline-hint { font-size: 10px; color: var(--t3, #888780); line-height: 1.4; }

@media (max-width: 1200px) {
  .ca-grid { grid-template-columns: 1fr; }
  .ca-grid-2-fixed { grid-template-columns: 1fr; }
}
</style>
