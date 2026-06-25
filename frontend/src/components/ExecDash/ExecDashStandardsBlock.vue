<script setup lang="ts">
/**
 * ExecDashStandardsBlock — Row 3 right.
 * "Внедрение стандартов" — МСФО + Forensic ring + attention list.
 *
 * Как в легасие Row 3 right (showExecDashView):
 *   - 2 ring cards horizontal: МСФО (зелёный), Forensic (амбер)
 *   - Each ring: SVG circle + done/total + "+N в процессе" sub-text
 *   - Attention list: компании где есть gap (МСФО не начат / Forensic тендер / etc)
 */
import { computed } from "vue";
import { useExecutiveDashboard } from "@/composables/useExecutiveDashboard";
import { SECTOR_COLORS } from "@/utils/sectorMeta";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";

const exec = useExecutiveDashboard();

const block = computed(() => exec.data.value?.standards || null);

// единый источник цветов секторов (см. sectorMeta.ts)
const sectorColor = SECTOR_COLORS as Record<string, string>;

// SVG ring math: circumference = 2 * π * 23 ≈ 144.5
const RING_CIRC = 144.5;

const ifrsDash = computed(() => {
  if (!block.value) return 0;
  return (block.value.ifrs.pct * RING_CIRC / 100).toFixed(1);
});

const forensicDash = computed(() => {
  if (!block.value) return 0;
  return (block.value.forensic.pct * RING_CIRC / 100).toFixed(1);
});

const ifrsSubText = computed(() => {
  if (!block.value) return "";
  const a = block.value.ifrs.active;
  return a > 0 ? `+${a} в процессе` : "";
});

const forensicSubText = computed(() => {
  if (!block.value) return "";
  const a = block.value.forensic.active;
  const i = block.value.forensic.init;
  const parts: string[] = [];
  if (a > 0) parts.push(`+${a} процесс`);
  if (i > 0) parts.push(`${i} тендер`);
  return parts.join(" · ");
});

function statusLabel(status: string, kind: "МСФО" | "Forensic"): string {
  if (status === "done") return `${kind} ✓`;
  if (status === "active" || status === "review") return `${kind} в процессе`;
  if (status === "init" && kind === "Forensic") return "Forensic тендер";
  return `${kind} не начат`;
}

function statusColor(status: string): string {
  if (status === "done") return "#1D9E75";
  if (status === "active" || status === "review") return "#EF9F27";
  if (status === "init") return "#7F77DD";
  return "#888780";
}
</script>

<template>
  <div class="ed-card eds-card">
    <!-- Header -->
    <div class="eds-hdr">
      <span class="eds-eyebrow">Внедрение стандартов</span>
      <span v-if="block && block.total_companies" class="eds-count">
        {{ block.total_companies }} компаний
      </span>
    </div>

    <!-- Empty state -->
    <UzaStateBlock
      v-if="!block || block.total_companies === 0"
      state="empty"
      variant="block"
      title="Нет данных по стандартам"
      :desc="`Для FY ${exec.year.value} нет информации о внедрении МСФО / Forensic`"
    />

    <template v-else>
      <!-- 2 ring cards horizontal -->
      <div class="eds-rings">
        <!-- МСФО ring -->
        <div class="eds-ring-card">
          <div class="eds-ring-svg-wrap">
            <svg width="54" height="54" viewBox="0 0 54 54" class="eds-ring-svg">
              <circle cx="27" cy="27" r="23" fill="none" stroke="rgba(0,0,0,.06)" stroke-width="5" />
              <circle
                cx="27"
                cy="27"
                r="23"
                fill="none"
                stroke="#1D9E75"
                stroke-width="5"
                stroke-linecap="round"
                :stroke-dasharray="`${ifrsDash} ${RING_CIRC}`"
              />
            </svg>
            <div class="eds-ring-num">
              {{ block.ifrs.done }}<span class="eds-ring-tot">/{{ block.total_companies }}</span>
            </div>
          </div>
          <div class="eds-ring-info">
            <div class="eds-ring-label eds-ring-label-ifrs">МСФО</div>
            <div class="eds-ring-sub">аудит завершён</div>
            <div v-if="ifrsSubText" class="eds-ring-progress">{{ ifrsSubText }}</div>
          </div>
        </div>

        <!-- Forensic ring -->
        <div class="eds-ring-card">
          <div class="eds-ring-svg-wrap">
            <svg width="54" height="54" viewBox="0 0 54 54" class="eds-ring-svg">
              <circle cx="27" cy="27" r="23" fill="none" stroke="rgba(0,0,0,.06)" stroke-width="5" />
              <circle
                cx="27"
                cy="27"
                r="23"
                fill="none"
                stroke="#EF9F27"
                stroke-width="5"
                stroke-linecap="round"
                :stroke-dasharray="`${forensicDash} ${RING_CIRC}`"
              />
            </svg>
            <div class="eds-ring-num">
              {{ block.forensic.done }}<span class="eds-ring-tot">/{{ block.total_companies }}</span>
            </div>
          </div>
          <div class="eds-ring-info">
            <div class="eds-ring-label eds-ring-label-forensic">Forensic</div>
            <div class="eds-ring-sub">аудит завершён</div>
            <div v-if="forensicSubText" class="eds-ring-progress">{{ forensicSubText }}</div>
          </div>
        </div>
      </div>

      <!-- Attention list label -->
      <div class="eds-att-hdr">
        Требуют внимания · {{ block.attention_list.length }}
      </div>

      <!-- Attention list -->
      <div class="eds-att-wrap">
        <div v-if="!block.attention_list.length" class="eds-att-clean">
          Все компании завершили МСФО и Forensic
        </div>
        <div
          v-for="(a, i) in block.attention_list"
          :key="a.company_id"
          class="eds-att-row"
          :style="{ '--rd': `${i * 40}ms` }"
          :title="`${a.name} · ${a.gaps.join(' · ')}`"
        >
          <span
            class="eds-att-bar"
            :style="{ background: sectorColor[a.sector] || '#888780' }"
          />
          <span class="eds-att-name">{{ a.name }}</span>
          <span class="eds-att-status">
            <span :style="{ color: statusColor(a.ifrs_status) }">
              {{ statusLabel(a.ifrs_status, 'МСФО') }}
            </span>
            <span class="eds-att-sep">·</span>
            <span :style="{ color: statusColor(a.forensic_status) }">
              {{ statusLabel(a.forensic_status, 'Forensic') }}
            </span>
          </span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.eds-card {
  display: flex;
  flex-direction: column;
  min-height: 420px;
  padding: 14px 14px 12px;
  background: var(--bg1, #fff);
  border-radius: 12px;
  box-shadow: 0 4px 14px rgba(15, 23, 60, 0.06);
  /* Pack 7.21: prevent the card from expanding its grid column when
     a long company name would otherwise force horizontal overflow */
  min-width: 0;
  overflow: hidden;
}

.eds-hdr {
  display: flex;
  align-items: baseline;
  padding: 0 0 8px;
  gap: 8px;
  flex-shrink: 0;
}
.eds-eyebrow {
  font-size: 11px;
  font-weight: 600;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.07em;
  flex: 1;
}
.eds-count {
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
}

.eds-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6B6A66;
  font-size: 12px;
  padding: 30px 10px;
  text-align: center;
}

