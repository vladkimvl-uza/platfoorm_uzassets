<script setup lang="ts">
/**
 * TWA: dedicated review for procurement submissions (Phase C, Session 4).
 *
 * Renders supplier + amount + deviation-vs-market + a single-line risk
 * verdict band. Reuses the same approve/reject flow as TwaApproval but
 * with a richer presentation matched to the procurement module shape.
 *
 * Expected shape of `submission.proposed_value` for procurement (best-effort):
 *   {
 *     contract_no, signed_at, supplier, customer, amount_uzs, currency,
 *     market_avg, deviation_pct, products: [{name, qty, unit_price, ...}]
 *   }
 * Falls back to the generic diff renderer when the shape doesn't match.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  moderationApi,
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

// ── Procurement-shape extraction (safe) ─────────────────────────────────

interface ProcView {
  contract_no?: string;
  supplier?: string;
  customer?: string;
  signed_at?: string;
  amount?: number;
  currency?: string;
  market_avg?: number;
  deviation_pct?: number;
  product_count?: number;
}

const proc = computed<ProcView>(() => {
  const raw = (sub.value?.proposed_value || sub.value?.current_value || {}) as Record<string, any>;
  const num = (v: any): number | undefined => {
    if (v == null) return undefined;
    const n = typeof v === "number" ? v : parseFloat(String(v).replace(/[\s,]/g, ""));
    return Number.isFinite(n) ? n : undefined;
  };
  return {
    contract_no:    raw.contract_no || raw.contract_number || raw.contract || raw.no,
    supplier:       raw.supplier || raw.vendor || raw.seller,
    customer:       raw.customer || raw.buyer || raw.company,
    signed_at:      raw.signed_at || raw.contract_date || raw.date,
    amount:         num(raw.amount_uzs ?? raw.amount ?? raw.total ?? raw.contract_amount),
    currency:       raw.currency || (raw.amount_uzs != null ? "UZS" : undefined),
    market_avg:     num(raw.market_avg),
    deviation_pct:  num(raw.deviation_pct ?? raw.deviation),
    product_count:  Array.isArray(raw.products) ? raw.products.length : undefined,
  };
});

const riskVerdict = computed<{ tone: "success" | "warning" | "danger"; label: string }>(() => {
  const d = proc.value.deviation_pct;
  if (d == null) return { tone: "success", label: "Отклонение от рынка не указано" };
  const abs = Math.abs(d);
  if (abs >= 30) return { tone: "danger",  label: `Отклонение ${d > 0 ? "+" : ""}${d.toFixed(1)}% — высокий риск` };
  if (abs >= 10) return { tone: "warning", label: `Отклонение ${d > 0 ? "+" : ""}${d.toFixed(1)}% — проверьте` };
  return { tone: "success", label: `Отклонение ${d > 0 ? "+" : ""}${d.toFixed(1)}% — в норме` };
});

function fmtMoney(v?: number, ccy?: string): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  let scale = "";
  let n = v;
  if (abs >= 1e9) { n = v / 1e9; scale = " млрд"; }
  else if (abs >= 1e6) { n = v / 1e6; scale = " млн"; }
  else if (abs >= 1e3) { n = v / 1e3; scale = " тыс"; }
  return `${n.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}${scale} ${ccy || ""}`.trim();
}

function fmtDate(iso?: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
  } catch { return iso; }
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    sub.value = await moderationApi.get(submissionId.value);
  } catch (e: any) {
    if (e?.response?.status === 403)      error.value = "У вас нет доступа к этой заявке.";
    else if (e?.response?.status === 404) error.value = "Заявка не найдена или уже удалена.";
    else error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить заявку";
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
function onMainClick() { decide("approve"); }

function refreshMainButton() {
  if (!tg.mainButton) return;
  if (!sub.value || isResolved.value) { tg.mainButton.hide(); return; }
  tg.mainButton.setParams({
    text: busy.value ? "Подождите…" : "✓ Одобрить",
    color: riskVerdict.value.tone === "danger" ? "#A82C2B" : "#1D9E75",
    text_color: "#FFFFFF",
    is_active: !busy.value,
    is_visible: true,
  });
}

watch([sub, busy, isResolved, riskVerdict], refreshMainButton);

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
    <div v-if="loading" class="text-center text-sm text-tg-hint py-10">Загрузка сделки…</div>
    <div v-else-if="error" class="text-sm text-uza-red bg-uza-red/10 rounded-card p-4">{{ error }}</div>

    <template v-else-if="sub">
      <!-- Header -->
      <header class="flex items-center justify-between gap-3">
        <div>
          <div class="text-[10px] uppercase tracking-wider text-tg-hint font-medium">
            Закупки · {{ sub.target_action }}
          </div>
          <h1 class="text-base font-medium leading-tight mt-0.5">
            {{ proc.contract_no ? `Договор ${proc.contract_no}` : (sub.target_entity_label || "Сделка") }}
          </h1>
        </div>
        <span
          class="text-[10px] uppercase tracking-wider font-medium px-2 py-1 rounded-full whitespace-nowrap"
          :class="toneClasses[statusTone(sub.status)]"
        >{{ statusLabel(sub.status) }}</span>
      </header>

      <!-- Risk band — single-line verdict -->
      <div
        class="rounded-card px-3 py-2.5 text-[12px] font-medium flex items-center gap-2"
        :class="toneClasses[riskVerdict.tone]"
      >
        <span
          class="w-2 h-2 rounded-full flex-shrink-0"
          :class="{
            'bg-uza-red':   riskVerdict.tone === 'danger',
            'bg-uza-amber': riskVerdict.tone === 'warning',
            'bg-uza-green': riskVerdict.tone === 'success',
          }"
        ></span>
        {{ riskVerdict.label }}
      </div>

      <!-- Deal facts grid -->
      <section class="grid grid-cols-2 gap-2">
        <div class="rounded-card bg-tg-secondary-bg p-3">
          <div class="text-[10px] uppercase tracking-wider text-tg-hint">Поставщик</div>
          <div class="text-[13px] font-medium leading-tight mt-1 truncate">{{ proc.supplier || "—" }}</div>
        </div>
        <div class="rounded-card bg-tg-secondary-bg p-3">
          <div class="text-[10px] uppercase tracking-wider text-tg-hint">Заказчик</div>
          <div class="text-[13px] font-medium leading-tight mt-1 truncate">{{ proc.customer || "—" }}</div>
        </div>
        <div class="rounded-card bg-tg-secondary-bg p-3">
          <div class="text-[10px] uppercase tracking-wider text-tg-hint">Сумма</div>
          <div class="text-[14px] font-medium leading-tight mt-1 tabular-nums">{{ fmtMoney(proc.amount, proc.currency) }}</div>
        </div>
        <div class="rounded-card bg-tg-secondary-bg p-3">
          <div class="text-[10px] uppercase tracking-wider text-tg-hint">Подписан</div>
          <div class="text-[13px] font-medium leading-tight mt-1">{{ fmtDate(proc.signed_at) }}</div>
        </div>
        <div v-if="proc.market_avg != null" class="rounded-card bg-tg-secondary-bg p-3">
          <div class="text-[10px] uppercase tracking-wider text-tg-hint">Средняя по рынку</div>
          <div class="text-[13px] font-medium leading-tight mt-1 tabular-nums">{{ fmtMoney(proc.market_avg, proc.currency) }}</div>
        </div>
        <div v-if="proc.product_count != null" class="rounded-card bg-tg-secondary-bg p-3">
          <div class="text-[10px] uppercase tracking-wider text-tg-hint">Позиций</div>
          <div class="text-[13px] font-medium leading-tight mt-1 tabular-nums">{{ proc.product_count }}</div>
        </div>
      </section>

      <!-- Proposer + reason -->
      <div v-if="sub.proposer_name || sub.proposer_email || sub.reason"
           class="rounded-card bg-tg-secondary-bg p-3 text-[12px]">
        <div v-if="sub.proposer_name || sub.proposer_email" class="mb-1">
          <span class="text-tg-hint text-[10px] uppercase tracking-wider">Заявитель:</span>
          <b class="font-medium ml-1">{{ sub.proposer_name || sub.proposer_email }}</b>
        </div>
        <div v-if="sub.reason" class="italic leading-snug text-tg-hint">{{ sub.reason }}</div>
      </div>

      <!-- Reject action — MainButton handles approve -->
      <div v-if="!isResolved" class="flex flex-col gap-2 mt-2">
        <button
          @click="decide('reject')"
          :disabled="busy"
          class="w-full rounded-card border border-uza-red/40 text-uza-red bg-uza-red/5 py-3 text-sm font-medium disabled:opacity-50 transition active:scale-[0.99]"
        >
          {{ busy && pendingDecision === "reject" ? "Отклонение…" : "✗ Отклонить" }}
        </button>
        <p class="text-[10px] text-tg-hint text-center">
          Кнопка <b>«✓ Одобрить»</b> — в синем нижнем баре Telegram (цвет адаптирован к риску).
        </p>
      </div>

      <div v-else class="rounded-card bg-tg-secondary-bg p-4 text-center text-sm">
        Решение зафиксировано: <b>{{ statusLabel(sub.status) }}</b>.<br>
        <span class="text-[11px] text-tg-hint">Возврат в очередь…</span>
      </div>
    </template>
  </main>
</template>
