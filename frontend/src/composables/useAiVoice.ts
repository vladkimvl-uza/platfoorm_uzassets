// useAiVoice — озвучка ответов ИИ (Web Speech Synthesis, singleton).
//
// Два режима:
//   • Ручной — кнопка «прослушать» на конкретном сообщении.
//   • Авто (voiceMode) — каждый завершённый ответ ассистента читается вслух.
// Голос подбирается ru-RU (с фолбэком). Состояние общее для всего чата,
// поэтому новый ответ прерывает чтение предыдущего.
import { reactive } from "vue";

const VOICE_MODE_KEY = "ai-voice-mode";

const state = reactive({
  supported: typeof window !== "undefined" && "speechSynthesis" in window,
  voiceMode: typeof localStorage !== "undefined" && localStorage.getItem(VOICE_MODE_KEY) === "1",
  speakingKey: null as string | null,
});

let _voicesTried = false;

// Определяем язык текста: ru / uz / en (для подбора голоса)
function _detectLang(text: string): "ru" | "uz" | "en" {
  const t = text || "";
  // i18n-exempt-start: script detection patterns classify answer text and are not UI copy.
  // Узбекская кириллица — специфические буквы
  if (/[ўғқҳ]/i.test(t)) return "uz";
  // Узбекская латиница — апострофы o'/g' + сочетания
  if (/[a-z]'|o['`]|g['`]/i.test(t) && !/[а-яё]/i.test(t)) return "uz";
  const cyr = (t.match(/[а-яё]/gi) || []).length;
  const lat = (t.match(/[a-z]/gi) || []).length;
  // i18n-exempt-end
  if (lat > cyr * 1.3) return "en";
  return "ru";
}

// i18n-exempt-start: speech lexicon follows the detected answer language, independently of UI locale.
const SPEECH_WORDS = {
  ru: { code: "фрагмент кода", done: "выполнено", attention: "внимание", failed: "не выполнено" },
  uz: { code: "kod parchasi", done: "bajarildi", attention: "diqqat", failed: "bajarilmadi" },
  en: { code: "code fragment", done: "completed", attention: "attention", failed: "not completed" },
} as const;
// i18n-exempt-end

function _pickVoice(lang: "ru" | "uz" | "en"): SpeechSynthesisVoice | null {
  if (!state.supported) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  const byPrefix = (p: string) => voices.find((v) => v.lang?.toLowerCase().startsWith(p));
  if (lang === "en") {
    return byPrefix("en") || byPrefix("ru") || voices.find((v) => v.default) || voices[0] || null;
  }
  if (lang === "uz") {
    // Узбекских голосов в браузерах почти нет — фолбэк на ru, затем en
    return byPrefix("uz") || byPrefix("ru") || byPrefix("en") || voices[0] || null;
  }
  return byPrefix("ru") || voices.find((v) => v.default) || voices[0] || null;
}

function _ensureVoicesLoaded() {
  if (!state.supported || _voicesTried) return;
  if (!window.speechSynthesis.getVoices().length) {
    _voicesTried = true;
    window.speechSynthesis.onvoiceschanged = () => { /* голоса подгрузились */ };
  }
}

/** Markdown/HTML → чистый текст для произношения. */
function toPlainText(src: string): string {
  if (!src) return "";
  const words = SPEECH_WORDS[_detectLang(src)];
  let t = src;
  // Служебная строка follow-ups — не читаем
  t = t.replace(/\[\[followups\]\][\s\S]*$/i, "");
  // Код-блоки → «фрагмент кода»
  t = t.replace(/```[\s\S]*?```/g, ` ${words.code}. `);
  // Таблицы: убираем разделители |---|, превращаем | в паузы
  t = t.replace(/^\s*\|?[\s:|-]*-{2,}[\s:|-]*\|?\s*$/gm, "");
  t = t.replace(/\|/g, ", ");
  // Markdown-разметка
  t = t.replace(/[#*_`>~]/g, "");
  t = t.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1"); // ссылки → текст
  t = t.replace(/✅/g, ` ${words.done} `).replace(/⚠️/g, ` ${words.attention} `).replace(/❌/g, ` ${words.failed} `);
  t = t.replace(/[ \t]+/g, " ").replace(/\n{2,}/g, ". ").replace(/\n/g, ". ");
  return t.trim();
}

function stop() {
  if (!state.supported) return;
  try { window.speechSynthesis.cancel(); } catch { /* noop */ }
  state.speakingKey = null;
}

function speak(key: string, src: string) {
  if (!state.supported) return;
  const text = toPlainText(src);
  if (!text) return;
  // Если уже читаем это же сообщение — стоп (toggle)
  if (state.speakingKey === key) { stop(); return; }
  stop();
  _ensureVoicesLoaded();
  const lang = _detectLang(text);
  const voice = _pickVoice(lang);
  const u = new SpeechSynthesisUtterance(text);
  if (voice) u.voice = voice;
  u.lang = voice?.lang || (lang === "en" ? "en-US" : lang === "uz" ? "uz-UZ" : "ru-RU");
  u.rate = 1.0;
  u.pitch = 1.0;
  u.onend = () => { if (state.speakingKey === key) state.speakingKey = null; };
  u.onerror = () => { if (state.speakingKey === key) state.speakingKey = null; };
  state.speakingKey = key;
  try { window.speechSynthesis.speak(u); }
  catch { state.speakingKey = null; }
}

function toggleVoiceMode() {
  state.voiceMode = !state.voiceMode;
  try { localStorage.setItem(VOICE_MODE_KEY, state.voiceMode ? "1" : "0"); } catch { /* noop */ }
  if (!state.voiceMode) stop();
}

export function useAiVoice() {
  return { state, speak, stop, toggleVoiceMode, toPlainText };
}
