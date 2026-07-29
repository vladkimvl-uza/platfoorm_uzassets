<script setup lang="ts">
/**
 * ExecCopilot — кнопка «ИИ аналитик» на виджете «Исполнение задач ожиданий
 * акционера» + выезжающая панель. ИИ (Opus) собирает на сервере проекты/прогресс/
 * просрочку + комментарии по проблемным (POST /ai/exec-sector-brief) и выдаёт
 * краткую сводку: причины, взаимосвязи, советы (markdown+таблицы/чарты через AiMessage).
 * Доступ определяется единым правом ai.view. Результаты СОХРАНЯЮТСЯ на сервере (system_config)
 * и подгружаются при открытии; «Обновить» перегенерирует.
 */
import { computed, ref } from "vue";
import { api } from "@/api/client";
import { useFocusTrap } from "@/composables/useFocusTrap";
import AiMessage from "@/components/Ai/AiMessage.vue";
import { useAiActivation } from "@/composables/useAiActivation";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();

const props = defineProps<{
  year: number;
  sectors?: string[] | null;
  companyId?: string | null;
}>();

// The parent applies the shared ai.view gate. This component only reflects the
// organization-wide activation switch.
const aiAct = useAiActivation();
aiAct.load();
const aiOff = computed(() => aiAct.state.loaded && !aiAct.state.active);

const open = ref(false);
const loading = ref(false);
const error = ref<string | null>(null);
const brief = ref<string>("");
const generatedAt = ref<string>("");
const activeFocus = ref<string>("overview");

// a11y: пока панель открыта — фокус-трап + возврат фокуса на триггер при закрытии
const panelEl = ref<HTMLElement | null>(null);
useFocusTrap(panelEl, open);

function fmtTs(iso: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("ru-RU", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
    });
  } catch { return ""; }
}

// Подгрузить сохранённую сводку для (год, focus). Возвращает true, если нашлась.
async function loadSaved(focus: string): Promise<boolean> {
  try {
    const { data } = await api.get("/ai/exec-sector-brief/saved", {
      params: {
        year: props.year,
        focus,
        sectors: props.sectors?.length ? props.sectors.join(",") : undefined,
        company_id: props.companyId || undefined,
      },
    });
    if (data && data.analysis) {
      brief.value = data.analysis;
      generatedAt.value = data.generated_at || "";
      return true;
    }
  } catch { /* нет сохранённой — сгенерируем */ }
  return false;
}

// Сгенерировать заново (и сохранить на сервере).
async function run(focus: string) {
  loading.value = true;
  error.value = null;
  activeFocus.value = focus;
  try {
    const { data } = await api.post("/ai/exec-sector-brief", {
      year: props.year,
      sectors: props.sectors && props.sectors.length ? props.sectors : null,
      company_id: props.companyId || null,
      focus: focus === "overview" ? null : focus,
    }, { timeout: 210000 });  // Opus по большому контексту: 20-60с, бэк ждёт 190с
    brief.value = (data && data.analysis) || t("ИИ вернул пустой ответ.");
    generatedAt.value = (data && data.generated_at) || "";
  } catch (e: any) {
    const code = e?.response?.status;
    error.value =
      code === 403 ? t("Нет доступа к ИИ-аналитику исполнения или ИИ-инструменты выключены.")
      : code === 503 ? t("ИИ-ассистент не сконфигурирован.")
      : e?.response?.data?.detail || e?.message || t("Не удалось получить сводку.");
  } finally {
    loading.value = false;
  }
}

// Показать таб: сначала сохранённое, иначе сгенерировать.
async function show(focus: string) {
  if (loading.value) return;
  activeFocus.value = focus;
  brief.value = "";
  generatedAt.value = "";
  const found = await loadSaved(focus);
  if (!found) await run(focus);
}

function openPanel() {
  if (aiOff.value) return;  // движок выключен — кнопка неактивна
  open.value = true;
  if (!brief.value && !loading.value) show("overview");
}
</script>

