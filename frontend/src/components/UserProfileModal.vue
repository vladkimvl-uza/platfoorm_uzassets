<script setup lang="ts">
/**
 * UserProfileModal — личный кабинет пользователя.
 *
 * Открывается по клику на профиль-чип внизу сайдбара. Позволяет
 * самостоятельно править ФИО / должность / телефон / отдел (PATCH /auth/me),
 * сменить пароль и перейти в раздел «Безопасность». Email/роли — read-only.
 */
import { reactive, ref, computed, onMounted } from "vue";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";
import { useRouter } from "vue-router";
import { companiesApi, type CompanyListItem } from "@/api/companies";
import UserAffiliationBadge from "@/components/rbac-v3/UserAffiliationBadge.vue";
import SocialLinks from "@/components/user/SocialLinks.vue";
import { useI18n } from "@/composables/useI18n";
import { INTL_LOCALE } from "@/locale";
import { companyDisplayName } from "@/utils/displayNames";
const { t, locale } = useI18n();


const emit = defineEmits<{ close: [] }>();
const auth = useAuthStore();
const router = useRouter();

const tab = ref<"profile" | "password">("profile");
// Компания (organization_id): юзер задаёт сам ОДИН раз при первой настройке.
const orgLocked = computed(() => !!auth.user?.org_profile_set);
const companyCatalog = ref<CompanyListItem[]>([]);
const allCompanies = computed(() => companyCatalog.value
  .map(company => ({ id: company.id, name: companyDisplayName(company) || company.code }))
  .filter(company => company.id)
  .sort((a, b) => a.name.localeCompare(b.name, INTL_LOCALE[locale.value])));
onMounted(async () => {
  if (orgLocked.value) return; // список нужен только для первичного выбора
  try {
    const r = await companiesApi.list({ per_page: 500 } as any);
    const items = (r as any)?.items || (r as any)?.companies || (Array.isArray(r) ? r : []);
    companyCatalog.value = items || [];
  } catch { /* список недоступен — поле скрыто */ }
});
const saving = ref(false);
const err = ref<string | null>(null);
const ok = ref<string | null>(null);

const u = computed(() => auth.user);
const initials = computed(() => {
  const n = (u.value?.full_name || u.value?.email || "?").trim();
  const parts = n.split(/\s+/);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || n[0]?.toUpperCase() || "?";
});
const avatar = computed(() => u.value?.avatar_url || null);

const fileInput = ref<HTMLInputElement | null>(null);
const uploadingPhoto = ref(false);

// Ужимаем картинку до 160px (квадрат, cover) → JPEG data-URL, чтобы хранить
// компактно в строке пользователя.
function _resizeToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const SZ = 160;
      const canvas = document.createElement("canvas");
      canvas.width = SZ; canvas.height = SZ;
      const ctx = canvas.getContext("2d");
      if (!ctx) return reject(new Error("canvas"));
      const scale = Math.max(SZ / img.width, SZ / img.height);
      const w = img.width * scale, h = img.height * scale;
      ctx.drawImage(img, (SZ - w) / 2, (SZ - h) / 2, w, h);
      resolve(canvas.toDataURL("image/jpeg", 0.82));
    };
    img.onerror = () => reject(new Error("image"));
    const r = new FileReader();
    r.onload = () => { img.src = String(r.result); };
    r.onerror = () => reject(new Error("read"));
    r.readAsDataURL(file);
  });
}

async function onPhotoPick(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (!file.type.startsWith("image/")) { err.value = t('Выберите изображение'); return; }
  uploadingPhoto.value = true; err.value = null; ok.value = null;
  try {
    const dataUrl = await _resizeToDataUrl(file);
    auth.setUser(await authApi.updateMe({ avatar_url: dataUrl }));
    ok.value = t("Фото обновлено");
    setTimeout(() => { ok.value = null; }, 2000);
  } catch (e: any) {
    err.value = e?.response?.data?.detail || t('Не удалось загрузить фото');
  } finally {
    uploadingPhoto.value = false;
    if (fileInput.value) fileInput.value.value = "";
  }
}

async function removePhoto() {
  uploadingPhoto.value = true; err.value = null;
  try { auth.setUser(await authApi.updateMe({ avatar_url: "" })); }
  catch (e: any) { err.value = e?.response?.data?.detail || t('Ошибка'); }
  finally { uploadingPhoto.value = false; }
}

const form = reactive({
  full_name: u.value?.full_name || "",
  job_title: u.value?.job_title || "",
  phone: u.value?.phone || "",
  department: u.value?.department || "",
  organization_id: u.value?.organization_id || "",
  linkedin_url: u.value?.linkedin_url || "",
  website_url: u.value?.website_url || "",
});

