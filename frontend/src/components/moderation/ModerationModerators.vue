<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import BIcon from "@/components/broadcasts/BIcon.vue";
import { moderationApi, type ModeratorUser } from "@/api/moderation";
import { useAuthStore } from "@/stores/auth";
import { useConfirm } from "@/composables/useConfirm";
import { useToast } from "@/composables/useToast";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();
const auth = useAuthStore();
const { confirmDialog } = useConfirm();
const toast = useToast();


const items = ref<ModeratorUser[]>([]);
const removed = ref<ModeratorUser[]>([]);
const loading = ref(false);
const busy = ref<Record<string, boolean>>({});
const error = ref<string | null>(null);

const canManage = computed(() => auth.hasPermission("admin.users"));
// Снять согласование с владельца может только владелец — кнопку остальным не
// показываем, чтобы не предлагать действие, которое вернётся 403.
// Себя вернуть сможет только тот, чей авторитет переживает отзыв: владелец и
// носитель роли «Администратор» проходят гард возврата, остальным после снятия
// собственного права уже нечем себя вернуть.
const canRestoreSelf = computed(() => auth.isOwner || auth.hasRole("admin"));

function canRemove(u: ModeratorUser): boolean {
  if (!canManage.value) return false;
  return !u.owner_only_removal || !!auth.isOwner;
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const r = await moderationApi.moderators();
    items.value = r.items;
    // Снятых показываем только тому, кто может вернуть — остальным это шум.
    if (canManage.value) {
      const rm = await moderationApi.removedModerators();
      removed.value = rm.items;
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  } finally { loading.value = false; }
}
onMounted(load);

function nameOf(u: ModeratorUser): string {
  return u.full_name || u.email;
}

async function remove(u: ModeratorUser) {
  const ok = await confirmDialog({
    title: t("Убрать из модераторов"),
    message: u.id === auth.user?.id
      ? (canRestoreSelf.value
          ? t("Вы снимаете право согласования С СЕБЯ: заявки перестанут открываться. Вернуть себя сможете здесь же, в блоке «Сняты с модерации». Продолжить?")
          : t("Вы снимаете право согласования С СЕБЯ: заявки перестанут открываться, и вернуть себя обратно вы уже не сможете — это сделает другой администратор. Продолжить?"))
      : t("«{name}» перестанет получать заявки и не сможет их согласовывать. Роли и остальные права не меняются, вернуть в модераторы можно в любой момент.", { name: nameOf(u) }),
    confirmText: t("Убрать"),
    danger: true,
  });
  if (!ok) return;
  busy.value[u.id] = true;
  try {
    await moderationApi.removeModerator(u.id);
    toast.success(t("«{name}» убран из модераторов", { name: nameOf(u) }));
    await load();
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || t("Не удалось убрать из модераторов");
    error.value = msg;
    toast.error(msg);
  } finally { busy.value[u.id] = false; }
}

async function restore(u: ModeratorUser) {
  busy.value[u.id] = true;
  try {
    await moderationApi.restoreModerator(u.id);
    toast.success(t("«{name}» снова модератор", { name: nameOf(u) }));
    await load();
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || t("Не удалось вернуть в модераторы");
    error.value = msg;
    toast.error(msg);
  } finally { busy.value[u.id] = false; }
}

function initials(u: ModeratorUser): string {
  if (!u.full_name) return u.email.slice(0, 2).toUpperCase();
  const parts = u.full_name.split(" ").filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return u.full_name.slice(0, 2).toUpperCase();
}
</script>

<template>
  <div class="mm-wrap">
    <div class="mm-hd">
      <BIcon name="info-circle" :size="14" />
      <span>{{ t('Модератор — тот, у кого есть право «Модерация: проверка»: оно приходит из роли, из личной выдачи в разделе «Доступ» или при назначении согласующим в карточке пользователя. Кнопка «убрать» отзывает право персонально, роли не трогает.') }}</span>
    </div>

    <div v-if="error" class="mm-err">{{ error }}</div>

    <div v-if="loading" class="mm-empty">{{ t('Загрузка…') }}</div>
    <div v-else-if="!items.length" class="mm-empty">
      <BIcon name="user-check" :size="14" />
      <div>{{ t('Модераторов пока нет') }}</div>
      <div style="font-size: 10px; margin-top: 4px;">{{ t('Выдайте право «Модерация: проверка» в разделе «Доступ» или назначьте согласующего в карточке пользователя') }}</div>
    </div>

    <div v-else class="mm-grid">
      <div v-for="u in items" :key="u.id" class="mm-card" :class="{ inactive: !u.is_active }">
        <span class="mm-avatar">{{ initials(u) }}</span>
        <div class="mm-body">
          <div class="mm-name">
            {{ u.full_name || u.email }}
            <span v-if="u.is_owner" class="mm-owner-pill">OWNER</span>
          </div>
          <div class="mm-email">{{ u.email }}</div>
          <div v-if="u.job_title || u.department" class="mm-job">
            <span v-if="u.job_title">{{ u.job_title }}</span>
            <span v-if="u.job_title && u.department"> · </span>
            <span v-if="u.department">{{ u.department }}</span>
          </div>
        </div>
        <div class="mm-status">
          <span v-if="!u.is_active" class="mm-inactive">{{ t('неактивен') }}</span>
          <button
            v-if="canRemove(u)"
            class="mm-remove"
            :disabled="busy[u.id]"
            :title="t('Убрать из модераторов')"
            @click="remove(u)"
          >
            <BIcon name="user-minus" :size="13" />
          </button>
          <span
            v-else-if="canManage"
            class="mm-locked"
            :title="t('Снять согласование с владельца платформы может только владелец')"
          >{{ t('только владелец') }}</span>
        </div>
      </div>
    </div>

    <!-- Снятые: без этого блока снятие было бы необратимым — вернуть право
         через сетку «Доступ к модулям» нельзя, этого кода в ней нет. -->
    <div v-if="canManage && removed.length" class="mm-removed">
      <div class="mm-removed-hd">{{ t('Сняты с модерации') }} · {{ removed.length }}</div>
      <div class="mm-grid">
        <div v-for="u in removed" :key="u.id" class="mm-card mm-card-off">
          <span class="mm-avatar">{{ initials(u) }}</span>
          <div class="mm-body">
            <div class="mm-name">{{ u.full_name || u.email }}</div>
            <div class="mm-email">{{ u.email }}</div>
          </div>
          <div class="mm-status">
            <button
              class="mm-restore"
              :disabled="busy[u.id]"
              :title="t('Вернуть в модераторы')"
              @click="restore(u)"
            >{{ t('вернуть') }}</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mm-wrap { display: flex; flex-direction: column; gap: 10px; }

