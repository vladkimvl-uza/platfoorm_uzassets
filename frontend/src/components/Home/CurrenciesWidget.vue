<script setup lang="ts">
/**
 * CurrenciesWidget — текущий курс ЦБ РУз для топ-5 резервных валют
 * (USD, EUR, CNY, JPY, GBP) через публичный API cbu.uz.
 *
 * Источник: https://cbu.uz/oz/arkhiv-kursov-valyut/json/ — без API-ключа,
 * обновляется ЦБ РУз ежедневно.
 *
 * Кеш 30 мин в localStorage.
 */
import { ref, onMounted } from "vue";
import { useI18n } from "@/composables/useI18n";

const { t } = useI18n();

interface Rate {
  ccy: "USD" | "EUR" | "CNY" | "JPY" | "GBP" | "RUB";
  nameRu: string;
  cc: string;            // ISO-2 страны для флага
  rate: number;          // UZS per nominal unit
  nominal: number;
  diff: number;          // delta vs prev day (positive = UZS weaker)
  date: string;          // YYYY-MM-DD
}
function flagUrl(cc: string): string { return `https://flagcdn.com/w40/${cc}.png`; }
interface Snapshot {
  rates: Rate[];
  fetchedAt: number;
}

const data = ref<Snapshot | null>(null);
const loading = ref(true);
const errorMsg = ref<string | null>(null);

const CACHE_KEY = "uza-cbu-rates-v3"; // v3: cc (ISO для флага) вместо emoji
const CACHE_TTL = 30 * 60 * 1000; // 30 min

const TARGET: { ccy: Rate["ccy"]; nameRu: string; cc: string }[] = [
  { ccy: "USD", nameRu: "Доллар США",      cc: "us" },
  { ccy: "EUR", nameRu: "Евро",            cc: "eu" },
  { ccy: "CNY", nameRu: "Китайский юань",  cc: "cn" },
  { ccy: "JPY", nameRu: "Японская иена",   cc: "jp" },
  { ccy: "GBP", nameRu: "Фунт стерлингов", cc: "gb" },
  { ccy: "RUB", nameRu: "Российский рубль", cc: "ru" },
];

function fmtRate(r: number): string {
  // 12 750.42 → разделяем тысячи thin-space, 2 знака после запятой
  return r.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtDiff(d: number): string {
  if (!Number.isFinite(d)) return "—";
  if (d === 0) return "0";
  const sign = d > 0 ? "+" : "−";
  return `${sign}${Math.abs(d).toFixed(2)}`;
}

async function loadRates() {
  // cache first
  try {
    const cached = localStorage.getItem(CACHE_KEY);
    if (cached) {
      const parsed = JSON.parse(cached) as Snapshot;
      if (Date.now() - parsed.fetchedAt < CACHE_TTL) {
        data.value = parsed;
        loading.value = false;
        return;
      }
    }
  } catch { /* ignore */ }

  try {
    const r = await fetch("https://cbu.uz/oz/arkhiv-kursov-valyut/json/", { mode: "cors" });
    if (!r.ok) throw new Error("CBU API " + r.status);
    const list = await r.json() as Array<{
      Ccy: string; CcyNm_RU?: string; Nominal: string; Rate: string; Diff: string; Date: string;
    }>;
    const byCcy = new Map(list.map((x) => [x.Ccy, x]));

    const rates: Rate[] = [];
    for (const t of TARGET) {
      const item = byCcy.get(t.ccy);
      if (!item) continue;
      rates.push({
        ccy: t.ccy,
        nameRu: t.nameRu,
        cc: t.cc,
        rate: parseFloat(item.Rate) || 0,
        nominal: parseInt(item.Nominal, 10) || 1,
        diff: parseFloat(item.Diff) || 0,
        date: item.Date || "",
      });
    }
    const snap: Snapshot = { rates, fetchedAt: Date.now() };
    data.value = snap;
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(snap)); } catch { /* ignore */ }
  } catch (e: any) {
    errorMsg.value = e?.message || t("Не удалось получить курсы");
  } finally {
    loading.value = false;
  }
}

onMounted(loadRates);
</script>

<template>
  <div class="cw-root">
    <div class="cw-head">
      <span class="cw-h-l">{{ t("ЦБ РУз") }}</span>
      <span v-if="data?.rates[0]?.date" class="cw-h-d">{{ data.rates[0].date }}</span>
    </div>
    <div v-if="loading" class="cw-loading">
      <div class="cw-spinner"></div>
    </div>
    <div v-else-if="errorMsg" class="cw-err" :title="errorMsg">—</div>
    <div v-else-if="data" class="cw-list">
      <div
        v-for="r in data.rates"
        :key="r.ccy"
        class="cw-row"
        :title="t('{name} (1 {ccy}{nom}) на {date}', { name: t(r.nameRu), ccy: r.ccy, nom: r.nominal !== 1 ? ' / ' + r.nominal : '', date: r.date })"
      >
        <img class="cw-flag" :src="flagUrl(r.cc || 'un')" :alt="(r.cc || '').toUpperCase()" width="18" height="13" loading="lazy" />
        <span class="cw-ccy">{{ r.ccy }}</span>
        <span class="cw-rate">{{ fmtRate(r.rate) }}</span>
        <span
          class="cw-diff"
          :class="{ 'cw-diff-up': r.diff > 0, 'cw-diff-dn': r.diff < 0 }"
        >{{ fmtDiff(r.diff) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cw-root {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  color: #fff;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  min-width: 360px;
  min-height: 72px;
  box-sizing: border-box;
  animation: cwIn 0.55s var(--ease-standard) 0.44s both;
}
@keyframes cwIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.cw-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.cw-h-l {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.50);
}
.cw-h-d {
  font-size: 9.5px;
  color: rgba(255, 255, 255, 0.35);
  font-variant-numeric: tabular-nums;
}

.cw-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.cw-row {
  display: grid;
  grid-template-columns: 18px 32px 1fr 56px;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
  font-size: 11.5px;
  font-variant-numeric: tabular-nums;
}
.cw-flag {
  width: 18px; height: 13px;
  border-radius: 2px; object-fit: cover;
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.18);
}
.cw-ccy {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: rgba(255, 255, 255, 0.55);
}
.cw-rate {
  font-size: 12px;
  font-weight: 600;
  color: #fff;
  text-align: right;
  letter-spacing: -0.01em;
}
.cw-diff {
  font-size: 10px;
  font-weight: 600;
  text-align: right;
  color: rgba(255, 255, 255, 0.40);
}
.cw-diff-up { color: #5DBFA1; }
.cw-diff-dn { color: #F0795A; }

.cw-loading, .cw-err {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 14px 0;
}
.cw-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.18);
  border-top-color: rgba(255, 255, 255, 0.65);
  border-radius: 50%;
  animation: cwSpin 0.7s linear infinite;
}
@keyframes cwSpin { to { transform: rotate(360deg); } }
.cw-err { color: rgba(255, 255, 255, 0.35); font-size: 12px; }
</style>
