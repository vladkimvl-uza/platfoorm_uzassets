<script setup lang="ts">
/**
 * FinAiAnnounceModal — премиум-анонс ИИ-возможностей модуля «Финансы».
 * Показывается ОДИН раз только целевым пользователям (по email) при входе на
 * /financials. Самодостаточен: сам проверяет email текущего юзера + флаг
 * localStorage и решает, показываться ли. Родителю достаточно отрендерить тег.
 */
import { ref, onMounted } from "vue";
import { useAuthStore } from "@/stores/auth";

const TARGET_EMAILS = ["b.abdinazarov@uz-assets.uz", "v.kim@uz-assets.uz"];
const FLAG = "fin.aiAnnounce.v1";

const auth = useAuthStore();
const open = ref(false);

const features = [
  {
    title: "ИИ-аналитик",
    text: "Задайте вопрос на естественном языке — получите разбор по любой компании портфеля: драйверы, риски, что требует внимания и куда направить капитал.",
  },
  {
    title: "Прогнозирование показателей",
    text: "Модели run-rate, CAGR и линейная достраивают будущие периоды по каждой строке P&L и баланса. Прогноз помечен и не смешивается с фактом.",
  },
  {
    title: "Анализ высокоуровневых показателей",
    text: "Сквозной разбор всех компаний по каждому ключевому показателю — с готовыми выводами и рекомендациями в один клик.",
  },
];

function _email(): string {
  return String((auth.user as any)?.email || "").trim().toLowerCase();
}
function _flagKey(): string {
  return FLAG + ":" + _email();
}

onMounted(() => {
  const email = _email();
  if (!TARGET_EMAILS.includes(email)) return;
  try {
    if (localStorage.getItem(_flagKey()) === "1") return;
  } catch { /* noop */ }
  // лёгкая задержка — даём странице «осесть», вход выглядит премиальнее
  window.setTimeout(() => { open.value = true; }, 520);
});

function close() {
  open.value = false;
  try { localStorage.setItem(_flagKey(), "1"); } catch { /* noop */ }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="faa-fade">
      <div v-if="open" class="faa-backdrop" @click.self="close">
        <Transition name="faa-pop" appear>
          <div
            v-if="open"
            class="faa-card"
            role="dialog"
            aria-modal="true"
            aria-label="Новые ИИ-возможности модуля Финансы"
          >
            <div class="faa-topbar" aria-hidden="true"></div>
            <button class="faa-close" type="button" @click="close" aria-label="Закрыть">×</button>

            <div class="faa-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
                <path d="M12 3l1.9 4.6L18.5 9.5 13.9 11.4 12 16l-1.9-4.6L5.5 9.5l4.6-1.9L12 3z" />
                <path d="M19 14l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7L19 14z" />
              </svg>
            </div>

            <div class="faa-eyebrow">Обновление · модуль «Финансы»</div>
            <h2 class="faa-title">В модуле «Финансы» теперь работает ИИ</h2>
            <p class="faa-intro">
              Интеллектуальный слой аналитики встроен прямо в модуль. Три новые возможности:
            </p>

            <ul class="faa-list">
              <li
                v-for="(f, i) in features"
                :key="f.title"
                class="faa-item"
                :style="{ '--d': (i * 95 + 120) + 'ms' }"
              >
                <span class="faa-bullet" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M5 12.5l4.5 4.5L19 7" />
                  </svg>
                </span>
                <span class="faa-item-body">
                  <span class="faa-item-title">{{ f.title }}</span>
                  <span class="faa-item-text">{{ f.text }}</span>
                </span>
              </li>
            </ul>

            <p class="faa-foot">Всё доступно прямо здесь, в модуле «Финансы».</p>
            <button class="faa-cta" type="button" @click="close">Перейти к аналитике</button>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.faa-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9800;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(12, 18, 48, 0.46);
  -webkit-backdrop-filter: blur(6px) saturate(1.1);
  backdrop-filter: blur(6px) saturate(1.1);
}

.faa-card {
  position: relative;
  width: 100%;
  max-width: 480px;
  max-height: 92dvh;
  overflow-y: auto;
  background: #fff;
  border-radius: 20px;
  padding: 30px 30px 26px;
  box-shadow:
    0 2px 6px rgba(16, 24, 64, 0.06),
    0 18px 44px rgba(16, 24, 64, 0.18),
    0 40px 90px rgba(16, 24, 64, 0.12);
  border: 1px solid rgba(16, 24, 64, 0.05);
}

/* Верхняя бренд-полоса + один проблеск-shimmer */
.faa-topbar {
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 4px;
  border-radius: 20px 20px 0 0;
  background: linear-gradient(90deg, #7F77DD 0%, #6C8BE0 45%, #1D9E75 100%);
  overflow: hidden;
}
.faa-topbar::after {
  content: "";
  position: absolute;
  top: 0; left: 0;
  width: 40%; height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.75), transparent);
  transform: translateX(-140%);
  animation: faaShimmer 1.5s ease 0.55s 1;
}

