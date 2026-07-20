<script setup lang="ts">
/**
 * ESGMaturityProfilePanel — профиль ESG-зрелости ОДНОЙ компании для встраивания
 * в воркспейс (та же матрица зрелости, что в /esg, но срез по компании): EMS-балл,
 * стадии по 6 измерениям, динамика ESG-рейтингов, годовая таблица ESG-отчётов.
 * Данные из общего getMaturityHeatmap → берём строку своей компании (синк с /esg).
 */
import { computed, ref, watch } from "vue";
import { esgApi, type ESGMaturityCompany } from "@/api/esg";
import { ratingsApi, type AgencyRatingBrief, type AgencyRatingHistoryItem } from "@/api/ratings";
import ESGReportsTable from "@/components/ESG/ESGReportsTable.vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";

const props = defineProps<{
  companyId: string;
  companyCode: string;
  year: number;
  canEdit?: boolean;
}>();

// Метки 6 измерений матрицы зрелости (1:1 с шапкой ESGMaturityMatrix).
const DIM_META: { key: string; label: string; max: number }[] = [
  { key: "D1",  label: "Системы менеджмента ИСО", max: 2 },
  { key: "D2",  label: "Подготовка ESG-отчётности", max: 3 },
  { key: "D2A", label: "Независимое заверение", max: 2 },
  { key: "D3",  label: "Получение ESG-рейтинга", max: 2 },
  { key: "D4",  label: "Климатическая стратегия", max: 4 },
  { key: "D5",  label: "Внедрение ESG-рисков", max: 3 },
];

const loading = ref(true);
const error = ref<string | null>(null);
const co = ref<ESGMaturityCompany | null>(null);

async function loadMaturity() {
  loading.value = true;
  error.value = null;
  try {
    const hm = await esgApi.getMaturityHeatmap(props.year);
    co.value = (hm.companies || []).find(c => c.company_id === props.companyId) || null;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "Не удалось загрузить зрелость";
    co.value = null;
  } finally {
    loading.value = false;
  }
}
watch(() => [props.companyId, props.year], loadMaturity, { immediate: true });

function emsColor(v: number): string {
  if (v >= 66) return "#1D9E75";
  if (v >= 33) return "#EF9F27";
  return "#E24B4A";
}
function stageColor(pct: number): string {
  if (pct >= 100) return "#1D9E75";
  if (pct >= 50) return "#7DC4A0";
  if (pct > 0) return "#EF9F27";
  return "#CBD5E1";
}
const dims = computed(() => {
  const ds = co.value?.dim_stage || {};
  const nr = new Set(co.value?.dim_not_required || []);
  return DIM_META.map(d => {
    const stage = ds[d.key] ?? 0;
    const notReq = nr.has(d.key);
    return { ...d, stage, notReq, pct: notReq ? 0 : Math.round((Math.min(stage, d.max) / d.max) * 100) };
  });
});

// ─── Динамика ESG-рейтингов (read-only, как в ESGMaturityProfileModal) ───
const ratings = ref<AgencyRatingBrief[]>([]);
const ratingsLoading = ref(false);
const histOpen = ref<string | null>(null);
const histItems = ref<AgencyRatingHistoryItem[]>([]);
const histLoading = ref(false);
const ACTION_LBL: Record<string, string> = { create: "создан", update: "изменён", delete: "удалён", snapshot: "снимок" };

async function loadRatings() {
  histOpen.value = null;
  ratingsLoading.value = true;
  try {
    const data = await ratingsApi.getCompanyRatings(props.companyCode);
    ratings.value = data.esg || [];
  } catch { ratings.value = []; }
  finally { ratingsLoading.value = false; }
}
watch(() => props.companyCode, loadRatings, { immediate: true });

async function toggleHistory(agency: string) {
  if (histOpen.value === agency) { histOpen.value = null; return; }
  histOpen.value = agency;
  histItems.value = [];
  histLoading.value = true;
  try {
    const data = await ratingsApi.getRatingHistory(props.companyCode, agency);
    histItems.value = data.items || [];
  } catch { histItems.value = []; }
  finally { histLoading.value = false; }
}
function histDate(iso: string): string {
  try { return new Date(iso).toLocaleDateString("ru", { day: "2-digit", month: "short", year: "numeric" }); }
  catch { return iso; }
}
</script>

