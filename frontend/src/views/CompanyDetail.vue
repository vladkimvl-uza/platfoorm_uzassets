<script setup lang="ts">
import { ref, onMounted, computed, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import { companiesApi } from "@/api/companies";
import { ratingsApi } from "@/api/ratings";
import type { CompanyRatingsResponse } from "@/api/ratings";
import type {
  CompanyDetail,
  FinancialReportBrief,
  GovernanceBrief,
} from "@/api/companies";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const route   = useRoute();
const router  = useRouter();
const code    = computed(() => String(route.params.code || "").toLowerCase());

const company   = ref<CompanyDetail | null>(null);
const financials = ref<FinancialReportBrief[]>([]);
const governance = ref<GovernanceBrief[]>([]);
const ratings   = ref<CompanyRatingsResponse | null>(null);
const loading   = ref(true);
const error     = ref<string | null>(null);

const activeTab = ref<"overview" | "financials" | "governance" | "ratings">("overview");
const tabs = computed(() => [
  { id: "overview" as const, label: t("Обзор") },
  { id: "financials" as const, label: t("Финансы"), count: financials.value.length },
  { id: "governance" as const, label: t("Управление"), count: governance.value.length },
  { id: "ratings" as const, label: t("Рейтинги"), count: (ratings.value?.credit.length || 0) + (ratings.value?.esg.length || 0) },
]);

async function loadAll() {
  loading.value = true;
  error.value = null;
  try {
    company.value = await companiesApi.getOne(code.value);
    // Fetch in parallel — silently swallow individual errors so page still renders
    const [fin, gov, rat] = await Promise.allSettled([
      companiesApi.getFinancials(code.value),
      companiesApi.getGovernance(code.value),
      ratingsApi.getCompanyRatings(code.value),
    ]);
    if (fin.status === "fulfilled") financials.value = fin.value;
    if (gov.status === "fulfilled") governance.value = gov.value;
    if (rat.status === "fulfilled") ratings.value = rat.value;
  } catch (e: any) {
    error.value = e?.response?.status === 404 ? t('Компания «{value0}» не найдена', { value0: code.value }) : (e?.response?.data?.detail || e?.message || t('Не удалось загрузить компанию'));
  } finally {
    loading.value = false;
  }
}

onMounted(loadAll);
watch(code, loadAll);

// Helpers
function fmtNum(value: string | number | null | undefined): string {
  if (value == null || value === "") return "—";
  const n = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(n)) return "—";
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(n);
}

function scoreColor(score: number | null | undefined): string {
  if (score == null) return "#94a3b8";
  if (score >= 850) return "#1D9E75";
  if (score >= 700) return "#378ADD";
  if (score >= 600) return "#EF9F27";
  return "#E24B4A";
}

const latestGov = computed(() => governance.value[0] || null);
const latestFin = computed(() => financials.value[0] || null);

const latestRevenue = computed(() => {
  if (!latestFin.value) return null;
  const revLine = latestFin.value.lines.find(l => l.line_code === "REVENUE");
  return revLine?.value;
});

function backToList() {
  void router.back();
}
</script>

