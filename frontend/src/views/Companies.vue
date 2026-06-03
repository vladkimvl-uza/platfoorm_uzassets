<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRouter } from "vue-router";
import { companiesApi } from "@/api/companies";
import type { CompanyListItem, SectorBrief } from "@/api/companies";
import CompanyAvatar from "@/components/CompanyAvatar.vue";

const router = useRouter();

const items   = ref<CompanyListItem[]>([]);
const sectors = ref<SectorBrief[]>([]);
const total   = ref(0);
const loading = ref(true);
const error   = ref<string | null>(null);

const search         = ref("");
const sectorFilter   = ref<string>("");
const sortBy         = ref<"sort_order" | "name_ru" | "governance_score" | "latest_revenue">("sort_order");
const sortDir        = ref<"asc" | "desc">("asc");
const showCustomOnly = ref<boolean | null>(null);

let searchTimer: number | null = null;

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const resp = await companiesApi.list({
      search: search.value.trim() || undefined,
      sector: sectorFilter.value || undefined,
      sort_by: sortBy.value,
      sort_dir: sortDir.value,
      is_custom: showCustomOnly.value,
      limit: 100,
    });
    items.value   = resp.items;
    sectors.value = resp.sectors;
    total.value   = resp.total;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить компании";
  } finally {
    loading.value = false;
  }
}

onMounted(load);

watch(search, () => {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = window.setTimeout(load, 250);
});
watch([sectorFilter, sortBy, sortDir, showCustomOnly], load);

function setSort(field: typeof sortBy.value) {
  if (sortBy.value === field) sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
  else { sortBy.value = field; sortDir.value = "asc"; }
}

function fmtRevenue(uzs: number | null, year: number | null): string {
  if (!uzs) return "—";
  const bn = uzs / 1_000_000_000;
  const formatted = bn >= 1000 ? `${(bn / 1000).toFixed(1)} трлн` : `${bn.toFixed(0)} млрд`;
  return year ? `${formatted} (${year})` : formatted;
}

function scoreColor(score: number | null): string {
  if (score == null) return "#94a3b8";
  if (score >= 850) return "#1D9E75";
  if (score >= 700) return "#378ADD";
  if (score >= 600) return "#EF9F27";
  return "#E24B4A";
}

function openCompany(code: string) {
  void router.push({ name: "company-detail", params: { code } });
}

function sortIcon(f: typeof sortBy.value): string {
  if (sortBy.value !== f) return "";
  return sortDir.value === "asc" ? " ↑" : " ↓";
}
</script>