<template>
  <div class="mpp">
    <UzaStateBlock v-if="loading" state="loading" text="Загрузка ESG-зрелости…" />
    <UzaStateBlock v-else-if="error" state="error" variant="block" :text="error" retry @retry="loadMaturity" />

    <template v-else>
      <!-- EMS + измерения -->
      <div v-if="co" class="mpp-mat">
        <div class="mpp-ems" :style="{ '--ems': emsColor(co.ems) }">
          <div class="mpp-ems-l">Индекс зрелости (EMS)</div>
          <div class="mpp-ems-v">{{ co.ems.toFixed(0) }}<span class="mpp-ems-of">/100</span></div>
          <div class="mpp-ems-track"><div class="mpp-ems-fill" :style="{ width: co.ems + '%' }"></div></div>
        </div>
        <div class="mpp-dims">
          <div v-for="d in dims" :key="d.key" class="mpp-dim" :class="{ 'mpp-dim-nr': d.notReq }">
            <div class="mpp-dim-hd">
              <span class="mpp-dim-l">{{ d.label }}</span>
              <span class="mpp-dim-v">{{ d.notReq ? 'не требуется' : `${d.stage}/${d.max}` }}</span>
            </div>
            <div class="mpp-dim-track">
              <div class="mpp-dim-fill" :style="{ width: d.pct + '%', background: stageColor(d.pct) }"></div>
            </div>
          </div>
        </div>
      </div>
      <UzaStateBlock v-else state="empty" variant="inline" :text="`Матрица зрелости за ${year} год не заполнена`" />

      <!-- Динамика рейтингов -->
      <div class="mpp-rh">
        <div class="mpp-rh-head">
          <span class="mpp-rh-title">Динамика рейтингов</span>
          <span class="mpp-rh-src">ESG-рейтинги агентств · история изменений</span>
        </div>
        <div v-if="ratingsLoading" class="mpp-rh-empty">Загрузка…</div>
        <template v-else>
          <div v-if="ratings.length" class="mpp-rh-list">
            <div v-for="r in ratings" :key="r.id" class="mpp-rh-wrap">
              <div class="mpp-rh-item">
                <div class="mpp-rh-l">
                  <span class="mpp-rh-ag">{{ r.agency }}</span>
                  <span class="mpp-rh-val">{{ r.score || r.rating || '—' }}</span>
                  <span v-if="r.outlook" class="mpp-rh-out">{{ r.outlook }}</span>
                </div>
                <div class="mpp-rh-r">
                  <span v-if="r.rating_date_text" class="mpp-rh-date">{{ r.rating_date_text }}</span>
                  <a v-if="r.report_url" class="mpp-rh-doc" :href="r.report_url" target="_blank" rel="noopener">отчёт</a>
                  <button class="mpp-rh-btn" type="button" :class="{ on: histOpen === r.agency }" @click="toggleHistory(r.agency)">история</button>
                </div>
              </div>
              <Transition name="mpp-hist">
                <div v-if="histOpen === r.agency" class="mpp-hist">
                  <div v-if="histLoading" class="mpp-hist-empty">Загрузка истории…</div>
                  <template v-else>
                    <div v-if="histItems.length" class="mpp-hist-tl">
                      <div v-for="(h, i) in histItems" :key="h.id" class="mpp-hist-row" :style="{ '--d': (i*40)+'ms' }">
                        <span class="mpp-hist-dot" :class="'a-'+h.action"></span>
                        <span class="mpp-hist-val">{{ h.score || h.rating || '—' }}</span>
                        <span v-if="h.outlook" class="mpp-hist-out">{{ h.outlook }}</span>
                        <span class="mpp-hist-act" :class="'a-'+h.action">{{ ACTION_LBL[h.action] || h.action }}</span>
                        <span class="mpp-hist-when">{{ histDate(h.created_at) }}</span>
                        <span v-if="h.changed_by_name" class="mpp-hist-who">· {{ h.changed_by_name }}</span>
                      </div>
                    </div>
                    <div v-else class="mpp-hist-empty">История пуста — изменения появятся после правок рейтинга</div>
                  </template>
                </div>
              </Transition>
            </div>
          </div>
          <div v-else class="mpp-rh-empty">Независимых ESG-рейтингов пока нет</div>
        </template>
      </div>

      <!-- Годовая таблица ESG-отчётов (редактируемая, с 2021) -->
      <ESGReportsTable :company-id="companyId" :can-edit="canEdit" />
    </template>
  </div>
</template>

<style scoped>
.mpp { display: flex; flex-direction: column; gap: 18px; }

