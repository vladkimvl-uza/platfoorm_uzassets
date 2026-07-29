<script setup lang="ts">
/**
 * WeatherWidget — текущая погода в Ташкенте через wttr.in (free, no API key).
 * Fetches /Tashkent?format=j1 (full JSON) on mount, caches in localStorage 30 min.
 */
import { ref, onMounted } from "vue";
import { useI18n } from "@/composables/useI18n";
import { i18nKey } from "@/locale/keys";


// aqiLabel хранится в localStorage-кеше по-русски; t() применяется в точке
// отображения, чтобы смена языка не «замораживалась» кешем.
const { t } = useI18n();

interface Weather {
  temp: number;          // °C
  feelsLike: number;
  desc: string;
  icon: string;          // emoji
  humidity: number;
  windKph: number;
  aqi: number | null;    // European AQI (0-100+)
  aqiLabel: string;      // Хорошо / Средне / Плохо ...
  aqiColor: string;      // CSS color for the badge
  // Tomorrow forecast — from wttr.in weather[1]
  tomorrow: {
    minTemp: number;
    maxTemp: number;
    desc: string;
    icon: string;
  } | null;
  fetchedAt: number;
}

const data = ref<Weather | null>(null);
const loading = ref(true);
const errorMsg = ref<string | null>(null);

const CACHE_KEY = "uza-weather-tashkent-v3"; // bumped: v2→v3 added tomorrow forecast
const CACHE_TTL = 30 * 60 * 1000; // 30 min

// European AQI scale → label + color
function aqiInfo(v: number | null): { label: string; color: string } {
  if (v == null || Number.isNaN(v)) return { label: "—", color: "#94A3B8" };
  if (v <= 20)  return { label: i18nKey("Хорошо"),       color: "#1D9E75" };
  if (v <= 40)  return { label: i18nKey("Удовл."),       color: "#84CC16" };
  if (v <= 60)  return { label: i18nKey("Умеренно"),     color: "#EAB308" };
  if (v <= 80)  return { label: i18nKey("Плохо"),        color: "#EF9F27" };
  if (v <= 100) return { label: i18nKey("Очень плохо"),  color: "#E24B4A" };
  return { label: i18nKey("Опасно"), color: "#991B1B" };
}

// wttr.in weather code/desc → ИМЯ иконки (без эмодзи — рендерим SVG через wxSvg).
// i18n-exempt-start: multilingual provider descriptions are classification aliases, not UI copy.
function weatherIcon(code: string, desc: string): string {
  const c = parseInt(code, 10);
  // Daytime detection — basic, just by hour
  const hour = new Date().getHours();
  const day = hour >= 6 && hour < 19;
  const d = (desc || "").toLowerCase();
  if (d.includes("thunder") || d.includes("storm") || d.includes("гроза")) return "storm";
  if (d.includes("snow") || d.includes("снег")) return "snow";
  if (d.includes("rain") || d.includes("дожд")) return "rain";
  if (d.includes("drizzle") || d.includes("мор")) return "drizzle";
  if (d.includes("fog") || d.includes("mist") || d.includes("туман")) return "fog";
  if (d.includes("cloud") || d.includes("обл")) return day ? "partly" : "cloud";
  if (d.includes("clear") || d.includes("ясн") || d.includes("sun") || d.includes("солн")) {
    return day ? "sun" : "moon";
  }
  // fallback by code groups
  if (c >= 200 && c < 300) return "storm";
  if (c >= 300 && c < 600) return "rain";
  if (c >= 600 && c < 700) return "snow";
  if (c >= 700 && c < 800) return "fog";
  if (c === 800) return day ? "sun" : "moon";
  if (c > 800) return "cloud";
  return day ? "sun" : "moon";
}
// i18n-exempt-end

// Имя погодной иконки → inline SVG (currentColor, размер 1em от font-size .ww-icon).
const _WX: Record<string, string> = {
  sun: '<circle cx="12" cy="12" r="4.3"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4l1.4-1.4M18 6l1.4-1.4"/>',
  moon: '<path d="M20 14.2A8 8 0 1 1 9.8 4 6.4 6.4 0 0 0 20 14.2z"/>',
  cloud: '<path d="M7 18a4 4 0 0 1-.5-7.97A5.5 5.5 0 0 1 17.4 9.3 3.8 3.8 0 0 1 17 18z"/>',
  partly: '<circle cx="8" cy="8" r="3"/><path d="M8 2.7v1.4M3.2 8h1.4M4.5 4.5l1 1"/><path d="M9.5 18.5a3.4 3.4 0 0 1-.4-6.78A4.6 4.6 0 0 1 18 12.8a3.4 3.4 0 0 1-.4 5.7z"/>',
  rain: '<path d="M7 14.5a3.6 3.6 0 0 1-.45-7.18A4.9 4.9 0 0 1 16.6 8.6 3.4 3.4 0 0 1 16.3 14.5z"/><path d="M8.5 17l-1 2.5M12 17l-1 2.5M15.5 17l-1 2.5"/>',
  drizzle: '<path d="M7 14.5a3.6 3.6 0 0 1-.45-7.18A4.9 4.9 0 0 1 16.6 8.6 3.4 3.4 0 0 1 16.3 14.5z"/><path d="M9 18h.01M12.5 18.5h.01M15.5 18h.01"/>',
  snow: '<path d="M7 14a3.6 3.6 0 0 1-.45-7.18A4.9 4.9 0 0 1 16.6 8.1 3.4 3.4 0 0 1 16.3 14z"/><path d="M8.5 17.5h.01M8.5 20h.01M12 18.5h.01M12 21h.01M15.5 17.5h.01M15.5 20h.01"/>',
  storm: '<path d="M7 13.5a3.6 3.6 0 0 1-.45-7.18A4.9 4.9 0 0 1 16.6 7.6 3.4 3.4 0 0 1 16.3 13.5z"/><path d="M12.5 13l-2.5 4h3l-2.5 4.5"/>',
  fog: '<path d="M4 8.5h13M5.5 5h12M4 12h16M6 15.5h12M5 19h10"/>',
};
function wxSvg(name: string): string {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:1em;height:1em;display:block">${_WX[name] || _WX.sun}</svg>`;
}

