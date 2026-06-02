<script setup lang="ts">
/**
 * UserProfileModal — личный кабинет пользователя.
 *
 * Открывается по клику на профиль-чип внизу сайдбара. Позволяет
 * самостоятельно править ФИО / должность / телефон / отдел (PATCH /auth/me),
 * сменить пароль и перейти в раздел «Безопасность». Email/роли — read-only.
 */
import { reactive, ref, computed } from "vue";
import { authApi } from "@/api/auth";
import { useAuthStore } from "@/stores/auth";
import { useRouter } from "vue-router";

const emit = defineEmits<{ close: [] }>();
const auth = useAuthStore();
const router = useRouter();

const tab = ref<"profile" | "password">("profile");
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
  if (!file.type.startsWith("image/")) { err.value = "Выберите изображение"; return; }
  uploadingPhoto.value = true; err.value = null; ok.value = null;
  try {
    const dataUrl = await _resizeToDataUrl(file);
    auth.setUser(await authApi.updateMe({ avatar_url: dataUrl }));
    ok.value = "Фото обновлено";
    setTimeout(() => { ok.value = null; }, 2000);
  } catch (e: any) {
    err.value = e?.response?.data?.detail || "Не удалось загрузить фото";
  } finally {
    uploadingPhoto.value = false;
    if (fileInput.value) fileInput.value.value = "";
  }
}

async function removePhoto() {
  uploadingPhoto.value = true; err.value = null;
  try { auth.setUser(await authApi.updateMe({ avatar_url: "" })); }
  catch (e: any) { err.value = e?.response?.data?.detail || "Ошибка"; }
  finally { uploadingPhoto.value = false; }
}

const form = reactive({
  full_name: u.value?.full_name || "",
  job_title: u.value?.job_title || "",
  phone: u.value?.phone || "",
  department: u.value?.department || "",
});

async function saveProfile() {
  saving.value = true; err.value = null; ok.value = null;
  try {
    const updated = await authApi.updateMe({
      full_name: form.full_name.trim(),
      job_title: form.job_title.trim(),
      phone: form.phone.trim(),
      department: form.department.trim(),
    });
    auth.setUser(updated);
    ok.value = "Профиль сохранён";
    setTimeout(() => { ok.value = null; }, 2200);
  } catch (e: any) {
    err.value = e?.response?.data?.detail || "Не удалось сохранить";
  } finally { saving.value = false; }
}

