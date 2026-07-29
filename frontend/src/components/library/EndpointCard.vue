<script setup lang="ts">
/**
 * EndpointCard — reusable for the right-panel, full API tab, and devdocs.
 * Method badges follow the handoff palette. `compact` mode shrinks padding.
 */
import { computed, ref } from "vue";
import type { CatalogEndpointWithSubstitution } from "@/api/apiCatalog";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


const props = defineProps<{
  endpoint: CatalogEndpointWithSubstitution | (CatalogEndpointWithSubstitution & { display_path?: undefined });
  compact?: boolean;
}>();

const emit = defineEmits<{ (e: "try", endpoint: CatalogEndpointWithSubstitution): void }>();

const displayPath = computed(() => (props.endpoint as any).display_path || props.endpoint.path);

const methodMeta = computed(() => {
  const m = (props.endpoint.method || "GET").toUpperCase();
  switch (m) {
    case "GET":       return { bg: "#E1F5EE", fg: "#0F6E56" };
    case "PATCH":     return { bg: "#FAEEDA", fg: "#854F0B" };
    case "POST":      return { bg: "#E6F1FB", fg: "#0C447C" };
    case "PUT":       return { bg: "#E6F1FB", fg: "#0C447C" };
    case "DELETE":    return { bg: "#FCEBEB", fg: "#A82C2B" };
    case "WEBSOCKET": return { bg: "rgba(127,119,221,.15)", fg: "#3C3489" };
    default:          return { bg: "#F1F5F9", fg: "#475569" };
  }
});

const accessMeta = computed(() => {
  const a = (props.endpoint as any).access_level;
  if (a === "public") return { bg: "rgba(29,158,117,.10)", fg: "#0F6E56", label: "public" };
  if (a === "admin")  return { bg: "rgba(226,75,74,.10)",  fg: "#A82C2B", label: "admin"  };
  // Specific scope like "kpi.write"
  if (props.endpoint.required_permission)
    return { bg: "rgba(226,75,74,.08)", fg: "#A82C2B", label: props.endpoint.required_permission };
  return { bg: "rgba(239,159,39,.12)", fg: "#854F0B", label: "authed" };
});

// Highlight {placeholders} in monospace path
const pathSegments = computed(() => {
  const path = displayPath.value;
  const out: { text: string; placeholder: boolean }[] = [];
  const re = /\{[^}]+\}/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(path)) !== null) {
    if (m.index > last) out.push({ text: path.slice(last, m.index), placeholder: false });
    out.push({ text: m[0], placeholder: true });
    last = m.index + m[0].length;
  }
  if (last < path.length) out.push({ text: path.slice(last), placeholder: false });
  return out;
});

const copied = ref(false);
async function copyPath() {
  try {
    await navigator.clipboard.writeText(displayPath.value);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 1500);
  } catch { /* ignore */ }
}
</script>

<template>
  <div class="ep-card" :class="{ 'ep-card-compact': compact }">
    <div class="ep-row">
      <span
        class="ep-method"
        :style="{ background: methodMeta.bg, color: methodMeta.fg }"
      >{{ endpoint.method }}</span>

      <code class="ep-path">
        <template v-for="(seg, i) in pathSegments" :key="i">
          <span :class="{ 'ep-path-ph': seg.placeholder }">{{ seg.text }}</span>
        </template>
      </code>

      <span
        class="ep-access"
        :style="{ background: accessMeta.bg, color: accessMeta.fg }"
      >{{ t(accessMeta.label) }}</span>
    </div>

    <div v-if="endpoint.summary" class="ep-summary">{{ endpoint.summary }}</div>

    <div class="ep-actions">
      <button class="ep-action" :class="{ 'ep-action-ok': copied }" @click="copyPath">
        {{ copied ? t('✓ Скопировано') : t('Копировать') }}
      </button>
      <button
        v-if="endpoint.method !== 'WEBSOCKET'"
        class="ep-action ep-action-primary"
        @click="emit('try', endpoint)"
      >Try →</button>
      <span v-if="endpoint.deprecated" class="ep-deprecated">deprecated</span>
    </div>
  </div>
</template>

<style scoped>
.ep-card {
  background: white;
  border: 0.5px solid #F1EFE8;
  border-radius: 10px;
  padding: 10px 12px;
  display: flex; flex-direction: column; gap: 6px;
  transition: border-color 120ms, box-shadow 120ms;
}
.ep-card:hover { border-color: rgba(127,119,221,.3); box-shadow: 0 2px 8px rgba(15,23,60,.04); }
.ep-card-compact { padding: 8px 10px; gap: 4px; font-size: 11.5px; }

.ep-row {
  display: flex; align-items: center; gap: 8px;
  min-width: 0;
}
.ep-method {
  flex-shrink: 0;
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  padding: 3px 7px;
  border-radius: 5px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
}
.ep-path {
  flex: 1;
  min-width: 0;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 11.5px;
  color: var(--t1, #1E2A4A);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ep-path-ph { color: var(--p-deep); font-weight: 600; }
.ep-access {
  flex-shrink: 0;
  font-size: 9.5px;
  font-weight: 500;
  padding: 2px 7px;
  border-radius: 8px;
}
.ep-summary {
  font-size: 11.5px;
  color: var(--t3, var(--t-muted));
  line-height: 1.4;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.ep-actions { display: flex; gap: 6px; align-items: center; margin-top: 2px; }
.ep-action {
  background: transparent;
  border: 1px solid var(--border-hard);
  border-radius: 6px;
  padding: 3px 8px;
  font-size: 10.5px;
  color: var(--t1, #1E2A4A);
  cursor: pointer;
  transition: all 120ms;
}
.ep-action:hover { background: rgba(127,119,221,.06); border-color: rgba(127,119,221,.3); }
.ep-action-ok { background: rgba(29,158,117,.10); color: #0F6E56; border-color: rgba(29,158,117,.3); }
.ep-action-primary { background: rgba(127,119,221,.08); border-color: rgba(127,119,221,.4); color: var(--p-deep); font-weight: 500; }
.ep-action-primary:hover { background: #7F77DD; color: white; border-color: #7F77DD; }

.ep-deprecated {
  font-size: 9.5px;
  color: #A82C2B;
  background: rgba(226,75,74,.08);
  padding: 2px 6px;
  border-radius: 8px;
  margin-left: auto;
}
</style>