async function loadWeather() {
  // try cache first
  try {
    const cached = localStorage.getItem(CACHE_KEY);
    if (cached) {
      const parsed = JSON.parse(cached) as Weather;
      if (Date.now() - parsed.fetchedAt < CACHE_TTL) {
        data.value = parsed;
        loading.value = false;
        return;
      }
    }
  } catch { /* ignore */ }

  try {
    // Parallel: wttr.in (weather) + open-meteo (AQI). Both free, no API key.
    const [wResp, aqiResp] = await Promise.allSettled([
      fetch("https://wttr.in/Tashkent?format=j1", { mode: "cors" }),
      fetch(
        "https://air-quality-api.open-meteo.com/v1/air-quality" +
          "?latitude=41.3111&longitude=69.2406&current=european_aqi",
        { mode: "cors" },
      ),
    ]);

    if (wResp.status !== "fulfilled" || !wResp.value.ok) {
      throw new Error("Weather API " + (wResp.status === "fulfilled" ? wResp.value.status : wResp.reason));
    }
    const j = await wResp.value.json();
    const c = j.current_condition?.[0];
    if (!c) throw new Error("Empty weather response");
    const desc = c.lang_ru?.[0]?.value || c.weatherDesc?.[0]?.value || "—";

    // AQI is best-effort — if it fails the widget still shows weather
    let aqi: number | null = null;
    if (aqiResp.status === "fulfilled" && aqiResp.value.ok) {
      try {
        const aj = await aqiResp.value.json();
        const v = aj?.current?.european_aqi;
        if (typeof v === "number") aqi = Math.round(v);
      } catch { /* ignore */ }
    }
    const aqiMeta = aqiInfo(aqi);

    // Tomorrow forecast — weather[1] in wttr.in response
    let tomorrow: Weather["tomorrow"] = null;
    const tw = j.weather?.[1];
    if (tw) {
      // Pick the midday hourly entry (index 4 = 12:00 if hourly is 3-hour intervals,
      // wttr.in returns 8 entries per day at 0/3/6/9/12/15/18/21)
      const noon = (tw.hourly || [])[4] || (tw.hourly || [])[0];
      const tDesc = noon?.lang_ru?.[0]?.value || noon?.weatherDesc?.[0]?.value || "";
      tomorrow = {
        minTemp: parseFloat(tw.mintempC) || 0,
        maxTemp: parseFloat(tw.maxtempC) || 0,
        desc: tDesc,
        icon: weatherIcon(noon?.weatherCode || "800", tDesc),
      };
    }

    const w: Weather = {
      temp: parseFloat(c.temp_C),
      feelsLike: parseFloat(c.FeelsLikeC),
      desc,
      icon: weatherIcon(c.weatherCode || "800", desc),
      humidity: parseInt(c.humidity, 10) || 0,
      windKph: parseFloat(c.windspeedKmph) || 0,
      aqi,
      aqiLabel: aqiMeta.label,
      aqiColor: aqiMeta.color,
      tomorrow,
      fetchedAt: Date.now(),
    };
    data.value = w;
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(w)); } catch { /* ignore */ }
  } catch (e: any) {
    errorMsg.value = e?.message || t("Не удалось получить погоду");
  } finally {
    loading.value = false;
  }
}

onMounted(loadWeather);
</script>

