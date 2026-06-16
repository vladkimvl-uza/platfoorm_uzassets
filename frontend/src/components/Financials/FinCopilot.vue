<template>
  <!-- Trigger: pill button (parent gates with v-if=hasAccess) -->
  <button class="fcp-trigger" :class="{ open }" type="button" @click="open = !open"
          title="ИИ-аналитик финансов">
    <span class="fcp-trigger-spark">✦</span>
    <span class="fcp-trigger-txt">ИИ-аналитик</span>
  </button>

  <Teleport to="body">
    <Transition name="fcp-back">
      <div v-if="open" class="fcp-back" @click="open = false" />
    </Transition>
    <Transition name="fcp-panel">
      <aside v-if="open" class="fcp-panel" role="dialog" aria-modal="true">
        <header class="fcp-head">
          <div class="fcp-head-l">
            <div class="fcp-icon">✦</div>
            <div>
              <h3>ИИ-аналитик · Финансы</h3>
              <p v-if="context">{{ context }}</p>
              <p v-else>портфель · все компании</p>
            </div>
          </div>
          <button class="fcp-x" type="button" @click="open = false" aria-label="Закрыть">✕</button>
        </header>

        <!-- Disclaimer -->
        <div class="fcp-disc">
          ⚠ Имеет доступ к web-поиску. ИИ может ошибаться — проверяйте важные цифры.
        </div>

        <!-- Empty state: suggested prompts -->
        <section v-if="!chat.messages.value.length" class="fcp-suggest">
          <h4>С чего начать</h4>
          <button v-for="(s, i) in SUGGESTIONS" :key="i" class="fcp-sg"
                  :disabled="chat.isStreaming.value" @click="ask(s)">
            {{ s }}
          </button>
        </section>

        <!-- Messages -->
        <section v-else class="fcp-msgs" ref="msgsBox">
          <AiMessage
            v-for="(m, i) in chat.messages.value"
            :key="i"
            :role="m.role"
            :content="m.content"
            :pending="m.pending ?? false"
            :error="m.error ?? false"
            :tool-calls="m.toolCalls"
          />
          <div v-if="chat.error.value" class="fcp-err">{{ chat.error.value }}</div>

          <!-- Follow-up chips -->
          <div v-if="!chat.isStreaming.value && chat.messages.value.length" class="fcp-followups">
            <button v-for="(f, i) in FOLLOWUPS" :key="i" class="fcp-fu" @click="ask(f)">{{ f }}</button>
          </div>
        </section>

        <footer class="fcp-foot">
          <AiInput
            :disabled="chat.isStreaming.value"
            placeholder="Спросите про финансы, прогноз, сравнение…"
            @submit="ask($event)"
          />
          <div class="fcp-foot-row">
            <button v-if="chat.isStreaming.value" class="fcp-stop" type="button" @click="chat.abort">■ Остановить</button>
            <button v-else-if="chat.messages.value.length" class="fcp-restart" type="button" @click="chat.reset">↺ Новый запрос</button>
          </div>
        </footer>
      </aside>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from "vue";
import AiMessage from "@/components/Ai/AiMessage.vue";
import AiInput from "@/components/Ai/AiInput.vue";
import { useAiChat } from "@/composables/useAiChat";

const props = defineProps<{
  context?: string; // человекочитаемый контекст экрана (компания/год/стандарт/метрика)
}>();

const open = ref(false);
const chat = useAiChat();
const msgsBox = ref<HTMLElement | null>(null);

const SUGGESTIONS = [
  "Проанализируй маржинальность по компаниям портфеля",
  "Кто тянет финансовый результат вниз и почему?",
  "Спрогнозируй выручку и прибыль на Q3–Q4 (run-rate)",
  "Сравни EBITDA компаний год к году",
  "IPO в Узбекистане и их результаты — что есть на рынке?",
];
const FOLLOWUPS = [
  "Построй график динамики",
  "Сравни с планом",
  "Дай рекомендации",
  "Покажи таблицей",
];

// Финансовый копилот: сильная модель + нативный web-поиск + полный набор
// инструментов (знает компании, проекты, задачи, KPI, финансы).
async function ask(text: string) {
  if (chat.isStreaming.value || !text.trim()) return;
  const prompt = props.context
    ? `[Контекст экрана: ${props.context}]\n${text}`
    : text;
  await chat.send(prompt, { model: "ai-balanced", maxTokens: 16000, web: true });
  scrollBottom();
}

function scrollBottom() {
  nextTick(() => { if (msgsBox.value) msgsBox.value.scrollTop = msgsBox.value.scrollHeight; });
}
watch(() => chat.messages.value.length, scrollBottom);
watch(() => chat.messages.value[chat.messages.value.length - 1]?.content, scrollBottom);
</script>

