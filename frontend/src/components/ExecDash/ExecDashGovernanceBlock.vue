<script setup lang="ts">
/**
 * ExecDashGovernanceBlock — Row 3 mid.
 * "Рейтинг корпуправления" — 4 KPI summary + top-7 список компаний.
 *
 * Как в легасие Row 3 mid (showExecDashView):
 *   - 4-KPI strip: Средний / Лучший / Независ.% / Женщин%
 *   - Header table: # | Компания | Балл / 1200
 *   - Top-7 список с medal badges (gold/silver/bronze) + цветной полосой сектора + прогресс-баром
 */
import { computed } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import Odometer from "@/components/Odometer.vue";

const exec = useExecutiveDashboard();

const block = computed(() => exec.data.value?.governance || null);

const sectorColor: Record<string, string> = {
  mining: "#7F77DD",
  oilgas: "#1D9E75",
  energy: "#EF9F27",
  transport: "#378ADD",
  other: "#888780",
};

function pctColor(pct: number): string {
  if (pct >= 75) return "#1D9E75";
  if (pct >= 55) return "#EF9F27";
  return "#E24B4A";
}

function medalColor(rank: number): string {
  if (rank === 0) return "#D4AF37";  // gold
  if (rank === 1) return "#9CA3AF";  // silver
  if (rank === 2) return "#CD7F32";  // bronze
  return "transparent";
}
</script>

<template>
  <div class="ed-card edg-card">
    <!-- Header -->
    <div class="edg-hdr">
      <span class="edg-eyebrow">Рейтинг корпуправления</span>
      <span v-if="block && block.total_companies" class="edg-count">
        <span v-count-up="block.total_companies">0</span> компаний
      </span>
    </div>

    <!-- Empty state -->
    <div v-if="!block || block.total_companies === 0" class="edg-empty">
      Нет данных о корпуправлении за FY {{ exec.year.value }}
    </div>

    <template v-else>
      <!-- 4-KPI summary strip -->
      <div class="edg-strip kpi-rail">
        <div class="edg-kpi">
          <div class="edg-kpi-val"><Odometer :value="block.avg_score" /></div>
          <div class="edg-kpi-lbl">Средний</div>
        </div>
        <div class="edg-kpi">
          <div class="edg-kpi-val edg-kpi-green"><Odometer :value="block.top_score" /></div>
          <div class="edg-kpi-lbl">Лучший</div>
        </div>
        <div class="edg-kpi">
          <div class="edg-kpi-val edg-kpi-purple">
            <Odometer :value="block.avg_indep_pct" /><span class="edg-kpi-u">%</span>
          </div>
          <div class="edg-kpi-lbl">Независ.</div>
        </div>
        <div class="edg-kpi edg-kpi-last">
          <div class="edg-kpi-val edg-kpi-rose">
            <Odometer :value="block.avg_women_pct" /><span class="edg-kpi-u">%</span>
          </div>
          <div class="edg-kpi-lbl">Женщин</div>
        </div>
      </div>

      <!-- Table header -->
      <div class="edg-thead">
        <div class="edg-th-bar" />
        <div class="edg-th-rank">#</div>
        <div class="edg-th-name">Компания</div>
        <div class="edg-th-score">Балл / 1200</div>
      </div>

      <!-- Top-7 list -->
      <div class="edg-rows">
        <div
          v-for="(co, i) in block.top_companies"
          :key="co.company_id"
          class="edg-row"
          :style="{ '--rd': `${i * 60}ms` }"
          :title="`${co.name} · НС ${co.board_size}ч · независ. ${co.independent_count} · женщин ${co.women_count}`"
        >
          <div
            class="edg-row-bar"
            :style="{ background: sectorColor[co.sector] || '#888780' }"
          />

          <span
            v-if="i < 3"
            class="edg-medal"
            :style="{ background: medalColor(i) }"
          >{{ i + 1 }}</span>
          <span v-else class="edg-rank">{{ i + 1 }}</span>

          <span class="edg-name">{{ co.name }}</span>

          <div class="edg-score-wrap">
            <div class="edg-pbar">
              <div
                class="edg-pbar-fill"
                :style="{
                  width: `${co.score_pct}%`,
                  background: pctColor(co.score_pct),
                }"
              />
            </div>
            <span
              class="edg-score"
              :style="{ color: pctColor(co.score_pct) }"
            >{{ co.score }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.edg-card {
  display: flex;
  flex-direction: column;
  min-height: 420px;
  padding: 14px 14px 12px;
  background: var(--bg1, #fff);
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.06);
  /* Pack 7.21: prevent grid column from expanding past 1fr allotment */
  min-width: 0;
  overflow: hidden;
}

.edg-hdr {
  display: flex;
  align-items: baseline;
  padding: 0 0 8px;
  gap: 8px;
  flex-shrink: 0;
}
.edg-eyebrow {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.07em;
  flex: 1;
}
.edg-count {
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
}

.edg-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #B4B2A9;
  font-size: 12px;
  padding: 30px 10px;
  text-align: center;
}