const pwd = reactive({ current: "", next: "", confirm: "" });
async function changePassword() {
  err.value = null; ok.value = null;
  if (pwd.next.length < 12) { err.value = "Новый пароль — минимум 12 символов"; return; }
  if (pwd.next !== pwd.confirm) { err.value = "Пароли не совпадают"; return; }
  saving.value = true;
  try {
    await authApi.changePassword(pwd.current, pwd.next);
    ok.value = "Пароль изменён. Другие сессии завершены.";
    pwd.current = pwd.next = pwd.confirm = "";
  } catch (e: any) {
    err.value = e?.response?.data?.detail || "Не удалось сменить пароль";
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
            <div class="up-avatar" :class="{ photo: avatar }" @click="fileInput?.click()" title="Сменить фото">
              <img v-if="avatar" :src="avatar" alt="" />
              <span v-else>{{ initials }}</span>
              <span class="up-avatar-cam">📷</span>
            </div>
            <input ref="fileInput" type="file" accept="image/*" style="display:none" @change="onPhotoPick" />
          </div>
          <div class="up-id-text">
            <div class="up-name">{{ u?.full_name || '—' }}</div>
            <div class="up-email">{{ u?.email }}</div>
            <div class="up-photo-acts">
              <button class="up-mini" :disabled="uploadingPhoto" @click="fileInput?.click()">{{ uploadingPhoto ? 'загрузка…' : 'сменить фото' }}</button>
              <button v-if="avatar" class="up-mini up-mini-del" :disabled="uploadingPhoto" @click="removePhoto">удалить</button>
            </div>
          </div>
        </div>
        <button class="up-x" @click="emit('close')" title="Закрыть">×</button>
      </header>

      <div class="up-tabs">
        <button :class="{ on: tab === 'profile' }" @click="tab = 'profile'">Профиль</button>
        <button :class="{ on: tab === 'password' }" @click="tab = 'password'">Пароль</button>
        <button class="up-tab-link" @click="goSecurity">Безопасность →</button>
      </div>

      <div class="up-body">
        <p v-if="err" class="up-msg up-err">{{ err }}</p>
        <p v-if="ok" class="up-msg up-ok">{{ ok }}</p>

        <template v-if="tab === 'profile'">
          <div class="up-grid">
            <label class="up-field"><span class="up-lbl">ФИО</span><input v-model="form.full_name" class="up-in" placeholder="Иванов Иван Иванович" /></label>
            <label class="up-field"><span class="up-lbl">Должность</span><input v-model="form.job_title" class="up-in" placeholder="Финансовый аналитик" /></label>
            <label class="up-field"><span class="up-lbl">Телефон</span><input v-model="form.phone" class="up-in" placeholder="+998 ..." /></label>
            <label class="up-field"><span class="up-lbl">Отдел</span><input v-model="form.department" class="up-in" placeholder="Финансовый блок" /></label>
            <label class="up-field up-wide"><span class="up-lbl">Email (нельзя изменить)</span><input :value="u?.email" class="up-in" disabled /></label>
          </div>
          <div v-if="u?.roles?.length" class="up-roles">
            <span class="up-lbl">Роли:</span>
            <span v-for="r in u.roles" :key="r" class="up-role">{{ r }}</span>
          </div>
          <div class="up-actions">
            <button class="up-btn up-primary" :disabled="saving" @click="saveProfile">{{ saving ? 'Сохранение…' : 'Сохранить профиль' }}</button>
          </div>
        </template>

        <template v-else>
          <div class="up-grid">
            <label class="up-field up-wide"><span class="up-lbl">Текущий пароль</span><input v-model="pwd.current" type="password" class="up-in" autocomplete="current-password" /></label>
            <label class="up-field"><span class="up-lbl">Новый пароль (≥12)</span><input v-model="pwd.next" type="password" class="up-in" autocomplete="new-password" /></label>
            <label class="up-field"><span class="up-lbl">Повторите</span><input v-model="pwd.confirm" type="password" class="up-in" autocomplete="new-password" /></label>
          </div>
          <div class="up-actions">
            <button class="up-btn up-primary" :disabled="saving" @click="changePassword">{{ saving ? 'Сохранение…' : 'Сменить пароль' }}</button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.up-bd { position: fixed; inset: 0; z-index: 300; background: rgba(15,18,40,.45); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; padding: 28px; }
.up-modal { width: min(540px, 100%); max-height: 90vh; background: var(--bg1, #fff); border-radius: 14px; box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08); display: flex; flex-direction: column; overflow: hidden; animation: upIn .3s cubic-bezier(.34,1.2,.64,1); }
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
.up-roles { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 12px; }
.up-role { font-size: 10.5px; font-weight: 600; padding: 2px 8px; border-radius: 7px; background: rgba(124,111,247,.10); color: var(--p-deep, #534AB7); }
.up-actions { display: flex; justify-content: flex-end; margin-top: 18px; }
.up-btn { padding: 9px 20px; border-radius: 9px; font-size: 13px; font-weight: 600; cursor: pointer; font-family: inherit; border: none; transition: all .14s; }
.up-btn:disabled { opacity: .6; cursor: not-allowed; }
.up-primary { background: linear-gradient(135deg, #8B7FFF 0%, #6C5CE7 100%); color: #fff; box-shadow: 0 2px 10px rgba(108,92,231,.32); }
.up-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 4px 16px rgba(108,92,231,.45); }
@media (max-width: 520px) { .up-grid { grid-template-columns: 1fr; } }
</style>
