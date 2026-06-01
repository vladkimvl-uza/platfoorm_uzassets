<template>
  <div
    class="ai-inp-wrap"
    :class="{
      'is-focused': focused,
      'is-disabled': disabled,
      'is-recording': recording,
      'is-ready': canSend,
      'is-burst': bursting,
    }"
  >
    <textarea
      ref="taRef"
      v-model="text"
      class="ai-inp-ta"
      :placeholder="recording ? 'Говорите…' : (placeholder || rotatingPlaceholder)"
      :disabled="disabled"
      rows="1"
      @keydown.enter.exact.prevent="onSubmit"
      @keydown.shift.enter.exact="onShiftEnter"
      @input="onInput"
      @focus="focused = true"
      @blur="focused = false"
    ></textarea>

    <button
      v-if="voiceSupported"
      class="ai-inp-mic"
      :class="{ 'is-recording': recording }"
      type="button"
      :disabled="disabled"
      :title="recording ? 'Остановить запись' : 'Голосовой ввод'"
      :aria-label="recording ? 'Остановить запись' : 'Голосовой ввод'"
      @click="toggleVoice"
    >
      <svg v-if="!recording" width="15" height="15" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
        <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
        <line x1="12" y1="19" x2="12" y2="23"/>
        <line x1="8" y1="23" x2="16" y2="23"/>
      </svg>
      <svg v-else width="14" height="14" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2.4"
           stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="6" y="6" width="12" height="12" rx="2"/>
      </svg>
      <span v-if="recording" class="ai-inp-mic-ring" aria-hidden="true"></span>
    </button>

    <button
      class="ai-inp-send"
      type="button"
      :disabled="!canSend"
      :title="canSend ? 'Отправить (Enter)' : ''"
      @click="onSubmit"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round">
        <path d="M5 12l14-7-7 14-2-7z"/>
      </svg>
    </button>

    <transition name="ai-mic-err">
      <div v-if="micError" class="ai-mic-err" role="alert">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" stroke-width="2"
             stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="10"/>
          <line x1="12" y1="8" x2="12" y2="12"/>
          <line x1="12" y1="16" x2="12.01" y2="16"/>
        </svg>
        <span>{{ micError }}</span>
        <button type="button" class="ai-mic-err-close" @click="micError = ''" aria-label="Закрыть">×</button>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onBeforeUnmount, onMounted } from "vue";

const props = defineProps<{
  disabled?: boolean;
  placeholder?: string;
}>();
const emit = defineEmits<{
  submit: [text: string];
}>();

const text = ref("");
const focused = ref(false);
const taRef = ref<HTMLTextAreaElement | null>(null);
const bursting = ref(false);

const canSend = computed(() => !props.disabled && text.value.trim().length > 0);

// ─── Premium polish: placeholder rotation ──────────────────────
// Меняем placeholder каждые 4s через простой index, CSS вешает
// fade-transition на ::placeholder, чтобы переход был плавным.
const PLACEHOLDERS = [
  "Спросите о портфеле, проектах, рейтингах…",
  "Сделай сводку по 2026 и покажи отстающих",
  "Какие задачи просрочены у Навоийского ГМК?",
  "Сравни выручку 2024 vs 2025 по секторам",
  "Топ-10 рисков по кредитному портфелю",
  "Какие BP-показатели не выполнены за Q1?",
];
const rotatingIdx = ref(0);
const rotatingPlaceholder = computed(() => PLACEHOLDERS[rotatingIdx.value]);
let placeholderTimer: number | null = null;
onMounted(() => {
  placeholderTimer = window.setInterval(() => {
    // Не крутим, если юзер сейчас активно печатает или в фокусе.
    if (focused.value || text.value.length > 0) return;
    rotatingIdx.value = (rotatingIdx.value + 1) % PLACEHOLDERS.length;
  }, 4000);
});
onBeforeUnmount(() => {
  if (placeholderTimer != null) window.clearInterval(placeholderTimer);
});

function onInput() {
  nextTick(() => {
    const ta = taRef.value;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 220) + "px";
  });
}

function onShiftEnter() {
  // allow newline
}

function onSubmit() {
  if (!canSend.value) return;
  const t = text.value.trim();
  // Premium polish: burst-animation на кнопке (см. .is-burst в CSS)
  bursting.value = true;
  window.setTimeout(() => { bursting.value = false; }, 650);
  emit("submit", t);
  text.value = "";
  nextTick(() => {
    if (taRef.value) {
      taRef.value.style.height = "auto";
      taRef.value.focus();
    }
  });
}

