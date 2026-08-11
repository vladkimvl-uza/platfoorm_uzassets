<script setup lang="ts">
/**
 * ChangeHistory — пер-сущностный журнал изменений «кто / что / когда».
 *
 * Показывает по конкретной записи: кто менял, какое действие (создал/изменил/
 * удалил), какие поля затронуты и когда. Данные — GET /history/{type}/{id}
 * (historyApi.entity). Открыт всем: ключ = неугадываемый UUID, отдаются только
 * имена полей (без значений). Ставится «где-то» на карточку любой сущности.
 *
 * Использование:
 *   <ChangeHistory entity-type="tasks" :entity-id="task.id" />
 */
import { ref, watch } from "vue";
import { historyApi, type ChangeEvent } from "@/api/history";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";

const { t } = useI18n();

const props = withDefaults(defineProps<{
  entityType: string;
  entityId: string | null | undefined;
  /** Заголовок панели. */
  title?: string;
  /** Свёрнута по умолчанию (по клику раскрывается и грузит). */
  collapsed?: boolean;
  /** Сколько записей тянуть. */
  limit?: number;
}>(), { collapsed: false, limit: 50 });

const events = ref<ChangeEvent[]>([]);
const loading = ref(false);
const loaded = ref(false);
const failed = ref(false);
const open = ref(!props.collapsed);

async function load() {
  if (!props.entityId) { events.value = []; loaded.value = true; return; }
  loading.value = true; failed.value = false;
  try {
    events.value = await historyApi.entity(props.entityType, String(props.entityId), props.limit);
  } catch {
    failed.value = true; events.value = [];
  } finally {
    loading.value = false; loaded.value = true;
  }
}

// Грузим при раскрытии (лениво) и при смене записи.
watch(() => [props.entityType, props.entityId, open.value], () => {
  if (open.value && props.entityId) load();
}, { immediate: true });

function toggle() { open.value = !open.value; }

// ─── Форматирование ───
const ACTION_META: Record<string, { label: string; cls: string }> = {
  CREATE: { label: "создал", cls: "a-create" },
  UPDATE: { label: "изменил", cls: "a-update" },
  DELETE: { label: "удалил", cls: "a-delete" },
  IMPORT: { label: "импортировал", cls: "a-update" },
  EXPORT: { label: "выгрузил", cls: "a-view" },
};
function actionLabel(a: string): string {
  return t(ACTION_META[a]?.label || a.toLowerCase());
}
function actionCls(a: string): string {
  return ACTION_META[a]?.cls || "a-update";
}

function actorName(e: ChangeEvent): string {
  if (!e.actor_email) return t("система");
  // email → имя до @ как компактная подпись, полный email в title
  return e.actor_email.split("@")[0];
}

function initials(e: ChangeEvent): string {
  const s = actorName(e);
  return (s[0] || "?").toUpperCase();
}