/* 4-KPI strip */
.edg-strip {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
  padding: 11px 8px;
  background: #F9F8FC;
  border-radius: 10px;
  border: 0.5px solid rgba(127, 119, 221, 0.12);
  flex-shrink: 0;
}
.edg-kpi {
  flex: 1;
  text-align: center;
  border-right: 0.5px solid rgba(0, 0, 0, 0.06);
}
.edg-kpi-last {
  border-right: none;
}
.edg-kpi-val {
  font-size: 18px;
  font-weight: 700;
  color: var(--t1, #1E2A4A);
  font-feature-settings: "tnum";
  line-height: 1.15;
  letter-spacing: -0.025em;
}
.edg-kpi-green {
  color: var(--green);
}
.edg-kpi-purple {
  color: var(--p-deep);
}
.edg-kpi-rose {
  color: #D4537E;
}
.edg-kpi-u {
  font-size: 12px;
  font-weight: 500;
}
.edg-kpi-lbl {
  font-size: 10px;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
  margin-top: 3px;
}

/* Table */
.edg-thead {
  display: flex;
  align-items: center;
  padding: 0 10px 4px;
  border-bottom: 0.5px solid rgba(0, 0, 0, 0.08);
  gap: 8px;
  flex-shrink: 0;
}
.edg-th-bar {
  width: 3px;
  flex-shrink: 0;
}
.edg-th-rank {
  width: 22px;
  text-align: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--t3, var(--t-muted));
  letter-spacing: 0.04em;
}
.edg-th-name {
  flex: 1;
  font-size: 11px;
  font-weight: 700;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.edg-th-score {
  width: 100px;
  text-align: right;
  font-size: 11px;
  font-weight: 700;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.edg-rows {
  display: flex;
  flex-direction: column;
  margin-top: 4px;
}

.edg-row {
  padding: 8px 10px;
  border-radius: 8px;
  margin-bottom: 1px;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background 0.15s;
  animation: edgRowIn 0.4s var(--ease-standard) var(--rd, 0ms) both;
  min-width: 0;  /* Pack 7.21: enable child ellipsis */
}
.edg-row:hover {
  background: rgba(127, 119, 221, 0.06);
}

.edg-row-bar {
  width: 3px;
  height: 16px;
  flex-shrink: 0;
}

.edg-medal {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  color: #fff;
  font-size: 10.5px;
  font-weight: 700;
  flex-shrink: 0;
  font-feature-settings: "tnum";
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.18);
}
.edg-rank {
  width: 20px;
  font-size: 11.5px;
  color: var(--t3, var(--t-muted));
  text-align: center;
  font-feature-settings: "tnum";
  font-weight: 600;
  flex-shrink: 0;
}

.edg-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--t1, #1E2A4A);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.edg-score-wrap {
  width: 100px;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  justify-content: flex-end;
}
.edg-pbar {
  width: 46px;
  height: 5px;
  background: rgba(0, 0, 0, 0.06);
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
}
.edg-pbar-fill {
  height: 5px;
  border-radius: 4px;
  transition: width 0.6s var(--ease-standard);
}
.edg-score {
  font-size: 13px;
  font-weight: 700;
  min-width: 36px;
  text-align: right;
  font-feature-settings: "tnum";
}

@keyframes edgRowIn {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