/* Ring cards */
.eds-rings {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
  flex-shrink: 0;
}
.eds-ring-card {
  flex: 1;
  background: #F9F8FC;
  border-radius: 10px;
  padding: 12px 10px;
  display: flex;
  align-items: center;
  gap: 12px;
  border: 1px solid rgba(0, 0, 0, 0.04);
}
.eds-ring-svg-wrap {
  position: relative;
  width: 54px;
  height: 54px;
  flex-shrink: 0;
}
.eds-ring-svg {
  transform: rotate(-90deg);
}
.eds-ring-svg circle:nth-child(2) {
  transition: stroke-dasharray 0.8s var(--ease-standard);
}
.eds-ring-num {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 13.5px;
  font-weight: 600;
  color: var(--t1, #1E2A4A);
  font-feature-settings: "tnum";
}
.eds-ring-tot {
  font-size: 9.5px;
  color: var(--t3, var(--t-muted));
  font-weight: 500;
}
.eds-ring-info {
  min-width: 0;
}
.eds-ring-label {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.eds-ring-label-ifrs {
  color: var(--green);
}
.eds-ring-label-forensic {
  color: var(--amber);
}
.eds-ring-sub {
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  margin-top: 2px;
}
.eds-ring-progress {
  font-size: 11px;
  color: #8A5F15;
  margin-top: 3px;
  font-weight: 500;
}

/* Attention list */
.eds-att-hdr {
  font-size: 11.5px;
  color: var(--t3, var(--t-muted));
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: 700;
  padding-bottom: 6px;
  flex-shrink: 0;
}

.eds-att-wrap {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;  /* Pack 7.21: prevent horizontal scroll on long names */
  min-height: 0;
}

.eds-att-clean {
  padding: 20px 0;
  text-align: center;
  color: var(--t3, var(--t-muted));
  font-size: 12px;
}

.eds-att-row {
  padding: 7px 0;
  border-bottom: 1px dashed rgba(0, 0, 0, 0.04);
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  animation: edsAttIn 0.4s var(--ease-standard) var(--rd, 0ms) both;
  /* Pack 7.21: allow inner .eds-att-name ellipsis to actually kick in
     by letting the flex row shrink below its content size */
  min-width: 0;
}

.eds-att-bar {
  width: 3px;
  height: 15px;
  border-radius: 1.5px;
  flex-shrink: 0;
}

.eds-att-name {
  flex: 1;
  color: var(--t1, #1E2A4A);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.eds-att-status {
  font-size: 11px;
  white-space: nowrap;
  font-weight: 500;
  flex-shrink: 0;
}
.eds-att-sep {
  color: var(--t3, var(--t-muted));
  margin: 0 4px;
}

@keyframes edsAttIn {
  from {
    opacity: 0;
    transform: translateX(6px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
</style>
