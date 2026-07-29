<template>
  <Transition name="uza-modal" appear>
  <Teleport to="body">
    <Transition name="ai-set-back">
      <div
        v-if="modelValue"
        class="ai-set-back"
        @click.self="close"
      ></div>
    </Transition>

    <Transition name="ai-drawer">
      <!-- a11y: Escape закрывает панель (через dirty-guard), tabindex делает
           контейнер фокусируемым для перехвата клавиши. -->
      <div
        v-if="modelValue"
        class="ai-set-drawer"
        role="dialog"
        aria-modal="true"
        :aria-label="t('Настройки ассистента')"
        tabindex="-1"
        @keydown.escape="close"
      >
        <header class="ai-set-head">
          <div>
            <h2>{{ t('Настройки ассистента') }}</h2>
            <!-- P1 аудита: подпись «Сохраняется автоматически» лгала —
                 сохранение ручное, и правки терялись при закрытии. -->
            <p>{{ dirty ? t("Есть несохранённые изменения") : t("Нажмите «Сохранить», чтобы применить") }}</p>
          </div>
          <button class="ai-set-x" type="button" @click="close" :aria-label="t('Закрыть')">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
        </header>

        <div v-if="cfg.loading.value && !cfg.state.value" class="ai-set-loading">
          <span class="ai-set-spinner"></span>
          <span>{{ t('Загрузка настроек') }}</span>
        </div>

        <form v-else class="ai-set-body" @submit.prevent="onSave">
          <!-- Anti-wipe: загрузка не удалась → показываем это явно и блокируем
               сохранение, чтобы дефолты формы не затёрли реальные настройки. -->
          <div v-if="loadFailed" class="ai-set-warn"> {{ t('Не удалось загрузить ваши настройки. Показаны значения по умолчанию — сохранение отключено, чтобы не перезаписать текущие. Закройте панель и откройте её заново.') }} </div>
          <!-- Role (Pack 7.7: grouped) -->
          <section class="ai-set-section">
            <h3>{{ t('Роль') }}</h3>
            <div v-for="(roles, groupKey) in cfg.rolesByGroup.value" :key="groupKey" class="ai-set-group">
              <div class="ai-set-group-label">{{ cfg.groupLabels.value[groupKey] }}</div>
              <div class="ai-set-grid">
                <label
                  v-for="r in roles"
                  :key="r.value"
                  class="ai-set-opt"
                  :class="{ active: form.role === r.value }"
                >
                  <input v-model="form.role" type="radio" :value="r.value" />
                  <div class="ai-set-opt-body">
                    <div class="ai-set-opt-title">{{ r.label }}</div>
                    <div class="ai-set-opt-desc">{{ r.desc }}</div>
                  </div>
                  <svg
                    v-if="form.role === r.value"
                    class="ai-set-check"
                    width="14" height="14" viewBox="0 0 24 24"
                    fill="none" stroke="currentColor" stroke-width="2.5"
                    stroke-linecap="round" stroke-linejoin="round"
                  >
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                </label>
              </div>
            </div>
          </section>

          <!-- Model picker (Pack 7.9d) -->
          <section class="ai-set-section">
            <h3>{{ t('Модель') }}</h3>
            <div class="ai-set-grid">
              <label
                v-for="m in cfg.models.value"
                :key="m.value"
                class="ai-set-opt"
                :class="{ active: form.model === m.value }"
              >
                <input v-model="form.model" type="radio" :value="m.value" />
                <div class="ai-set-opt-body">
                  <div class="ai-set-opt-title">
                    {{ m.label }}
                    <span v-if="m.badge" class="ai-set-opt-badge">{{ m.badge }}</span>
                  </div>
                  <div class="ai-set-opt-desc">{{ m.desc }}</div>
                </div>
                <svg
                  v-if="form.model === m.value"
                  class="ai-set-check"
                  width="14" height="14" viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" stroke-width="2.5"
                  stroke-linecap="round" stroke-linejoin="round"
                >
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              </label>
            </div>
          </section>

          <!-- Style -->
          <section class="ai-set-section">
            <h3>{{ t('Стиль ответа') }}</h3>
            <div class="ai-set-grid">
              <label
                v-for="s in cfg.styles.value"
                :key="s.value"
                class="ai-set-opt"
                :class="{ active: form.style === s.value }"
              >
                <input v-model="form.style" type="radio" :value="s.value" />
                <div class="ai-set-opt-body">
                  <div class="ai-set-opt-title">{{ s.label }}</div>
                  <div class="ai-set-opt-desc">{{ s.desc }}</div>
                </div>
                <svg
                  v-if="form.style === s.value"
                  class="ai-set-check"
                  width="14" height="14" viewBox="0 0 24 24"
                  fill="none" stroke="currentColor" stroke-width="2.5"
                  stroke-linecap="round" stroke-linejoin="round"
                >
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              </label>
            </div>
          </section>

          <!-- Temperature -->
          <section class="ai-set-section">
            <div class="ai-set-row">
              <label>{{ t('Креативность') }}</label>
              <span class="ai-set-val">{{ form.temperature.toFixed(2) }}</span>
            </div>
            <input
              v-model.number="form.temperature"
              type="range"
              min="0"
              max="1"
              step="0.05"
              class="ai-set-range"
            />
            <div class="ai-set-hint"> {{ t('0 — точно по данным · 1 — больше свободы') }} </div>
          </section>

          <!-- Max tokens -->
          <section class="ai-set-section">
            <label class="ai-set-label">{{ t('Лимит ответа') }}</label>
            <select v-model.number="form.max_tokens" class="ai-set-select">
              <option :value="4000">{{ t('4 000 токенов · короткие') }}</option>
              <option :value="8000">{{ t('8 000 токенов') }}</option>
              <option :value="16000">{{ t('16 000 токенов · рекомендуется') }}</option>
              <option :value="32000">{{ t('32 000 токенов · подробные') }}</option>
              <option :value="64000">{{ t('64 000 токенов · максимум') }}</option>
            </select>
          </section>

          <!-- Custom instructions -->
          <section class="ai-set-section">
            <label class="ai-set-label"> {{ t('Дополнительные инструкции') }} <span class="ai-set-hint-inline">{{ (form.custom_instructions || "").length }} / 4000</span>
            </label>
            <textarea
              v-model="form.custom_instructions"
              rows="4"
              :placeholder="t('Например: всегда сравнивай с прошлым годом; используй термины МСФО без перевода')"
              maxlength="4000"
              class="ai-set-textarea"
            ></textarea>
          </section>

          <p v-if="cfg.error.value" class="ai-set-err">{{ t(cfg.error.value) }}</p>

          <footer class="ai-set-foot">
            <button type="button" class="ai-set-btn ai-set-btn-secondary" @click="close"> {{ t('Закрыть') }} </button>
            <button type="submit" class="ai-set-btn ai-set-btn-primary" :disabled="cfg.saving.value || loadFailed">
              <span v-if="cfg.saving.value">{{ t('Сохранение…') }}</span>
              <span v-else>{{ t('Сохранить') }}</span>
            </button>
          </footer>
        </form>
      </div>
    </Transition>
  </Teleport>
  </Transition>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useAiConfig } from "@/composables/useAiConfig";