.mm-hd {
  background: rgba(55,138,221,.06);
  border-radius: 7px;
  padding: 8px 12px;
  font-size: 11px;
  color: var(--color-text-secondary);
  display: flex; align-items: flex-start; gap: 7px;
  line-height: 1.45;
  position: relative; overflow: hidden;
}
.mm-hd::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--blue);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation: uzaStripeDrawIn .6s var(--ease-standard) both;
  transform-origin: left center;
  pointer-events: none;
}
.mm-hd i { font-size: 14px; color: #185FA5; margin-top: 1px; flex-shrink: 0; }

.mm-err { background: rgba(226,75,74,.08); color: var(--sev-critical); padding: 8px 12px; border-radius: 7px; font-size: 11.5px; }

.mm-empty {
  padding: 60px 20px;
  text-align: center;
  color: var(--color-text-tertiary);
  font-size: 12px;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
}

.mm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 8px;
}

.mm-card {
  display: flex; align-items: center; gap: 9px;
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 8px;
  padding: 10px 12px;
  transition: background .12s, border-color .12s;
  position: relative; overflow: hidden;
  --mm-accent: #7F77DD;
}
.mm-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0;
  height: 3px; background: var(--mm-accent);
  border-top-left-radius: inherit; border-top-right-radius: inherit;
  animation:
    uzaStripeDrawIn .8s var(--ease-standard) 100ms both,
    uzaStripeBreathe 2.8s ease-in-out 1s infinite;
  pointer-events: none;
}
.mm-card:hover { background: rgba(127,119,221,.03); }
.mm-card.inactive { opacity: .55; --mm-accent: var(--t-muted); }

.mm-avatar {
  width: 34px; height: 34px;
  border-radius: 50%;
  background: rgba(127,119,221,.15);
  color: var(--p-deep);
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 11.5px; font-weight: 500;
  flex-shrink: 0;
}

.mm-body { flex: 1; min-width: 0; }
.mm-name {
  font-size: 12.5px;
  color: var(--color-text-primary);
  font-weight: 500;
  display: flex; align-items: center; gap: 5px;
}
.mm-owner-pill {
  background: linear-gradient(95deg, #1E2A4A, #4B477E);
  color: #fff;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: .04em;
}
.mm-email { font-size: 10.5px; color: var(--color-text-tertiary); margin-top: 1px; }
.mm-job { font-size: 10px; color: var(--color-text-secondary); margin-top: 2px; }
.mm-status { flex-shrink: 0; display: flex; align-items: center; gap: 6px; }

.mm-remove {
  width: 24px; height: 24px; border-radius: 6px;
  border: 0.5px solid var(--color-border-tertiary);
  background: transparent; color: var(--color-text-tertiary);
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer; transition: background .12s, color .12s, border-color .12s;
}
.mm-card:hover .mm-remove { border-color: rgba(226,75,74,.35); }
.mm-remove:hover { background: rgba(226,75,74,.10); color: var(--sev-critical, #E24B4A); }
.mm-remove:disabled { opacity: .45; cursor: default; }

.mm-locked {
  font-size: 8.5px; text-transform: uppercase; letter-spacing: .04em;
  color: var(--color-text-tertiary); background: rgba(0,0,0,.04);
  padding: 1px 6px; border-radius: 3px; white-space: nowrap;
}

.mm-removed { margin-top: 6px; }
.mm-removed-hd {
  font-size: 10px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
  color: var(--color-text-tertiary); margin-bottom: 6px;
}
.mm-card-off { opacity: .6; --mm-accent: var(--t-muted, #94A3B8); }
.mm-restore {
  border: 0.5px solid var(--color-border-tertiary); border-radius: 6px;
  background: transparent; color: var(--p-deep, #534AB7);
  font: inherit; font-size: 10.5px; font-weight: 600;
  padding: 3px 9px; cursor: pointer; white-space: nowrap;
  transition: background .12s;
}
.mm-restore:hover { background: rgba(127,119,221,.12); }
.mm-restore:disabled { opacity: .45; cursor: default; }
.mm-inactive {
  background: rgba(0,0,0,.04);
  color: var(--color-text-tertiary);
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 9px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: .04em;
}
</style>