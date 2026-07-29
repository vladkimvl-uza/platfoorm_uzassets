<script setup lang="ts">
/**
 * PmoHealth — авто-RAG здоровья портфеля + генерация статус-отчёта (P2).
 * Сигналы (слип/блок/просрочка/риски) считает бэкенд `/pmo/.../health`.
 */
import { ref, computed, watch, onMounted } from "vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import { pmoApi, type HealthResponse, type StatusReport } from "@/api/pmo";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";
const { t } = useI18n();


const props = defineProps<{ companyCode: string; canEdit?: boolean; refreshTick?: number }>();
const emit = defineEmits<{ (e: "open", p: { id: string; kind: "project" | "task" }): void }>();

const loading = ref(true);
const error = ref<string | null>(null);
const data = ref<HealthResponse | null>(null);
const reports = ref<StatusReport[]>([]);
const genBusy = ref(false);
const useAi = ref(false);
const showHistory = ref(false);

const RAG_LABELS: Record<string, string> = {
  green: i18nKey("зелёный"),
  amber: i18nKey("жёлтый"),
  red: i18nKey("красный"),
};
const RAG_C: Record<string, string> = { green: "#1D9E75", amber: "#D97706", red: "#E24B4A" };

async function load() {
  loading.value = true; error.value = null;
  try {
    const [h, rs] = await Promise.all([
      pmoApi.getHealth(props.companyCode),
      pmoApi.listStatusReports(props.companyCode).catch(() => []),
    ]);
    data.value = h;
    reports.value = rs;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || t('Не удалось загрузить здоровье');
  } finally {
    loading.value = false;
  }
}
onMounted(load);
watch(() => [props.companyCode, props.refreshTick], load);

async function generate() {
  genBusy.value = true;
  try {
    const rep = await pmoApi.createStatusReport(props.companyCode, { project_id: null, use_ai: useAi.value });
    reports.value = [rep, ...reports.value];
    showHistory.value = true;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось сформировать отчёт');
  } finally {
    genBusy.value = false;
  }
}

const fmtDt = (s: string) => new Date(s).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const latest = computed(() => reports.value[0] || null);
</script>