async function saveProfile() {
  saving.value = true; err.value = null; ok.value = null;
  try {
    const payload: any = {
      full_name: form.full_name.trim(),
      job_title: form.job_title.trim(),
      phone: form.phone.trim(),
      department: form.department.trim(),
      linkedin_url: form.linkedin_url.trim(),
      website_url: form.website_url.trim(),
    };
    // Компанию шлём только при первичной настройке (потом заблокировано).
    if (!orgLocked.value && form.organization_id) payload.organization_id = form.organization_id;
    const updated = await authApi.updateMe(payload);
    auth.setUser(updated);
    ok.value = t("Профиль сохранён");
    setTimeout(() => { ok.value = null; }, 2200);
  } catch (e: any) {
    err.value = e?.response?.data?.detail || t('Не удалось сохранить');
  } finally { saving.value = false; }
}

// «Не помню текущий пароль» → запуск восстановления (forgot-password flow).
function forgotFromProfile() {
  emit("close");
  router.push("/forgot-password");
}

const pwd = reactive({ current: "", next: "", confirm: "" });
async function changePassword() {
  err.value = null; ok.value = null;
  if (pwd.next.length < 12) { err.value = t('Новый пароль — минимум 12 символов'); return; }
  if (pwd.next !== pwd.confirm) { err.value = t('Пароли не совпадают'); return; }
  saving.value = true;
  try {
    await authApi.changePassword(pwd.current, pwd.next);
    ok.value = t("Пароль изменён. Другие сессии завершены.");
    pwd.current = pwd.next = pwd.confirm = "";
  } catch (e: any) {
    err.value = e?.response?.data?.detail || t('Не удалось сменить пароль');
  } finally { saving.value = false; }
}

function goSecurity() { emit("close"); router.push("/settings/security"); }
</script>

