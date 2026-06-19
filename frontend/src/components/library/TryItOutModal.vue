<script setup lang="ts">
/**
 * TryItOutModal — live execution for catalog endpoints (Phase 5.6).
 * Routes through backend /api-catalog/try so auth context + audit work.
 */
import { computed, ref, watch } from "vue";
import { apiCatalog, type CatalogEndpointWithSubstitution, type TryResponse } from "@/api/apiCatalog";
import ModalShell from "@/components/ModalShell.vue";

const props = defineProps<{
  open: boolean;
  endpoint: CatalogEndpointWithSubstitution | null;
}>();
const emit = defineEmits<{ (e: "close"): void }>();

const url        = ref("");
const bodyJson   = ref("");
const headersTxt = ref("");
const running    = ref(false);
const response   = ref<TryResponse | null>(null);
const error      = ref<string | null>(null);
const showConfirm= ref(false);

const isDestructive = computed(() =>
  props.endpoint && ["POST", "PATCH", "PUT", "DELETE"].includes(props.endpoint.method.toUpperCase()),
);

watch(() => props.open, (open) => {
  if (open && props.endpoint) {
    const p = (props.endpoint as any).display_path || props.endpoint.path;
    url.value      = "/api" + p;
    bodyJson.value = isDestructive.value
      ? JSON.stringify({ example: "see schema" }, null, 2)
      : "";
    headersTxt.value = "";
    response.value = null;
    error.value = null;
    showConfirm.value = false;
  }
});

async function run() {
  if (!props.endpoint) return;
  if (isDestructive.value && !showConfirm.value) {
    showConfirm.value = true;
    return;
  }
  running.value = true;
  error.value = null;
  response.value = null;
  try {
    let parsedBody: any = null;
    if (bodyJson.value.trim() && isDestructive.value) {
      try {
        parsedBody = JSON.parse(bodyJson.value);
      } catch {
        error.value = "JSON body не парсится — проверьте синтаксис";
        running.value = false;
        return;
      }
    }
    const headers: Record<string, string> = {};
    headersTxt.value.split("\n").forEach((line) => {
      const idx = line.indexOf(":");
      if (idx > 0) {
        const k = line.slice(0, idx).trim();
        const v = line.slice(idx + 1).trim();
        if (k && v) headers[k] = v;
      }
    });
    response.value = await apiCatalog.try({
      method: props.endpoint.method as any,
      path: url.value,
      headers,
      body: parsedBody,
      confirm_destructive: isDestructive.value,
    });
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Запрос упал";
  } finally {
    running.value = false;
  }
}

function statusTone(code: number): string {
  if (code >= 200 && code < 300) return "ok";
  if (code >= 400 && code < 500) return "warn";
  return "bad";
}

function fmtJson(s: string | null): string {
  if (!s) return "";
  try {
    return JSON.stringify(JSON.parse(s), null, 2);
  } catch {
    return s;
  }
}
</script>

<template>
  <ModalShell :open="open && !!endpoint" size="lg" @close="emit('close')">
    <template #header>
      <div v-if="endpoint" class="tio-head-l">
        <div class="tio-eyebrow">Try it out</div>
        <h3 class="tio-title">
          <span class="tio-method" :data-m="endpoint.method.toUpperCase()">{{ endpoint.method }}</span>
          {{ (endpoint as any).display_path || endpoint.path }}
        </h3>
      </div>
    </template>

    <template v-if="endpoint">
      <div class="tio-body">
        <div class="tio-row">
          <label class="tio-label">URL</label>
          <input v-model="url" type="text" class="tio-input tio-input-mono" />
        </div>

        <div class="tio-row">
          <label class="tio-label">Headers <span class="tio-hint">(по строке: Name: value)</span></label>
          <textarea v-model="headersTxt" rows="2" class="tio-input tio-input-mono"
                    placeholder="X-Custom-Header: value"></textarea>
        </div>

        <div v-if="isDestructive" class="tio-row">
          <label class="tio-label">Body (JSON)</label>
          <textarea v-model="bodyJson" rows="6" class="tio-input tio-input-mono"></textarea>
        </div>

        <div v-if="error" class="tio-err">{{ error }}</div>

        <div v-if="showConfirm && !response" class="tio-confirm">
          <b>{{ endpoint.method }}</b> — деструктивный запрос. Реальные данные изменятся.
          Нажмите «Run» ещё раз для подтверждения.
        </div>

        <!-- Response -->
        <div v-if="response" class="tio-resp">
          <div class="tio-resp-h">
            <span class="tio-resp-status" :class="`tio-resp-${statusTone(response.status_code)}`">
              {{ response.status_code }}
            </span>
            <span class="tio-resp-time">{{ response.duration_ms }} ms</span>
            <span v-if="response.truncated" class="tio-resp-trunc">truncated (>64KB)</span>
          </div>
          <pre class="tio-resp-body">{{ fmtJson(response.body) }}</pre>
        </div>
      </div>
    </template>

    <template #footer>
      <button class="tio-btn tio-btn-secondary" @click="emit('close')">Закрыть</button>
      <button
        class="tio-btn tio-btn-primary"
        :disabled="running || !url"
        @click="run"
      >{{ running ? "Выполняем…" : showConfirm ? "Run (подтвердить)" : "Run" }}</button>
    </template>
  </ModalShell>
