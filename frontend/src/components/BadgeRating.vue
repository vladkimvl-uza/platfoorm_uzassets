<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  agency: string;  // "Fitch" | "S&P" | "Moody's" | "Sustainable Fitch" | "S&P ESG" | "CDP"
  rating: string | null | undefined;
  score?: string | null;
  outlook?: string | null;
  size?: "sm" | "md";
}>();

// Точная логика _ratBadge из легасиа line 32469
const ratClass = computed(() => {
  const r = (props.rating || "").toUpperCase();
  if (!r) return null;

  const ag = props.agency;
  if (ag === "Fitch" || ag === "S&P" || ag === "Moody's") {
    if (r.startsWith("AA") || r.startsWith("A")) return "rat-good";
    if (r.startsWith("BBB")) return "rat-good";
    if (r.startsWith("BB") || r.startsWith("B+") || r.startsWith("B ")) return "rat-mid";
    if (r === "B" || r.startsWith("B-")) return "rat-mid";
    if (r.startsWith("CCC") || r === "D") return "rat-low";
    return "rat-mid";
  }
  if (ag === "Sustainable Fitch" || ag === "S&P ESG") {
    const n = parseInt(r);
    if (n <= 5) {
      // rating scale 1-5
      if (n <= 2) return "rat-good";
      if (n === 3) return "rat-mid";
      return "rat-low";
    }
    // score scale 0-100
    if (n >= 65) return "rat-good";
    if (n >= 45) return "rat-mid";
    return "rat-low";
  }
  if (ag === "CDP") {
    if (r === "A" || r === "A-") return "rat-good";
    if (r === "B" || r === "B-") return "rat-mid";
    return "rat-low";
  }
  return "rat-mid";
});

const display = computed(() => {
  const r = (props.rating || "").toUpperCase();
  if (!r) return "—";
  if ((props.agency === "Sustainable Fitch" || props.agency === "S&P ESG")
      && props.score && String(props.score).trim() !== r) {
    return `${r}·${props.score}`;
  }
  return r;
});

const outlookMeta = computed(() => {
  if (!props.outlook) return null;
  const m: Record<string, { label: string; color: string }> = {
    Positive:   { label: "Поз.",  color: "#1D9E75" },
    Negative:   { label: "Нег.",  color: "#E24B4A" },
    Developing: { label: "Разв.", color: "#378ADD" },
    Stable:     { label: "Стаб.", color: "#378ADD" },
  };
  return m[props.outlook] || { label: "Стаб.", color: "#378ADD" };
});
</script>

<template>
  <span class="rt-row">
    <span v-if="rating" class="rt-rat" :class="[ratClass, `size-${size || 'md'}`]">
      {{ display }}
    </span>
    <span v-else class="rt-dash">—</span>
    <span v-if="outlookMeta" class="rt-olk"
          :style="{ background: outlookMeta.color + '18', color: outlookMeta.color }">
      {{ outlookMeta.label }}
    </span>
  </span>
</template>

<style scoped>
.rt-row {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.rt-rat {
  display: inline-block;
  font-weight: 700;
  border-radius: 4px;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.02em;
  line-height: 1;
}
.rt-rat.size-sm { padding: 2px 6px; font-size: 10px; }
.rt-rat.size-md { padding: 2px 7px; font-size: 11px; }

.rat-good { background: var(--green-l); color: #0E7A58; }
.rat-mid  { background: var(--orange-l); color: #92400E; }
.rat-low  { background: var(--red-l); color: var(--sev-critical); }

.rt-dash {
  color: var(--t3, #94a3b8);
  font-size: 11px;
}

.rt-olk {
  display: inline-block;
  font-size: 8.5px;
  font-weight: 600;
  padding: 1px 4px;
  border-radius: 3px;
  line-height: 1;
}
</style>
