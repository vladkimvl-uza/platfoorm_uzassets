<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import { useAuthStore } from "@/stores/auth";
import { companiesApi } from "@/api/companies";
import { useCompaniesStore } from "@/stores/companies";
import { usePortfolioYearStore } from "@/stores/portfolioYear";
import CompanyAvatar from "@/components/CompanyAvatar.vue";
import type {
  CompanyListItem, SectorBrief,
  CompanyCreatePayload, CompanyUpdatePayload,
  SectorCreatePayload, SectorUpdatePayload,
} from "@/api/companies";

const auth = useAuthStore();
const companiesStore = useCompaniesStore();

// =====================================================================
// Permission gates
// =====================================================================
const canEditCompanies   = computed(() => auth.isOwner || auth.hasPermission("companies.edit") || auth.hasPermission("admin.users"));
const canCreateCompanies = computed(() => auth.isOwner || auth.hasPermission("companies.create") || auth.hasPermission("admin.users"));
const canDeleteCompanies = computed(() => auth.isOwner || auth.hasPermission("companies.delete") || auth.hasPermission("admin.users"));
const canCascadeDelete   = computed(() => auth.isOwner);  // Only owner can hard-delete with cascade

const canEditSectors     = computed(() => auth.isOwner || auth.hasPermission("sectors.edit") || auth.hasPermission("admin.users"));
const canCreateSectors   = computed(() => auth.isOwner || auth.hasPermission("sectors.create") || auth.hasPermission("admin.users"));
const canDeleteSectors   = computed(() => auth.isOwner || auth.hasPermission("sectors.delete") || auth.hasPermission("admin.users"));

// =====================================================================
// State
// =====================================================================
const activeTab = ref<"companies" | "sectors">("companies");

const companies = ref<CompanyListItem[]>([]);
const sectors   = ref<SectorBrief[]>([]);
const loading   = ref(false);
const search    = ref("");
const filterSector  = ref("");
const filterActive  = ref<"all" | "active" | "inactive">("active");

// Dialogs
const showCreateCompany = ref(false);
const showEditCompany   = ref(false);
const showDeleteCompany = ref(false);
// Pack 148 D: inline minimal Add-Company panel above the table
// (preferred over the modal — only the modal handles edits).
const showInlineCreate  = ref(false);

const showCreateSector  = ref(false);
const showEditSector    = ref(false);
const showDeleteSector  = ref(false);

const editingCompany = ref<CompanyListItem | null>(null);
const editingSector  = ref<SectorBrief | null>(null);

// Forms
const companyForm = ref<CompanyCreatePayload & { is_active?: boolean; hidden_years?: number[]; logo_url?: string | null }>({
  code: "", name_ru: "", name_short: "", name_uz: "", name_en: "",
  sector_code: "", legal_form: "", inn: "", description: "",
  website: "", address: "", ceo_name: "",
  employees_count: undefined, founded_year: undefined,
  is_active: true, hidden_years: [], logo_url: null,
});

// ── Логотип: ресайз до 256px (вписать, без обрезки), PNG (сохранить прозрачность) ──
const logoInput = ref<HTMLInputElement | null>(null);
function _resizeLogo(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const MAX = 256;
      const scale = Math.min(1, MAX / Math.max(img.width, img.height));
      const w = Math.round(img.width * scale), h = Math.round(img.height * scale);
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) return reject(new Error("canvas"));
      ctx.drawImage(img, 0, 0, w, h);
      resolve(canvas.toDataURL("image/png"));
    };
    img.onerror = () => reject(new Error("image"));
    const r = new FileReader();
    r.onload = () => { img.src = String(r.result); };
    r.onerror = () => reject(new Error("read"));
    r.readAsDataURL(file);
  });
}
async function onLogoPick(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) { formError.value = "Выберите изображение (PNG/SVG/JPG)"; return; }
  try {
    companyForm.value.logo_url = await _resizeLogo(file);
  } catch { formError.value = "Не удалось обработать изображение"; }
  finally { if (logoInput.value) logoInput.value.value = ""; }
}
function removeLogo() { companyForm.value.logo_url = ""; }

// Годы для настройки видимости (из реестра годов портфеля, fallback — диапазон)
const yearStore = usePortfolioYearStore();
const yearOptions = computed<number[]>(() => {
  const ys = yearStore.availableYears;
  if (ys && ys.length) return [...ys].sort((a, b) => b - a);
  return [2026, 2025, 2024, 2023, 2022, 2021];
});
function toggleHiddenYear(y: number) {
  const arr = companyForm.value.hidden_years || (companyForm.value.hidden_years = []);
  const i = arr.indexOf(y);
  if (i >= 0) arr.splice(i, 1); else arr.push(y);
}

