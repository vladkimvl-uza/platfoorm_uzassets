<script setup lang="ts">
/**
 * TWA universal moderation review screen (Phase C, Session 4).
 *
 * Generic enough for KPI/BP/financials/governance — the procurement module
 * has a dedicated TwaProcurementReview with risk indicators.
 *
 * Interaction:
 *   • MainButton  → "Утвердить" (becomes "Подтвердить — Утвердить" after tap-1)
 *   • SecondaryButton (or footer button) → "На доработку"
 *   • BackButton  → back to /twa/tasks
 *   • Haptics on every action (selectionChanged / notificationOccurred)
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  moderationApi,
  moduleLabel,
  statusLabel,
  statusTone,
  type ModSubmission,
} from "@/api/moderation";
import { useTelegramWebApp } from "@/composables/useTelegramWebApp";

const route  = useRoute();
const router = useRouter();
const tg     = useTelegramWebApp();

const submissionId = computed(() => String(route.params.id || ""));

const sub = ref<ModSubmission | null>(null);
const loading = ref(true);
const error = ref<string | null>(null);
const busy = ref(false);
const pendingDecision = ref<"approve" | "reject" | null>(null);

const isResolved = computed(() =>
  sub.value && ["approved", "rejected", "applied", "withdrawn"].includes(sub.value.status),
);

const toneClasses = {
  info:    "bg-tg-secondary-bg text-tg-text",
  success: "bg-uza-green/10 text-uza-green",
  warning: "bg-uza-amber/15 text-uza-amber",
  danger:  "bg-uza-red/10 text-uza-red",
} as const;

async function load() {
  loading.value = true;
  error.value = null;
  try {
    sub.value = await moderationApi.get(submissionId.value);
  } catch (e: any) {
    if (e?.response?.status === 403) {
      error.value = "У вас нет доступа к этой заявке.";
    } else if (e?.response?.status === 404) {
      error.value = "Заявка не найдена или уже удалена.";
    } else {
      error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить заявку";
    }
  } finally {
    loading.value = false;
  }
}

async function decide(decision: "approve" | "reject") {
  if (!sub.value || busy.value || isResolved.value) return;
  pendingDecision.value = decision;
  busy.value = true;
  tg.mainButton?.disable();
  try {
    const updated = decision === "approve"
      ? await moderationApi.approve(sub.value.id)
      : await moderationApi.reject(sub.value.id);
    sub.value = updated;
    tg.haptics?.notificationOccurred(decision === "approve" ? "success" : "warning");
    // Brief delay so user sees the new status, then back to list
    setTimeout(() => router.replace("/twa/tasks"), 700);
  } catch (e: any) {
    tg.haptics?.notificationOccurred("error");
    error.value = e?.response?.data?.detail || e?.message || "Не удалось выполнить действие";
  } finally {
    busy.value = false;
    pendingDecision.value = null;
    tg.mainButton?.enable();
  }
}

function onBack() {
  router.push("/twa/tasks");
}

function fmtValue(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try { return JSON.stringify(v, null, 2); } catch { return String(v); }
}

// ── Telegram WebApp button wiring ──────────────────────────────────────

function onMainClick() { decide("approve"); }

function refreshMainButton() {
  if (!tg.mainButton) return;
  if (!sub.value || isResolved.value) {
    tg.mainButton.hide();
    return;
  }
  tg.mainButton.setParams({
    text: busy.value ? "Подождите…" : "✓ Утвердить",
    color: "#1D9E75",
    text_color: "#FFFFFF",
    is_active: !busy.value,
    is_visible: true,
  });
}

watch([sub, busy, isResolved], refreshMainButton);

onMounted(() => {
  tg.setHeaderColor("#1E2A4A");
  tg.backButton?.show();
  tg.backButton?.onClick(onBack);
  tg.mainButton?.onClick(onMainClick);
  load();
});

onBeforeUnmount(() => {
  tg.backButton?.offClick(onBack);
  tg.backButton?.hide();
  tg.mainButton?.offClick(onMainClick);
  tg.mainButton?.hide();
});
</script>

<template>
  <main class="flex flex-col gap-4 p-4 min-h-screen pb-32">
    <div v-if="loading" class="text-center text-sm text-tg-hint py-10">Загрузка заявки…</div>

    <div v-else-if="error" class="text-sm text-uza-red bg-uza-red/10 rounded-card p-4">
      {{ error }}
    </div>

    <template v-else-if="sub">
      <!-- Module + status header -->
      <header class="flex items-center justify-between gap-3">
        <div>
          <div class="text-[10px] uppercase tracking-wider text-tg-hint font-medium">
            {{ moduleLabel(sub.target_module) }} · {{ sub.target_action }}
          </div>
          <h1 class="text-base font-medium leading-tight mt-0.5">
            {{ sub.target_entity_label || sub.field_path || "Заявка" }}
          </h1>
        </div>
        <span
          class="text-[10px] uppercase tracking-wider font-medium px-2 py-1 rounded-full whitespace-nowrap"
          :class="toneClasses[statusTone(sub.status)]"
        >{{ statusLabel(sub.status) }}</span>
      </header>

      <!-- Proposer info -->
      <div v-if="sub.proposer_name || sub.proposer_email" class="rounded-card bg-tg-secondary-bg p-3 text-[12px]">
        <div class="text-tg-hint text-[10px] uppercase tracking-wider mb-1">Заявитель</div>
        <div class="font-medium">{{ sub.proposer_name || sub.proposer_email }}</div>
        <div v-if="sub.proposer_name && sub.proposer_email" class="text-tg-hint">{{ sub.proposer_email }}</div>
      </div>

      <!-- Reason / note -->
      <div v-if="sub.reason" class="rounded-card bg-tg-secondary-bg p-3 text-[12px]">
        <div class="text-tg-hint text-[10px] uppercase tracking-wider mb-1">Обоснование</div>
        <div class="italic leading-snug">{{ sub.reason }}</div>
      </div>

      <!-- Value diff: current → proposed -->
      <div v-if="sub.current_value != null || sub.proposed_value != null"
           class="rounded-card bg-tg-secondary-bg p-3 text-[12px] flex flex-col gap-2">
        <div class="text-tg-hint text-[10px] uppercase tracking-wider">Изменение</div>
        <div v-if="sub.field_path" class="font-mono text-[11px] text-tg-hint">{{ sub.field_path }}</div>
        <div class="flex flex-col gap-1">
          <div class="text-[10px] text-tg-hint">было</div>
          <pre class="bg-uza-red/8 text-uza-red rounded px-2 py-1.5 whitespace-pre-wrap break-words font-mono text-[11px] leading-snug"
            >{{ fmtValue(sub.current_value) }}</pre>
        </div>
        <div class="flex flex-col gap-1">
          <div class="text-[10px] text-tg-hint">станет</div>
          <pre class="bg-uza-green/8 text-uza-green rounded px-2 py-1.5 whitespace-pre-wrap break-words font-mono text-[11px] leading-snug"
            >{{ fmtValue(sub.proposed_value) }}</pre>
        </div>
      </div>

      <!-- Apply error if any -->
      <div v-if="sub.apply_status === 'failed' || sub.apply_error"
           class="rounded-card bg-uza-red/10 text-uza-red p-3 text-[12px]">
        <div class="text-[10px] uppercase tracking-wider font-medium mb-1">Ошибка применения</div>
        <div class="font-mono text-[11px]">{{ sub.apply_error || "неизвестная ошибка" }}</div>
      </div>

      <!-- Reject button (Main = approve; secondary = reject) -->
      <div v-if="!isResolved" class="flex flex-col gap-2 mt-2">
        <button
          @click="decide('reject')"
          :disabled="busy"
          class="w-full rounded-card border border-uza-red/40 text-uza-red bg-uza-red/5 py-3 text-sm font-medium disabled:opacity-50 transition active:scale-[0.99]"
        >
          {{ busy && pendingDecision === "reject" ? "Отклонение…" : "✗ На доработку" }}
        </button>
        <p class="text-[10px] text-tg-hint text-center">
          Кнопка <b>«✓ Утвердить»</b> внизу экрана — в синем нижнем баре Telegram.
        </p>
      </div>

      <div v-else class="rounded-card bg-tg-secondary-bg p-4 text-center text-sm">
        Решение зафиксировано: <b>{{ statusLabel(sub.status) }}</b>.<br>
        <span class="text-[11px] text-tg-hint">Возврат в очередь через секунду…</span>
      </div>
    </template>
  </main>
</template>