.mpp-mat { display: grid; grid-template-columns: 220px 1fr; gap: 16px; }
@media (max-width: 820px) { .mpp-mat { grid-template-columns: 1fr; } }
.mpp-ems {
  background: var(--bg2, #FAFAFD); border: 1px solid var(--line, #ECEAF4); border-radius: 12px;
  padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; align-self: start;
}
.mpp-ems-l { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.mpp-ems-v { font-size: 30px; font-weight: 400; letter-spacing: -.02em; color: var(--ems, #1D9E75); font-variant-numeric: tabular-nums; }
.mpp-ems-of { font-size: 13px; opacity: .5; margin-left: 2px; }
.mpp-ems-track { height: 6px; border-radius: 999px; background: var(--bg3, #EEEDF4); overflow: hidden; margin-top: 4px; }
.mpp-ems-fill { height: 100%; border-radius: 999px; background: var(--ems, #1D9E75); transition: width .8s var(--ease-standard, cubic-bezier(.4,0,.2,1)); }

.mpp-dims { display: grid; grid-template-columns: repeat(2, 1fr); gap: 11px 18px; align-content: start; }
@media (max-width: 560px) { .mpp-dims { grid-template-columns: 1fr; } }
.mpp-dim-nr { opacity: .5; }
.mpp-dim-hd { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin-bottom: 5px; }
.mpp-dim-l { font-size: 12px; font-weight: 500; color: var(--t1, #1A1730); }
.mpp-dim-v { font-size: 11.5px; font-weight: 500; color: var(--t2, #6B6880); font-variant-numeric: tabular-nums; }
.mpp-dim-track { height: 6px; border-radius: 999px; background: var(--bg3, #EEEDF4); overflow: hidden; }
.mpp-dim-fill { height: 100%; border-radius: 999px; transition: width .7s var(--ease-standard, cubic-bezier(.4,0,.2,1)); }

/* Динамика рейтингов */
.mpp-rh-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.mpp-rh-title { font-size: 13px; font-weight: 600; color: var(--t1, #1E2A4A); }
.mpp-rh-src { font-size: 10.5px; color: var(--t3, #94A3B8); }
.mpp-rh-empty { font-size: 11.5px; color: var(--t3, #94A3B8); padding: 6px 0; }
.mpp-rh-list { display: flex; flex-direction: column; gap: 8px; }
.mpp-rh-wrap { display: flex; flex-direction: column; }
.mpp-rh-item { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 13px; border-radius: 10px; background: var(--bg2, #FAFAFC); border: 1px solid var(--line, #ECEAF5); }
.mpp-rh-l { display: inline-flex; align-items: baseline; gap: 10px; min-width: 0; }
.mpp-rh-ag { font-size: 12.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.mpp-rh-val { font-size: 12.5px; font-weight: 600; color: #6C5CE7; font-variant-numeric: tabular-nums; }
.mpp-rh-out { font-size: 11px; color: var(--t2, #475569); }
.mpp-rh-r { display: inline-flex; align-items: center; gap: 12px; flex-shrink: 0; }
.mpp-rh-date { font-size: 10.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }
.mpp-rh-doc { font-size: 10.5px; color: #6C5CE7; text-decoration: none; }
.mpp-rh-doc:hover { text-decoration: underline; }
.mpp-rh-btn { font-size: 10.5px; font-weight: 600; color: var(--t3, #94A3B8); background: transparent; border: 1px solid var(--line, #ECEAF5); border-radius: 7px; padding: 3px 9px; cursor: pointer; transition: all .15s ease; }
.mpp-rh-btn:hover, .mpp-rh-btn.on { color: #6C5CE7; border-color: rgba(108,92,231,.4); background: rgba(108,92,231,.06); }
.mpp-hist { overflow: hidden; padding: 4px 13px 8px; }
.mpp-hist-empty { font-size: 11px; color: var(--t3, #94A3B8); padding: 6px 2px; }
.mpp-hist-tl { display: flex; flex-direction: column; gap: 0; border-left: 2px solid var(--line, #ECEAF5); margin-left: 4px; padding-left: 12px; }
.mpp-hist-row { position: relative; display: flex; align-items: baseline; gap: 7px; padding: 5px 0; font-size: 11.5px; animation: mppHistIn .35s ease var(--d, 0ms) both; }
@keyframes mppHistIn { from { opacity: 0; transform: translateX(-4px); } to { opacity: 1; transform: translateX(0); } }
.mpp-hist-dot { position: absolute; left: -19px; top: 9px; width: 9px; height: 9px; border-radius: 50%; background: #94A3B8; box-shadow: 0 0 0 3px #fff; }
.mpp-hist-dot.a-create { background: #1D9E75; }
.mpp-hist-dot.a-update { background: #6C5CE7; }
.mpp-hist-dot.a-delete { background: #E24B4A; }
.mpp-hist-val { font-weight: 600; color: var(--t1, #1E2A4A); font-variant-numeric: tabular-nums; }
.mpp-hist-out { font-size: 10.5px; color: var(--t2, #475569); }
.mpp-hist-act { font-size: 9.5px; font-weight: 600; border-radius: 5px; padding: 1px 6px; background: #F1F5F9; color: #64748B; }
.mpp-hist-act.a-create { background: #DCFCE7; color: #1D9E75; }
.mpp-hist-act.a-update { background: #EDE9FE; color: #6C5CE7; }
.mpp-hist-act.a-delete { background: #FEE2E2; color: #E24B4A; }
.mpp-hist-when { font-size: 10.5px; color: var(--t3, #94A3B8); font-variant-numeric: tabular-nums; }
.mpp-hist-who { font-size: 10.5px; color: var(--t3, #94A3B8); }
.mpp-hist-enter-active, .mpp-hist-leave-active { transition: max-height .28s ease, opacity .2s ease; max-height: 400px; }
.mpp-hist-enter-from, .mpp-hist-leave-to { max-height: 0; opacity: 0; }
</style>
