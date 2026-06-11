<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  // Либо abbr+sector задаём явно, либо name (тогда подберём из COMPANIES)
  abbr?: string;
  name?: string;
  sector?: string;
  size?: number;  // px высоты, default 22
}>();

// Из легасиа bgMap/txMap (line 7100)
const SECTOR_COLORS: Record<string, { bg: string; tx: string }> = {
  mining:    { bg: "#EEEDFE",                  tx: "#3C3489" },
  oilgas:    { bg: "#DCFCE7",                  tx: "#1D9E75" },
  energy:    { bg: "#FEF9C3",                  tx: "#633806" },
  transport: { bg: "rgba(55,138,221,.10)",     tx: "#378ADD" },
  other:     { bg: "#F1EFE8",                  tx: "#444441" },
};

const sec = computed(() => SECTOR_COLORS[props.sector || "other"] || SECTOR_COLORS.other);
const s = computed(() => props.size || 22);
const fontSize = computed(() => (s.value < 24 ? 9 : 10));
const minWidth = computed(() => Math.max(s.value, 36));

const abbrText = computed(() => {
  if (props.abbr) return props.abbr;
  if (props.name) {
    return props.name
      .split(/\s+/)
      .map(w => w[0])
      .join("")
      .toUpperCase()
      .slice(0, 4);
  }
  return "?";
});
</script>

<template>
  <div class="co-badge"
       :style="{
         minWidth: minWidth + 'px',
         height: s + 'px',
         background: sec.bg,
         color: sec.tx,
         fontSize: fontSize + 'px',
       }">
    {{ abbrText }}
  </div>
</template>

<style scoped>
.co-badge {
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-weight: 500;
  font-family: "Geist Mono", monospace;
  letter-spacing: 0.03em;
  padding: 0 4px;
  line-height: 1;
}
</style>