import { useConfirm } from "@/composables/useConfirm";
import { useI18n } from "@/composables/useI18n";
import { useToast } from "@/composables/useToast";

const { t } = useI18n();
const toast = useToast();
const { confirmDialog } = useConfirm();

const props = defineProps<{
  modelValue: boolean;
}>();
const emit = defineEmits<{
  "update:modelValue": [v: boolean];
  saved: [];
}>();

const cfg = useAiConfig();

const form = ref({
  role: "analyst",
  style: "structured",
  model: "ai-balanced",
  temperature: 0.25,
  max_tokens: 16000,
  custom_instructions: "",
});

// Снимок загруженных настроек — для dirty-guard и anti-wipe (P1 аудита:
// правки терялись без предупреждения, а при сбое загрузки форма показывала
// хардкод-дефолты и «Сохранить» затирало реальные настройки).
const snapshot = ref<string>("");
const loadFailed = ref(false);
const dirty = computed(
  () => snapshot.value !== "" && JSON.stringify(form.value) !== snapshot.value,
);

watch(
  () => props.modelValue,
  async (v) => {
    if (v) {
      loadFailed.value = false;
      const c = await cfg.load();
      if (c) {
        form.value = {
          role: c.role,
          style: c.style,
          model: c.model || "ai-balanced",
          temperature: c.temperature,
          max_tokens: c.max_tokens,
          custom_instructions: c.custom_instructions || "",
        };
        snapshot.value = JSON.stringify(form.value);
      } else {
        // Anti-wipe: НЕ показываем дефолты как «текущие настройки» и не даём
        // сохранить — иначе перезапишем реальные значения хардкодом.
        loadFailed.value = true;
        snapshot.value = "";
      }
    }
  },
);