</template>

<style scoped>
/* Обёртка/шапка/футер — из ModalShell (Teleport + ESC + фокус-трап + --z-top). */
.tio-head-l { display: flex; flex-direction: column; min-width: 0; }
.tio-eyebrow { font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--t3, var(--t-muted)); font-weight: 500; }
.tio-title   { font-size: 14px; font-weight: 500; color: var(--t1, #1E2A4A); margin: 4px 0 0 0; font-family: ui-monospace, "SF Mono", Menlo, monospace; word-break: break-all; }
.tio-method  {
  font-size: 9.5px; font-weight: 600; padding: 3px 7px; border-radius: 5px;
  margin-right: 6px; letter-spacing: 0.06em;
}
.tio-method[data-m="GET"]    { background: #E1F5EE; color: #0F6E56; }
.tio-method[data-m="PATCH"]  { background: #FAEEDA; color: #854F0B; }
.tio-method[data-m="POST"],
.tio-method[data-m="PUT"]    { background: #E6F1FB; color: #0C447C; }
.tio-method[data-m="DELETE"] { background: #FCEBEB; color: #A82C2B; }

.tio-body { display: flex; flex-direction: column; gap: 12px; }
.tio-row { display: flex; flex-direction: column; gap: 5px; }
.tio-label { font-size: 10.5px; letter-spacing: 0.04em; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; }
.tio-hint  { text-transform: none; color: #C8C7C0; font-weight: 400; }
.tio-input {
  border: 1px solid var(--border-hard); border-radius: 8px;
  padding: 8px 10px; font-size: 12px;
  color: var(--t1, #1E2A4A); background: white;
  outline: none; font-family: inherit; resize: vertical;
}
.tio-input:focus { border-color: #7F77DD; box-shadow: 0 0 0 2px rgba(127,119,221,.15); }
.tio-input-mono { font-family: ui-monospace, "SF Mono", Menlo, monospace; }

.tio-err     { padding: 8px 12px; background: rgba(226,75,74,.08); color: #A82C2B; border-radius: 8px; font-size: 12px; }
.tio-confirm { padding: 10px 12px; background: rgba(239,159,39,.10); color: #854F0B; border-radius: 8px; font-size: 12px; }

.tio-resp { display: flex; flex-direction: column; gap: 6px; }
.tio-resp-h { display: flex; align-items: center; gap: 8px; font-size: 11px; }
.tio-resp-status { padding: 2px 8px; border-radius: 6px; font-weight: 600; font-variant-numeric: tabular-nums; }
.tio-resp-ok   { background: rgba(29,158,117,.10); color: #0F6E56; }
.tio-resp-warn { background: rgba(239,159,39,.12); color: #854F0B; }
.tio-resp-bad  { background: rgba(226,75,74,.10); color: #A82C2B; }
.tio-resp-time { color: var(--t3, var(--t-muted)); }
.tio-resp-trunc{ color: #A82C2B; }
.tio-resp-body {
  background: #1E2A4A; color: var(--border-input);
  border-radius: 8px; padding: 12px;
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  font-size: 11px; line-height: 1.5;
  max-height: 360px; overflow: auto;
  margin: 0;
  white-space: pre-wrap; word-wrap: break-word;
}

.tio-btn  { padding: 7px 14px; border-radius: 8px; font-size: 12px; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all 150ms; }
.tio-btn-secondary { background: transparent; color: var(--t1, #1E2A4A); border-color: var(--border-hard); }
.tio-btn-secondary:hover { background: rgba(15,23,60,.04); }
.tio-btn-primary   { background: #7F77DD; color: white; }
.tio-btn-primary:hover:not(:disabled) { background: var(--p-deep); }
.tio-btn-primary:disabled { opacity: .6; cursor: wait; }
</style>
