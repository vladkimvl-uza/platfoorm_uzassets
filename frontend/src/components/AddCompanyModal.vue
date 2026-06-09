<script setup lang="ts">
/**
 * AddCompanyModal — лёгкий модал создания новой компании.
 * Используется в /kpi и /business-plan. Минимальные поля: код + название (RU),
 * сектор опционально. Право — companies.create (owner/admin/organization).
 */
import { ref, onMounted } from "vue";
import { companiesApi, type SectorBrief, type CompanyDetail } from "@/api/companies";

const emit = defineEmits<{ (e: "close"): void; (e: "created", company: CompanyDetail): void }>();

const code = ref("");
const nameRu = ref("");
const sectorCode = ref("");
const sectors = ref<SectorBrief[]>([]);
const saving = ref(false);
const error = ref("");

onMounted(async () => {
  try { sectors.value = await companiesApi.listSectors(); } catch { /* sectors optional */ }
});

function normCode() {
  // код — латиница/цифры в нижнем регистре (как у остальных: ngmk, agmk…)
  code.value = code.value.trim().toLowerCase().replace(/[^a-z0-9_-]/g, "");
}

async function submit() {
  error.value = "";
  if (!code.value.trim()) { error.value = "Укажите код компании"; return; }
  if (!nameRu.value.trim()) { error.value = "Укажите название (RU)"; return; }
  saving.value = true;
  try {
    const detail = await companiesApi.create({
      code: code.value.trim(),
      name_ru: nameRu.value.trim(),
      sector_code: sectorCode.value || undefined,
    });
    emit("created", detail);
  } catch (e: any) {
    const status = e?.response?.status;
    error.value = status === 409
      ? "Компания с таким кодом уже существует"
      : (e?.response?.data?.detail || "Не удалось создать компанию");
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="acm-overlay" @click.self="emit('close')">
    <div class="acm-card" role="dialog" aria-label="Новая компания">
      <div class="acm-head">
        <span class="acm-title">Новая компания</span>
        <button class="acm-x" @click="emit('close')" aria-label="Закрыть">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
        </button>
      </div>

      <div class="acm-body">
        <label class="acm-field">
          <span class="acm-lbl">Код <i>*</i></span>
          <input v-model="code" @blur="normCode" type="text" class="acm-input" placeholder="напр. ngmk" autocomplete="off" spellcheck="false" />
          <span class="acm-hint">латиница/цифры, нижний регистр — уникальный идентификатор</span>
        </label>
        <label class="acm-field">
          <span class="acm-lbl">Название (RU) <i>*</i></span>
          <input v-model="nameRu" type="text" class="acm-input" placeholder="АО «…»" />
        </label>
        <label class="acm-field">
          <span class="acm-lbl">Сектор</span>
          <select v-model="sectorCode" class="acm-input">
            <option value="">— не выбран —</option>
            <option v-for="s in sectors" :key="s.code" :value="s.code">{{ s.name_ru }}</option>
          </select>
        </label>

        <div v-if="error" class="acm-err">{{ error }}</div>
      </div>

      <div class="acm-foot">
        <button class="acm-btn acm-btn-ghost" @click="emit('close')" :disabled="saving">Отмена</button>
        <button class="acm-btn acm-btn-primary" @click="submit" :disabled="saving">
          {{ saving ? "Создание…" : "Создать" }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.acm-overlay { position: fixed; inset: 0; z-index: 9500; background: rgba(15,18,40,.45); backdrop-filter: blur(8px); display: flex; align-items: center; justify-content: center; padding: 16px; --ease: cubic-bezier(.34,1.2,.64,1); }
.acm-card { width: 100%; max-width: 440px; background: #fff; border-radius: 14px; box-shadow: 0 24px 64px rgba(15,23,60,.24); overflow: hidden; animation: acmIn .3s var(--ease); }
@keyframes acmIn { from { opacity: 0; transform: translateY(12px) scale(.97); } to { opacity: 1; transform: none; } }
.acm-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 18px; border-bottom: 1px solid rgba(15,23,60,.07); }
.acm-title { font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A); }
.acm-x { width: 28px; height: 28px; border: none; background: transparent; color: var(--t3, #94A3B8); border-radius: 8px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: background .14s, color .14s; }
.acm-x:hover { background: rgba(15,23,60,.06); color: var(--t1, #1E2A4A); }
.acm-body { padding: 16px 18px; display: flex; flex-direction: column; gap: 13px; }
.acm-field { display: flex; flex-direction: column; gap: 5px; }
.acm-lbl { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.acm-lbl i { color: #E24B4A; font-style: normal; }
.acm-input { font-size: 13px; color: var(--t1, #1E2A4A); background: var(--bg-soft, #FAFAFC); border: 1px solid rgba(15,23,60,.12); border-radius: 9px; padding: 9px 12px; outline: none; font-family: inherit; transition: border-color .16s var(--ease), box-shadow .16s var(--ease); }
.acm-input:focus { border-color: rgba(127,119,221,.5); box-shadow: 0 0 0 3px rgba(127,119,221,.10); }
.acm-hint { font-size: 11px; color: var(--t3, #94A3B8); }
.acm-err { font-size: 12px; color: #B91C1C; background: rgba(226,75,74,.08); border-radius: 8px; padding: 9px 11px; }
.acm-foot { display: flex; justify-content: flex-end; gap: 9px; padding: 14px 18px; border-top: 1px solid rgba(15,23,60,.07); }
.acm-btn { font-size: 13px; font-weight: 500; border-radius: 9px; padding: 9px 18px; cursor: pointer; font-family: inherit; border: 1px solid transparent; transition: all .16s var(--ease); }
.acm-btn:disabled { opacity: .6; cursor: default; }
.acm-btn-ghost { background: transparent; border-color: rgba(15,23,60,.14); color: var(--t2, #475569); }
.acm-btn-ghost:hover:not(:disabled) { background: rgba(15,23,60,.04); }
.acm-btn-primary { background: linear-gradient(135deg, #534AB7, #7F77DD); color: #fff; box-shadow: 0 4px 14px rgba(83,74,183,.28); }
.acm-btn-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 8px 20px rgba(83,74,183,.36); }
</style>