async function close() {
  if (dirty.value) {
    const ok = await confirmDialog({
      message: t("Есть несохранённые изменения настроек ИИ. Закрыть без сохранения?"),
      danger: true,
    });
    if (!ok) return;
  }
  emit("update:modelValue", false);
}

async function onSave() {
  if (loadFailed.value) {
    toast.error(t("Настройки не были загружены — сохранение отключено, чтобы не затереть текущие. Закройте и откройте панель заново."));
    return;
  }
  const saved = await cfg.save({
    role: form.value.role,
    style: form.value.style,
    model: form.value.model,
    temperature: form.value.temperature,
    max_tokens: form.value.max_tokens,
    custom_instructions: form.value.custom_instructions || null,
  });
  if (saved) {
    snapshot.value = JSON.stringify(form.value);
    toast.success(t("Настройки ассистента сохранены"));
    emit("saved");
    emit("update:modelValue", false);   // закрываем без повторного dirty-guard
  } else {
    toast.error(cfg.error.value ? t(cfg.error.value) : t("Не удалось сохранить настройки ассистента"));
  }
}
</script>

<style scoped>
/* Backdrop.
   P1 аудита: здесь стоял хардкод 9998 против var(--z-overlay)=9000 у дровера —
   затемнение рисовалось ПОВЕРХ панели, и любой клик по роли/слайдеру/«Сохранить»
   попадал в бэкдроп и ЗАКРЫВАЛ настройки (изменить их через UI было нельзя).
   Обе поверхности переведены на единую шкалу --z-*. */
.ai-set-back {
  position: fixed;
  inset: 0;
  background: rgba(15, 18, 40, 0.45);
  -webkit-backdrop-filter: blur(8px);
          backdrop-filter: blur(8px);
  z-index: var(--z-overlay, 9000);
}

/* Anti-wipe баннер (сбой загрузки настроек) */
.ai-set-warn {
  margin: 0 0 14px;
  padding: 11px 13px;
  background: rgba(239, 159, 39, 0.10);
  border: 1px solid rgba(239, 159, 39, 0.32);
  border-radius: 10px;
  font-size: 12.5px;
  line-height: 1.5;
  color: #A36500;
}