<template>
  <div class="ph">
    <UzaStateBlock v-if="loading" state="loading" :text="t('Расчёт здоровья портфеля…')" />
    <UzaStateBlock v-else-if="error" state="error" variant="block" :title="t('Ошибка')" :text="error" retry @retry="load" />

    <template v-else-if="data">
      <!-- Сводка портфеля -->
      <div class="ph-top">
        <div class="ph-rag" :style="{ '--rag': RAG_C[data.portfolio_rag] }">
          <span class="ph-rag-dot"></span>
          <div>
            <div class="ph-rag-l">{{ t('Здоровье портфеля') }}</div>
            <div class="ph-rag-v">{{ t(RAG_LABELS[data.portfolio_rag]) }}</div>
          </div>
        </div>
        <div class="ph-counts">
          <span class="ph-cnt" style="--c:#E24B4A"><b>{{ data.red }}</b> {{ t('красных') }}</span>
          <span class="ph-cnt" style="--c:#D97706"><b>{{ data.amber }}</b> {{ t('жёлтых') }}</span>
          <span class="ph-cnt" style="--c:#1D9E75"><b>{{ data.green }}</b> {{ t('зелёных') }}</span>
          <span class="ph-cnt" style="--c:#534AB7"><b>{{ data.open_risks }}</b> {{ t('откр. рисков') }}</span>
          <span class="ph-cnt" style="--c:#E24B4A"><b>{{ data.high_risks }}</b> {{ t('высоких') }}</span>
        </div>
        <div class="ph-gen">
          <label class="ph-ai"><input type="checkbox" v-model="useAi" :disabled="!canEdit" /> {{ t('AI-резюме') }}</label>
          <button class="ph-gen-btn" :disabled="!canEdit || genBusy" @click="generate">
            {{ genBusy ? t('Формирую…') : t('Сформировать статус-отчёт') }}
          </button>
        </div>
      </div>

      <!-- Последний отчёт -->
      <div v-if="latest" class="ph-report">
        <div class="ph-report-h">
          <span class="ph-rag-dot sm" :style="{ '--rag': RAG_C[latest.rag] }"></span>
          {{ t('Статус-отчёт ·') }} {{ fmtDt(latest.created_at) }}
          <button class="ph-hist-toggle" @click="showHistory = !showHistory">
            {{ showHistory ? t('скрыть историю') : t('история ({value0})', { value0: reports.length }) }}
          </button>
        </div>
        <pre class="ph-report-body">{{ latest.summary }}</pre>
      </div>

      <div v-if="showHistory && reports.length > 1" class="ph-hist">
        <div v-for="r in reports.slice(1)" :key="r.id" class="ph-hist-item">
          <span class="ph-rag-dot sm" :style="{ '--rag': RAG_C[r.rag] }"></span>
          <span class="ph-hist-dt">{{ fmtDt(r.created_at) }}</span>
          <span class="ph-hist-sum">{{ (r.summary || "").split("\n")[0] }}</span>
        </div>
      </div>

      <!-- Карточки проектов -->
      <div class="ph-grid">
        <div
          v-for="(p, idx) in data.projects"
          :key="p.project_id || 'orphan'"
          class="ph-card"
          :class="{ 'is-click': !!p.project_id, ['rag-' + p.rag]: true }"
          :style="{ '--rag': RAG_C[p.rag], animationDelay: Math.min(idx * 0.04, 0.5) + 's' }"
          @click="p.project_id && emit('open', { id: p.project_id, kind: 'project' })"
        >
          <div class="ph-card-h">
            <span class="ph-rag-dot sm"></span>
            <span class="ph-card-title">{{ p.title }}</span>
            <span class="ph-card-rag">{{ t(RAG_LABELS[p.rag]) }}</span>
          </div>
          <div class="ph-bar"><span :style="{ width: p.progress_percent + '%', background: RAG_C[p.rag] }"></span></div>
          <div class="ph-metrics">
            <span :class="{ bad: p.slip_days > 0 }">{{ t('слип') }} {{ p.slip_days }}{{ t('д') }}</span>
            <span :class="{ bad: p.overdue_count > 0 }">{{ t('просроч.') }} {{ p.overdue_count }}</span>
            <span :class="{ bad: p.blocked_count > 0 }">{{ t('блок.') }} {{ p.blocked_count }}</span>
            <span :class="{ bad: p.high_risks > 0 }">{{ t('риски') }} {{ p.open_risks }}<template v-if="p.high_risks">/{{ p.high_risks }}{{ t('выс') }}</template></span>
          </div>
          <div v-if="p.reasons.length" class="ph-reasons">
            <span v-for="(r, i) in p.reasons" :key="i" class="ph-reason">{{ r }}</span>
          </div>
        </div>
      </div>

      <UzaStateBlock v-if="!data.projects.length" state="empty" variant="block" :title="t('Нет проектов')" :text="t('Добавьте проекты с задачами и датами — здесь появится их здоровье.')" />
    </template>
  </div>
</template>

<style scoped>
.ph { padding: 4px 2px 24px; }

