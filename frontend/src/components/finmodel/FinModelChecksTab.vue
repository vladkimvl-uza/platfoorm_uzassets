<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { finmodelApi, type ValidationIssue } from "@/api/finmodel";

const props = defineProps<{
  companyId: string;
  year: number | null;
}>();

const issues = ref<ValidationIssue[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

async function reload() {
  error.value = null;
  if (!props.companyId || !props.year) {
    issues.value = [];
    return;
  }
  loading.value = true;
  try {
    issues.value = await finmodelApi.validate(props.companyId, props.year);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить проверки";
  } finally {
    loading.value = false;
  }
}

watch(() => [props.companyId, props.year], reload, { immediate: true });

const counts = computed(() => ({
  error: issues.value.filter(i => i.severity === "error").length,
  warning: issues.value.filter(i => i.severity === "warning").length,
  info: issues.value.filter(i => i.severity === "info").length,
}));
</script>

<template>
  <section class="fm-checks">
    <header class="fm-checks-head">
      <span class="fm-checks-cap">Валидация модели</span>
      <span class="fm-checks-counts">
        <span class="fm-c-pill fm-c-error">errors: {{ counts.error }}</span>
        <span class="fm-c-pill fm-c-warning">warnings: {{ counts.warning }}</span>
        <span class="fm-c-pill fm-c-info">info: {{ counts.info }}</span>
      </span>
      <button class="fm-c-refresh" type="button" :disabled="loading" @click="reload">
        {{ loading ? "Проверяем…" : "Обновить" }}
      </button>
    </header>

    <div v-if="!companyId || !year" class="fm-checks-empty">
      Выберите компанию и год.
    </div>
    <div v-else-if="error" class="fm-checks-err">{{ error }}</div>
    <div v-else-if="loading && !issues.length" class="fm-checks-empty">Проверяем…</div>
    <div v-else-if="issues.length === 0" class="fm-checks-ok">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none"
           stroke="#0F6E56" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="8" cy="8" r="6"/><path d="M5 8l2 2 4-4"/>
      </svg>
      Все проверки пройдены — замечаний нет.
    </div>
    <ul v-else class="fm-checks-list">
      <li v-for="i in issues" :key="i.rule_id + (i.row_code || '')" :class="['fm-check-item', `fm-sev-${i.severity}`]">
        <span class="fm-check-sev">{{ i.severity }}</span>
        <span v-if="i.row_code" class="fm-check-code">{{ i.row_code }}</span>
        <span class="fm-check-msg">{{ i.message_ru }}</span>
        <span class="fm-check-rule">{{ i.rule_id }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.fm-checks { padding: 16px 18px; }
.fm-checks-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.fm-checks-cap {
  font-size: 10px;
  font-weight: 500;
  color: var(--t3, var(--t-muted));
  letter-spacing: .08em;
  text-transform: uppercase;
}
.fm-checks-counts { display: flex; gap: 6px; }
.fm-c-pill {
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 500;
}
.fm-c-error { background: rgba(226, 75, 74, .10); color: #C0322F; }
.fm-c-warning { background: rgba(239, 159, 39, .12); color: #B96A07; }
.fm-c-info { background: rgba(55, 138, 221, .10); color: #1F5A99; }
.fm-c-refresh {
  margin-left: auto;
  height: 24px;
  padding: 0 10px;
  background: transparent;
  border: 1px solid var(--border-hard);
  border-radius: 6px;
  font-size: 11px;
  color: var(--t1, #1E2A4A);
  font-family: inherit;
  cursor: pointer;
}
.fm-c-refresh:disabled { opacity: .5; cursor: not-allowed; }
.fm-checks-empty {
  padding: 28px 12px;
  text-align: center;
  font-size: 11px;
  color: var(--t3, var(--t-muted));
  font-style: italic;
}
.fm-checks-err {
  padding: 12px 14px;
  background: rgba(226, 75, 74, .06);
  border: 1px solid rgba(226, 75, 74, .25);
  border-radius: 8px;
  font-size: 11px;
  color: #C0322F;
}
.fm-checks-ok {
  padding: 24px;
  background: rgba(29, 158, 117, .06);
  border: 1px solid rgba(29, 158, 117, .25);
  border-radius: 10px;
  font-size: 12px;
  color: #0F6E56;
  display: flex;
  align-items: center;
  gap: 9px;
  justify-content: center;
}
.fm-checks-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px; }
.fm-check-item {
  display: grid;
  grid-template-columns: 70px 60px 1fr 140px;
  gap: 12px;
  align-items: center;
  padding: 9px 12px;
  border-radius: 7px;
  font-size: 11.5px;
}
.fm-sev-error { background: rgba(226, 75, 74, .05); border: 0.5px solid rgba(226, 75, 74, .25); }
.fm-sev-warning { background: rgba(239, 159, 39, .05); border: 0.5px solid rgba(239, 159, 39, .25); }
.fm-sev-info { background: rgba(55, 138, 221, .05); border: 0.5px solid rgba(55, 138, 221, .25); }
.fm-check-sev {
  font-size: 9.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: .06em;
}
.fm-sev-error .fm-check-sev { color: #C0322F; }
.fm-sev-warning .fm-check-sev { color: #B96A07; }
.fm-sev-info .fm-check-sev { color: #1F5A99; }
.fm-check-code {
  font-family: ui-monospace, monospace;
  font-size: 10.5px;
  color: var(--t3, var(--t-muted));
}
.fm-check-msg { color: var(--t1, #1E2A4A); }
.fm-check-rule {
  font-family: ui-monospace, monospace;
  font-size: 10px;
  color: #C8C7C0;
  text-align: right;
}
</style>
