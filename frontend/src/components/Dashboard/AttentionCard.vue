<template>
  <transition name="atc-fade">
    <section v-if="loaded && (items.length || allClear)" class="atc">
      <div class="atc-aura" aria-hidden="true"></div>

      <div class="atc-head">
        <div class="atc-greet">
          <div class="atc-greet-line">{{ greeting }}<span v-if="userName">, {{ userName }}</span></div>
          <div class="atc-greet-sub">
            <template v-if="allClear">Всё под контролем — критичных сигналов нет</template>
            <template v-else>{{ items.length }} {{ pluralThings(items.length) }} требуют внимания</template>
          </div>
        </div>
        <div class="atc-brand" aria-hidden="true">
          <EptLogo :size="34" />
        </div>
      </div>

      <div v-if="allClear" class="atc-clear">
        <span class="atc-clear-ic">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 6L9 17l-5-5"/>
          </svg>
        </span>
        <span>Портфель в норме. Просрочек, рисков и задач на модерации нет.</span>
      </div>

      <div v-else class="atc-items">
        <button
          v-for="(it, i) in items"
          :key="it.id"
          class="atc-item"
          :class="`sev-${it.severity}`"
          :style="{ animationDelay: `${i * 70}ms` }"
          type="button"
          @click="go(it.link)"
        >
          <span class="atc-item-ic">
            <svg v-if="it.icon === 'alert'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5M12 16h.01"/></svg>
            <svg v-else-if="it.icon === 'clock'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
            <svg v-else-if="it.icon === 'pulse'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2 6 4-12 2 6h6"/></svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l7 4v6c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z"/></svg>
          </span>
          <span class="atc-item-txt">
            <span class="atc-item-title">{{ it.title }}</span>
            <span class="atc-item-detail">{{ it.detail }}</span>
          </span>
          <span class="atc-item-go">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
          </span>
        </button>
      </div>

      <button v-if="!allClear" class="atc-ask" type="button" @click="askBrief">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
        </svg>
        Спросить ИИ: «что мне делать в первую очередь?»
      </button>
    </section>
  </transition>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { useRouter } from "vue-router";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";
import EptLogo from "@/components/EptLogo.vue";

interface Item {
  id: string; severity: "critical" | "warning" | "info";
  icon: string; count: number; title: string; detail: string; link: string;
}

const router = useRouter();
const auth = useAuthStore();

const items = ref<Item[]>([]);
const allClear = ref(false);
const loaded = ref(false);

const userName = (() => {
  const n = (auth.user?.full_name || "").trim();
  if (!n) return "";
  return n.split(/\s+/)[0]; // имя
})();

const greeting = (() => {
  const h = new Date().getHours();
  if (h < 5) return "Доброй ночи";
  if (h < 12) return "Доброе утро";
  if (h < 18) return "Добрый день";
  return "Добрый вечер";
})();

function pluralThings(n: number): string {
  const m10 = n % 10, m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return "вещь";
  if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return "вещи";
  return "вещей";
}

function go(link: string) {
  if (link) router.push(link);
}

function askBrief() {
  // Открывает ИИ-ассистента с готовым вопросом-приоритизацией
  try {
    sessionStorage.setItem(
      "uza_ai_prefill",
      "Что мне нужно сделать в первую очередь сегодня? Приоритизируй просрочки, риски и дедлайны по портфелю. Используй list_overdue_tasks и list_status_updates.",
    );
  } catch { /* noop */ }
  router.push("/ai-chat");
}

onMounted(async () => {
  try {
    const { data } = await api.get("/insights/attention");
    items.value = data?.items || [];
    allClear.value = !!data?.all_clear;
  } catch {
    items.value = [];
    allClear.value = false;
  } finally {
    loaded.value = true;
  }
});
</script>

