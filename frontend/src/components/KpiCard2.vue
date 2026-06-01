<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  label: string;
  value?: number | string;
  // Цвет акцента — экспонируется как --kpi2-accent для top stripe
  // (стрипа рендерится через uza-kpi-etalon.css :where(.kpi2)::before)
  accent?: string;
  // Анимация задержка ms (для каскадного появления)
  animationDelay?: number;
  // Затемнить если значение = 0
  dim?: boolean;
  // Доп. под-значение
  subValue?: string;
  // Split layout — два числа (например проектов/задач)
  splitLeft?: { value: number | string; sub: string };
  splitRight?: { value: number | string; sub: string };
  size?: "sm" | "md" | "lg";
  // D2 — alert-вариант для критических метрик (просрочка и т.п.)
  variant?: "default" | "alert";
  // D3 — числа разной жирностью (целая 600 / дробная+единица muted)
  mixed?: boolean;
}>();

// D3 — разбор значения на префикс/целую/дробную/единицу.
// Строгий матч: опц. валюта + число + опц. дробь + опц. известная единица.
// Всё прочее (Q3, v3, текст, даты, «—») → null → обычный рендер без искажений.
const numParts = computed(() => {
  const raw = String(props.value ?? "").trim();
  const m = raw.match(/^([$₽€⃀]?)([\d\s,]*\d)(\.\d+)?\s*(%|M|B|K|млн|млрд|тыс|шт)?$/i);
  if (!m) return null;
  return { pre: m[1] || "", int: m[2], dec: m[3] || "", unit: m[4] || "" };
});
</script>

<template>
  <!-- Pack 7.9: убран класс fin-shimmer чтобы scoped ::before не перебивал
       эталонный top-stripe из uza-kpi-etalon.css.
       Сам shimmer pass теперь приходит из exec-animations.css globally
       через .kpi2 selector (без scoping). -->
  <div class="kpi2"
       :class="[`size-${size || 'md'}`, { dim, 'is-alert': variant === 'alert' }]"
       :style="{
         '--kpi2-accent': accent || '#7F77DD',
         animationDelay: (animationDelay || 0) + 'ms',
       } as any">
    <span v-if="variant === 'alert'" class="kpi2-alert-dot"></span>
    <div class="kpi2-lbl">{{ label }}</div>

    <!-- Split layout (two values side-by-side) -->
    <div v-if="splitLeft && splitRight" class="kpi2-split">
      <div>
        <div class="kpi2-num" :style="{ color: accent || '#7F77DD' }">
          {{ splitLeft.value }}
        </div>
        <div class="kpi2-sub">{{ splitLeft.sub }}</div>
      </div>
      <div class="kpi2-divider"></div>
      <div>
        <div class="kpi2-num" :style="{ color: accent || '#7F77DD' }">
          {{ splitRight.value }}
        </div>
        <div class="kpi2-sub">{{ splitRight.sub }}</div>
      </div>
    </div>

    <!-- Single value -->
    <template v-else>
      <div class="kpi2-val">
        <template v-if="mixed !== false && numParts"><span v-if="numParts.pre" class="kv-unit">{{ numParts.pre }}</span><span class="kv-int">{{ numParts.int }}</span><span v-if="numParts.dec" class="kv-dec">{{ numParts.dec }}</span><span v-if="numParts.unit" class="kv-unit">{{ numParts.unit }}</span></template>
        <template v-else>{{ value }}</template>
      </div>
      <div v-if="subValue" class="kpi2-sub-bottom">{{ subValue }}</div>
    </template>
  </div>
</template>

<style scoped>
@keyframes kpi2In {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* Pack 7.9 changes:
 *   • REMOVED border-left: 3px solid var(--kpi2-accent)
 *     (top stripe via uza-kpi-etalon.css is now the sole accent)
 *   • REMOVED .kpi2.fin-shimmer::before scoped selector
 *     (it conflicted with the etalon ::before; global shimmer remains
 *      via exec-animations.css)
 */
.kpi2 {
  position: relative;
  background: var(--bg1, #fff);
  padding: 14px 18px;
  border-radius: 12px;
  border: 1px solid var(--border1, #E2E8F0);
  box-shadow: 0 4px 12px rgba(15, 23, 60, 0.04);
  animation: kpi2In .5s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  overflow: hidden;
}

.kpi2.dim {
  opacity: 0.55;
}

.kpi2-lbl {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--t3, #64748B);
  margin-bottom: 6px;
  position: relative;
  z-index: 3;
}

.kpi2-val {
  font-size: 28px;
  font-weight: 400;
  letter-spacing: -0.04em;
  line-height: 1;
  color: var(--t1, #1E2A4A);
  font-variant-numeric: tabular-nums;
  position: relative;
  z-index: 3;
}

.kpi2-sub-bottom {
  font-size: 10px;
  color: var(--t3, #64748B);
  margin-top: 4px;
  position: relative;
  z-index: 3;
}

.kpi2-split {
  display: grid;
  grid-template-columns: 1fr 1px 1fr;
  align-items: center;
  margin-top: 4px;
  position: relative;
  z-index: 3;
}
.kpi2-num {
  font-size: 22px;
  font-weight: 400;
  letter-spacing: -0.04em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.kpi2-sub {
  font-size: 10px;
  color: var(--t3, #64748B);
  margin-top: 2px;
}
.kpi2-divider {
  background: var(--border1, #E2E8F0);
  height: 32px;
}
.kpi2-split > div:nth-child(3) {
  padding-left: 12px;
}

/* Sizes */
.size-sm { padding: 10px 14px; }
.size-sm .kpi2-val { font-size: 22px; }
.size-sm .kpi2-num { font-size: 18px; }

.size-lg { padding: 18px 22px; }
.size-lg .kpi2-val { font-size: 36px; }
.size-lg .kpi2-num { font-size: 28px; }

/* D3 — mixed-weight number (целая 600 / дробная + единица 400 muted) */
.kv-int  { font-weight: 600; }
.kv-dec  { font-weight: 400; color: var(--t3, #64748B); }
.kv-unit { font-weight: 400; font-size: .62em; color: var(--t3, #64748B); margin-left: 1px; }

/* D2 — alert-вариант (критические метрики) */
.kpi2.is-alert {
  background: linear-gradient(135deg, #7F1D1D 0%, #B5302F 100%);
  border-color: rgba(226, 75, 74, .5);
  box-shadow: 0 6px 18px rgba(150, 30, 30, .28);
}
.kpi2.is-alert .kpi2-lbl { color: rgba(255, 255, 255, .78); }
.kpi2.is-alert .kpi2-val,
.kpi2.is-alert .kpi2-val .kv-dec,
.kpi2.is-alert .kpi2-val .kv-unit { color: #fff; }
.kpi2.is-alert .kpi2-sub-bottom { color: rgba(255, 255, 255, .72); }
.kpi2-alert-dot {
  position: absolute; top: 12px; right: 14px; z-index: 4;
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--bg1, #fff);
  animation: kpi2Pulse 1.6s ease-in-out infinite;
}
@keyframes kpi2Pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%      { opacity: .35; transform: scale(.72); }
}
</style>