<template>
  <div class="uza-page">
    <!-- Header -->
    <div style="margin-bottom: 14px; display: flex; align-items: end; justify-content: space-between;">
      <div>
        <div class="uza-section-label">Портфель</div>
        <h1 style="font-size: 18px; font-weight: 500; color: var(--t1);
                   letter-spacing: -.02em; margin-top: 2px;">Компании</h1>
        <div style="font-size: 11px; color: var(--t3); margin-top: 3px;">
          <span v-count-up="total">0</span> {{ total === 1 ? "компания" : "компаний" }}
          <span v-if="sectorFilter || search" style="color: #7C6FF7;">· фильтр активен</span>
        </div>
      </div>
    </div>

    <!-- Filter bar -->
    <div class="uza-section" style="padding: 14px 18px; margin-bottom: 14px;
                                     animation: uzaCardIn .55s cubic-bezier(0.34, 1.2, 0.64, 1) 80ms both;">
      <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 220px; position: relative;">
          <input v-model="search" type="text" placeholder="Поиск по коду, имени…"
                 class="uza-input" style="padding-right: 30px;" />
          <button v-if="search" @click="search = ''"
                  style="position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
                         color: var(--t3); border: none; background: transparent;
                         font-size: 14px; cursor: pointer; line-height: 1;
                         padding: 2px 6px; border-radius: 4px;
                         transition: background .12s, color .12s;"
                  onmouseover="this.style.background='rgba(15,23,60,.06)'; this.style.color='var(--t1)'"
                  onmouseout="this.style.background='transparent'; this.style.color='var(--t3)'">×</button>
        </div>

        <select v-model="sectorFilter" class="uza-input" style="width: auto; min-width: 180px;">
          <option value="">Все секторы</option>
          <option v-for="s in sectors" :key="s.code" :value="s.code">{{ s.name_ru }}</option>
        </select>

        <select v-model="showCustomOnly" class="uza-input" style="width: auto; min-width: 200px;">
          <option :value="null">Все компании</option>
          <option :value="false">Только канонические</option>
          <option :value="true">Только пользовательские</option>
        </select>

        <button v-if="search || sectorFilter || showCustomOnly !== null"
                @click="search=''; sectorFilter=''; showCustomOnly=null"
                class="btn-s">Сбросить</button>
      </div>
    </div>

    <!-- Loading / error / empty -->
    <div v-if="loading" class="uza-card" style="padding: 60px; text-align: center;
                                                 color: var(--t3); font-size: 12px;">
      <span class="uza-spinner" style="width: 20px; height: 20px;"></span>
      <div style="margin-top: 10px;">Загрузка…</div>
    </div>

    <div v-else-if="error" class="uza-card"
         style="padding: 18px; color: #B91C1C; font-size: 13px;
                background: rgba(239, 68, 68, .04);
                border-color: rgba(239, 68, 68, .25);">
      {{ error }}
    </div>

    <div v-else-if="items.length === 0" class="uza-card"
         style="padding: 60px; text-align: center; color: var(--t3); font-size: 12px;">
      Компаний по заданным фильтрам не найдено.
    </div>

    <!-- Table -->
    <div v-else class="uza-section" style="padding: 0; overflow: hidden;
                                            animation: uzaCardIn .55s cubic-bezier(0.34, 1.2, 0.64, 1) 160ms both;">
      <div style="overflow-x: auto;">
        <table class="uza-table">
          <thead>
            <tr>
              <th @click="setSort('name_ru')" style="cursor: pointer; user-select: none;">
                Компания{{ sortIcon("name_ru") }}
              </th>
              <th>Сектор</th>
              <th class="num" @click="setSort('latest_revenue')" style="cursor: pointer; user-select: none;">
                Выручка{{ sortIcon("latest_revenue") }}
              </th>
              <th @click="setSort('governance_score')"
                  style="cursor: pointer; user-select: none; text-align: center;">
                Governance{{ sortIcon("governance_score") }}
              </th>
              <th style="text-align: center; width: 110px;">Данные</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(c, idx) in items" :key="c.code"
                @click="openCompany(c.code)"
                style="cursor: pointer; animation: paRateIn .42s cubic-bezier(0.34, 1.2, 0.64, 1) both;"
                :style="{
                  animationDelay: `${200 + idx * 25}ms`,
                  position: 'relative',
                }">
              <td style="padding-left: 18px;">
                <span class="uza-stripe-el" :style="{ '--stripe-color': c.sector_color || 'transparent' }" />
                <div style="display:flex; align-items:center; gap:10px;">
                  <CompanyAvatar :name="c.name_short || c.code" :color="c.sector_color || '#888780'" :size="30" />
                  <div style="min-width:0;">
                    <div style="font-weight: 500; color: var(--t1);">
                      {{ c.name_short || c.code.toUpperCase() }}
                    </div>
                    <div style="font-size: 11px; color: var(--t3); margin-top: 1px;">
                      {{ c.name_ru }}
                    </div>
                  </div>
                </div>
              </td>
              <td>
                <span v-if="c.sector_name" class="uza-pill"
                      :style="c.sector_color ? {
                        background: c.sector_color + '15',
                        color: c.sector_color,
                      } : {}">
                  {{ c.sector_name }}
                </span>
                <span v-else style="font-size: 11px; color: var(--t3);">—</span>
              </td>
              <td class="num" style="font-size: 11.5px; color: var(--t2);">
                {{ fmtRevenue(c.latest_revenue, c.latest_revenue_year) }}
              </td>
              <td style="text-align: center;">
                <span v-if="c.governance_score != null"
                      style="display: inline-block; padding: 1px 9px; font-size: 12px;
                             font-weight: 500; border-radius: 11px;
                             font-variant-numeric: tabular-nums;"
                      :style="{
                        background: scoreColor(c.governance_score) + '15',
                        color: scoreColor(c.governance_score),
                      }">
                  <span v-count-up="{ value: c.governance_score, key: `co-gov-${c.code}` }">0</span>
                </span>
                <span v-else style="font-size: 11px; color: var(--t3);">—</span>
              </td>
              <td style="text-align: center;">
                <div style="display: inline-flex; gap: 3px;">
                  <span v-if="c.has_financials" class="uza-pill uza-pill-blue"
                        style="font-size: 9px; padding: 1px 5px;" title="Финансовая отчётность">ФО</span>
                  <span v-if="c.has_governance" class="uza-pill uza-pill-teal"
                        style="font-size: 9px; padding: 1px 5px;" title="Корпоративное управление">КУ</span>
                  <span v-if="c.is_custom" class="uza-pill uza-pill-purple"
                        style="font-size: 9px; padding: 1px 5px;" title="Пользовательская компания">+</span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