<template>
  <div class="up-bd" @click.self="emit('close')">
    <div class="up-modal">
      <header class="up-head">
        <div class="up-id">
          <div class="up-avatar-wrap">
            <div class="up-avatar" :class="{ photo: avatar }" @click="fileInput?.click()" :title="t('Сменить фото')">
              <img v-if="avatar" :src="avatar" alt="" />
              <span v-else>{{ initials }}</span>
              <span class="up-avatar-cam" aria-hidden="true">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>
              </span>
            </div>
            <input ref="fileInput" type="file" accept="image/*" style="display:none" @change="onPhotoPick" />
          </div>
          <div class="up-id-text">
            <div class="up-name">{{ u?.full_name || '—' }}</div>
            <div class="up-email">{{ u?.email }}</div>
            <UserAffiliationBadge
              v-if="u?.company || u?.sector || u?.department || u?.job_title"
              class="up-aff" size="sm"
              :company="u?.company" :sector="u?.sector" :department="u?.department" :job-title="u?.job_title"
            />
            <SocialLinks
              v-if="u?.linkedin_url || u?.website_url || u?.telegram_username"
              class="up-social" size="sm"
              :linkedin="u?.linkedin_url" :website="u?.website_url" :telegram="u?.telegram_username"
            />
            <div class="up-photo-acts">
              <button class="up-mini" :disabled="uploadingPhoto" @click="fileInput?.click()">{{ uploadingPhoto ? t('загрузка…') : t('сменить фото') }}</button>
              <button v-if="avatar" class="up-mini up-mini-del" :disabled="uploadingPhoto" @click="removePhoto">{{ t('удалить') }}</button>
            </div>
          </div>
        </div>
        <button class="up-x" @click="emit('close')" :title="t('Закрыть')">×</button>
      </header>

      <div class="up-tabs">
        <button :class="{ on: tab === 'profile' }" @click="tab = 'profile'">{{ t('Профиль') }}</button>
        <button :class="{ on: tab === 'password' }" @click="tab = 'password'">{{ t('Пароль') }}</button>
        <button class="up-tab-link" @click="goSecurity">{{ t('Безопасность →') }}</button>
      </div>

      <div class="up-body">
        <p v-if="err" class="up-msg up-err">{{ err }}</p>
        <p v-if="ok" class="up-msg up-ok">{{ ok }}</p>

        <template v-if="tab === 'profile'">
          <div class="up-grid">
            <label class="up-field"><span class="up-lbl">{{ t('ФИО') }}</span><input v-model="form.full_name" class="up-in" :placeholder="t('Иванов Иван Иванович')" /></label>
            <label class="up-field"><span class="up-lbl">{{ t('Должность') }}</span><input v-model="form.job_title" class="up-in" :placeholder="t('Финансовый аналитик')" /></label>
            <label class="up-field"><span class="up-lbl">{{ t('Телефон') }}</span><input v-model="form.phone" class="up-in" placeholder="+998 ..." /></label>
            <label class="up-field"><span class="up-lbl">{{ t('Отдел') }}</span><input v-model="form.department" class="up-in" :placeholder="t('Финансовый блок')" /></label>
            <!-- Компания: редактируется юзером только при первой настройке -->
            <label v-if="!orgLocked" class="up-field">
              <span class="up-lbl">{{ t('Компания') }} <em class="up-once">{{ t('указывается один раз') }}</em></span>
              <select v-model="form.organization_id" class="up-in">
                <option value="">{{ t('— Выберите компанию') }}</option>
                <option v-for="c in allCompanies" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </label>
            <div v-else class="up-field">
              <span class="up-lbl">{{ t('Компания / сектор') }}</span>
              <div class="up-locked">
                <span>{{ u?.company || t('Не указана') }}<template v-if="u?.sector"> · {{ u?.sector }}</template></span>
                <span class="up-locked-ic" :title="t('Изменяет только администратор')"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg></span>
              </div>
            </div>
            <label class="up-field up-wide"><span class="up-lbl">{{ t('Email (нельзя изменить)') }}</span><input :value="u?.email" class="up-in" disabled /></label>

            <!-- Соцссылки: LinkedIn + сайт (премиум, с логотипами) -->
            <label class="up-field up-wide">
              <span class="up-lbl">LinkedIn</span>
              <span class="up-in-ico">
                <svg class="up-ico-li" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28zM5.34 7.43a2.06 2.06 0 1 1 0-4.13 2.06 2.06 0 0 1 0 4.13zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.72V1.72C24 .77 23.2 0 22.22 0z"/></svg>
                <input v-model="form.linkedin_url" class="up-in up-in-pad" placeholder="linkedin.com/in/username" />
              </span>
            </label>
            <label class="up-field up-wide">
              <span class="up-lbl">{{ t('Сайт / портфолио') }}</span>
              <span class="up-in-ico">
                <svg class="up-ico-web" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                <input v-model="form.website_url" class="up-in up-in-pad" placeholder="example.com" />
              </span>
            </label>
          </div>
          <div v-if="u?.roles?.length" class="up-roles">
            <span class="up-lbl">{{ t('Роли:') }}</span>
            <span v-for="r in u.roles" :key="r" class="up-role">{{ r }}</span>
          </div>
          <div class="up-actions">
            <button class="up-btn up-primary" :disabled="saving" @click="saveProfile">{{ saving ? t('Сохранение…') : t('Сохранить профиль') }}</button>
          </div>
        </template>

        <template v-else>
          <div class="up-grid">
            <label class="up-field up-wide"><span class="up-lbl">{{ t('Текущий пароль') }}</span><input v-model="pwd.current" type="password" class="up-in" autocomplete="current-password" /></label>
            <label class="up-field"><span class="up-lbl">{{ t('Новый пароль (≥12)') }}</span><input v-model="pwd.next" type="password" class="up-in" autocomplete="new-password" /></label>
            <label class="up-field"><span class="up-lbl">{{ t('Повторите') }}</span><input v-model="pwd.confirm" type="password" class="up-in" autocomplete="new-password" /></label>
          </div>
          <button class="up-forgot" type="button" @click="forgotFromProfile">{{ t('Не помню текущий пароль') }}</button>
          <div class="up-actions">
            <button class="up-btn up-primary" :disabled="saving" @click="changePassword">{{ saving ? t('Сохранение…') : t('Сменить пароль') }}</button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.up-bd { position: fixed; inset: 0; z-index: 300; background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; padding: 28px; }