// ─────────────────────────────────────────────────────────────
// Голосовой ввод — Pack 7.44 (Web Speech API, RU, live-streaming)
// ─────────────────────────────────────────────────────────────
const SpeechRecognition =
  (typeof window !== "undefined" &&
    ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition)) ||
  null;

const voiceSupported = ref(!!SpeechRecognition);
const micError = ref("");
const recording = ref(false);
let recognition: any = null;
let baseText = "";          // Текст в input ДО старта записи (чтобы не затирать)
let silenceTimer: any = null;
const SILENCE_MS = 2000;    // Авто-стоп через 2 сек тишины

function startVoice() {
  if (!SpeechRecognition || recording.value) return;

  try {
    micError.value = "";
    recognition = new SpeechRecognition();
    recognition.lang = "ru-RU";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    baseText = text.value;
    if (baseText.length && !baseText.endsWith(" ")) baseText += " ";

    recognition.onstart = () => {
      recording.value = true;
      resetSilenceTimer();
    };

    recognition.onresult = (event: any) => {
      let finalTr = "";
      let interimTr = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        if (r.isFinal) finalTr += r[0].transcript;
        else interimTr += r[0].transcript;
      }
      // Накопительный текст: baseText + всё распознанное в этой сессии
      if (finalTr) {
        baseText += finalTr;
        text.value = baseText;
      } else {
        text.value = baseText + interimTr;
      }
      onInput();
      resetSilenceTimer();
    };

    recognition.onerror = (e: any) => {
      const err = e?.error || "unknown";
      console.warn("[AiInput] Speech recognition error:", err);
      if (err === "not-allowed" || err === "service-not-allowed") {
        micError.value = "Доступ к микрофону заблокирован. Разрешите его в настройках сайта (значок 🔒 в адресной строке) и обновите страницу.";
      } else if (err === "no-speech") {
        micError.value = "Не услышал речь. Попробуйте ещё раз.";
      } else if (err === "audio-capture") {
        micError.value = "Микрофон не найден. Подключите устройство и попробуйте снова.";
      } else if (err === "network") {
        micError.value = "Ошибка сети распознавания. Проверьте интернет.";
      } else {
        micError.value = "Ошибка распознавания: " + err;
      }
      setTimeout(() => { micError.value = ""; }, 7000);
      stopVoice();
    };

    recognition.onend = () => {
      recording.value = false;
      clearSilenceTimer();
      recognition = null;
    };

    recognition.start();
  } catch (err) {
    console.warn("[AiInput] Не удалось запустить распознавание:", err);
    recording.value = false;
  }
}

function stopVoice() {
  clearSilenceTimer();
  if (recognition) {
    try { recognition.stop(); } catch { /* noop */ }
  }
  recording.value = false;
}

function toggleVoice() {
  if (props.disabled) return;
  if (recording.value) stopVoice();
  else startVoice();
}

function resetSilenceTimer() {
  clearSilenceTimer();
  silenceTimer = setTimeout(() => stopVoice(), SILENCE_MS);
}
function clearSilenceTimer() {
  if (silenceTimer) {
    clearTimeout(silenceTimer);
    silenceTimer = null;
  }
}

onBeforeUnmount(() => { stopVoice(); });
</script>

<style scoped>
/* ═══ Premium polish · animated angle для conic-rim ═══ */
@property --ai-inp-rim-angle {
  syntax: "<angle>";
  initial-value: 0deg;
  inherits: false;
}

.ai-inp-wrap {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding: 8px 8px 8px 16px;

  background: var(--ai-glass-bg-strong);
  -webkit-backdrop-filter: var(--ai-glass-blur);
          backdrop-filter: var(--ai-glass-blur);
  border: 1px solid var(--ai-glass-border);
  border-radius: 16px;
  box-shadow: var(--ai-shadow-soft);
  transition:
    border-color 0.25s var(--ai-easing-soft),
    box-shadow  0.4s  var(--ai-easing-soft);
  position: relative;
  isolation: isolate;
}

/* ═══ Premium: animated conic rim — спин по периметру в focus ═══
   Используем 2 псевдо: ::before = подсветка (мягкий conic-gradient
   с прозрачными секторами), маска через padding-trick. Включается
   только когда .is-focused. */
.ai-inp-wrap::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1px;
  background: conic-gradient(
    from var(--ai-inp-rim-angle, 0deg),
    transparent 0deg,
    transparent 200deg,
    rgba(127, 119, 221, 0.0)  220deg,
    rgba(127, 119, 221, 0.85) 270deg,
    rgba(29, 158, 117, 0.65)  310deg,
    rgba(127, 119, 221, 0.0)  340deg,
    transparent 360deg
  );
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
          mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  mask-composite: exclude;
  opacity: 0;
  transition: opacity 0.35s ease;
  pointer-events: none;
  z-index: 3;
}

