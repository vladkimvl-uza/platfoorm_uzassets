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

let _voice: SpeechSynthesisVoice | null = null;
let _voicesTried = false;

function _pickVoice(): SpeechSynthesisVoice | null {
  if (!state.supported) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;
  // Приоритет: ru-RU → любой ru → дефолт
  return (
    voices.find((v) => v.lang === "ru-RU") ||
    voices.find((v) => v.lang?.toLowerCase().startsWith("ru")) ||
    voices.find((v) => v.default) ||
    voices[0] ||
    null
  );
}

function _ensureVoice() {
  if (!state.supported) return;
  if (_voice) return;
  _voice = _pickVoice();
  if (!_voice && !_voicesTried) {
    _voicesTried = true;
    // voices грузятся асинхронно — повторим по событию
    window.speechSynthesis.onvoiceschanged = () => { _voice = _pickVoice(); };
  }
}

/** Markdown/HTML → чистый текст для произношения. */
function toPlainText(src: string): string {
  if (!src) return "";
  let t = src;
  // Служебная строка follow-ups — не читаем
  t = t.replace(/\[\[followups\]\][\s\S]*$/i, "");
  // Код-блоки → «фрагмент кода»
  t = t.replace(/```[\s\S]*?```/g, " фрагмент кода. ");
  // Таблицы: убираем разделители |---|, превращаем | в паузы
  t = t.replace(/^\s*\|?[\s:|-]*-{2,}[\s:|-]*\|?\s*$/gm, "");
  t = t.replace(/\|/g, ", ");
  // Markdown-разметка
  t = t.replace(/[#*_`>~]/g, "");
  t = t.replace(/\[([^\]]+)\]\([^)]*\)/g, "$1"); // ссылки → текст
  t = t.replace(/✅/g, " выполнено ").replace(/⚠️/g, " внимание ").replace(/❌/g, " не выполнено ");
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
  _ensureVoice();
  const u = new SpeechSynthesisUtterance(text);
  if (_voice) u.voice = _voice;
  u.lang = _voice?.lang || "ru-RU";
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