const sectorForm = ref<SectorCreatePayload>({
  code: "", name_ru: "", name_uz: "", name_en: "",
  color_hex: "", sort_order: 1000,
});

const formError = ref<string | null>(null);
const formSubmitting = ref(false);

// Cascade flag for delete dialog
const deleteCascade = ref(false);

// =====================================================================
// Loaders
// =====================================================================
async function loadCompanies() {
  loading.value = true;
  try {
    const params: any = { limit: 200 };
    if (filterSector.value) params.sector = filterSector.value;
    if (search.value)       params.search = search.value;
    params.active_only = filterActive.value === "active";
    const r = await companiesApi.list(params);
    let list = r.items;
    if (filterActive.value === "inactive") {
      list = list.filter(c => !c.is_active);
    }
    companies.value = list;
  } finally {
    loading.value = false;
  }
}

async function loadSectors() {
  loading.value = true;
  try {
    sectors.value = await companiesApi.listSectors(true);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await Promise.all([loadCompanies(), loadSectors()]);
});

let searchTimer: number | null = null;
function onSearch() {
  if (searchTimer) window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(loadCompanies, 300);
}

// =====================================================================
// Company CRUD
// =====================================================================
function openCreateCompany() {
  companyForm.value = {
    code: "", name_ru: "", name_short: "", name_uz: "", name_en: "",
    sector_code: sectors.value[0]?.code || "",
    legal_form: "АО", inn: "", description: "",
    website: "", address: "", ceo_name: "",
    employees_count: undefined, founded_year: undefined,
    is_active: true,
  };
  formError.value = null;
  showCreateCompany.value = true;
}

function toggleInlineCreate() {
  showInlineCreate.value = !showInlineCreate.value;
  if (showInlineCreate.value) {
    companyForm.value = {
      code: "", name_ru: "", name_short: "", name_uz: "", name_en: "",
      sector_code: "",
      legal_form: "АО", inn: "", description: "",
      website: "", address: "", ceo_name: "",
      employees_count: undefined, founded_year: undefined,
      is_active: true,
    };
    formError.value = null;
  }
}

function openEditCompany(c: CompanyListItem) {
  editingCompany.value = c;
  companyForm.value = {
    code: c.code,
    name_ru: c.name_ru,
    name_short: c.name_short || "",
    name_uz: (c as any).name_uz || "",
    name_en: (c as any).name_en || "",
    sector_code: c.sector?.code || "",
    legal_form: (c as any).legal_form || "",
    inn: "", description: "", website: "", address: "", ceo_name: "",
    employees_count: undefined, founded_year: undefined,
    is_active: c.is_active,
    hidden_years: c.hidden_years ? [...c.hidden_years] : [],
    logo_url: c.logo_url ?? null,
  };
  formError.value = null;
  showEditCompany.value = true;
}

async function submitCreateCompany() {
  if (formSubmitting.value) return;
  formError.value = null;
  formSubmitting.value = true;
  try {
    await companiesApi.create({
      code: companyForm.value.code.toLowerCase().trim(),
      name_ru: companyForm.value.name_ru.trim(),
      name_short: companyForm.value.name_short || undefined,
      name_uz: companyForm.value.name_uz || undefined,
      name_en: companyForm.value.name_en || undefined,
      sector_code: companyForm.value.sector_code || undefined,
      legal_form: companyForm.value.legal_form || undefined,
    });
    showCreateCompany.value = false;
    showInlineCreate.value = false;
    await loadCompanies();
    // Pack 148 D: surface the new company in cached pickers (sidebar,
    // KPI, FinModel, InvestProjects, RBAC groups list) immediately.
    await companiesStore.reload();
  } catch (e: any) {
    if (e?.response?.status === 409) {
      formError.value = `Компания с тикером '${companyForm.value.code}' уже существует.`;
    } else {
      formError.value = e?.response?.data?.detail || e?.message || "Ошибка создания";
    }
  } finally {
    formSubmitting.value = false;
  }
}

async function submitEditCompany() {
  if (formSubmitting.value || !editingCompany.value) return;
  formError.value = null;
  formSubmitting.value = true;
  try {
    const patch: CompanyUpdatePayload = {};
    // Only include fields that are non-empty (don't accidentally null out optional fields)
    if (companyForm.value.name_ru) patch.name_ru = companyForm.value.name_ru;
    if (companyForm.value.name_short !== undefined) patch.name_short = companyForm.value.name_short;
    if (companyForm.value.name_uz !== undefined) patch.name_uz = companyForm.value.name_uz;
    if (companyForm.value.name_en !== undefined) patch.name_en = companyForm.value.name_en;
    if (companyForm.value.sector_code !== undefined) patch.sector_code = companyForm.value.sector_code;
    if (companyForm.value.legal_form !== undefined) patch.legal_form = companyForm.value.legal_form;
    if (companyForm.value.is_active !== undefined) patch.is_active = companyForm.value.is_active;
    patch.hidden_years = companyForm.value.hidden_years || [];  // всегда шлём (чтобы снятие работало)
    if (companyForm.value.logo_url !== undefined) patch.logo_url = companyForm.value.logo_url ?? "";
    await companiesApi.update(editingCompany.value.code, patch);
    showEditCompany.value = false;
    await loadCompanies();
    await companiesStore.reload();
  } catch (e: any) {
    formError.value = e?.response?.data?.detail || e?.message || "Ошибка сохранения";
  } finally {
    formSubmitting.value = false;
  }
}