/* Drawer */
.ai-set-drawer {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(440px, 100%);
  background: var(--ai-glass-bg-strong);
  -webkit-backdrop-filter: var(--ai-glass-blur);
          backdrop-filter: var(--ai-glass-blur);
  border-left: 1px solid var(--ai-glass-border);
  box-shadow: var(--ai-shadow-modal);
  /* ВЫШЕ бэкдропа — иначе панель некликабельна (см. комментарий у .ai-set-back) */
  z-index: calc(var(--z-overlay, 9000) + 1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Animations */
.ai-set-back-enter-active,
.ai-set-back-leave-active {
  transition: opacity 0.25s var(--ai-easing-soft);
}
.ai-set-back-enter-from,
.ai-set-back-leave-to { opacity: 0; }

.ai-drawer-enter-active,
.ai-drawer-leave-active {
  transition: transform 0.4s var(--ai-easing), opacity 0.25s var(--ai-easing-soft);
}
.ai-drawer-enter-from,
.ai-drawer-leave-to {
  transform: translateX(100%);
  opacity: 0.6;
}

/* Header */
.ai-set-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 22px 24px 14px;
  border-bottom: 1px solid rgba(127, 119, 221, 0.12);
}
.ai-set-head h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 500;
  letter-spacing: -0.01em;
  color: var(--uza-navy);
}
.ai-set-head p {
  margin: 4px 0 0;
  font-size: 11px;
  color: rgba(30, 42, 74, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.ai-set-x {
  border: 0;
  background: transparent;
  cursor: pointer;
  color: rgba(30, 42, 74, 0.6);
  width: 28px;
  height: 28px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  transition: all 0.15s;
}
.ai-set-x:hover {
  background: rgba(127, 119, 221, 0.08);
  color: var(--uza-purple);
}

/* Loading */
.ai-set-loading {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 12px;
  color: rgba(30, 42, 74, 0.5);
}
.ai-set-spinner {
  width: 22px;
  height: 22px;
  border: 2px solid rgba(127, 119, 221, 0.2);
  border-top-color: var(--uza-purple);
  border-radius: 50%;
  animation: ai-set-spin 0.7s linear infinite;
}
@keyframes ai-set-spin { to { transform: rotate(360deg); } }

/* Body */
.ai-set-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px 24px;
}

.ai-set-section {
  margin-top: 18px;
}
.ai-set-section:first-child { margin-top: 0; }

.ai-set-section h3 {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(30, 42, 74, 0.55);
  margin: 0 0 10px;
}

.ai-set-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(30, 42, 74, 0.55);
  margin-bottom: 8px;
}
.ai-set-hint-inline {
  text-transform: none;
  letter-spacing: normal;
  font-size: 10px;
  color: rgba(30, 42, 74, 0.4);
}

.ai-set-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}
.ai-set-row label {
  font-size: 10px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(30, 42, 74, 0.55);
}
.ai-set-val {
  font-size: 14px;
  font-weight: 500;
  color: var(--uza-purple);
  font-variant-numeric: tabular-nums;
}

.ai-set-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 6px;
}

.ai-set-opt {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--ai-glass-border);
  border-radius: var(--ai-radius-md);
  cursor: pointer;
  transition: all 0.18s var(--ai-easing-soft);
  background: rgba(255, 255, 255, 0.4);
}
.ai-set-opt:hover {
  background: white;
  border-color: rgba(127, 119, 221, 0.3);
  transform: translateX(2px);
}
.ai-set-opt.active {
  background: rgba(127, 119, 221, 0.06);
  border-color: rgba(127, 119, 221, 0.4);
  box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.08);
}
/* a11y (P2 аудита): `display:none` полностью убирал радио из дерева
   доступности — ни один из 13 вариантов роли, 3 моделей и 4 стилей не получал
   фокус и не читался диктором, выбрать их с клавиатуры было нельзя.
   Прячем визуально, но оставляем фокусируемыми. */
.ai-set-opt input[type="radio"] {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
/* Видимый индикатор фокуса — на карточке-обёртке */
.ai-set-opt:has(input[type="radio"]:focus-visible) {
  outline: 2px solid var(--uza-purple, #7C6FF7);
  outline-offset: 2px;
}
.ai-set-opt-body { flex: 1; }
.ai-set-opt-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--uza-navy);
  letter-spacing: -0.01em;
}
.ai-set-opt.active .ai-set-opt-title { color: var(--uza-purple); }
.ai-set-opt-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  font-size: 9px;
  font-weight: 500;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border-radius: 4px;
  background: rgba(127, 119, 221, 0.12);
  color: var(--uza-purple);
  vertical-align: middle;
}
.ai-set-opt-desc {
  font-size: 11px;
  color: rgba(30, 42, 74, 0.55);
  margin-top: 2px;
  line-height: 1.4;
}
.ai-set-check {
  color: var(--uza-purple);
  flex-shrink: 0;
  margin-top: 2px;
}