.ph-top { display: flex; flex-wrap: wrap; align-items: center; gap: 18px; padding: 15px 18px; border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: var(--r2, 14px); background: linear-gradient(180deg, var(--bg1, #fff), var(--bg2, #fafafc)); box-shadow: var(--sh); margin-bottom: 14px; animation: phCardIn .45s var(--ease-out) both; }
.ph-rag { display: flex; align-items: center; gap: 12px; }
.ph-rag-dot { width: 17px; height: 17px; border-radius: 50%; background: var(--rag, #94a3b8); box-shadow: 0 0 0 4px color-mix(in srgb, var(--rag) 16%, transparent), 0 0 16px color-mix(in srgb, var(--rag) 45%, transparent); flex-shrink: 0; }
.ph-rag-dot.sm { width: 9px; height: 9px; box-shadow: none; }
.ph-rag-l { font-size: var(--fs-2xs, 9px); text-transform: uppercase; letter-spacing: .06em; color: var(--t3, #94a3b8); font-weight: 600; }
.ph-rag-v { font-size: var(--fs-lg, 15px); font-weight: 500; color: var(--rag); text-transform: capitalize; }
.ph-counts { display: flex; flex-wrap: wrap; gap: 14px; }
.ph-cnt { font-size: var(--fs-base, 12px); color: var(--t2, #475569); }
.ph-cnt b { color: var(--c); font-weight: 600; font-size: var(--fs-md, 13px); }
.ph-gen { margin-left: auto; display: flex; align-items: center; gap: 12px; }
.ph-ai { display: inline-flex; align-items: center; gap: 5px; font-size: var(--fs-sm, 11px); color: var(--t2); cursor: pointer; }
.ph-gen-btn { padding: 8px 14px; border-radius: 9px; border: 1px solid var(--p, #7c6ff7); background: var(--p, #7c6ff7); color: #fff; font-size: var(--fs-sm, 11.5px); font-weight: 500; cursor: pointer; font-family: inherit; }
.ph-gen-btn:disabled { opacity: .5; cursor: default; }

.ph-report { border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: var(--r, 10px); padding: 12px 14px; background: var(--bg2, #fafafc); margin-bottom: 14px; animation: phSlideIn .42s var(--ease-out) both; }
@keyframes phSlideIn { from { opacity: 0; transform: translateY(-7px); } to { opacity: 1; transform: translateY(0); } }
.ph-report-h { display: flex; align-items: center; gap: 8px; font-size: var(--fs-sm, 11.5px); font-weight: 600; color: var(--t1, #1e2a4a); margin-bottom: 8px; }
.ph-hist-toggle { margin-left: auto; background: none; border: none; color: var(--p-deep, #534ab7); font-size: var(--fs-xs, 10.5px); cursor: pointer; font-family: inherit; }
.ph-report-body { margin: 0; white-space: pre-wrap; font-family: inherit; font-size: var(--fs-base, 12.5px); line-height: 1.55; color: var(--t1, #1e2a4a); }
.ph-hist { margin-bottom: 14px; display: flex; flex-direction: column; gap: 4px; }
.ph-hist-item { display: flex; align-items: center; gap: 8px; font-size: var(--fs-sm, 11px); color: var(--t3, #94a3b8); }
.ph-hist-dt { flex-shrink: 0; font-variant-numeric: tabular-nums; }
.ph-hist-sum { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ph-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; }
.ph-card {
  position: relative; overflow: hidden;
  border: 1px solid var(--border, rgba(99,102,180,.12));
  border-radius: var(--r, 10px); padding: 15px 14px 13px; background: var(--bg1, #fff);
  transition: box-shadow .18s var(--ease-standard), transform .18s var(--ease-standard), border-color .18s;
  animation: phCardIn .5s var(--ease-out) both;
}
/* Акцент — ВЕРХНЯЯ полоса (не left-border). */
.ph-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 3px;
  background: linear-gradient(90deg, var(--rag, #94a3b8), color-mix(in srgb, var(--rag) 40%, transparent));
}
.ph-card.is-click { cursor: pointer; }
.ph-card.is-click:hover { box-shadow: 0 8px 22px rgba(15,23,60,.10); transform: translateY(-2px); border-color: color-mix(in srgb, var(--rag) 38%, var(--border)); }
.ph-card-h { display: flex; align-items: center; gap: 7px; }
.ph-card .ph-rag-dot.sm { background: var(--rag); box-shadow: 0 0 0 3px color-mix(in srgb, var(--rag) 15%, transparent); }
@keyframes phCardIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
.ph-card-title { font-size: var(--fs-md, 13px); font-weight: 500; color: var(--t1, #1e2a4a); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.ph-card-rag { font-size: var(--fs-2xs, 9px); text-transform: uppercase; letter-spacing: .05em; color: var(--rag); font-weight: 700; }
.ph-bar { height: 5px; border-radius: 3px; background: rgba(99,102,180,.12); overflow: hidden; margin: 9px 0; }
.ph-bar span { display: block; height: 100%; border-radius: 3px; transform-origin: left center; animation: phBarGrow .9s var(--ease-out) both; animation-delay: .15s; }
@keyframes phBarGrow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
.ph-metrics { display: flex; flex-wrap: wrap; gap: 10px; font-size: var(--fs-xs, 10.5px); color: var(--t3, #94a3b8); font-variant-numeric: tabular-nums; }
.ph-metrics .bad { color: #E24B4A; font-weight: 600; }
.ph-reasons { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.ph-reason { font-size: var(--fs-2xs, 9px); padding: 2px 6px; border-radius: 5px; background: color-mix(in srgb, var(--rag) 12%, transparent); color: var(--rag); font-weight: 600; }

@media (max-width: 768px) { .ph-top { flex-direction: column; align-items: flex-start; } .ph-gen { margin-left: 0; } }
</style>
