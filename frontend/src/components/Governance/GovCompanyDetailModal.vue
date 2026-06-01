<template>
  <div class="gd-backdrop" @click.self="$emit('close')">
    <div class="gd-modal">
      <div v-if="loading && !detail" class="gd-loading">Загрузка...</div>
      <div v-else-if="error && !detail" class="gd-error">{{ error }}</div>

      <template v-else-if="detail">
        <!-- Header -->
        <div class="gd-header">
          <div class="gd-header-l">
            <div class="gd-eyebrow">Корп. управление · детали</div>
            <h2 class="gd-title">{{ detail.company_name || detail.company_code }}</h2>
            <div class="gd-meta">
              <span class="gd-co-code">{{ detail.company_code }}</span>
              <span v-if="detail.sector_code" class="gd-sector">{{ detail.sector_code }}</span>
              <span class="gd-meta-sep">·</span>
              <span>FY {{ detail.year }}</span>
              <span v-if="detail.score != null" class="gd-meta-sep">·</span>
              <span v-if="detail.score != null" class="gd-score-pill" :style="{ background: scoreColor(detail.score) + '18', color: scoreColor(detail.score) }">
                Балл КУ {{ fmt.fmtNumber(detail.score, { decimals: 0 }) }}/100
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
            <button class="gd-close" @click="$emit('close')">×</button>
          </div>
        </div>

        <!-- Body -->
        <div class="gd-body">
          <!-- Diversity bars -->
          <div class="gd-sec">
            <div class="gd-sec-h">Состав совета директоров</div>
            <div v-if="!detail.data" class="gd-empty">
              Данные за {{ detail.year }} ещё не заведены
            </div>
            <div v-else class="gd-diversity">
              <div class="gd-div-row">
                <div class="gd-div-l">
                  <span class="gd-div-label">Независимые директора</span>
                  <span class="gd-div-target">цель ≥33%</span>
                </div>
                <div class="gd-div-bar-wrap">
                  <div class="gd-div-bar">
                    <div class="gd-div-bar-fill" :style="{ width: (detail.independent_pct || 0) + '%', background: diversityColor(detail.independent_pct, 33) }" />
                    <div class="gd-div-bar-target" :style="{ left: '33%' }" title="Целевой порог 33%" />
                  </div>
                  <div class="gd-div-vals">
                    <span class="gd-div-pct" :style="{ color: diversityColor(detail.independent_pct, 33) }">
                      {{ fmt.fmtPercent(detail.independent_pct, { decimals: 0 }) }}
                    </span>
                    <span class="gd-div-count">
                      {{ detail.data.independent_directors_count ?? "—" }} из {{ detail.data.board_size ?? "—" }}
                    </span>
                  </div>
                </div>
              </div>

              <div class="gd-div-row">
                <div class="gd-div-l">
                  <span class="gd-div-label">Женщины-директора</span>
                  <span class="gd-div-target">цель ≥20%</span>
                </div>
                <div class="gd-div-bar-wrap">
                  <div class="gd-div-bar">
                    <div class="gd-div-bar-fill" :style="{ width: (detail.women_pct || 0) + '%', background: diversityColor(detail.women_pct, 20) }" />
                    <div class="gd-div-bar-target" :style="{ left: '20%' }" title="Целевой порог 20%" />
                  </div>
                  <div class="gd-div-vals">
                    <span class="gd-div-pct" :style="{ color: diversityColor(detail.women_pct, 20) }">
                      {{ fmt.fmtPercent(detail.women_pct, { decimals: 0 }) }}
                    </span>
                    <span class="gd-div-count">
                      {{ detail.data.women_directors_count ?? "—" }} из {{ detail.data.board_size ?? "—" }}
                    </span>
                  </div>
                </div>
              </div>

              <div class="gd-div-row">
                <div class="gd-div-l">
                  <span class="gd-div-label">Иностранные директора</span>
                  <span class="gd-div-target">цель ≥10%</span>
                </div>
                <div class="gd-div-bar-wrap">
                  <div class="gd-div-bar">
                    <div class="gd-div-bar-fill" :style="{ width: (detail.foreign_pct || 0) + '%', background: diversityColor(detail.foreign_pct, 10) }" />
                    <div class="gd-div-bar-target" :style="{ left: '10%' }" title="Целевой порог 10%" />
                  </div>
                  <div class="gd-div-vals">
                    <span class="gd-div-pct" :style="{ color: diversityColor(detail.foreign_pct, 10) }">
                      {{ fmt.fmtPercent(detail.foreign_pct, { decimals: 0 }) }}
                    </span>
                    <span class="gd-div-count">
                      {{ detail.data.foreign_directors_count ?? "—" }} из {{ detail.data.board_size ?? "—" }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Committees + meetings -->
          <div v-if="detail.data" class="gd-sec">
            <div class="gd-sec-h">Комитеты и заседания</div>
            <div class="gd-grid">
              <div class="gd-card">
                <div class="gd-card-l">Комитеты</div>
                <div class="gd-comm">
                  <span class="gd-comm-pill" :class="{ has: detail.data.has_audit_committee }">Аудит</span>
                  <span class="gd-comm-pill" :class="{ has: detail.data.has_remuneration_committee }">Возн.</span>
                  <span class="gd-comm-pill" :class="{ has: detail.data.has_nomination_committee }">Назн.</span>
                  <span class="gd-comm-pill" :class="{ has: detail.data.has_strategy_committee }">Стратегия</span>
                </div>
                <div class="gd-card-meta">
                  {{ committeeCount }} из 4
                </div>
              </div>

              <div class="gd-card">
                <div class="gd-card-l">Заседаний/год</div>
                <div class="gd-card-v" :style="{ color: meetingsColor }">
                  {{ detail.data.meetings_per_year ?? "—" }}
                </div>
                <div class="gd-card-meta">цель ≥4</div>
              </div>

              <div class="gd-card">
                <div class="gd-card-l">Посещаемость</div>
                <div class="gd-card-v" :style="{ color: attendanceColor }">
                  {{ detail.data.avg_attendance_pct != null ? detail.data.avg_attendance_pct + "%" : "—" }}
                </div>
                <div class="gd-card-meta">цель ≥80%</div>
              </div>

              <div class="gd-card">
                <div class="gd-card-l">Средний возраст</div>
                <div class="gd-card-v">
                  {{ detail.data.avg_age ?? "—" }}
                </div>
                <div class="gd-card-meta">лет</div>
              </div>
            </div>
            <div v-if="detail.data.notes" class="gd-notes">
              <span class="gd-notes-l">Примечания:</span>
              <span>{{ detail.data.notes }}</span>
            </div>
          </div>

          <!-- Board members table -->
          <div class="gd-sec">
            <div class="gd-sec-h">Члены совета директоров · {{ detail.board_members.length }}</div>
            <div v-if="!detail.board_members.length" class="gd-empty">
              Список членов совета не заполнен
            </div>
            <table v-else class="gd-tbl">
              <thead>
                <tr>
                  <th>ФИО</th>
                  <th>Должность</th>
                  <th>Тип роли</th>
                  <th class="flags">Призн.</th>
                  <th>Назначен</th>
                  <th>Срок до</th>
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
                      {{ roleTypeMeta(m.role_type).label }}
                    </span>
                    <span v-else class="gd-na">—</span>
                  </td>
                  <td class="flags">
                    <span v-if="m.is_independent" class="gd-flag gd-flag-i" title="Независимый">i</span>
                    <span v-if="m.is_woman" class="gd-flag gd-flag-w" title="Женщина">♀</span>
                    <span v-if="m.is_foreign" class="gd-flag gd-flag-f" title="Иностранный">⏚</span>
                  </td>
                  <td class="date">{{ formatDate(m.appointed_date) }}</td>
                  <td class="date">{{ formatDate(m.term_end_date) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
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

const fmt = useFormatters();

const props = defineProps<{
  companyId: string;
  initialYear?: number | null;
}>();

defineEmits<{
  (e: "close"): void;
}>();

const detail = ref<GovernanceCompanyDetail | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const currentYear = ref<number | null>(props.initialYear ?? null);

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
    error.value = err?.response?.data?.detail || err?.message || "Не удалось загрузить";
  } finally {
    loading.value = false;
  }
}

onMounted(load);
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
    d.has_remuneration_committee,
    d.has_nomination_committee,
    d.has_strategy_committee,
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
</script>

<style scoped>
.gd-backdrop {
  position: fixed; inset: 0;
  background: rgba(15, 18, 40, .45);
  backdrop-filter: blur(8px);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
}
.gd-modal {
  background: var(--bg1, #fff);
  border: 1px solid var(--card-border, transparent);
  border-radius: 14px;
  width: min(1100px, 96vw);
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .18);
  animation: modalIn .45s var(--ease-standard);
  overflow: hidden;
}
@keyframes modalIn { from { opacity: 0; transform: scale(.96) translateY(8px); } to { opacity: 1; transform: scale(1) translateY(0); } }

.gd-loading, .gd-error { padding: 50px 20px; text-align: center; font-size: 13px; color: rgba(15, 23, 60, .55); }
.gd-error { color: var(--sev-high); }

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

.gd-empty {
  text-align: center;
  padding: 24px;
  color: rgba(15, 23, 60, .45);
  font-size: 11.5px;
  font-style: italic;
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
</style>