function relTime(iso: string | null): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const sec = Math.round((Date.now() - then) / 1000);
  if (sec < 45) return t("только что");
  const min = Math.round(sec / 60);
  if (min < 60) return t("{n} мин назад", { n: min });
  const hr = Math.round(min / 60);
  if (hr < 24) return t("{n} ч назад", { n: hr });
  const day = Math.round(hr / 24);
  if (day < 30) return t("{n} дн назад", { n: day });
  return absTime(iso);
}
function absTime(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString(getCurrentIntlLocale(), {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return iso; }
}
</script>

<template>
  <div class="chh" v-if="entityId">
    <button type="button" class="chh-head" @click="toggle" :aria-expanded="open">
      <svg class="chh-ico" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v5h5"/><path d="M3.05 13A9 9 0 1 0 6 5.3L3 8"/><path d="M12 7v5l3 2"/></svg>
      <span class="chh-title">{{ t(title || "История изменений") }}</span>
      <span v-if="loaded && !loading && events.length" class="chh-count">{{ events.length }}</span>
      <svg class="chh-chev" :class="{ open }" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
    </button>

    <Transition name="chh-exp">
      <div v-if="open" class="chh-body">
        <div v-if="loading" class="chh-msg">{{ t("Загрузка…") }}</div>
        <div v-else-if="failed" class="chh-msg">{{ t("Не удалось загрузить историю") }}</div>
        <div v-else-if="!events.length" class="chh-msg">{{ t("Изменений не зафиксировано") }}</div>
        <ul v-else class="chh-list">
          <li v-for="(e, i) in events" :key="e.id" class="chh-item" :style="{ animationDelay: Math.min(i, 12) * 28 + 'ms' }">
            <span class="chh-avatar" :title="e.actor_email || t('система')">{{ initials(e) }}</span>
            <div class="chh-main">
              <div class="chh-line">
                <span class="chh-actor" :title="e.actor_email || ''">{{ actorName(e) }}</span>
                <span class="chh-act" :class="actionCls(e.action)">{{ actionLabel(e.action) }}</span>
                <span v-if="e.entity_label" class="chh-label">· {{ e.entity_label }}</span>
              </div>
              <div v-if="e.fields && e.fields.length" class="chh-fields">
                <span v-for="f in e.fields.slice(0, 8)" :key="f" class="chh-field">{{ f }}</span>
                <span v-if="e.fields.length > 8" class="chh-field more">+{{ e.fields.length - 8 }}</span>
              </div>
            </div>
            <time class="chh-time" :title="absTime(e.at)">{{ relTime(e.at) }}</time>
          </li>
        </ul>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.chh { font-family: var(--font, system-ui); border-top: 0.5px solid var(--color-border, rgba(0,0,0,.08)); }
.chh-head { width: 100%; display: flex; align-items: center; gap: 8px; padding: 10px 2px; background: transparent; border: 0; cursor: pointer; font-family: inherit; color: var(--color-text-secondary, #6B6880); }
.chh-head:hover { color: var(--color-text, #1E2A4A); }
.chh-ico { flex: none; opacity: .8; }
.chh-title { flex: 1; text-align: left; font-size: 12px; font-weight: 600; letter-spacing: .01em; }
.chh-count { flex: none; font-size: 10.5px; font-weight: 600; padding: 1px 7px; border-radius: 999px; background: color-mix(in srgb, var(--color-accent, #7F77DD) 12%, transparent); color: var(--color-accent, #6A61C9); }
.chh-chev { flex: none; transition: transform .2s; opacity: .7; }
.chh-chev.open { transform: rotate(180deg); }

.chh-body { padding: 2px 0 8px; }
.chh-msg { font-size: 11.5px; color: var(--color-text-tertiary, #94A3B8); padding: 6px 2px; }

.chh-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.chh-item { display: flex; align-items: flex-start; gap: 9px; padding: 7px 8px; border-radius: 8px; transition: background .12s; animation: chhIn .28s cubic-bezier(.4,0,.2,1) both; }
.chh-item:hover { background: color-mix(in srgb, var(--color-accent, #7F77DD) 5%, transparent); }
.chh-avatar { flex: none; width: 24px; height: 24px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; color: #fff; background: linear-gradient(135deg, #8B82E6, #5D53C4); }
.chh-main { flex: 1; min-width: 0; }
.chh-line { display: flex; align-items: baseline; gap: 5px; flex-wrap: wrap; font-size: 12px; line-height: 1.4; }
.chh-actor { font-weight: 600; color: var(--color-text, #1E2A4A); }
.chh-act { font-weight: 500; }
.chh-act.a-create { color: #1D9E75; }
.chh-act.a-update { color: #6A61C9; }
.chh-act.a-delete { color: #D2564F; }
.chh-act.a-view { color: var(--color-text-tertiary, #94A3B8); }
.chh-label { color: var(--color-text-tertiary, #94A3B8); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
.chh-fields { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.chh-field { font-size: 10px; padding: 1px 7px; border-radius: 5px; background: color-mix(in srgb, var(--color-accent, #7F77DD) 8%, transparent); color: var(--color-text-secondary, #6B6880); }
.chh-field.more { background: transparent; color: var(--color-text-tertiary, #94A3B8); }
.chh-time { flex: none; font-size: 10.5px; color: var(--color-text-tertiary, #94A3B8); white-space: nowrap; padding-top: 2px; }

@keyframes chhIn { from { opacity: 0; transform: translateY(-2px); } to { opacity: 1; transform: none; } }
.chh-exp-enter-active, .chh-exp-leave-active { transition: opacity .2s ease, max-height .24s cubic-bezier(.4,0,.2,1); overflow: hidden; }
.chh-exp-enter-from, .chh-exp-leave-to { opacity: 0; max-height: 0; }
.chh-exp-enter-to, .chh-exp-leave-from { opacity: 1; max-height: 900px; }

@media (prefers-reduced-motion: reduce) {
  .chh-item { animation: none; }
  .chh-exp-enter-active, .chh-exp-leave-active { transition: none; }
}
</style>