<template>
  <div class="ww-root">
    <div v-if="loading" class="ww-loading">
      <div class="ww-spinner"></div>
    </div>
    <div v-else-if="errorMsg" class="ww-err" :title="errorMsg">
      <span>—</span>
    </div>
    <template v-else-if="data">
      <!-- Row 1: icon + main (temp/desc) + meta (3 compact rows) -->
      <div class="ww-top">
        <div class="ww-icon" v-html="wxSvg(data.icon)"></div>
        <div class="ww-main">
          <div class="ww-temp">{{ Math.round(data.temp) }}°<span>C</span></div>
          <div class="ww-desc">{{ t(data.desc) }}</div>
        </div>
        <div class="ww-meta">
          <div class="ww-meta-row" :title="t('Ощущается как {n}°', { n: Math.round(data.feelsLike) })">
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
              <circle cx="8" cy="11" r="2.5"/>
              <path d="M8 8.5V3a1.5 1.5 0 013 0v5.5" stroke-linecap="round"/>
            </svg>
            <span>{{ t("ощущ. {n}°", { n: Math.round(data.feelsLike) }) }}</span>
          </div>
          <div class="ww-meta-row">
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M8 2C6 5 4 7 4 9.5a4 4 0 008 0C12 7 10 5 8 2z" stroke-linejoin="round"/>
            </svg>
            <span>{{ data.humidity }}%</span>
          </div>
          <div class="ww-meta-row">
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M2 6h9a2 2 0 100-4M2 10h11a2 2 0 110 4M2 8h6"/>
            </svg>
            <span>{{ Math.round(data.windKph) }} {{ t("км/ч") }}</span>
          </div>
        </div>
      </div>

      <!-- Row 2: AQI + Tomorrow forecast -->
      <div class="ww-bottom">
        <div
          v-if="data.aqi != null"
          class="ww-aqi"
          :style="{ background: data.aqiColor + '22', color: data.aqiColor, borderColor: data.aqiColor + '55' }"
          :title="t('Индекс качества воздуха (European AQI): {v} — {label}', { v: data.aqi, label: t(data.aqiLabel) }) + '\n' + t('Источник: open-meteo.com (PM2.5 + PM10 + O₃ + NO₂ + SO₂)')"
        >
          <span class="ww-aqi-l">{{ t("ИКВ") }}</span>
          <span class="ww-aqi-v">{{ data.aqi }}</span>
          <span class="ww-aqi-q">{{ t(data.aqiLabel) }}</span>
        </div>
        <div
          v-if="data.tomorrow"
          class="ww-tom"
          :title="t('Завтра: {desc}, от {min}° до {max}°', { desc: data.tomorrow.desc, min: Math.round(data.tomorrow.minTemp), max: Math.round(data.tomorrow.maxTemp) })"
        >
          <span class="ww-tom-l">{{ t("Завтра") }}</span>
          <span class="ww-tom-icon" v-html="wxSvg(data.tomorrow.icon)"></span>
          <span class="ww-tom-temp">
            <span class="ww-tom-min">{{ Math.round(data.tomorrow.minTemp) }}°</span>
            <span class="ww-tom-sep">/</span>
            <span class="ww-tom-max">{{ Math.round(data.tomorrow.maxTemp) }}°</span>
          </span>
        </div>
        <div class="ww-city-inline">{{ t("Ташкент") }}</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ww-root {
  display: flex;
  flex-direction: column;
  gap: 10px;
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
  animation: wwIn 0.55s var(--ease-standard) 0.28s both;
}
.ww-top {
  display: flex;
  align-items: center;
  gap: 14px;
}
.ww-bottom {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
@keyframes wwIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.ww-icon {
  font-size: 36px;
  line-height: 1;
  flex-shrink: 0;
  color: #fff;
  display: inline-flex;
  filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.3));
}
.ww-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.ww-temp {
  font-size: 26px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
}
.ww-temp span {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.55);
  font-weight: 500;
  margin-left: 1px;
}
.ww-desc {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.65);
  text-transform: capitalize;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 110px;
}
.ww-meta {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding-left: 12px;
  border-left: 1px solid rgba(255, 255, 255, 0.10);
  margin-left: auto;
  flex-shrink: 0;
}
.ww-meta-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10.5px;
  color: rgba(255, 255, 255, 0.55);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.ww-aqi {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  border: 1px solid;
  border-radius: 8px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.ww-aqi-l {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.85;
}
.ww-aqi-v {
  font-size: 13px;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.ww-aqi-q {
  font-size: 10px;
  opacity: 0.85;
}

/* Tomorrow forecast pill */
.ww-tom {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.04);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.ww-tom-l {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.45);
}
.ww-tom-icon {
  font-size: 14px;
  line-height: 1;
  color: rgba(255, 255, 255, 0.85);
  display: inline-flex;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.3));
}
.ww-tom-temp {
  display: inline-flex;
  align-items: baseline;
  gap: 2px;
  font-size: 12px;
  font-weight: 600;
}
.ww-tom-min {
  color: rgba(255, 255, 255, 0.55);
}
.ww-tom-sep {
  color: rgba(255, 255, 255, 0.30);
  font-weight: 400;
}
.ww-tom-max {
  color: #fff;
}
.ww-city-inline {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.35);
  margin-left: auto;
}

.ww-loading, .ww-err {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 48px;
}
.ww-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.18);
  border-top-color: rgba(255, 255, 255, 0.65);
  border-radius: 50%;
  animation: wwSpin 0.7s linear infinite;
}
@keyframes wwSpin { to { transform: rotate(360deg); } }
.ww-err { color: rgba(255, 255, 255, 0.35); font-size: 18px; }
</style>
