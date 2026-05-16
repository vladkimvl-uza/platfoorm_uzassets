<script setup lang="ts">
/**
 * Per-type notification preferences at /notifications/settings.
 * For Pack 11.0 only in_app channel is wired; email/telegram are visible but disabled
 * with hint "будет в Pack 11.2".
 */
import { onMounted, ref } from "vue";
import {
  notificationsApi,
  type NotificationPreference, type NotificationType,
} from "@/api/notifications";

const types = ref<NotificationType[]>([]);
const categories = ref<string[]>([]);
const prefs = ref<Record<string, NotificationPreference>>({});
const loading = ref(false);
const saving = ref(false);
const error = ref<string | null>(null);
const okMsg = ref<string | null>(null);

async function loadAll() {
  loading.value = true;
  try {
    const tdata = await notificationsApi.types();
    types.value = tdata.types;
    categories.value = tdata.categories;
    const list = await notificationsApi.preferences();
    prefs.value = {};
    list.forEach((p) => { prefs.value[p.notification_type] = p; });
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  } finally { loading.value = false; }
}

onMounted(loadAll);

function getPref(code: string): NotificationPreference {
  if (!prefs.value[code]) {
    prefs.value[code] = {
      notification_type: code,
      channels: { in_app: true },
      is_muted: false,
      mute_until: null,
      digest_mode: "none",
    };
  }
  return prefs.value[code];
}

function toggleChannel(code: string, channel: string) {
  const p = getPref(code);
  p.channels = { ...p.channels, [channel]: !p.channels[channel] };
}

function toggleMute(code: string) {
  const p = getPref(code);
  p.is_muted = !p.is_muted;
}

async function saveAll() {
  saving.value = true;
  error.value = null;
  okMsg.value = null;
  try {
    const payload = Object.values(prefs.value).map((p) => ({
      notification_type: p.notification_type,
      channels: p.channels,
      is_muted: p.is_muted,
      mute_until: p.mute_until,
      digest_mode: p.digest_mode,
    }));
    await notificationsApi.updatePreferences(payload);
    okMsg.value = "Настройки сохранены";
    setTimeout(() => (okMsg.value = null), 2500);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  } finally { saving.value = false; }
}

async function sendTest() {
  await notificationsApi.sendTest();
  okMsg.value = "Тестовое уведомление отправлено — проверьте колокольчик";
  setTimeout(() => (okMsg.value = null), 3000);
}

function typesIn(category: string): NotificationType[] {
  return types.value.filter((t) => t.category === category);
}
</script>

<template>
  <div class="np-wrap">
    <div class="np-topbar">
      <div class="np-tb-l">
        <div class="np-eyebrow">
          <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><circle cx="8" cy="8" r="2"/><path d="M12.5 9.5l1 1M2.5 9.5l-1 1M9.5 12.5l1 1M9.5 2.5l1-1M6.5 12.5l-1 1M6.5 2.5l-1-1M12.5 6.5l1-1M2.5 6.5l-1-1"/></svg>
          Настройки · уведомления
        </div>
        <div class="np-title">Каналы и предпочтения</div>
        <div class="np-sub">Управление тем, какие уведомления вы получаете и где</div>
      </div>
      <div class="np-tb-r">
        <button class="np-btn np-btn-ghost" @click="sendTest">Отправить тест</button>
        <button class="np-btn np-btn-primary" :disabled="saving" @click="saveAll">{{ saving ? "Сохраняем..." : "Сохранить" }}</button>
      </div>
    </div>

    <div v-if="error" class="np-msg np-msg-err">{{ error }}</div>
    <div v-if="okMsg" class="np-msg np-msg-ok">{{ okMsg }}</div>

    <div class="np-body">
      <div v-for="cat in categories" :key="cat" class="np-card">
        <div class="np-card-hd">
          <span class="np-card-ttl">{{ cat }}</span>
          <span class="np-card-cnt">{{ typesIn(cat).length }} типов</span>
        </div>

        <div class="np-row np-row-head">
          <div class="np-row-l">Тип уведомления</div>
          <div class="np-row-prio">Приоритет</div>
          <div class="np-row-ch">In-app</div>
          <div class="np-row-ch np-row-soon">Email <span class="np-soon-pill">скоро</span></div>
          <div class="np-row-ch np-row-soon">Telegram <span class="np-soon-pill">скоро</span></div>
          <div class="np-row-mute">Mute</div>
        </div>

        <div v-for="t in typesIn(cat)" :key="t.code" class="np-row">
          <div class="np-row-l">
            <div class="np-type-label">{{ t.label }}</div>
            <div class="np-type-code">{{ t.code }}</div>
          </div>
          <div class="np-row-prio">
            <span class="np-prio-pill" :class="`prio-${t.priority}`">{{ t.priority }}</span>
          </div>
          <div class="np-row-ch">
            <label class="np-switch">
              <input type="checkbox"
                     :checked="getPref(t.code).channels.in_app !== false"
                     :disabled="getPref(t.code).is_muted"
                     @change="toggleChannel(t.code, 'in_app')"/>
              <span class="np-switch-tr"></span>
            </label>
          </div>
          <div class="np-row-ch np-row-soon">
            <label class="np-switch disabled">
              <input type="checkbox" disabled/>
              <span class="np-switch-tr"></span>
            </label>
          </div>
          <div class="np-row-ch np-row-soon">
            <label class="np-switch disabled">
              <input type="checkbox" disabled/>
              <span class="np-switch-tr"></span>
            </label>
          </div>
          <div class="np-row-mute">
            <button class="np-mute-btn"
                    :class="{ active: getPref(t.code).is_muted }"
                    @click="toggleMute(t.code)"
                    :title="getPref(t.code).is_muted ? 'Включить' : 'Mute'">
              <svg v-if="!getPref(t.code).is_muted" width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 6.5a3 3 0 0 0-6 0v3l-1.5 1.5h9L11 9.5v-3z"/><path d="M6 12.5a2 2 0 0 0 4 0"/></svg>
              <svg v-else width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 6.5a3 3 0 0 0-6 0v3l-1.5 1.5h9L11 9.5v-3z"/><path d="M2 2l12 12"/></svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.np-wrap { background: #F4F3F9; min-height: 100%; font-family: var(--font, system-ui); }