<template>
  <button class="ec-trigger" :class="{ 'ec-off': aiOff }" :disabled="aiOff"
          type="button" :title="aiOff ? t('ИИ-ассистент выключен владельцем') : t('ИИ-аналитик исполнения')"
          @click="openPanel">
    <span class="ec-spark" aria-hidden="true">AI</span>
    {{ aiOff ? t('ИИ выключен') : t('ИИ аналитик') }}
  </button>

  <Teleport to="body">
    <Transition name="ec-slide">
      <aside v-if="open" ref="panelEl" tabindex="-1" class="ec-panel" role="dialog" aria-modal="true"
             :aria-label="t('ИИ-аналитик исполнения')" @keydown.esc.stop.prevent="open = false">
        <header class="ec-head">
          <div class="ec-head-l">
            <span class="ec-ai-badge">AI</span>
            <div>
              <div class="ec-title">{{ t("ИИ-аналитик · Исполнение по секторам") }}</div>
              <div class="ec-sub">{{ t("Opus · проекты, задачи, комментарии и ход — причины, связи, советы") }}</div>
            </div>
          </div>
          <button class="ec-x" type="button" @click="open = false" :aria-label="t('Закрыть')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                 stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </header>

        <div class="ec-tabs">
          <div class="uza-seg">
            <button :class="['uza-seg-btn', { on: activeFocus === 'overview' }]" :disabled="loading" @click="show('overview')">{{ t("Сводка") }}</button>
            <button :class="['uza-seg-btn', { on: activeFocus === 'risks' }]" :disabled="loading" @click="show('risks')">{{ t("Риски") }}</button>
            <button :class="['uza-seg-btn', { on: activeFocus === 'delays' }]" :disabled="loading" @click="show('delays')">{{ t("Причины задержек") }}</button>
          </div>
          <button v-if="brief && !loading" class="ec-refresh" type="button" @click="run(activeFocus)" :title="t('Сгенерировать заново')">↻ {{ t("Обновить") }}</button>
        </div>

        <div class="ec-body">
          <div v-if="loading" class="ec-load">
            <span class="ec-dots"><i></i><i></i><i></i></span>
            {{ t("ИИ анализирует проекты, задачи и комментарии…") }}
          </div>
          <div v-else-if="error" class="ec-err">{{ error }}</div>
          <template v-else-if="brief">
            <div v-if="generatedAt" class="ec-ts">{{ t("Сгенерировано {ts}", { ts: fmtTs(generatedAt) }) }}</div>
            <AiMessage role="assistant" :content="brief" />
          </template>
          <div v-else class="ec-empty">{{ t("Нажми «Сводка» — ИИ соберёт причины, взаимосвязи и советы по исполнению.") }}</div>
        </div>

        <footer class="ec-foot">{{ t("Сводка опирается на реальные данные карточек. Проверяйте критичные выводы.") }}</footer>
      </aside>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ec-trigger {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 6px 13px 6px 8px; border: none; border-radius: 999px; cursor: pointer;
  background: linear-gradient(135deg, #8B7FF0, #6C5CE7); color: #fff;
  font: 600 11.5px var(--font, inherit); letter-spacing: .01em;
  box-shadow: 0 2px 10px rgba(108, 92, 231, .32);
  transition: transform .15s var(--ease-standard, ease), box-shadow .15s;
}
.ec-trigger:hover { transform: translateY(-1px); box-shadow: 0 5px 16px rgba(108, 92, 231, .42); }
.ec-trigger:active { transform: scale(.97); }
.ec-spark { font-size: 9px; font-weight: 700; background: rgba(255,255,255,.22); border-radius: 6px; padding: 2px 5px; letter-spacing: .04em; }

/* Выключенное состояние (движок выключен глобально) — единообразно с прочими ИИ-кнопками */
.ec-trigger.ec-off {
  background: var(--bg3, #E5E7EB); color: var(--t3, #94A3B8);
  box-shadow: none; cursor: not-allowed;
}
.ec-trigger.ec-off:hover { transform: none; box-shadow: none; }
.ec-trigger.ec-off:active { transform: none; }
.ec-trigger.ec-off .ec-spark { background: rgba(148, 163, 184, .22); color: var(--t3, #94A3B8); }

.ec-panel {
  position: fixed; top: 14px; right: 14px; bottom: 14px;
  width: min(620px, calc(100vw - 28px));
  z-index: var(--z-top, 9990);
  display: flex; flex-direction: column;
  background: var(--card-bg, rgba(255, 255, 255, 0.92));
  backdrop-filter: blur(20px) saturate(1.5); -webkit-backdrop-filter: blur(20px) saturate(1.5);
  border: 1px solid rgba(127, 119, 221, 0.18); border-radius: 16px;
  box-shadow: 0 24px 64px rgba(15, 23, 60, .2), 0 8px 24px rgba(15, 23, 60, .1);
  overflow: hidden;
}
.ec-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid var(--border, rgba(99,102,180,.1)); }
.ec-head-l { display: flex; align-items: center; gap: 10px; min-width: 0; }
.ec-ai-badge { flex-shrink: 0; width: 30px; height: 30px; display: flex; align-items: center; justify-content: center; border-radius: 9px; background: linear-gradient(135deg, #8B7FF0, #6C5CE7); color: #fff; font: 700 11px var(--font, inherit); }
.ec-title { font-size: 13.5px; font-weight: 600; color: var(--t1, #1E2A4A); letter-spacing: -.01em; }
.ec-sub { font-size: 10.5px; color: var(--t3, #94A3B8); margin-top: 1px; }
.ec-x { background: transparent; border: none; cursor: pointer; color: var(--t3, #94A3B8); padding: 5px; border-radius: 7px; display: flex; transition: background .12s, color .12s; }
.ec-x:hover { background: var(--bg3, rgba(235,238,255,.7)); color: var(--t1, #1E2A4A); }

.ec-tabs { display: flex; gap: 8px; padding: 10px 16px 0; flex-wrap: wrap; align-items: center; }
/* .ec-tab → единый .uza-seg/.uza-seg-btn */
.ec-refresh { margin-left: auto; background: transparent; border: none; color: var(--p-deep, #534AB7); font: 500 11px var(--font, inherit); cursor: pointer; padding: 5px 8px; border-radius: 7px; }
.ec-refresh:hover { background: rgba(124,111,247,.08); }

.ec-body { flex: 1; overflow-y: auto; padding: 14px 16px; }
.ec-ts { font-size: 10px; color: var(--t3, #94A3B8); margin-bottom: 8px; }
.ec-load { display: flex; align-items: center; gap: 10px; color: var(--t3, #64748B); font-size: 12.5px; padding: 14px 2px; }
.ec-dots { display: inline-flex; gap: 4px; }
.ec-dots i { width: 6px; height: 6px; border-radius: 50%; background: var(--p, #7C6FF7); animation: ecPulse 1.1s ease-in-out infinite; }
.ec-dots i:nth-child(2) { animation-delay: .15s; }
.ec-dots i:nth-child(3) { animation-delay: .3s; }
@keyframes ecPulse { 0%, 100% { opacity: .3; transform: scale(.8); } 50% { opacity: 1; transform: scale(1); } }
.ec-err { font-size: 12.5px; color: var(--sev-high, #E24B4A); background: rgba(226,75,74,.07); border: 1px solid rgba(226,75,74,.25); border-radius: 9px; padding: 10px 12px; }
.ec-empty { font-size: 12.5px; color: var(--t3, #94A3B8); padding: 16px 2px; line-height: 1.5; }
.ec-foot { padding: 10px 16px; border-top: 1px solid var(--border, rgba(99,102,180,.1)); font-size: 10px; color: var(--t3, #94A3B8); background: var(--bg2, rgba(255,255,255,.6)); }

.ec-slide-enter-active, .ec-slide-leave-active { transition: opacity .26s var(--ease-out, ease), transform .26s var(--ease-out, ease); }
.ec-slide-enter-from, .ec-slide-leave-to { opacity: 0; transform: translateX(20px); }

@media (prefers-reduced-motion: reduce) {
  .ec-trigger, .ec-slide-enter-active, .ec-slide-leave-active, .ec-dots i { transition: none; animation: none; }
}
</style>