<style scoped>
.fcp-trigger {
  display: inline-flex; align-items: center; gap: 7px;
  background: linear-gradient(135deg, #8B7FF0, #6C5CE7);
  color: #fff; border: none; cursor: pointer;
  padding: 7px 14px; border-radius: 10px;
  font-size: 12px; font-weight: 600; font-family: inherit;
  box-shadow: 0 3px 12px rgba(108, 92, 231, .35), inset 0 1px 0 rgba(255,255,255,.2);
  transition: transform .18s cubic-bezier(.34,1.4,.5,1), box-shadow .18s;
}
.fcp-trigger:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(108, 92, 231, .5); }
.fcp-trigger.open { transform: translateY(0) scale(.97); }
.fcp-trigger-spark { animation: fcpSpark 2.4s ease-in-out infinite; }
@keyframes fcpSpark { 0%,100%{ opacity:1; transform:scale(1); } 50%{ opacity:.6; transform:scale(1.2) rotate(8deg); } }

.fcp-back { position: fixed; inset: 0; background: rgba(20,16,40,.28); backdrop-filter: blur(2px); z-index: 9300; }
.fcp-panel {
  position: fixed; top: 0; right: 0; bottom: 0; z-index: 9301;
  width: min(440px, 96vw);
  background: var(--bg1, #fff);
  border-left: 1px solid rgba(15,23,60,.08);
  box-shadow: -16px 0 48px rgba(15,23,60,.18);
  display: flex; flex-direction: column;
  font-family: Geist, system-ui, sans-serif;
}
.fcp-back-enter-active, .fcp-back-leave-active { transition: opacity .25s; }
.fcp-back-enter-from, .fcp-back-leave-to { opacity: 0; }
.fcp-panel-enter-active { transition: transform .34s cubic-bezier(.22,1,.36,1); }
.fcp-panel-leave-active { transition: transform .26s ease; }
.fcp-panel-enter-from, .fcp-panel-leave-to { transform: translateX(100%); }

.fcp-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 18px 12px; border-bottom: 1px solid rgba(15,23,60,.06); }
.fcp-head-l { display: flex; align-items: center; gap: 11px; }
.fcp-icon {
  width: 34px; height: 34px; border-radius: 10px; flex-shrink: 0;
  background: linear-gradient(135deg, #8B7FF0, #6C5CE7); color: #fff;
  display: inline-flex; align-items: center; justify-content: center; font-size: 16px;
}
.fcp-head h3 { font-size: 14px; font-weight: 600; margin: 0; color: var(--t1, #1e2a4a); }
.fcp-head p { font-size: 11px; color: rgba(15,23,60,.55); margin: 2px 0 0; }
.fcp-x { background: transparent; border: none; font-size: 16px; color: rgba(15,23,60,.45); cursor: pointer; padding: 4px 8px; }
.fcp-x:hover { color: rgba(15,23,60,.8); }

.fcp-disc {
  margin: 10px 14px 0; padding: 8px 11px; border-radius: 9px;
  background: rgba(224,146,47,.1); border: 1px solid rgba(224,146,47,.25);
  font-size: 10.5px; font-weight: 500; color: #8A5A12; line-height: 1.4;
}

.fcp-suggest { padding: 14px; display: flex; flex-direction: column; gap: 7px; }
.fcp-suggest h4 { font-size: 10px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: rgba(15,23,60,.5); margin: 0 0 3px; }
.fcp-sg {
  text-align: left; background: var(--bg2, #F7F7FB); border: 1px solid rgba(15,23,60,.06);
  border-radius: 10px; padding: 10px 12px; font-size: 12px; color: var(--t1, #1e2a4a);
  cursor: pointer; font-family: inherit; transition: all .15s; line-height: 1.35;
  animation: fcpIn .4s ease backwards;
}
.fcp-sg:nth-child(2){animation-delay:.04s}.fcp-sg:nth-child(3){animation-delay:.08s}
.fcp-sg:nth-child(4){animation-delay:.12s}.fcp-sg:nth-child(5){animation-delay:.16s}.fcp-sg:nth-child(6){animation-delay:.2s}
@keyframes fcpIn { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
.fcp-sg:hover:not(:disabled) { background: rgba(127,119,221,.1); border-color: rgba(127,119,221,.3); transform: translateX(2px); }
.fcp-sg:disabled { opacity: .5; cursor: default; }

.fcp-msgs { flex: 1; overflow-y: auto; padding: 14px; display: flex; flex-direction: column; gap: 12px; }
.fcp-err { font-size: 12px; color: #C5352F; background: rgba(226,75,74,.08); border-radius: 8px; padding: 8px 11px; }

.fcp-followups { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 2px; }
.fcp-fu {
  background: rgba(127,119,221,.1); border: 1px solid rgba(127,119,221,.22); color: #5B51C2;
  border-radius: 999px; padding: 5px 11px; font-size: 11px; font-weight: 500; cursor: pointer;
  font-family: inherit; transition: all .15s;
}
.fcp-fu:hover { background: rgba(127,119,221,.18); transform: translateY(-1px); }

.fcp-foot { border-top: 1px solid rgba(15,23,60,.06); padding: 12px 14px; }
.fcp-foot-row { display: flex; gap: 10px; margin-top: 6px; }
.fcp-stop, .fcp-restart {
  background: transparent; border: none; cursor: pointer; font-size: 11px; font-weight: 600;
  color: rgba(15,23,60,.55); font-family: inherit; padding: 2px 0;
}
.fcp-stop:hover, .fcp-restart:hover { color: var(--t1, #1e2a4a); }
</style>