.np-topbar {
  background: linear-gradient(95deg, #1E2A4A 0%, #2D3760 60%, #4B477E 100%);
  padding: 14px 22px;
  display: flex; align-items: center; justify-content: space-between;
}
.np-eyebrow { font-size: 10px; color: rgba(255,255,255,.55); letter-spacing: .08em; text-transform: uppercase; font-weight: 500; display: flex; align-items: center; gap: 6px; }
.np-title { font-size: 17px; color: #fff; font-weight: 500; margin-top: 2px; }
.np-sub { font-size: 11px; color: rgba(255,255,255,.65); }

.np-btn { border: 0; padding: 7px 14px; border-radius: 7px; font-size: 11.5px; font-family: inherit; font-weight: 500; cursor: pointer; }
.np-btn-primary { background: #7F77DD; color: #fff; }
.np-btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.np-btn-ghost   { background: rgba(255,255,255,.1); color: #fff; }

.np-tb-r { display: flex; gap: 8px; }

.np-msg { padding: 10px 22px; font-size: 12px; }
.np-msg-err { background: rgba(226,75,74,.08); color: #A32D2D; }
.np-msg-ok  { background: rgba(29,158,117,.08); color: #0F6E56; }

.np-body { padding: 14px 22px 24px; display: flex; flex-direction: column; gap: 12px; }

.np-card {
  background: #fff;
  border: 0.5px solid rgba(0,0,0,.06);
  border-radius: 12px;
  overflow: hidden;
}
.np-card-hd {
  padding: 11px 16px;
  background: #FAFAFC;
  border-bottom: 0.5px solid rgba(0,0,0,.05);
  display: flex; justify-content: space-between; align-items: center;
}
.np-card-ttl { font-size: 11px; color: #888780; text-transform: uppercase; letter-spacing: .07em; font-weight: 500; }
.np-card-cnt { font-size: 10.5px; color: #888780; }

.np-row {
  display: grid;
  grid-template-columns: 1fr 90px 70px 90px 100px 60px;
  align-items: center;
  padding: 9px 16px;
  border-bottom: 0.5px solid rgba(0,0,0,.04);
  gap: 8px;
}
.np-row:last-child { border-bottom: 0; }
.np-row-head {
  background: #FAFAFC;
  font-size: 9.5px;
  color: #888780;
  text-transform: uppercase;
  letter-spacing: .06em;
  font-weight: 500;
}
.np-row-l { min-width: 0; }
.np-type-label { font-size: 12.5px; color: #1E2A4A; font-weight: 500; }
.np-type-code { font-size: 10px; color: #888780; font-family: monospace; margin-top: 1px; }
.np-row-prio, .np-row-ch, .np-row-mute { text-align: center; }
.np-row-soon { position: relative; opacity: .65; }
.np-soon-pill {
  font-size: 8.5px; background: rgba(239,159,39,.12); color: #854F0B;
  padding: 1px 5px; border-radius: 4px; margin-left: 4px;
}

.np-prio-pill {
  font-size: 9.5px; padding: 2px 7px; border-radius: 4px;
  font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
}
.np-prio-pill.prio-low { background: rgba(136,135,128,.1); color: #5F5E5A; }
.np-prio-pill.prio-normal { background: rgba(127,119,221,.1); color: #534AB7; }
.np-prio-pill.prio-high { background: rgba(239,159,39,.12); color: #854F0B; }
.np-prio-pill.prio-critical { background: rgba(226,75,74,.12); color: #A32D2D; }

.np-switch { position: relative; display: inline-block; width: 30px; height: 16px; cursor: pointer; }
.np-switch input { opacity: 0; width: 0; height: 0; }
.np-switch-tr { position: absolute; inset: 0; background: #D3D1C7; border-radius: 9px; transition: background .2s; }
.np-switch-tr::before { content: ""; position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; background: #fff; border-radius: 50%; transition: left .2s; }
.np-switch input:checked + .np-switch-tr { background: #1D9E75; }
.np-switch input:checked + .np-switch-tr::before { left: 16px; }
.np-switch input:disabled + .np-switch-tr { background: #E0DED5; cursor: not-allowed; }

.np-mute-btn {
  background: transparent; border: 0.5px solid rgba(0,0,0,.12);
  color: #888780; padding: 4px 7px; border-radius: 5px;
  cursor: pointer; display: inline-flex; align-items: center; justify-content: center;
}
.np-mute-btn.active { background: rgba(226,75,74,.1); color: #A32D2D; border-color: rgba(226,75,74,.3); }
</style>