function openDeleteCompany(c: CompanyListItem) {
  editingCompany.value = c;
  deleteCascade.value = false;
  formError.value = null;
  showDeleteCompany.value = true;
}

async function submitDeleteCompany() {
  if (formSubmitting.value || !editingCompany.value) return;
  formSubmitting.value = true;
  try {
    await companiesApi.remove(editingCompany.value.code, deleteCascade.value);
    showDeleteCompany.value = false;
    await loadCompanies();
    await companiesStore.reload();
  } catch (e: any) {
    formError.value = e?.response?.data?.detail || e?.message || "Ошибка удаления";
  } finally {
    formSubmitting.value = false;
  }
}

// =====================================================================
// Sector CRUD
// =====================================================================
function openCreateSector() {
  sectorForm.value = {
    code: "", name_ru: "", name_uz: "", name_en: "",
    color_hex: "", sort_order: (Math.max(0, ...sectors.value.map(s => s.sort_order)) + 10),
  };
  formError.value = null;
  showCreateSector.value = true;
}

function openEditSector(s: SectorBrief) {
  editingSector.value = s;
  sectorForm.value = {
    code: s.code,
    name_ru: s.name_ru, name_uz: s.name_uz || "", name_en: s.name_en || "",
    color_hex: s.color_hex || "",
    sort_order: s.sort_order,
  };
  formError.value = null;
  showEditSector.value = true;
}

async function submitCreateSector() {
  if (formSubmitting.value) return;
  formError.value = null;
  formSubmitting.value = true;
  try {
    await companiesApi.createSector({
      code: sectorForm.value.code.toLowerCase().trim(),
      name_ru: sectorForm.value.name_ru.trim(),
      name_uz: sectorForm.value.name_uz || undefined,
      name_en: sectorForm.value.name_en || undefined,
      color_hex: sectorForm.value.color_hex || undefined,
      sort_order: sectorForm.value.sort_order,
    });
    showCreateSector.value = false;
    await loadSectors();
  } catch (e: any) {
    if (e?.response?.status === 409) {
      formError.value = `Сектор '${sectorForm.value.code}' уже существует.`;
    } else {
      formError.value = e?.response?.data?.detail || e?.message || "Ошибка создания";
    }
  } finally {
    formSubmitting.value = false;
  }
}

async function submitEditSector() {
  if (formSubmitting.value || !editingSector.value) return;
  formError.value = null;
  formSubmitting.value = true;
  try {
    await companiesApi.updateSector(editingSector.value.code, {
      name_ru: sectorForm.value.name_ru,
      name_uz: sectorForm.value.name_uz || null,
      name_en: sectorForm.value.name_en || null,
      color_hex: sectorForm.value.color_hex || null,
      sort_order: sectorForm.value.sort_order,
    });
    showEditSector.value = false;
    await loadSectors();
  } catch (e: any) {
    formError.value = e?.response?.data?.detail || e?.message || "Ошибка сохранения";
  } finally {
    formSubmitting.value = false;
  }
}

function openDeleteSector(s: SectorBrief) {
  editingSector.value = s;
  formError.value = null;
  showDeleteSector.value = true;
}

async function submitDeleteSector() {
  if (formSubmitting.value || !editingSector.value) return;
  formSubmitting.value = true;
  try {
    await companiesApi.removeSector(editingSector.value.code);
    showDeleteSector.value = false;
    await loadSectors();
  } catch (e: any) {
    if (e?.response?.status === 409) {
      formError.value = e?.response?.data?.detail;
    } else {
      formError.value = e?.response?.data?.detail || e?.message || "Ошибка удаления";
    }
  } finally {
    formSubmitting.value = false;
  }
}
</script>