/* Range slider */
.ai-set-range {
  width: 100%;
  -webkit-appearance: none;
  appearance: none;
  background: transparent;
  margin: 6px 0;
}
.ai-set-range::-webkit-slider-runnable-track {
  height: 4px;
  background: linear-gradient(90deg,
    var(--uza-purple) 0%,
    var(--uza-purple) calc(var(--val, 0) * 100%),
    rgba(127, 119, 221, 0.15) calc(var(--val, 0) * 100%));
  border-radius: 2px;
}
.ai-set-range::-moz-range-track {
  height: 4px;
  background: rgba(127, 119, 221, 0.15);
  border-radius: 2px;
}
.ai-set-range::-moz-range-progress {
  height: 4px;
  background: var(--uza-purple);
  border-radius: 2px;
}
.ai-set-range::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--uza-purple);
  border: 2px solid white;
  box-shadow: 0 2px 8px rgba(127, 119, 221, 0.4);
  margin-top: -6px;
  cursor: pointer;
  transition: transform 0.15s;
}
.ai-set-range::-webkit-slider-thumb:hover {
  transform: scale(1.15);
}
.ai-set-range::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--uza-purple);
  border: 2px solid white;
  box-shadow: 0 2px 8px rgba(127, 119, 221, 0.4);
  cursor: pointer;
}

.ai-set-hint {
  font-size: 11px;
  color: rgba(30, 42, 74, 0.45);
  margin-top: 2px;
}

/* Select */
.ai-set-select {
  width: 100%;
  padding: 9px 12px;
  font-size: 13px;
  color: var(--uza-navy);
  background: white;
  border: 1px solid var(--ai-glass-border);
  border-radius: var(--ai-radius-md);
  cursor: pointer;
  transition: border-color 0.15s;
}
.ai-set-select:hover { border-color: rgba(127, 119, 221, 0.3); }
.ai-set-select:focus {
  outline: none;
  border-color: var(--uza-purple);
  box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.12);
}

/* Textarea */
.ai-set-textarea {
  width: 100%;
  padding: 10px 12px;
  font-size: 13px;
  font-family: inherit;
  color: var(--uza-navy);
  background: white;
  border: 1px solid var(--ai-glass-border);
  border-radius: var(--ai-radius-md);
  resize: vertical;
  line-height: 1.5;
  transition: border-color 0.15s;
}
.ai-set-textarea:focus {
  outline: none;
  border-color: var(--uza-purple);
  box-shadow: 0 0 0 3px rgba(127, 119, 221, 0.12);
}

.ai-set-err {
  margin: 14px 0 0;
  padding: 9px 12px;
  background: rgba(254, 242, 242, 0.9);
  border: 1px solid rgba(252, 165, 165, 0.6);
  color: #991B1B;
  border-radius: var(--ai-radius-md);
  font-size: 12px;
}

/* Footer */
.ai-set-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid rgba(127, 119, 221, 0.10);
}

.ai-set-btn {
  padding: 9px 18px;
  font-size: 12.5px;
  font-weight: 500;
  border-radius: var(--ai-radius-md);
  border: 0;
  cursor: pointer;
  transition: all 0.15s var(--ai-easing-soft);
}
.ai-set-btn-secondary {
  background: rgba(255, 255, 255, 0.6);
  border: 1px solid var(--ai-glass-border);
  color: rgba(30, 42, 74, 0.7);
}
.ai-set-btn-secondary:hover {
  background: white;
  color: var(--uza-navy);
}
.ai-set-btn-primary {
  background: linear-gradient(135deg, var(--uza-purple) 0%, var(--uza-purple-2) 100%);
  color: white;
  box-shadow: 0 4px 14px rgba(127, 119, 221, 0.32);
}
.ai-set-btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(127, 119, 221, 0.42);
}
.ai-set-btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ai-set-group { margin-bottom: 14px; }
.ai-set-group:last-child { margin-bottom: 0; }
.ai-set-group-label {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: rgba(30, 42, 74, 0.45);
  margin-bottom: 6px;
  padding-left: 2px;
}
</style>