/* ═══ Premium: Aurora glow — мягкое purple-свечение под полем ═══ */
.ai-inp-wrap::after {
  content: "";
  position: absolute;
  inset: -14px;
  border-radius: 24px;
  background: radial-gradient(
    60% 60% at 50% 50%,
    rgba(127, 119, 221, 0.22),
    rgba(127, 119, 221, 0.10) 45%,
    transparent 70%
  );
  filter: blur(14px);
  opacity: 0;
  transition: opacity 0.45s ease;
  pointer-events: none;
  z-index: -1;
}

.ai-inp-wrap.is-focused {
  border-color: rgba(127, 119, 221, 0.42);
  box-shadow:
    var(--ai-shadow-soft),
    0 0 0 4px rgba(127, 119, 221, 0.10);
}
.ai-inp-wrap.is-focused::before {
  opacity: 1;
  animation: aiInpRimSpin 6s linear infinite;
}
.ai-inp-wrap.is-focused::after {
  opacity: 1;
  animation: aiInpAuroraPulse 3.4s ease-in-out infinite;
}

@keyframes aiInpRimSpin {
  to { --ai-inp-rim-angle: 360deg; }
}
@keyframes aiInpAuroraPulse {
  0%, 100% { opacity: 0.7; transform: scale(0.985); }
  50%      { opacity: 1.0; transform: scale(1.015); }
}

.ai-inp-wrap.is-disabled {
  opacity: 0.6;
  pointer-events: none;
}

.ai-inp-wrap.is-recording {
  border-color: rgba(226, 75, 74, 0.45);
  box-shadow:
    var(--ai-shadow-soft),
    0 0 0 4px rgba(226, 75, 74, 0.12);
}

.ai-inp-ta {
  flex: 1;
  border: 0;
  background: transparent;
  outline: none;
  resize: none;
  font: inherit;
  font-size: 13.5px;
  line-height: 1.55;
  color: var(--uza-navy);
  padding: 8px 0;
  max-height: 220px;
  overflow-y: auto;
  font-family: inherit;
}

.ai-inp-ta::placeholder {
  color: rgba(30, 42, 74, 0.4);
  /* Premium: плавный fade при смене placeholder каждые 4s */
  transition: color 0.4s ease, opacity 0.4s ease;
}

/* ─────────── Mic button (голосовой ввод) ─────────── */
.ai-inp-mic {
  position: relative;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  border: 1px solid rgba(30, 42, 74, 0.10);
  background: rgba(255, 255, 255, 0.6);
  color: rgba(30, 42, 74, 0.62);
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: transform 0.18s var(--ai-easing), background 0.2s, color 0.2s, border-color 0.2s;
}
.ai-inp-mic:hover:not(:disabled) {
  transform: translateY(-1px) scale(1.04);
  background: rgba(127, 119, 221, 0.08);
  color: var(--uza-purple, #7F77DD);
  border-color: rgba(127, 119, 221, 0.32);
}
.ai-inp-mic:active:not(:disabled) {
  transform: translateY(0) scale(0.96);
}
.ai-inp-mic:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.ai-inp-mic.is-recording {
  background: #E24B4A;
  color: #fff;
  border-color: #E24B4A;
  animation: ai-mic-pulse 1.4s ease-in-out infinite;
}
@keyframes ai-mic-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(226, 75, 74, 0.55); }
  50%      { box-shadow: 0 0 0 8px rgba(226, 75, 74, 0); }
}
.ai-inp-mic-ring {
  position: absolute; inset: -4px;
  border-radius: 14px;
  border: 1.5px solid rgba(226, 75, 74, 0.55);
  animation: ai-mic-ring 1.6s ease-out infinite;
  pointer-events: none;
}
@keyframes ai-mic-ring {
  0%   { transform: scale(.85); opacity: 1; }
  100% { transform: scale(1.4);  opacity: 0; }
}

.ai-inp-send {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  border: 0;
  background: linear-gradient(135deg, var(--uza-purple) 0%, var(--uza-purple-2) 100%);
  color: white;
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: transform 0.18s var(--ai-easing), opacity 0.2s, box-shadow 0.2s;
  box-shadow: 0 4px 12px rgba(127, 119, 221, 0.35);
  position: relative;
  overflow: visible;
}