<template>
  <div class="uza-page">
    <!-- Loading -->
    <div v-if="loading" class="uza-card p-12 text-center text-slate-400 text-sm">
      {{ t('Загрузка…') }}
    </div>

    <!-- Error -->
    <div v-else-if="error" class="uza-card p-6">
      <div class="text-uza-red text-sm">{{ error }}</div>
      <button @click="backToList" class="mt-4 text-xs text-uza-purple hover:underline">
        {{ t('← Назад к списку') }}
      </button>
    </div>

    <!-- Content -->
    <template v-else-if="company">
      <!-- Breadcrumbs -->
      <nav class="flex items-center gap-2 text-xs text-slate-400 mb-4">
        <span class="text-slate-600">{{ company.name_short || company.code.toUpperCase() }}</span>
      </nav>

      <!-- Header card -->
      <div
        class="uza-card p-6 mb-4"
        :style="company.sector?.color_hex ? { 'border-top': `3px solid ${company.sector.color_hex}` } : {}"
      >
        <div class="flex items-start justify-between gap-4 flex-wrap">
          <div class="flex-1 min-w-[300px]">
            <div class="uza-section-label">{{ company.code.toUpperCase() }}</div>
            <h1 class="text-[22px] font-normal text-slate-900 tracking-uza-tight mt-1">
              {{ company.name_short || company.name_ru }}
            </h1>
            <div v-if="company.name_short && company.name_ru !== company.name_short"
                 class="text-sm text-slate-500 mt-1">
              {{ company.name_ru }}
            </div>
            <div class="flex items-center gap-3 mt-3 flex-wrap">
              <span
                v-if="company.sector"
                class="inline-block px-2 py-0.5 text-[11px] rounded-uza-pill"
                :style="{ background: (company.sector.color_hex || '#777') + '15', color: company.sector.color_hex || '#777' }"
              >{{ company.sector.name_ru }}</span>

              <span
                v-if="company.is_custom"
                class="inline-block px-2 py-0.5 text-[10px] uppercase tracking-uza-label2 rounded font-medium bg-purple-50 text-uza-purple"
              >{{ t('Пользовательская') }}</span>

              <span
                v-if="!company.is_active"
                class="inline-block px-2 py-0.5 text-[10px] uppercase tracking-uza-label2 rounded font-medium bg-red-50 text-uza-red"
              >{{ t('Неактивна') }}</span>
            </div>
          </div>

          <!-- Quick stats -->
          <div class="flex gap-6 flex-wrap">
            <div v-if="latestRevenue">
              <div class="uza-section-label">{{ t('Выручка (') }}{{ latestFin?.year }})</div>
              <div class="text-[22px] font-normal text-slate-900 tabular-nums tracking-uza-tight mt-1">
                <span v-count-up="{ value: latestRevenue, decimals: 0, thousandSep: true, key: `co-rev-${$route.params.code}` }">0</span>
              </div>
              <div class="text-[10px] text-slate-400 uppercase tracking-uza-label2">{{ t('тыс. сум') }}</div>
            </div>
            <div v-if="latestGov?.score">
              <div class="uza-section-label">Governance ({{ latestGov.year }})</div>
              <div
                class="text-[22px] font-normal tabular-nums tracking-uza-tight mt-1"
                :style="{ color: scoreColor(latestGov.score) }"
              ><span v-count-up="{ value: latestGov.score, key: `co-gov-${$route.params.code}` }">0</span></div>
              <div class="text-[10px] text-slate-400 uppercase tracking-uza-label2">{{ t('из 1000') }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tabs -->
      <div class="flex border-b border-slate-200 mb-4 -mx-2 px-2">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id as any"
          class="px-4 py-2 text-sm transition-colors"
          :class="activeTab === tab.id
            ? 'text-uza-purple border-b-2 border-uza-purple -mb-px font-medium'
            : 'text-slate-500 hover:text-slate-700'"
        >
          {{ tab.label }}
          <span v-if="tab.count" class="ml-1 text-[10px] tabular-nums">({{ tab.count }})</span>
        </button>
      </div>

      <!-- Tab: Overview -->
      <div v-if="activeTab === 'overview'" class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="uza-card p-5">
          <div class="uza-section-label mb-3">{{ t('Основная информация') }}</div>
          <dl class="text-sm space-y-2">
            <div class="flex justify-between gap-4">
              <dt class="text-slate-500">{{ t('Код') }}</dt>
              <dd class="tabular-nums">{{ company.code.toUpperCase() }}</dd>
            </div>
            <div v-if="company.legal_form" class="flex justify-between gap-4">
              <dt class="text-slate-500">{{ t('Форма') }}</dt>
              <dd>{{ company.legal_form }}</dd>
            </div>
            <div v-if="company.inn" class="flex justify-between gap-4">
              <dt class="text-slate-500">{{ t('ИНН') }}</dt>
              <dd class="tabular-nums">{{ company.inn }}</dd>
            </div>
            <div v-if="company.founded_year" class="flex justify-between gap-4">
              <dt class="text-slate-500">{{ t('Основана') }}</dt>
              <dd class="tabular-nums">{{ company.founded_year }}</dd>
            </div>
            <div v-if="company.employees_count" class="flex justify-between gap-4">
              <dt class="text-slate-500">{{ t('Сотрудников') }}</dt>
              <dd class="tabular-nums">{{ fmtNum(company.employees_count) }}</dd>
            </div>
            <div v-if="company.ceo_name" class="flex justify-between gap-4">
              <dt class="text-slate-500">CEO</dt>
              <dd>{{ company.ceo_name }}</dd>
            </div>
            <div v-if="company.website" class="flex justify-between gap-4">
              <dt class="text-slate-500">{{ t('Сайт') }}</dt>
              <dd><a :href="company.website" target="_blank" class="text-uza-blue hover:underline">{{ company.website }}</a></dd>
            </div>
          </dl>
        </div>

        <div v-if="company.description || latestGov" class="uza-card p-5">
          <div class="uza-section-label mb-3">{{ t('Сводка') }}</div>
          <p v-if="company.description" class="text-sm text-slate-700 leading-relaxed mb-3">
            {{ company.description }}
          </p>
          <div v-if="latestGov" class="text-sm space-y-2">
            <div class="flex justify-between gap-4">
              <span class="text-slate-500">{{ t('Совет директоров') }}</span>
              <span class="tabular-nums">{{ latestGov.board_size || "—" }}</span>
            </div>
            <div class="flex justify-between gap-4">
              <span class="text-slate-500">{{ t('Независимые') }}</span>
              <span class="tabular-nums">{{ latestGov.independent_directors_count || "—" }}</span>
            </div>
            <div class="flex justify-between gap-4">
              <span class="text-slate-500">{{ t('Женщины в совете') }}</span>
              <span class="tabular-nums">{{ latestGov.women_directors_count || "—" }}</span>
            </div>
            <div class="flex justify-between gap-4">
              <span class="text-slate-500">{{ t('Заседаний в год') }}</span>
              <span class="tabular-nums">{{ latestGov.meetings_per_year || "—" }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab: Financials -->
      <div v-else-if="activeTab === 'financials'" class="uza-card overflow-hidden">
        <div v-if="financials.length === 0" class="p-12 text-center text-slate-400 text-sm">
          {{ t('Финансовая отчётность не загружена.') }}
        </div>
        <table v-else class="w-full text-sm">
          <thead class="bg-slate-50/60 border-b border-slate-100 text-[10px] uppercase tracking-uza-label2 text-slate-500">
            <tr>
              <th class="text-left px-4 py-3 font-medium">{{ t('Период') }}</th>
              <th class="text-left px-3 py-3 font-medium">{{ t('Стандарт') }}</th>
              <th class="text-right px-3 py-3 font-medium">{{ t('Выручка') }}</th>
              <th class="text-right px-3 py-3 font-medium">{{ t('Прибыль') }}</th>
              <th class="text-center px-3 py-3 font-medium">{{ t('Аудит') }}</th>
              <th class="text-center px-3 py-3 font-medium">{{ t('Источник') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="r in financials" :key="`${r.year}-${r.quarter || 0}-${r.standard}`" class="hover:bg-slate-50/80">
              <td class="px-4 py-3 font-medium tabular-nums">
                {{ r.year }}{{ r.quarter ? ` Q${r.quarter}` : "" }}
              </td>
              <td class="px-3 py-3 text-xs uppercase tracking-uza-label2 text-slate-600">
                {{ r.standard }}
              </td>
              <td class="px-3 py-3 text-right tabular-nums text-xs">
                {{ fmtNum(r.lines.find(l => l.line_code === "REVENUE")?.value) }}
              </td>
              <td class="px-3 py-3 text-right tabular-nums text-xs">
                {{ fmtNum(r.lines.find(l => l.line_code === "PROFIT" || l.line_code === "NET_PROFIT")?.value) }}
              </td>
              <td class="px-3 py-3 text-center text-xs">
                <span v-if="r.is_audited" class="text-uza-teal">✓</span>
                <span v-else class="text-slate-300">—</span>
              </td>
              <td class="px-3 py-3 text-center text-xs text-slate-500">{{ r.source }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Tab: Governance -->
      <div v-else-if="activeTab === 'governance'" class="uza-card overflow-hidden">
        <div v-if="governance.length === 0" class="p-12 text-center text-slate-400 text-sm">
          {{ t('Данные по корпоративному управлению не загружены.') }}
        </div>
        <table v-else class="w-full text-sm">
          <thead class="bg-slate-50/60 border-b border-slate-100 text-[10px] uppercase tracking-uza-label2 text-slate-500">
            <tr>
              <th class="text-left px-4 py-3 font-medium">{{ t('Год') }}</th>
              <th class="text-center px-3 py-3 font-medium">{{ t('Совет') }}</th>
              <th class="text-center px-3 py-3 font-medium">{{ t('Незав.') }}</th>
              <th class="text-center px-3 py-3 font-medium">{{ t('Жен.') }}</th>
              <th class="text-center px-3 py-3 font-medium">{{ t('Иностр.') }}</th>
              <th class="text-center px-3 py-3 font-medium">{{ t('Заседаний') }}</th>
              <th class="text-center px-3 py-3 font-medium">{{ t('Комитеты') }}</th>
              <th class="text-right px-4 py-3 font-medium">Score</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            <tr v-for="g in governance" :key="g.year" class="hover:bg-slate-50/80">
              <td class="px-4 py-3 font-medium tabular-nums">{{ g.year }}</td>
              <td class="px-3 py-3 text-center tabular-nums">{{ g.board_size || "—" }}</td>
              <td class="px-3 py-3 text-center tabular-nums">{{ g.independent_directors_count || "—" }}</td>
              <td class="px-3 py-3 text-center tabular-nums">{{ g.women_directors_count || "—" }}</td>
              <td class="px-3 py-3 text-center tabular-nums">{{ g.foreign_directors_count || "—" }}</td>
              <td class="px-3 py-3 text-center tabular-nums">{{ g.meetings_per_year || "—" }}</td>
              <td class="px-3 py-3 text-center text-xs">
                <span v-if="g.has_audit_committee" :title="t('Аудит')" class="text-uza-teal mr-1">{{ t('А') }}</span>
                <span v-if="g.has_strategy_committee" :title="t('Стратегия')" class="text-uza-blue">{{ t('С') }}</span>
              </td>
              <td class="px-4 py-3 text-right">
                <span
                  v-if="g.score != null"
                  class="inline-block px-2 py-0.5 text-[11px] font-medium rounded-uza-pill tabular-nums"
                  :style="{ background: scoreColor(g.score) + '15', color: scoreColor(g.score) }"
                >{{ g.score }}</span>
                <span v-else class="text-slate-400">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Tab: Ratings -->
      <div v-else-if="activeTab === 'ratings'" class="space-y-4">
        <div v-if="!ratings || (ratings.credit.length === 0 && ratings.esg.length === 0)"
             class="uza-card p-12 text-center text-slate-400 text-sm">
          {{ t('У компании нет публичных рейтингов.') }}
        </div>
        <template v-else>
          <!-- Credit ratings -->
          <div v-if="ratings.credit.length > 0" class="uza-card p-5">
            <div class="uza-section-label mb-3">{{ t('Кредитные рейтинги') }}</div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div v-for="r in ratings.credit" :key="r.id"
                   class="border border-slate-100 rounded-xl p-4 hover:border-slate-200 transition-colors">
                <div class="flex items-center justify-between gap-2 mb-2">
                  <div class="text-[10px] uppercase tracking-uza-label2 text-slate-500">{{ r.agency }}</div>
                  <a v-if="r.report_url" :href="r.report_url" target="_blank"
                     class="text-[10px] text-uza-purple hover:underline">{{ t('отчёт ↗') }}</a>
                </div>
                <div class="text-[28px] font-normal tracking-uza-tight text-slate-900">
                  {{ r.rating || "—" }}
                </div>
                <div v-if="r.outlook" class="text-xs mt-1"
                     :style="{ color: r.outlook === 'Positive' ? '#1D9E75' : r.outlook === 'Negative' ? '#E24B4A' : r.outlook === 'Developing' ? '#EF9F27' : '#64748B' }">
                  {{ r.outlook }}
                </div>
                <div v-if="r.rating_date_text" class="text-[10px] text-slate-400 mt-1 tabular-nums">
                  {{ r.rating_date_text }}
                </div>
              </div>
            </div>
          </div>

          <!-- ESG ratings -->
          <div v-if="ratings.esg.length > 0" class="uza-card p-5">
            <div class="uza-section-label mb-3">{{ t('ESG-рейтинги') }}</div>
            <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div v-for="r in ratings.esg" :key="r.id"
                   class="border border-slate-100 rounded-xl p-4 hover:border-slate-200 transition-colors">
                <div class="flex items-center justify-between gap-2 mb-2">
                  <div class="text-[10px] uppercase tracking-uza-label2 text-uza-teal">{{ r.agency }}</div>
                  <a v-if="r.report_url" :href="r.report_url" target="_blank"
                     class="text-[10px] text-uza-purple hover:underline">{{ t('отчёт ↗') }}</a>
                </div>
                <div class="flex items-baseline gap-2">
                  <div class="text-[28px] font-normal tracking-uza-tight text-slate-900">
                    {{ r.rating || "—" }}
                  </div>
                  <div v-if="r.score" class="text-[15px] text-slate-500 tabular-nums">
                    score <span v-count-up="{ value: r.score, decimals: 0, key: `esg-score-${r.id}` }">0</span>
                  </div>
                </div>
                <div v-if="r.outlook" class="text-xs mt-1 text-slate-500">{{ r.outlook }}</div>
                <div v-if="r.rating_date_text" class="text-[10px] text-slate-400 mt-1 tabular-nums">
                  {{ r.rating_date_text }}
                </div>
              </div>
            </div>
          </div>
        </template>
      </div>
    </template>
  </div>
</template>
