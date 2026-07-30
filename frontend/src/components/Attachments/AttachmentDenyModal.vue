<template>
  <ModalShell :open="true" size="md" @close="$emit('close')">
    <template #header>
      <div class="adm-title">
        {{ t('Доступ к файлу') }}
        <span class="adm-filename">«{{ filename }}»</span>
      </div>
    </template>

    <div class="adm-body-inner">
      <!-- Add deny -->
      <div class="adm-add">
        <div class="adm-add-label">{{ t('Скрыть для пользователя:') }}</div>
        <UserAutocomplete
          v-model:email="addEmail"
          v-model:name="addName"
          :placeholder="t('email или ФИО — выбери из списка')"
          @pick="onPickUser"
        />
        <input
          v-model="addReason"
          type="text"
          class="adm-reason"
          :placeholder="t('Причина (необязательно)')"
        />
      </div>

      <!-- Denied users list -->
      <div class="adm-list-h">
        {{ t('Скрыт от:') }} <span class="adm-cnt">{{ deniedUsers.length }}</span>
      </div>
      <div v-if="loading" class="adm-empty">{{ t('Загрузка…') }}</div>
      <div v-else-if="deniedUsers.length === 0" class="adm-empty">
        {{ t('Файл виден всем пользователям с доступом к компании.') }}
      </div>
      <ul v-else class="adm-list">
        <li v-for="u in deniedUsers" :key="u.user_id" class="adm-item">
          <div class="adm-item-body">
            <div class="adm-item-name">{{ u.user_full_name || u.user_email || u.user_id }}</div>
            <div class="adm-item-meta">
              <span v-if="u.user_email && u.user_email !== u.user_full_name">{{ u.user_email }}</span>
              <span class="adm-meta-sep">·</span>
              <span :title="u.denied_at">{{ fmtDate(u.denied_at) }}</span>
              <span v-if="u.reason" class="adm-meta-sep">·</span>
              <span v-if="u.reason" class="adm-reason-chip">{{ u.reason }}</span>
            </div>
          </div>
          <button class="adm-allow" @click="onAllow(u.user_id)" :title="t('Восстановить доступ')">
            {{ t('Открыть доступ') }}
          </button>
        </li>
      </ul>

      <div v-if="error" class="adm-error">{{ error }}</div>
    </div>
  </ModalShell>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import UserAutocomplete from "@/components/UserAutocomplete.vue";
import ModalShell from "@/components/ModalShell.vue";
import {
  attachmentsApi,
  type AttachmentKind,
  type DeniedUser,
} from "@/api/attachments";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
const { t } = useI18n();


const props = defineProps<{
  kind: AttachmentKind;
  attId: string;
  filename: string;
}>();

const emit = defineEmits<{
  close: [];
  changed: [];
}>();

const deniedUsers = ref<DeniedUser[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);

const addEmail = ref("");
const addName = ref("");
const addReason = ref("");

async function load() {
  loading.value = true;
  error.value = null;
  try {
    deniedUsers.value = await attachmentsApi.listDeniedUsers(props.kind, props.attId);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось загрузить');
  } finally {
    loading.value = false;
  }
}

async function onPickUser(user: { id: string; email: string }) {
  error.value = null;
  try {
    await attachmentsApi.deny(props.kind, props.attId, user.id, addReason.value || undefined);
    addEmail.value = "";
    addName.value = "";
    addReason.value = "";
    await load();
    emit("changed");
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось скрыть');
  }
}

async function onAllow(userId: string) {
  error.value = null;
  try {
    await attachmentsApi.allow(props.kind, props.attId, userId);
    await load();
    emit("changed");
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('Не удалось восстановить');
  }
}

function fmtDate(iso: string): string {
  try { return new Date(iso).toLocaleDateString(getCurrentIntlLocale(), { day: "2-digit", month: "short", year: "2-digit" }); }
  catch { return ""; }
}

onMounted(load);
</script>

<style scoped>
/* Шапка и обёртка модалки — из ModalShell (Teleport + ESC + фокус-трап + --z-top). */
.adm-title {
  font-size: 13px; font-weight: 500;
  color: var(--t1, #1E2A4A); letter-spacing: -.01em;
  min-width: 0;
}
.adm-filename {
  color: var(--t3, var(--t-muted)); font-weight: 400;
  margin-left: 4px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  display: inline-block; max-width: 320px; vertical-align: bottom;
}

.adm-body-inner {
  display: flex; flex-direction: column; gap: 12px;
}

.adm-add {
  display: flex; flex-direction: column; gap: 6px;
  padding: 10px 12px;
  background: rgba(127, 119, 221, .05);
  border-radius: 8px;
}
.adm-add-label {
  font-size: 10.5px; color: var(--t3, var(--t-muted));
  text-transform: uppercase; letter-spacing: .06em;
  font-weight: 500;
}
.adm-reason {
  width: 100%;
  padding: 6px 9px;
  background: var(--bg1, #fff);
  border: 0.5px solid var(--border-hard);
  border-radius: 6px;
  font-family: inherit; font-size: 11.5px;
  color: var(--t1, #1E2A4A); outline: none;
}
.adm-reason:focus { border-color: rgba(127, 119, 221, .45); }

.adm-list-h {
  font-size: 11px; font-weight: 500;
  text-transform: uppercase; letter-spacing: .08em;
  color: var(--t3, var(--t-muted));
}
.adm-cnt {
  background: rgba(127, 119, 221, .12);
  color: var(--p-deep);
  padding: 1px 7px;
  border-radius: 8px;
  margin-left: 4px;
  font-size: 10px;
}

.adm-empty {
  font-size: 11.5px;
  color: rgba(30, 42, 74, 0.35);
  font-style: italic;
  padding: 8px 0;
}

.adm-list {
  list-style: none; padding: 0; margin: 0;
  display: flex; flex-direction: column; gap: 2px;
}
.adm-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 10px; border-radius: 8px;
}
.adm-item:hover { background: var(--bg2, #FAFAFC); }
.adm-item-body { flex: 1; min-width: 0; }
.adm-item-name {
  font-size: 12.5px; font-weight: 500;
  color: var(--t1, #1E2A4A);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.adm-item-meta {
  font-size: 10.5px; color: var(--t3, var(--t-muted));
  display: flex; gap: 4px; flex-wrap: wrap; align-items: baseline;
}
.adm-meta-sep { opacity: .35; }
.adm-reason-chip {
  background: rgba(127, 119, 221, .08);
  color: var(--p-deep);
  padding: 0 5px;
  border-radius: 4px;
}
.adm-allow {
  background: transparent;
  border: 0.5px solid var(--border-hard);
  color: var(--green);
  padding: 4px 9px;
  border-radius: 6px;
  font-family: inherit;
  font-size: 10.5px;
  font-weight: 500;
  cursor: pointer;
  transition: background .12s, border-color .12s;
}
.adm-allow:hover { background: rgba(29, 158, 117, .08); border-color: rgba(29, 158, 117, .35); }

.adm-error {
  font-size: 11px; color: var(--sev-high);
  padding: 6px 10px; border-radius: 6px;
  background: rgba(226, 75, 74, .07);
}
</style>
