<script setup lang="ts">
defineProps<{
  consultants: Array<{ id: string; abbr: string; color: string }> | string[] | null | undefined;
  size?: "sm" | "md";
}>();

// Default consultant palette — fallback if consultant has no color
const DEFAULT_COLORS: Record<string, string> = {
  kpmg:       "#0091DA",
  pwc:        "#D04A02",
  ey:         "#FFE600",
  deloitte:   "#86BC25",
  mckinsey:   "#003A70",
  bcg:        "#177B57",
  rothschild: "#7C0007",
  cmt:        "#7F77DD",
  techenergy: "#EF9F27",
  degolyer:   "#888780",
  hpbs:       "#534AB7",
};
const DEFAULT_LABELS: Record<string, string> = {
  kpmg: "KPMG", pwc: "PwC", ey: "EY", deloitte: "DLT",
  mckinsey: "McK", bcg: "BCG", rothschild: "ROT",
  cmt: "CMT", techenergy: "TECH", degolyer: "DGY", hpbs: "HPB",
};

function normalize(c: any): { id: string; abbr: string; color: string } {
  if (typeof c === "string") {
    const k = c.toLowerCase();
    return {
      id: k,
      abbr: DEFAULT_LABELS[k] || c.toUpperCase().slice(0, 4),
      color: DEFAULT_COLORS[k] || "#7F77DD",
    };
  }
  return c;
}
</script>

<template>
  <div v-if="consultants && consultants.length" class="cons-row" :class="`size-${size || 'md'}`">
    <span v-for="c in consultants.map(normalize)" :key="c.id"
          class="cons-pill"
          :style="{
            background: c.color + '18',
            color: c.color,
          }">
      {{ c.abbr }}
    </span>
  </div>
</template>

<style scoped>
.cons-row {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 3px;
}
.cons-pill {
  font-weight: 700;
  border-radius: 4px;
  white-space: nowrap;
  letter-spacing: 0.02em;
  line-height: 1;
}
.size-sm .cons-pill { font-size: 9px;  padding: 1px 4px; }
.size-md .cons-pill { font-size: 10px; padding: 1px 5px; }
</style>