<style scoped>
.atc {
  position: relative;
  overflow: hidden;
  margin-bottom: clamp(10px, 1vw, 16px);
  padding: clamp(14px, 1.2vw, 20px) clamp(16px, 1.4vw, 22px);
  border-radius: 18px;
  background: linear-gradient(135deg, #1E2A4A 0%, #2A2065 55%, #534AB7 100%);
  color: #fff;
  box-shadow: 0 18px 48px rgba(30, 36, 90, 0.28), 0 4px 14px rgba(30, 36, 90, 0.16);
}
.atc-aura {
  position: absolute;
  top: -40%; right: -10%;
  width: 380px; height: 380px;
  background: radial-gradient(circle, rgba(127, 119, 221, 0.55), transparent 60%);
  filter: blur(20px);
  pointer-events: none;
  animation: atc-aura 9s ease-in-out infinite;
}
@keyframes atc-aura {
  0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.8; }
  50% { transform: translate(-20px, 20px) scale(1.12); opacity: 1; }
}

.atc-head {
  position: relative; z-index: 1;
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  margin-bottom: 14px;
}
.atc-greet-line {
  font-size: clamp(17px, 1.5vw, 21px);
  font-weight: 500;
  letter-spacing: -0.02em;
}
.atc-greet-sub {
  margin-top: 3px;
  font-size: 12.5px;
  color: rgba(255, 255, 255, 0.72);
  letter-spacing: 0.01em;
}
.atc-brand {
  flex-shrink: 0;
  width: 44px; height: 44px;
  display: grid; place-items: center;
  background: rgba(255, 255, 255, 0.10);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 12px;
  -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px);
}

.atc-clear {
  position: relative; z-index: 1;
  display: flex; align-items: center; gap: 10px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  font-size: 13px;
  color: rgba(255, 255, 255, 0.9);
}
.atc-clear-ic {
  display: grid; place-items: center;
  width: 30px; height: 30px; flex-shrink: 0;
  border-radius: 9px;
  background: rgba(29, 158, 117, 0.28);
  color: #6EE7B7;
}

.atc-items {
  position: relative; z-index: 1;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  gap: 8px;
}
.atc-item {
  display: flex; align-items: center; gap: 11px;
  padding: 11px 12px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.07);
  -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
  color: #fff;
  cursor: pointer;
  text-align: left;
  transition: transform 0.16s var(--ease-standard, ease), background 0.16s, border-color 0.16s;
  opacity: 0;
  animation: atc-item-in 0.45s var(--ease-standard, ease) both;
}
@keyframes atc-item-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.atc-item:hover {
  transform: translateY(-2px);
  background: rgba(255, 255, 255, 0.13);
  border-color: rgba(255, 255, 255, 0.28);
}
.atc-item-ic {
  flex-shrink: 0;
  width: 34px; height: 34px;
  display: grid; place-items: center;
  border-radius: 10px;
}
.atc-item-ic svg { width: 18px; height: 18px; }
.atc-item.sev-critical .atc-item-ic { background: rgba(226, 75, 74, 0.26); color: #FCA5A5; }
.atc-item.sev-warning  .atc-item-ic { background: rgba(239, 159, 39, 0.26); color: #FCD34D; }
.atc-item.sev-info     .atc-item-ic { background: rgba(55, 138, 221, 0.26); color: #93C5FD; }
.atc-item-txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.atc-item-title {
  font-size: 13px; font-weight: 500; letter-spacing: -0.01em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.atc-item-detail {
  font-size: 11px; color: rgba(255, 255, 255, 0.62);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.atc-item-go { flex-shrink: 0; color: rgba(255, 255, 255, 0.5); transition: transform 0.16s, color 0.16s; }
.atc-item:hover .atc-item-go { transform: translateX(3px); color: #fff; }

.atc-ask {
  position: relative; z-index: 1;
  margin-top: 12px;
  display: inline-flex; align-items: center; gap: 7px;
  padding: 8px 13px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: rgba(255, 255, 255, 0.10);
  color: #fff;
  font-size: 12px; font-weight: 500;
  cursor: pointer;
  transition: all 0.16s ease;
}
.atc-ask:hover {
  background: rgba(255, 255, 255, 0.18);
  border-color: rgba(255, 255, 255, 0.4);
  transform: translateY(-1px);
}

.atc-fade-enter-active { transition: opacity 0.4s ease, transform 0.4s var(--ease-standard, ease); }
.atc-fade-enter-from { opacity: 0; transform: translateY(-8px); }

@media (prefers-reduced-motion: reduce) {
  .atc-aura, .atc-item { animation: none !important; }
  .atc-item { opacity: 1; }
}
</style>