.up-modal { width: min(540px, 100%); max-height: 90dvh; background: var(--bg1, #fff); border-radius: 14px; box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08); display: flex; flex-direction: column; overflow: hidden; animation: upIn .3s cubic-bezier(.34,1.2,.64,1); }
@keyframes upIn { from { opacity:0; transform: translateY(12px) scale(.98); } to { opacity:1; transform:none; } }
.up-head { display: flex; align-items: center; justify-content: space-between; padding: 18px 20px 16px; border-bottom: 1px solid var(--border-hard, #E5E7EB); }
.up-id { display: flex; align-items: center; gap: 12px; }
.up-avatar-wrap { flex-shrink: 0; }
.up-avatar { position: relative; width: 48px; height: 48px; border-radius: 13px; background: linear-gradient(135deg, #8B7FFF 0%, #534AB7 100%); color: #fff; display: flex; align-items: center; justify-content: center; font-size: 16px; font-weight: 600; cursor: pointer; overflow: hidden; }
.up-avatar img { width: 100%; height: 100%; object-fit: cover; }
.up-avatar-cam { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 15px; background: rgba(0,0,0,.4); opacity: 0; transition: opacity .15s; }
.up-avatar:hover .up-avatar-cam { opacity: 1; }
.up-photo-acts { display: flex; gap: 10px; margin-top: 3px; }
.up-mini { background: none; border: none; padding: 0; font-size: 10.5px; font-weight: 500; color: var(--p-deep, #534AB7); cursor: pointer; font-family: inherit; }
.up-mini:hover { text-decoration: underline; }
.up-mini-del { color: var(--sev-high, #E24B4A); }
.up-mini:disabled { opacity: .6; cursor: default; }
.up-name { font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A); }
.up-email { font-size: 12px; color: var(--t3, #94A3B8); }
.up-aff { margin-top: 5px; }
.up-once { font-style: normal; font-size: 9.5px; font-weight: 500; text-transform: none; letter-spacing: 0; color: #D97706; background: rgba(217,119,6,.1); border-radius: 5px; padding: 1px 6px; margin-left: 6px; }
.up-locked { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 9px 12px; border: 1px solid var(--border-hard, #E5E7EB); border-radius: 9px; background: #F7F6FD; font-size: 13px; color: var(--t1, #1E2A4A); }
.up-locked-ic { font-size: 12px; opacity: .6; }
.up-forgot { background: none; border: none; padding: 4px 0 2px; margin-top: 4px; font-size: 12px; font-weight: 500; color: var(--p-deep, #534AB7); cursor: pointer; font-family: inherit; }
.up-forgot:hover { text-decoration: underline; }
.up-x { background: none; border: none; font-size: 26px; line-height: 1; color: var(--t3, #94A3B8); cursor: pointer; }
.up-x:hover { color: var(--t1, #1E2A4A); }
.up-tabs { display: flex; gap: 4px; padding: 10px 20px 0; border-bottom: 1px solid var(--border-hard, #E5E7EB); }
.up-tabs button { background: none; border: none; padding: 8px 14px 12px; font-size: 13px; font-weight: 500; color: var(--t3, #64748B); cursor: pointer; border-bottom: 2px solid transparent; font-family: inherit; }
.up-tabs button.on { color: var(--p-deep, #534AB7); border-bottom-color: var(--p, #7C6FF7); }
.up-tab-link { margin-left: auto; color: var(--p-deep, #534AB7) !important; }
.up-body { padding: 18px 20px; overflow-y: auto; }
.up-msg { font-size: 12.5px; margin: 0 0 12px; padding: 9px 12px; border-radius: 8px; }
.up-err { background: rgba(226,75,74,.08); border: 1px solid rgba(226,75,74,.3); color: #A82C2B; }
.up-ok { background: rgba(29,158,117,.10); border: 1px solid rgba(29,158,117,.3); color: #0F6E56; }
.up-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.up-field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.up-wide { grid-column: 1 / -1; }
.up-lbl { font-size: 11px; font-weight: 500; color: var(--t3, #64748B); }
.up-in { width: 100%; box-sizing: border-box; padding: 8px 11px; border: 1.5px solid var(--border-input, #E2E8F0); border-radius: 8px; font-size: 13px; color: var(--t1, #1E2A4A); outline: none; font-family: inherit; background: var(--bg2, #F8FAFC); transition: border-color .14s, box-shadow .14s; }
.up-in:focus { border-color: var(--p, #7C6FF7); box-shadow: 0 0 0 3px rgba(124,111,247,.14); }
.up-in:disabled { color: var(--t3, #94A3B8); }
.up-social { margin-top: 8px; }
/* Инпут с фирменным логотипом слева */
.up-in-ico { position: relative; display: block; }
.up-in-ico svg { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); width: 16px; height: 16px; pointer-events: none; }
.up-ico-li { color: #0A66C2; }
.up-ico-web { color: #6E61E8; }
.up-in-pad { padding-left: 36px; }
.up-roles { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 12px; }
.up-role { font-size: 10.5px; font-weight: 600; padding: 2px 8px; border-radius: 7px; background: rgba(124,111,247,.10); color: var(--p-deep, #534AB7); }
.up-actions { display: flex; justify-content: flex-end; margin-top: 18px; }
.up-btn { padding: 9px 20px; border-radius: 9px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit; border: none; transition: all .14s; }
.up-btn:disabled { opacity: .6; cursor: not-allowed; }
.up-primary { background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); color: #fff; box-shadow: 0 2px 10px rgba(108,92,231,.32); }
.up-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(108,92,231,.45); }
@media (max-width: 520px) { .up-grid { grid-template-columns: 1fr; } }
</style>
