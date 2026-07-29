<script setup lang="ts">
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();
defineProps<{
  direction: { code: string; label: string; color: string } | null | undefined;
  variant?: "bar" | "dot" | "pill";
  size?: "sm" | "md" | "lg";
}>();
</script>

<template>
  <div v-if="direction" class="dir-badge"
       :class="[`dir-${size || 'md'}`, `dir-${variant || 'bar'}`]"
       :style="(variant || 'bar') === 'pill'
         ? { background: direction.color + '18', color: direction.color }
         : {}">
    <span v-if="(variant || 'bar') === 'bar'" class="dir-bar"
          :style="{ background: direction.color }"></span>
    <span v-else-if="(variant || 'bar') === 'dot'" class="dir-dot"
          :style="{ background: direction.color }"></span>
    <!-- bar/dot: НЕЙТРАЛЬНЫЙ текст + цвет только в акценте (полоска/точка) — иначе
         разноцветные названия «светофорят». pill остаётся цветным чипом. -->
    <span class="dir-label" :style="(variant || 'bar') === 'pill' ? {} : { color: 'var(--t1, #1E2A4A)' }">
      {{ t(direction.label) }}
    </span>
  </div>
</template>

<style scoped>
.dir-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  line-height: 1;
}

/* Variant: pill — coloured background fill */
.dir-pill {
  padding: 3px 9px;
  border-radius: 11px;
  font-weight: 500;
}

/* Variant: bar — vertical 3px stripe */
.dir-bar {
  display: inline-block;
  width: 3px;
  border-radius: 1.5px;
  flex-shrink: 0;
}

/* Variant: dot */
.dir-dot {
  display: inline-block;
  border-radius: 50%;
  flex-shrink: 0;
}

.dir-label {
  font-weight: 500;
  letter-spacing: -0.005em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dir-sm .dir-bar { height: 10px; }
.dir-sm .dir-dot { width: 6px; height: 6px; }
.dir-sm .dir-label { font-size: 10px; letter-spacing: 0.01em; }
.dir-sm.dir-pill { padding: 2px 7px; font-size: 9.5px; }

.dir-md .dir-bar { height: 12px; }
.dir-md .dir-dot { width: 7px; height: 7px; }
.dir-md .dir-label { font-size: 11.5px; }
.dir-md.dir-pill { padding: 3px 9px; font-size: 11px; }

.dir-lg .dir-bar { height: 16px; width: 4px; }
.dir-lg .dir-dot { width: 9px; height: 9px; }
.dir-lg .dir-label { font-size: 13px; }
.dir-lg.dir-pill { padding: 5px 12px; font-size: 12px; }
</style>
