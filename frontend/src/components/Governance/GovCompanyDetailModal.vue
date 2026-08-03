<template>
  <div class="gd-backdrop" @click.self="$emit('close')">
    <div class="gd-modal">
      <UzaStateBlock v-if="loading && !detail" state="loading" />
      <UzaStateBlock v-else-if="error && !detail" state="error" variant="block" :text="error" />

      <template v-else-if="detail">
        <!-- Header -->
        <div class="gd-header">
          <div class="gd-header-l">
            <div class="gd-eyebrow">{{ t('Корп. управление · детали') }}</div>
            <h2 class="gd-title">{{ localizedCompanyName }}</h2>
            <div class="gd-meta">
              <span v-if="detail.sector_code" class="gd-sector">{{ sectorName }}</span>
              <span class="gd-meta-sep">·</span>
              <span>FY {{ detail.year }}</span>
              <span v-if="detail.score != null" class="gd-meta-sep">·</span>
              <span v-if="detail.score != null" class="gd-score-pill" :style="{ background: scoreColor(detail.score) + '18', color: scoreColor(detail.score) }">
                {{ t('Балл КУ') }} {{ fmt.fmtNumber(detail.score, { decimals: 0 }) }}/100
              </span>
            </div>
          </div>
          <div class="gd-header-r">
            <select
              v-if="detail.available_years.length > 1"
              :value="String(detail.year)"
              @change="onYearChange"
              class="gd-year-sel"
            >
              <option v-for="y in detail.available_years" :key="y" :value="y">{{ y }}</option>
            </select>
            <button
              v-if="govPerm.canEdit.value"
              class="gd-edit-btn"
              @click="editorOpen = true"
              :title="t('Редактировать показатели и совет директоров')"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path d="M11.5 2.5l2 2L6 12l-2.6.6.6-2.6 7.5-7.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
              </svg>
              {{ t('Редактировать') }}
            </button>
            <button class="gd-close" @click="$emit('close')">×</button>
          </div>
        </div>

        <!-- Body -->
        <div class="gd-body">
          <!-- Балл корпоративного управления: из чего сложился -->
          <div v-if="detail.score != null && detail.score_breakdown?.length" class="gd-sec">
            <div class="gd-sec-h">{{ t('Балл корпоративного управления') }}</div>
            <div class="gd-score-wrap">
              <div class="gd-score-big" :style="{ '--sc': scoreColor(detail.score) }">
                <span class="gd-score-val">{{ fmt.fmtNumber(detail.score, { decimals: 0 }) }}</span>
                <span class="gd-score-max">/100</span>
                <span class="gd-score-cap">{{ t('composite') }}</span>
              </div>
              <div class="gd-score-factors">
                <div v-for="(f, i) in detail.score_breakdown" :key="f.key"
                     class="gd-sf" :class="{ 'is-missing': f.missing }"
                     :style="{ '--d': i * 40 + 'ms' }">
                  <div class="gd-sf-top">
                    <span class="gd-sf-label">{{ t(f.label) }}</span>
                    <span class="gd-sf-weight">{{ t('вес') }} {{ Math.round(f.weight * 100) }}%</span>
                    <span v-if="!f.missing" class="gd-sf-pts">+{{ f.points }}</span>
                    <span v-else class="gd-sf-na">{{ t('нет данных') }}</span>
                  </div>
                  <div class="gd-sf-bar">
                    <span class="gd-sf-fill" :style="{ width: ((f.ratio ?? 0) * 100) + '%' }"></span>
                  </div>
                  <div class="gd-sf-foot">
                    <span>{{ f.value_text || '—' }}</span>
                    <span class="gd-sf-target">{{ t('цель') }} {{ f.target_text }}</span>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="missingFactors > 0" class="gd-score-note">
              {{ t('Балл посчитан по {value0} факторам из {value1}: веса недостающих перераспределены. Заполните их — оценка станет полной.', {
                  value0: detail.score_breakdown.length - missingFactors,
                  value1: detail.score_breakdown.length,
              }) }}
            </div>
          </div>

          <!-- Diversity bars -->
          <div class="gd-sec">
            <div class="gd-sec-h">
              {{ t('Состав совета директоров') }}
              <span v-if="detail.board_actual != null" class="gd-board-cnt">
                {{ detail.board_actual }}<template v-if="detail.data?.board_size"> {{ t('из') }} {{ detail.data.board_size }}</template>
              </span>
              <span v-if="detail.vacant_seats" class="gd-vacant">
                {{ t('{value0} вакансий', { value0: detail.vacant_seats }) }}
              </span>
            </div>
            <UzaStateBlock v-if="!detail.data" state="empty" variant="inline" :text="t('Данные за {value0} ещё не заведены', { value0: detail.year })" />
            <div v-else class="gd-diversity">
              <div class="gd-div-row">
                <div class="gd-div-l">
                  <span class="gd-div-label">{{ t('Независимые директора') }}</span>
                  <span class="gd-div-target">{{ t('цель ≥33%') }}</span>
                </div>
                <div class="gd-div-bar-wrap">
                  <div class="gd-div-bar">
                    <div class="gd-div-bar-fill" :style="{ width: Math.min(100, Math.max(0, detail.independent_pct || 0)) + '%', backgroundColor: divBarFill(detail.independent_pct, 33) }" />
                    <div class="gd-div-bar-target" :style="{ left: '33%' }" :title="t('Целевой порог 33%')" />
                  </div>
                  <div class="gd-div-vals">
                    <span class="gd-div-pct" :style="{ color: diversityColor(detail.independent_pct, 33) }">
                      {{ fmt.fmtPercent(detail.independent_pct, { decimals: 0 }) }}
                    </span>
                    <span class="gd-div-count">
                      {{ detail.data.independent_directors_count ?? "—" }} {{ t('из') }} {{ detail.data.board_size ?? "—" }}
                    </span>
                  </div>
                </div>
              </div>

              <div class="gd-div-row">
                <div class="gd-div-l">
                  <span class="gd-div-label">{{ t('Женщины-директора') }}</span>
                  <span class="gd-div-target">{{ t('цель ≥20%') }}</span>
                </div>
                <div class="gd-div-bar-wrap">
                  <div class="gd-div-bar">
                    <div class="gd-div-bar-fill" :style="{ width: Math.min(100, Math.max(0, detail.women_pct || 0)) + '%', backgroundColor: divBarFill(detail.women_pct, 20) }" />
                    <div class="gd-div-bar-target" :style="{ left: '20%' }" :title="t('Целевой порог 20%')" />
                  </div>
                  <div class="gd-div-vals">
                    <span class="gd-div-pct" :style="{ color: diversityColor(detail.women_pct, 20) }">
                      {{ fmt.fmtPercent(detail.women_pct, { decimals: 0 }) }}
                    </span>
                    <span class="gd-div-count">
                      {{ detail.data.women_directors_count ?? "—" }} {{ t('из') }} {{ detail.data.board_size ?? "—" }}
                    </span>
                  </div>
                </div>
              </div>

              <div class="gd-div-row">
                <div class="gd-div-l">
                  <span class="gd-div-label">{{ t('Иностранные директора') }}</span>
                  <span class="gd-div-target">{{ t('цель ≥10%') }}</span>
                </div>
                <div class="gd-div-bar-wrap">
                  <div class="gd-div-bar">
                    <div class="gd-div-bar-fill" :style="{ width: Math.min(100, Math.max(0, detail.foreign_pct || 0)) + '%', backgroundColor: divBarFill(detail.foreign_pct, 10) }" />
                    <div class="gd-div-bar-target" :style="{ left: '10%' }" :title="t('Целевой порог 10%')" />
                  </div>
                  <div class="gd-div-vals">
                    <span class="gd-div-pct" :style="{ color: diversityColor(detail.foreign_pct, 10) }">
                      {{ fmt.fmtPercent(detail.foreign_pct, { decimals: 0 }) }}
                    </span>
                    <span class="gd-div-count">
                      {{ detail.data.foreign_directors_count ?? "—" }} {{ t('из') }} {{ detail.data.board_size ?? "—" }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Committees + meetings -->
          <div v-if="detail.data" class="gd-sec">
            <div class="gd-sec-h">{{ t('Комитеты и заседания') }}</div>
            <div class="gd-grid">
              <div class="gd-card">
                <div class="gd-card-l">{{ t('Комитеты') }}</div>
                <div class="gd-comm">
                  <span class="gd-comm-pill" :class="{ has: detail.data.has_audit_committee }" :title="t('Комитет по аудиту')">{{ t('Аудит') }}</span>
                  <span class="gd-comm-pill" :class="{ has: detail.data.has_strategy_committee }" :title="t('Комитет по стратегии')">{{ t('Стратегия') }}</span>
                  <span class="gd-comm-pill" :class="{ has: detail.data.has_nomination_committee || detail.data.has_remuneration_committee }" :title="t('Комитет по назначениям и вознаграждениям')">{{ t('Назначения и вознагр.') }}</span>
                  <span class="gd-comm-pill" :class="{ has: detail.data.has_anticorr_committee }" :title="t('Антикоррупционный комитет')">{{ t('Антикор.') }}</span>
                  <span class="gd-comm-pill" :class="{ has: detail.data.has_induction_program }" :title="t('Программа введения в должность')">{{ t('Введение') }}</span>
                </div>
                <div class="gd-card-meta">
                  {{ committeeCount }} {{ t('из 5') }}
                </div>
              </div>

              <div class="gd-card">
                <div class="gd-card-l">{{ t('Заседаний/год') }}</div>
                <div class="gd-card-v" :style="{ color: meetingsColor }">
                  {{ detail.data.meetings_per_year ?? "—" }}
                </div>
                <div class="gd-card-meta">{{ t('цель ≥4') }}</div>
              </div>

              <div class="gd-card">
                <div class="gd-card-l">{{ t('Посещаемость') }}</div>
                <div class="gd-card-v" :style="{ color: attendanceColor }">
                  {{ detail.data.avg_attendance_pct != null ? detail.data.avg_attendance_pct + "%" : "—" }}
                </div>
                <div class="gd-card-meta">{{ t('цель ≥80%') }}</div>
              </div>

              <div class="gd-card">
                <div class="gd-card-l">{{ t('Средний возраст') }}</div>
                <div class="gd-card-v">
                  {{ detail.data.avg_age ?? "—" }}
                </div>
                <div class="gd-card-meta">{{ t('лет') }}</div>
              </div>
            </div>
            <div v-if="detail.data.notes" class="gd-notes">
              <span class="gd-notes-l">{{ t('Примечания:') }}</span>
              <span>{{ detail.data.notes }}</span>
            </div>
          </div>

          <!-- Board members table -->
          <div class="gd-sec">
            <div class="gd-sec-h">{{ t('Члены совета директоров ·') }} {{ detail.board_members.length }}</div>
            <UzaStateBlock v-if="!detail.board_members.length" state="empty" variant="inline" :text="t('Список членов совета не заполнен')" />
            <table v-else class="gd-tbl">
              <thead>
                <tr>
                  <th>{{ t('ФИО') }}</th>
                  <th>{{ t('Должность') }}</th>
                  <th>{{ t('Тип роли') }}</th>
                  <th class="flags">{{ t('Призн.') }}</th>
                  <th>{{ t('Назначен') }}</th>
                  <th>{{ t('Срок до') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="m in detail.board_members" :key="m.id">
                  <td class="name">{{ m.full_name }}</td>
                  <td class="position">{{ m.position || "—" }}</td>
                  <td>
                    <span
                      v-if="m.role_type"
                      class="gd-role"
                      :style="{ background: roleTypeMeta(m.role_type).color + '18', color: roleTypeMeta(m.role_type).color }"
                    >
                      {{ t(roleTypeMeta(m.role_type).label) }}
                    </span>
                    <span v-else class="gd-na">—</span>
                  </td>
                  <td class="flags">
                    <span v-if="m.is_independent" class="gd-flag gd-flag-i" :title="t('Независимый')">i</span>
                    <span v-if="m.is_woman" class="gd-flag gd-flag-w" :title="t('Женщина')">♀</span>
                    <span v-if="m.is_foreign" class="gd-flag gd-flag-f" :title="t('Иностранный')">⏚</span>
                  </td>
                  <td class="date">{{ formatDate(m.appointed_date) }}</td>
                  <td class="date">{{ formatDate(m.term_end_date) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Инлайн-редактор: открывается поверх карточки (ModalShell teleport),
             общий бэкенд с /governance — после сейва карточка и дашборд рефетчат. -->
        <GovernanceEditor
          v-if="editorOpen"
          :company-id="props.companyId"
          :company-name="localizedCompanyName"
          :year="detail.year"
          :data="detail.data"
          :members="detail.board_members"
          @close="editorOpen = false"
          @saved="onEditorSaved"
        />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  diversityColor,
  formatDate,
  governanceApi,
  roleTypeMeta,
  scoreColor,
  type GovernanceCompanyDetail,
} from "@/api/governance";
import { useFormatters } from "@/composables/useFormatters";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import GovernanceEditor from "@/components/Governance/GovernanceEditor.vue";
import { useCompaniesStore } from "@/stores/companies";
import { usePermissions } from "@/composables/usePermissions";
import { useI18n } from "@/composables/useI18n";
import { resolveCompanyDisplayName } from "@/utils/displayNames";
const { t } = useI18n();


const fmt = useFormatters();
const companiesStore = useCompaniesStore();
const govPerm = usePermissions("governance");
const editorOpen = ref(false);
// Подпись сектора «как он есть» в каталоге (name_ru), а не код ("energy").
const sectorName = computed(() =>
  companiesStore.getSectorName(detail.value?.sector_code) || detail.value?.sector_code || "",
);

const props = defineProps<{
  companyId: string;
  initialYear?: number | null;
}>();

const emit = defineEmits<{
  (e: "close"): void;
  (e: "saved"): void;
}>();

function onEditorSaved() {
  editorOpen.value = false;
  load();            // перечитать карточку с новыми данными
  emit("saved");     // дать дашборду /governance обновить рейтинги/KPI
}

const detail = ref<GovernanceCompanyDetail | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const currentYear = ref<number | null>(props.initialYear ?? null);
/** Сколько факторов балла остались незаполненными — показываем честно. */
const missingFactors = computed(
  () => (detail.value?.score_breakdown || []).filter((f: any) => f.missing).length,
);

const localizedCompanyName = computed(() =>
  companiesStore.getCompanyNameById(detail.value?.company_id)
  || resolveCompanyDisplayName(
    detail.value?.company_name || detail.value?.company_code,
    detail.value?.company_id || detail.value?.company_code,
  )
  || "—",
);

async function load() {
  loading.value = true;
  error.value = null;
  try {
    detail.value = await governanceApi.getCompanyDetail(
      props.companyId,
      currentYear.value ?? undefined,
    );
    currentYear.value = detail.value.year;
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string };
    error.value = err?.response?.data?.detail || err?.message || t('Не удалось загрузить');
  } finally {
    loading.value = false;
  }
}

onMounted(() => { load(); void companiesStore.ensureLoaded(); });
watch(() => props.companyId, load);

function onYearChange(e: Event) {
  const v = parseInt((e.target as HTMLSelectElement).value, 10);
  if (!isNaN(v)) {
    currentYear.value = v;
    load();
  }
}

const committeeCount = computed(() => {
  const d = detail.value?.data;
  if (!d) return 0;
  return [
    d.has_audit_committee,
    d.has_strategy_committee,
    (d.has_nomination_committee || d.has_remuneration_committee),
    d.has_anticorr_committee,
    d.has_induction_program,
  ].filter(Boolean).length;
});

const meetingsColor = computed(() => {
  const m = detail.value?.data?.meetings_per_year;
  if (m == null) return "rgba(15, 23, 60, .55)";
  if (m >= 4) return "#1D9E75";
  if (m >= 2) return "#EF9F27";
  return "#E24B4A";
});

const attendanceColor = computed(() => {
  const a = detail.value?.data?.avg_attendance_pct;
  if (a == null) return "rgba(15, 23, 60, .55)";
  if (a >= 80) return "#1D9E75";
  if (a >= 60) return "#EF9F27";
  return "#E24B4A";
});

/**
 * Цвет ЗАЛИВКИ diversity-баров — мягкая пастель (единый стиль баров портфеля).
 * Отдельно от diversityColor (которая остаётся для ТЕКСТА % рядом с баром,
 * где важнее читаемость). Та же логика порогов, что и diversityColor.
 */
function divBarFill(pct: number | null | undefined, target: number): string {
  if (pct == null) return "#B8B7B0";
  if (pct >= target) return "#5DC093";
  if (pct >= target * 0.6) return "#EFB373";
  return "#E2807F";
}
</script>

<style scoped>
.gd-backdrop {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, .45);
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
  /* Ниже ModalShell (--z-top 9990): инлайн-редактор (GovernanceEditor) должен
     открываться ПОВЕРХ карточки, а не «на заднем фоне». Раньше было 9999. */
  z-index: var(--z-overlay, 9000);
  display: flex;
  align-items: center;
  justify-content: center;
}
.gd-modal {
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  width: min(1100px, 96vw);
  max-height: 92dvh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18);
  animation: modalIn .45s var(--ease-standard);
  overflow: hidden;
}
@keyframes modalIn { from { opacity: 0; transform: scale(.96) translateY(8px); } to { opacity: 1; transform: scale(1) translateY(0); } }

.gd-header {
  padding: 18px 22px 14px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  border-bottom: 1px solid rgba(15, 23, 60, .06);
}
.gd-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: rgba(15, 23, 60, .55); }
.gd-title { font-size: 17px; font-weight: 600; margin: 4px 0 0; color: var(--t1, #1e2a4a); line-height: 1.3; letter-spacing: -.005em; }
.gd-meta { font-size: 11px; color: rgba(15, 23, 60, .55); margin-top: 4px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.gd-co-code { font-family: 'SF Mono', 'Menlo', monospace; background: rgba(15, 23, 60, .06); padding: 1px 6px; border-radius: 3px; font-weight: 600; }
.gd-sector { background: rgba(127, 119, 221, .12); color: #7F77DD; padding: 1px 6px; border-radius: 3px; font-weight: 600; font-size: 10px; }
.gd-meta-sep { opacity: .4; }
.gd-score-pill { padding: 2px 8px; border-radius: 4px; font-size: 10.5px; font-weight: 600; }

.gd-header-r { display: flex; gap: 8px; align-items: center; }
.gd-year-sel {
  font: inherit;
  font-size: 11px;
  padding: 4px 9px;
  border: 1px solid rgba(15, 23, 60, .12);
  border-radius: 5px;
  background: var(--bg1, #fff);
  font-feature-settings: 'tnum';
  outline: none;
  font-family: inherit;
}
.gd-edit-btn {
  display: inline-flex; align-items: center; gap: 6px;
  background: linear-gradient(135deg, #8B7FF0 0%, #6C5CE7 100%);
  color: #fff; border: none; border-radius: 8px;
  padding: 7px 13px; font-size: 12px; font-weight: 600; cursor: pointer;
  font-family: inherit; letter-spacing: .01em;
  box-shadow: 0 3px 10px rgba(108, 92, 231, .32);
  transition: box-shadow .18s ease, transform .18s ease;
}
.gd-edit-btn:hover { box-shadow: 0 5px 16px rgba(108, 92, 231, .46); transform: translateY(-1px); }
.gd-edit-btn:active { transform: translateY(0) scale(.98); }
.gd-close { background: transparent; border: none; font-size: 24px; color: rgba(15, 23, 60, .45); cursor: pointer; padding: 0 8px; }
.gd-close:hover { color: var(--t1, #1e2a4a); }

.gd-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 22px 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.gd-sec-h {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  margin-bottom: 10px;
}

.gd-diversity { display: flex; flex-direction: column; gap: 10px; }

.gd-div-row {
  background: var(--bg2, #FAFAFD);
  border-radius: 8px;
  padding: 10px 14px;
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 16px;
  align-items: center;
}
@media (max-width: 700px) {
  .gd-div-row { grid-template-columns: 1fr; }
}

.gd-div-label { font-size: 11.5px; font-weight: 500; color: var(--t1, #1e2a4a); }
.gd-div-target { font-size: 9.5px; color: rgba(15, 23, 60, .55); margin-left: 6px; }

.gd-div-bar-wrap { display: flex; align-items: center; gap: 12px; }
.gd-div-bar {
  flex: 1;
  position: relative;
  height: 14px;
  background: rgba(15, 23, 60, .05);
  border-radius: 7px;
  overflow: hidden;
}
.gd-div-bar-fill {
  position: absolute;
  left: 0; top: 0; bottom: 0;
  border-radius: 7px;
  /* Премиум-глянец: светлый верхний хайлайт поверх цвета бара. */
  background-image: linear-gradient(180deg, rgba(255, 255, 255, 0.30) 0%, rgba(255, 255, 255, 0) 55%);
  transition: width .8s var(--ease-standard);
}
.gd-div-bar-target {
  position: absolute;
  top: -2px; bottom: -2px;
  width: 2px;
  background: rgba(15, 23, 60, .35);
  border-radius: 1px;
}

.gd-div-vals { display: flex; gap: 8px; align-items: baseline; min-width: 130px; justify-content: flex-end; }
.gd-div-pct {
  font-size: 14px;
  font-weight: 600;
  font-feature-settings: 'tnum';
  letter-spacing: -.01em;
}
.gd-div-count { font-size: 10.5px; color: rgba(15, 23, 60, .55); font-feature-settings: 'tnum'; }

.gd-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr 1fr 1fr;
  gap: 10px;
}
@media (max-width: 800px) { .gd-grid { grid-template-columns: 1fr 1fr; } }

.gd-card {
  background: var(--bg2, #FAFAFD);
  border-radius: 8px;
  padding: 12px 14px;
  position: relative; overflow: hidden;
}
.gd-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: var(--accent, #7F77DD);
  border-radius: inherit; border-bottom-left-radius: 0; border-bottom-right-radius: 0;
  pointer-events: none;
}

.gd-card-l {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  margin-bottom: 6px;
}
.gd-card-v {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -.025em;
  color: var(--t1, #1e2a4a);
  font-feature-settings: 'tnum';
}
.gd-card-meta { font-size: 10px; color: rgba(15, 23, 60, .55); margin-top: 2px; }

.gd-comm { display: flex; gap: 4px; flex-wrap: wrap; }
.gd-comm-pill {
  font-size: 9.5px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 4px;
  background: rgba(15, 23, 60, .05);
  color: rgba(15, 23, 60, .35);
  letter-spacing: .04em;
}
.gd-comm-pill.has {
  background: rgba(29, 158, 117, .12);
  color: var(--green);
}

.gd-notes {
  margin-top: 8px;
  padding: 8px 12px;
  background: var(--bg2, #FAFAFD);
  border-radius: 6px;
  font-size: 11.5px;
  color: rgba(15, 23, 60, .65);
  line-height: 1.5;
}
.gd-notes-l { font-weight: 600; margin-right: 4px; color: var(--t1, #1e2a4a); }

.gd-tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
}
.gd-tbl thead th {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: rgba(15, 23, 60, .55);
  text-align: left;
  padding: 8px 8px;
  background: var(--bg2, #FAFAFD);
  border-bottom: 1px solid rgba(15, 23, 60, .08);
}
.gd-tbl thead th.flags { width: 80px; }

.gd-tbl tbody td {
  padding: 9px 8px;
  border-bottom: 1px solid rgba(15, 23, 60, .04);
  color: var(--t1, #1e2a4a);
}
.gd-tbl td.name { font-weight: 500; }
.gd-tbl td.position { color: rgba(15, 23, 60, .65); font-size: 11px; }
.gd-tbl td.date { font-feature-settings: 'tnum'; color: rgba(15, 23, 60, .55); font-size: 10.5px; }

.gd-role {
  font-size: 9.5px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 3px;
  letter-spacing: .04em;
}

.gd-flag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  margin-right: 3px;
}
.gd-flag-i { background: rgba(29, 158, 117, .15); color: var(--green); }
.gd-flag-w { background: rgba(127, 119, 221, .15); color: #7F77DD; }
.gd-flag-f { background: rgba(168, 85, 247, .15); color: #A855F7; }

.gd-na { color: rgba(15, 23, 60, .35); }

/* ── Балл КУ: из чего сложился ── */
.gd-score-wrap { display: grid; grid-template-columns: 132px 1fr; gap: 18px; align-items: start; }
.gd-score-big {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: color-mix(in srgb, var(--sc) 9%, transparent);
  border: 1px solid color-mix(in srgb, var(--sc) 24%, transparent);
  border-radius: 14px; padding: 16px 10px;
}
.gd-score-val { font-size: 34px; font-weight: 500; color: var(--sc); line-height: 1; font-variant-numeric: tabular-nums; }
.gd-score-max { font-size: 12px; color: var(--t3, #94A3B8); margin-top: 2px; }
.gd-score-cap { font-size: 9px; text-transform: uppercase; letter-spacing: .07em; color: var(--t4, #B4B2A9); margin-top: 7px; }
.gd-score-factors { display: flex; flex-direction: column; gap: 9px; }
.gd-sf {
  animation: gdSfIn .34s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)) both;
  animation-delay: var(--d, 0ms);
}
@keyframes gdSfIn { from { opacity: 0; transform: translateX(-6px); } to { opacity: 1; transform: none; } }
.gd-sf.is-missing { opacity: .55; }
.gd-sf-top { display: flex; align-items: baseline; gap: 8px; margin-bottom: 4px; }
.gd-sf-label { font-size: 12px; font-weight: 500; color: var(--t1, #1E2A4A); }
.gd-sf-weight { font-size: 10px; color: var(--t4, #B4B2A9); }
.gd-sf-pts { margin-left: auto; font-size: 12px; font-weight: 600; color: #0F6E56; font-variant-numeric: tabular-nums; }
.gd-sf-na { margin-left: auto; font-size: 10.5px; color: var(--t3, #94A3B8); }
.gd-sf-bar { height: 6px; border-radius: 999px; background: var(--bg2, #F1F2F6); overflow: hidden; }
.gd-sf-fill {
  display: block; height: 100%; border-radius: inherit;
  background: linear-gradient(90deg, #8B7FFF, #6C5CE7);
  transition: width .5s var(--ease-standard, cubic-bezier(.34,1.2,.64,1));
}
.gd-sf-foot { display: flex; justify-content: space-between; margin-top: 3px; font-size: 10.5px; color: var(--t3, #94A3B8); }
.gd-sf-target { opacity: .85; }
.gd-score-note {
  margin-top: 12px; font-size: 11.5px; line-height: 1.5; color: var(--t2, #4B5468);
  background: rgba(217,119,6,.07); border: 1px solid rgba(217,119,6,.20);
  border-radius: 10px; padding: 9px 12px;
}
.gd-board-cnt {
  font-size: 11px; font-weight: 600; color: var(--p-deep, #534AB7);
  background: rgba(124,111,247,.12); border-radius: 999px; padding: 2px 9px; margin-left: 8px;
}
.gd-vacant {
  font-size: 10.5px; font-weight: 600; color: #B45309;
  background: rgba(217,119,6,.13); border-radius: 999px; padding: 2px 9px; margin-left: 6px;
}
@media (max-width: 720px) { .gd-score-wrap { grid-template-columns: 1fr; } }
@media (prefers-reduced-motion: reduce) { .gd-sf { animation: none; } .gd-sf-fill { transition: none; } }
</style>