.faa-close {
  position: absolute;
  top: 14px; right: 14px;
  width: 30px; height: 30px;
  display: inline-flex; align-items: center; justify-content: center;
  border: none; border-radius: 9px;
  background: rgba(16, 24, 64, 0.04);
  color: var(--t3, #64748B);
  font-size: 19px; line-height: 1; cursor: pointer;
  transition: background 0.14s ease, color 0.14s ease;
}
.faa-close:hover { background: rgba(16, 24, 64, 0.09); color: var(--t1, #1E2A4A); }

/* Иконка-искра в градиентном круге + мягкое свечение + лёгкий пульс */
.faa-icon {
  width: 60px; height: 60px;
  margin: 4px 0 16px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 18px;
  color: #fff;
  background: linear-gradient(135deg, #7F77DD 0%, #1D9E75 100%);
  box-shadow: 0 10px 24px rgba(127, 119, 221, 0.34), 0 4px 10px rgba(29, 158, 117, 0.22);
  animation: faaPulse 2.6s ease-in-out 1s infinite;
}
.faa-icon svg { width: 30px; height: 30px; }

.faa-eyebrow {
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--p, #7C6FF7);
  margin-bottom: 8px;
}
.faa-title {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
  line-height: 1.22;
  letter-spacing: -0.015em;
  color: var(--t1, #1E2A4A);
}
.faa-intro {
  margin: 0 0 18px;
  font-size: 13.5px;
  line-height: 1.5;
  color: var(--t2, #334155);
}

.faa-list { list-style: none; margin: 0 0 18px; padding: 0; display: flex; flex-direction: column; gap: 14px; }
.faa-item {
  display: flex; gap: 12px; align-items: flex-start;
  opacity: 0;
  animation: faaItemIn 0.5s var(--ease-standard, cubic-bezier(0.34, 1.2, 0.64, 1)) var(--d, 0ms) both;
}
.faa-bullet {
  flex-shrink: 0;
  width: 24px; height: 24px; margin-top: 1px;
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: 50%;
  color: #fff;
  background: linear-gradient(135deg, #7F77DD, #1D9E75);
  box-shadow: 0 2px 6px rgba(29, 158, 117, 0.28);
}
.faa-bullet svg { width: 13px; height: 13px; }
.faa-item-body { display: flex; flex-direction: column; gap: 2px; }
.faa-item-title { font-size: 13.5px; font-weight: 600; color: var(--t1, #1E2A4A); }
.faa-item-text { font-size: 12.5px; line-height: 1.45; color: var(--t3, #64748B); }

.faa-foot {
  margin: 0 0 18px;
  font-size: 12.5px;
  font-style: italic;
  color: var(--t3, #64748B);
}

.faa-cta {
  width: 100%;
  padding: 12px 18px;
  border: none; border-radius: 12px;
  font-size: 14px; font-weight: 600; color: #fff; cursor: pointer;
  background: linear-gradient(135deg, #7F77DD 0%, #6C5CE7 55%, #1D9E75 130%);
  box-shadow: 0 8px 20px rgba(108, 92, 231, 0.32);
  transition: transform 0.15s var(--ease-standard, ease), box-shadow 0.15s ease, filter 0.15s ease;
}
.faa-cta:hover { transform: translateY(-1px); box-shadow: 0 12px 26px rgba(108, 92, 231, 0.4); filter: brightness(1.03); }
.faa-cta:active { transform: translateY(0); }

/* ── Анимации входа ── */
.faa-fade-enter-active, .faa-fade-leave-active { transition: opacity 0.28s ease; }
.faa-fade-enter-from, .faa-fade-leave-to { opacity: 0; }

.faa-pop-enter-active { transition: transform 0.46s cubic-bezier(0.34, 1.4, 0.5, 1), opacity 0.32s ease; }
.faa-pop-leave-active { transition: transform 0.2s ease, opacity 0.2s ease; }
.faa-pop-enter-from { transform: translateY(18px) scale(0.94); opacity: 0; }
.faa-pop-leave-to { transform: translateY(8px) scale(0.98); opacity: 0; }

@keyframes faaShimmer { to { transform: translateX(360%); } }
@keyframes faaPulse {
  0%, 100% { box-shadow: 0 10px 24px rgba(127, 119, 221, 0.34), 0 4px 10px rgba(29, 158, 117, 0.22); }
  50%      { box-shadow: 0 12px 30px rgba(127, 119, 221, 0.48), 0 6px 16px rgba(29, 158, 117, 0.32); }
}
@keyframes faaItemIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

@media (max-width: 560px) {
  .faa-card { padding: 24px 20px 22px; border-radius: 16px; }
  .faa-title { font-size: 19px; }
}
</style>