<template>
  <div class="p-6 max-w-[1400px] mx-auto">
    <div class="mb-4">
      <div class="uza-section-label">Администрирование</div>
      <h1 class="text-[15px] font-medium tracking-uza-snug mt-1">Компании и сектора</h1>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 mb-4 border-b border-slate-200">
      <button v-for="tab in [
                {id: 'companies', label: `Компании (${companies.length})`},
                {id: 'sectors',   label: `Сектора (${sectors.length})`},
              ]" :key="tab.id"
              @click="activeTab = tab.id as any"
              class="px-4 py-2 text-sm transition-colors relative"
              :class="activeTab === tab.id ? 'text-uza-purple font-medium' : 'text-slate-500 hover:text-slate-700'">
        {{ tab.label }}
        <span v-if="activeTab === tab.id" class="absolute bottom-0 left-0 right-0 h-0.5 bg-uza-purple"></span>
      </button>
    </div>

    <!-- TAB: COMPANIES -->
    <div v-if="activeTab === 'companies'">
      <div class="uza-card p-4 mb-4 flex items-center gap-3 flex-wrap">
        <input v-model="search" @input="onSearch" type="text" placeholder="Поиск..."
               class="flex-1 min-w-[200px] px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple focus:outline-none"/>
        <select v-model="filterSector" @change="loadCompanies"
                class="px-3 py-2 text-sm rounded-uza-pill border border-slate-200 bg-white focus:border-uza-purple">
          <option value="">Все сектора</option>
          <option v-for="s in sectors" :key="s.code" :value="s.code">{{ s.name_ru }}</option>
        </select>
        <select v-model="filterActive" @change="loadCompanies"
                class="px-3 py-2 text-sm rounded-uza-pill border border-slate-200 bg-white focus:border-uza-purple">
          <option value="active">Активные</option>
          <option value="inactive">Отключенные</option>
          <option value="all">Все</option>
        </select>
        <button v-if="canCreateCompanies" @click="toggleInlineCreate"
                class="px-4 py-2 text-sm bg-uza-purple text-white rounded-uza-pill hover:bg-uza-purple/90">
          {{ showInlineCreate ? "− Скрыть форму" : "+ Добавить компанию" }}
        </button>
      </div>

      <!-- Pack 148 D: minimal inline Add-Company form above the list. -->
      <div v-if="showInlineCreate && canCreateCompanies" class="uza-card p-4 mb-4 border border-uza-purple/30">
        <div class="uza-section-label mb-2">Новая компания</div>
        <div v-if="formError" class="text-xs text-uza-red mb-2">{{ formError }}</div>
        <div class="grid grid-cols-2 gap-2">
          <input v-model="companyForm.code" placeholder="Тикер (lowercase, напр. uzbekugol)"
                 class="px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple focus:outline-none font-mono"/>
          <input v-model="companyForm.name_short" placeholder="Короткое имя"
                 class="px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple focus:outline-none"/>
          <input v-model="companyForm.name_ru" placeholder="Полное название (RU) *"
                 class="col-span-2 px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple focus:outline-none"/>
          <select v-model="companyForm.sector_code"
                  class="px-3 py-2 text-sm rounded-uza-pill border border-slate-200 bg-white focus:border-uza-purple">
            <option value="">— выбрать сектор —</option>
            <option v-for="s in sectors" :key="s.code" :value="s.code">{{ s.name_ru }}</option>
          </select>
          <select v-model="companyForm.legal_form"
                  class="px-3 py-2 text-sm rounded-uza-pill border border-slate-200 bg-white focus:border-uza-purple">
            <option>АО</option><option>ООО</option><option>ГП</option>
          </select>
        </div>
        <div class="mt-3 flex items-center gap-2 justify-end">
          <span class="text-[10px] text-slate-500 mr-auto">
            При создании автоматически появится 1:1 группа RBAC v3 с тем же кодом — её можно
            сразу использовать для добавления пользователей.
          </span>
          <button @click="showInlineCreate = false"
                  class="px-3 py-1.5 text-xs text-slate-600 hover:text-slate-900">Отмена</button>
          <button @click="submitCreateCompany"
                  :disabled="!companyForm.code || !companyForm.name_ru || formSubmitting"
                  class="px-4 py-1.5 text-sm bg-uza-purple text-white rounded-uza-pill hover:bg-uza-purple/90 disabled:opacity-50">
            {{ formSubmitting ? "Создание…" : "Создать (с группой)" }}
          </button>
        </div>
      </div>

      <div v-if="loading" class="uza-card p-12 text-center text-slate-400 text-sm">Загрузка…</div>
      <div v-else-if="companies.length === 0" class="uza-card p-12 text-center text-slate-400 text-sm">
        Компании не найдены.
      </div>
      <div v-else class="uza-card overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50/60 border-b border-slate-100 text-[10px] uppercase tracking-uza-label2 text-slate-500">
            <tr>
              <th class="text-left px-4 py-3 font-medium">Тикер</th>
              <th class="text-left px-3 py-3 font-medium">Название</th>
              <th class="text-left px-3 py-3 font-medium">Сектор</th>
              <th class="text-center px-3 py-3 font-medium">Статус</th>
              <th class="text-center px-3 py-3 font-medium">Тип</th>
              <th class="text-right px-4 py-3 font-medium">Действия</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="c in companies" :key="c.id" class="hover:bg-slate-50/80"
                :style="!c.is_active ? { opacity: 0.5 } : {}">
              <td class="px-4 py-3 uppercase font-medium text-slate-900">{{ c.code }}</td>
              <td class="px-3 py-3">
                <div style="display:flex;align-items:center;gap:8px;">
                  <CompanyAvatar :name="c.name_short || c.code" :color="c.sector_color || '#888780'" :size="28" :logo="c.logo_url" />
                  <div style="min-width:0;">
                    <div class="text-slate-900">{{ c.name_short || c.name_ru }}</div>
                    <div class="text-xs text-slate-500">{{ c.name_ru }}</div>
                  </div>
                </div>
              </td>
              <td class="px-3 py-3 text-xs text-slate-600">{{ c.sector?.name_ru || "—" }}</td>
              <td class="px-3 py-3 text-center">
                <span v-if="c.is_active" class="inline-block px-2 py-0.5 rounded-uza-pill text-[10px]"
                      style="background:#1D9E7515;color:#1D9E75">Активна</span>
                <span v-else class="inline-block px-2 py-0.5 rounded-uza-pill text-[10px]"
                      style="background:#94A3B815;color: var(--t3, #64748B)">Отключена</span>
              </td>
              <td class="px-3 py-3 text-center text-[10px] uppercase tracking-uza-label2 text-slate-500">
                {{ (c as any).is_custom ? "Custom" : "Системная" }}
              </td>
              <td class="px-4 py-3 text-right whitespace-nowrap">
                <button v-if="canEditCompanies" @click="openEditCompany(c)"
                        class="text-uza-purple text-xs hover:underline mr-3">Изменить</button>
                <button v-if="canDeleteCompanies" @click="openDeleteCompany(c)"
                        class="text-uza-red text-xs hover:underline">Удалить</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- TAB: SECTORS -->
    <div v-else-if="activeTab === 'sectors'">
      <div class="uza-card p-4 mb-4 flex items-center justify-between">
        <div class="text-sm text-slate-600">
          {{ sectors.length }} секторов · сортировка по `sort_order`
        </div>
        <button v-if="canCreateSectors" @click="openCreateSector"
                class="px-4 py-2 text-sm bg-uza-purple text-white rounded-uza-pill hover:bg-uza-purple/90">
          + Добавить сектор
        </button>
      </div>

      <div v-if="loading" class="uza-card p-12 text-center text-slate-400 text-sm">Загрузка…</div>
      <div v-else-if="sectors.length === 0" class="uza-card p-12 text-center text-slate-400 text-sm">
        Секторов нет.
      </div>
      <div v-else class="uza-card overflow-hidden">
        <table class="w-full text-sm">
          <thead class="bg-slate-50/60 border-b border-slate-100 text-[10px] uppercase tracking-uza-label2 text-slate-500">
            <tr>
              <th class="text-left px-4 py-3 font-medium">Код</th>
              <th class="text-left px-3 py-3 font-medium">RU</th>
              <th class="text-left px-3 py-3 font-medium">UZ</th>
              <th class="text-left px-3 py-3 font-medium">EN</th>
              <th class="text-center px-3 py-3 font-medium">Цвет</th>
              <th class="text-center px-3 py-3 font-medium">Компаний</th>
              <th class="text-center px-3 py-3 font-medium">Порядок</th>
              <th class="text-right px-4 py-3 font-medium">Действия</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="s in sectors" :key="s.id" class="hover:bg-slate-50/80">
              <td class="px-4 py-3"><code class="text-xs text-slate-500">{{ s.code }}</code></td>
              <td class="px-3 py-3 font-medium">{{ s.name_ru }}</td>
              <td class="px-3 py-3 text-xs text-slate-600">{{ s.name_uz || "—" }}</td>
              <td class="px-3 py-3 text-xs text-slate-600">{{ s.name_en || "—" }}</td>
              <td class="px-3 py-3 text-center">
                <span v-if="s.color_hex" class="inline-block w-4 h-4 rounded-full align-middle"
                      :style="{ background: s.color_hex }"></span>
                <span v-else class="text-slate-300 text-xs">—</span>
              </td>
              <td class="px-3 py-3 text-center tabular-nums text-xs"
                  :class="s.company_count === 0 ? 'text-slate-400' : 'text-slate-700'">
                {{ s.company_count ?? 0 }}
              </td>
              <td class="px-3 py-3 text-center tabular-nums text-xs text-slate-500">{{ s.sort_order }}</td>
              <td class="px-4 py-3 text-right whitespace-nowrap">
                <button v-if="canEditSectors" @click="openEditSector(s)"
                        class="text-uza-purple text-xs hover:underline mr-3">Изменить</button>
                <button v-if="canDeleteSectors && s.company_count === 0" @click="openDeleteSector(s)"
                        class="text-uza-red text-xs hover:underline">Удалить</button>
                <span v-else-if="(s.company_count ?? 0) > 0" class="text-slate-300 text-xs"
                      title="Сначала переподключите компании на другой сектор">
                  Используется
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ============================== DIALOGS ============================== -->
    <!-- COMPANY: Create/Edit -->
    <div v-if="showCreateCompany || showEditCompany"
         class="fixed inset-0 bg-slate-900/45 backdrop-blur-sm flex items-center justify-center z-50 p-4"
         @click.self="showCreateCompany = false; showEditCompany = false">
      <div class="bg-white rounded-2xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div class="uza-section-label mb-3">
          {{ showCreateCompany ? "Новая компания" : `Редактирование: ${editingCompany?.name_short || editingCompany?.code}` }}
        </div>
        <div class="space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-slate-600 mb-1">Тикер (lowercase)</label>
              <input v-model="companyForm.code" type="text"
                     :readonly="showEditCompany"
                     placeholder="например: ngmk"
                     class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple font-mono"
                     :class="showEditCompany ? 'bg-slate-50 cursor-not-allowed' : ''"/>
            </div>
            <div>
              <label class="block text-xs text-slate-600 mb-1">Сектор</label>
              <select v-model="companyForm.sector_code"
                      class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 bg-white focus:border-uza-purple">
                <option value="">— не указан —</option>
                <option v-for="s in sectors" :key="s.code" :value="s.code">{{ s.name_ru }}</option>
              </select>
            </div>
          </div>
          <div>
            <label class="block text-xs text-slate-600 mb-1">Название (RU)</label>
            <input v-model="companyForm.name_ru" type="text"
                   placeholder="АО «Навоийский ГМК»"
                   class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple"/>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-slate-600 mb-1">Короткое имя</label>
              <input v-model="companyForm.name_short" type="text"
                     placeholder="НГМК"
                     class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple"/>
            </div>
            <div>
              <label class="block text-xs text-slate-600 mb-1">Правовая форма</label>
              <select v-model="companyForm.legal_form"
                      class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 bg-white focus:border-uza-purple">
                <option value="АО">АО</option>
                <option value="ГП">ГП</option>
                <option value="ООО">ООО</option>
                <option value="">— не указано —</option>
              </select>
            </div>
          </div>
          <div>
            <label class="block text-xs text-slate-600 mb-1">Название (UZ кириллица)</label>
            <input v-model="companyForm.name_uz" type="text"
                   placeholder="“Навоий КМК” АЖ"
                   class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple"/>
          </div>
          <div>
            <label class="block text-xs text-slate-600 mb-1">Название (EN)</label>
            <input v-model="companyForm.name_en" type="text"
                   placeholder='"Navoiy MMC" JSC'
                   class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple"/>
          </div>
          <label v-if="showEditCompany" class="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
            <input v-model="companyForm.is_active" type="checkbox"/>
            Активна
          </label>

          <!-- Логотип компании -->
          <div v-if="showEditCompany" class="ca-logo-block">
            <div class="ca-logo-preview" :class="{ empty: !companyForm.logo_url }">
              <img v-if="companyForm.logo_url" :src="companyForm.logo_url" alt="лого" />
              <span v-else>нет лого</span>
            </div>
            <div class="ca-logo-side">
              <div class="ca-logo-label">Логотип</div>
              <div class="ca-logo-hint">
                PNG с прозрачным фоном, <b>квадрат 1:1</b>, минимум <b>256×256px</b>
                (рекомендуется 512×512). Система ужмёт до 256px. Отображается 24–64px.
              </div>
              <div class="ca-logo-acts">
                <button type="button" class="ca-logo-btn" @click="logoInput?.click()">Загрузить</button>
                <button v-if="companyForm.logo_url" type="button" class="ca-logo-btn ca-logo-del" @click="removeLogo">Удалить</button>
              </div>
              <input ref="logoInput" type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" style="display:none" @change="onLogoPick" />
            </div>
          </div>

          <!-- Per-year visibility: скрыть компанию и её данные из выбранных годов -->
          <div v-if="showEditCompany" class="ca-hide-block">
            <div class="ca-hide-label">Скрыть из годов</div>
            <div class="ca-hide-sub">В отмеченных годах компания и все её данные не показываются на дашбордах.</div>
            <div class="ca-hide-years">
              <button v-for="y in yearOptions" :key="y" type="button"
                      :class="['ca-hide-year', { on: (companyForm.hidden_years || []).includes(y) }]"
                      @click="toggleHiddenYear(y)">{{ y }}</button>
            </div>
          </div>

          <div v-if="formError" class="text-uza-red text-xs">{{ formError }}</div>
          <div class="flex gap-2 justify-end pt-2">
            <button @click="showCreateCompany = false; showEditCompany = false"
                    class="px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 rounded-uza-pill">Отмена</button>
            <button @click="showCreateCompany ? submitCreateCompany() : submitEditCompany()"
                    :disabled="formSubmitting || !companyForm.code || !companyForm.name_ru"
                    class="px-4 py-2 text-sm bg-uza-purple text-white rounded-uza-pill hover:bg-uza-purple/90 disabled:opacity-40">
              {{ formSubmitting ? "Сохранение…" : (showCreateCompany ? "Создать" : "Сохранить") }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- COMPANY: Delete confirmation -->
    <div v-if="showDeleteCompany"
         class="fixed inset-0 bg-slate-900/45 backdrop-blur-sm flex items-center justify-center z-50 p-4"
         @click.self="showDeleteCompany = false">
      <div class="bg-white rounded-2xl p-6 max-w-md w-full">
        <div class="uza-section-label mb-1">Удаление компании</div>
        <div class="text-sm text-slate-700 mb-4">
          {{ editingCompany?.name_short || editingCompany?.code }} ({{ editingCompany?.code }})
        </div>
        <div class="space-y-3 text-sm">
          <label class="flex items-start gap-2 cursor-pointer p-3 rounded-xl border-2"
                 :class="!deleteCascade ? 'border-uza-purple bg-uza-purple/5' : 'border-slate-200'">
            <input v-model="deleteCascade" type="radio" :value="false" class="mt-0.5"/>
            <div>
              <div class="font-medium">Деактивировать (рекомендуется)</div>
              <div class="text-xs text-slate-500 mt-0.5">
                Компания скрывается из активных списков, но все данные сохраняются.
                Можно вернуть установив «Активна».
              </div>
            </div>
          </label>
          <label class="flex items-start gap-2 cursor-pointer p-3 rounded-xl border-2"
                 :class="deleteCascade ? 'border-uza-red bg-red-50' : 'border-slate-200'"
                 v-if="canCascadeDelete">
            <input v-model="deleteCascade" type="radio" :value="true" class="mt-0.5"/>
            <div>
              <div class="font-medium text-uza-red">Полное удаление (необратимо)</div>
              <div class="text-xs text-slate-500 mt-0.5">
                Удаляет компанию И ВСЕ связанные данные: финансы, рейтинги, задачи, проекты.
                Только владелец платформы.
              </div>
            </div>
          </label>
          <div v-if="formError" class="text-uza-red text-xs">{{ formError }}</div>
          <div class="flex gap-2 justify-end pt-2">
            <button @click="showDeleteCompany = false"
                    class="px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 rounded-uza-pill">Отмена</button>
            <button @click="submitDeleteCompany" :disabled="formSubmitting"
                    class="px-4 py-2 text-sm rounded-uza-pill text-white disabled:opacity-40"
                    :class="deleteCascade ? 'bg-uza-red hover:bg-red-700' : 'bg-uza-amber hover:bg-amber-600'">
              {{ formSubmitting ? "Удаление…" : (deleteCascade ? "Удалить полностью" : "Деактивировать") }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- SECTOR: Create/Edit -->
    <div v-if="showCreateSector || showEditSector"
         class="fixed inset-0 bg-slate-900/45 backdrop-blur-sm flex items-center justify-center z-50 p-4"
         @click.self="showCreateSector = false; showEditSector = false">
      <div class="bg-white rounded-2xl p-6 max-w-md w-full">
        <div class="uza-section-label mb-3">
          {{ showCreateSector ? "Новый сектор" : `Редактирование: ${editingSector?.name_ru}` }}
        </div>
        <div class="space-y-3">
          <div>
            <label class="block text-xs text-slate-600 mb-1">Код (latin lowercase)</label>
            <input v-model="sectorForm.code" type="text"
                   :readonly="showEditSector"
                   placeholder="например: mining_metallurgy"
                   class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple font-mono"
                   :class="showEditSector ? 'bg-slate-50 cursor-not-allowed' : ''"/>
          </div>
          <div>
            <label class="block text-xs text-slate-600 mb-1">Название (RU)</label>
            <input v-model="sectorForm.name_ru" type="text"
                   class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple"/>
          </div>
          <div>
            <label class="block text-xs text-slate-600 mb-1">Название (UZ кириллица)</label>
            <input v-model="sectorForm.name_uz" type="text"
                   class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple"/>
          </div>
          <div>
            <label class="block text-xs text-slate-600 mb-1">Название (EN)</label>
            <input v-model="sectorForm.name_en" type="text"
                   class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple"/>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-slate-600 mb-1">Цвет (hex)</label>
              <input v-model="sectorForm.color_hex" type="text" placeholder="#7F77DD"
                     class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple font-mono"/>
            </div>
            <div>
              <label class="block text-xs text-slate-600 mb-1">Порядок</label>
              <input v-model.number="sectorForm.sort_order" type="number"
                     class="w-full px-3 py-2 text-sm rounded-uza-pill border border-slate-200 focus:border-uza-purple"/>
            </div>
          </div>
          <div v-if="formError" class="text-uza-red text-xs">{{ formError }}</div>
          <div class="flex gap-2 justify-end pt-2">
            <button @click="showCreateSector = false; showEditSector = false"
                    class="px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 rounded-uza-pill">Отмена</button>
            <button @click="showCreateSector ? submitCreateSector() : submitEditSector()"
                    :disabled="formSubmitting || !sectorForm.code || !sectorForm.name_ru"
                    class="px-4 py-2 text-sm bg-uza-purple text-white rounded-uza-pill hover:bg-uza-purple/90 disabled:opacity-40">
              {{ formSubmitting ? "Сохранение…" : (showCreateSector ? "Создать" : "Сохранить") }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- SECTOR: Delete confirmation -->
    <div v-if="showDeleteSector"
         class="fixed inset-0 bg-slate-900/45 backdrop-blur-sm flex items-center justify-center z-50 p-4"
         @click.self="showDeleteSector = false">
      <div class="bg-white rounded-2xl p-6 max-w-md w-full">
        <div class="uza-section-label mb-1">Удаление сектора</div>
        <div class="text-sm text-slate-700 mb-3">
          {{ editingSector?.name_ru }} (<code>{{ editingSector?.code }}</code>)
        </div>
        <div class="text-xs text-slate-500 mb-3">
          Удаление возможно только если сектор не содержит активных компаний.
        </div>
        <div v-if="formError" class="text-uza-red text-xs mb-3">{{ formError }}</div>
        <div class="flex gap-2 justify-end">
          <button @click="showDeleteSector = false"
                  class="px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 rounded-uza-pill">Отмена</button>
          <button @click="submitDeleteSector" :disabled="formSubmitting"
                  class="px-4 py-2 text-sm bg-uza-red text-white rounded-uza-pill hover:bg-red-700 disabled:opacity-40">
            {{ formSubmitting ? "Удаление…" : "Удалить" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ca-logo-block { display: flex; gap: 14px; padding: 12px; border: 1px solid var(--border-hard, #E5E7EB); border-radius: 11px; background: var(--bg2, #F8FAFC); }
.ca-logo-preview { width: 72px; height: 72px; flex-shrink: 0; border-radius: 14px; background: #fff; border: 1px solid var(--border-hard, #E5E7EB); display: flex; align-items: center; justify-content: center; overflow: hidden; }
.ca-logo-preview.empty { font-size: 10px; color: var(--t3, #94A3B8); }
.ca-logo-preview img { width: 100%; height: 100%; object-fit: contain; padding: 8px; box-sizing: border-box; }
.ca-logo-side { flex: 1; min-width: 0; }
.ca-logo-label { font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A); }
.ca-logo-hint { font-size: 11px; color: var(--t3, #94A3B8); margin: 3px 0 8px; line-height: 1.45; }
.ca-logo-acts { display: flex; gap: 8px; }
.ca-logo-btn { padding: 5px 12px; border-radius: 8px; border: 1px solid var(--border-input, #E2E8F0); background: #fff; font-size: 11.5px; font-weight: 600; color: var(--p-deep, #534AB7); cursor: pointer; font-family: inherit; transition: all .13s; }
.ca-logo-btn:hover { border-color: var(--p, #7C6FF7); background: rgba(124,111,247,.06); }
.ca-logo-del { color: var(--sev-high, #E24B4A); }
.ca-logo-del:hover { border-color: var(--sev-high, #E24B4A); background: rgba(226,75,74,.06); }

.ca-hide-block { padding: 12px; border: 1px solid var(--border-hard, #E5E7EB); border-radius: 11px; background: var(--bg2, #F8FAFC); }
.ca-hide-label { font-size: 12px; font-weight: 600; color: var(--t1, #1E2A4A); }
.ca-hide-sub { font-size: 11px; color: var(--t3, #94A3B8); margin: 2px 0 9px; line-height: 1.4; }
.ca-hide-years { display: flex; flex-wrap: wrap; gap: 6px; }
.ca-hide-year { padding: 5px 13px; border-radius: 8px; border: 1px solid var(--border-input, #E2E8F0); background: #fff; font-size: 12.5px; font-weight: 600; color: var(--t2, #475569); cursor: pointer; font-family: inherit; transition: all .13s; }
.ca-hide-year:hover { border-color: var(--sev-high, #E24B4A); }
.ca-hide-year.on { background: rgba(226,75,74,.10); border-color: rgba(226,75,74,.45); color: #C0392B; }
</style>