.ai-inp-send:hover:not(:disabled) {
  transform: translateY(-1px) scale(1.04);
  box-shadow: 0 6px 18px rgba(127, 119, 221, 0.45);
}
.ai-inp-send:active:not(:disabled) {
  transform: translateY(0) scale(0.96);
}
.ai-inp-send:disabled {
  background: rgba(30, 42, 74, 0.12);
  color: rgba(30, 42, 74, 0.4);
  cursor: not-allowed;
  box-shadow: none;
}

.ai-inp-send svg {
  transition: transform 0.18s var(--ai-easing);
}
.ai-inp-send:hover:not(:disabled) svg {
  transform: translate(1px, -1px);
}

/* ═══ Premium: «ready» deep-breath — одноразовая пульсация когда
   текст впервые становится непустым (.is-ready ставится на wrap). ═══ */
.ai-inp-wrap.is-ready .ai-inp-send:not(:disabled) {
  animation: aiInpReadyBreath 1.6s cubic-bezier(0.34, 1.2, 0.64, 1) 1;
}
@keyframes aiInpReadyBreath {
  0%   { box-shadow: 0 4px 12px rgba(127, 119, 221, 0.35); }
  40%  { box-shadow: 0 4px 18px rgba(127, 119, 221, 0.65), 0 0 0 6px rgba(127, 119, 221, 0.12); }
  100% { box-shadow: 0 4px 12px rgba(127, 119, 221, 0.35); }
}

/* ═══ Premium: BURST на клик — стрелка «улетает» + shockwave ═══ */
.ai-inp-wrap.is-burst .ai-inp-send svg {
  animation: aiInpArrowFly 0.55s cubic-bezier(0.5, 0, 0.75, 0) 1;
}
.ai-inp-wrap.is-burst .ai-inp-send::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  border: 2px solid rgba(127, 119, 221, 0.65);
  animation: aiInpShockwave 0.6s cubic-bezier(0.22, 1, 0.36, 1) 1;
  pointer-events: none;
}
@keyframes aiInpArrowFly {
  0%   { transform: translate(0, 0)        scale(1)    rotate(0deg);   opacity: 1; }
  60%  { transform: translate(14px, -14px) scale(1.15) rotate(8deg);   opacity: 0.6; }
  61%  { transform: translate(-12px, 8px)  scale(0.4)  rotate(-20deg); opacity: 0; }
  100% { transform: translate(0, 0)        scale(1)    rotate(0deg);   opacity: 1; }
}
@keyframes aiInpShockwave {
  0%   { transform: scale(1);   opacity: 0.8; }
  100% { transform: scale(2.2); opacity: 0; }
}

/* ═══ Premium: тонкий caret-glow под textarea-курсором в focus ═══
   Это не настоящий caret (браузер рендерит свой) — это subtle
   подсветка-полоска под полем для ощущения "alive". */
.ai-inp-wrap.is-focused .ai-inp-ta {
  /* Subtle gradient text-shadow на caret цвет — браузер caret-color */
  caret-color: var(--uza-purple, #7F77DD);
}

/* ─────────── Mic error toast (Pack 7.44) ─────────── */
.ai-mic-err {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0; right: 0;
  margin: 0 auto;
  max-width: 460px;
  padding: 10px 36px 10px 12px;
  background: var(--bg1, #fff);
  border: 1px solid rgba(226, 75, 74, 0.32);
  border-radius: 10px;
  box-shadow: 0 6px 22px rgba(0, 0, 0, .12);
  position: relative; overflow: hidden;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
  color: #791F1F;
  line-height: 1.4;
  z-index: 5;
}
.ai-mic-err > svg { color: #E24B4A; flex-shrink: 0; margin-top: 1px; }
.ai-mic-err > span { flex: 1; }
.ai-mic-err-close {
  position: absolute; top: 4px; right: 6px;
  width: 22px; height: 22px;
  background: transparent; border: 0;
  font-size: 18px; line-height: 1;
  color: rgba(0,0,0,.4);
  cursor: pointer; border-radius: 4px;
}
.ai-mic-err-close:hover { background: rgba(0,0,0,.05); color: #791F1F; }
.ai-inp-wrap { position: relative; }

.ai-mic-err-enter-active, .ai-mic-err-leave-active {
  transition: opacity .25s, transform .25s cubic-bezier(0.34, 1.2, 0.64, 1);
}
.ai-mic-err-enter-from, .ai-mic-err-leave-to {
  opacity: 0; transform: translateY(6px);
}
.ai-mic-err::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: #E24B4A;
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .6s cubic-bezier(0.34, 1.2, 0.64, 1) both;
  transform-origin: left center;
  pointer-events: none;
}
</style>
