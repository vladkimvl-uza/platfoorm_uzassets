<script setup lang="ts">
/**
 * AddCompanyModal — лёгкий модал создания новой компании.
 * Используется в /kpi и /business-plan. Минимальные поля: код + название (RU),
 * сектор опционально. Право — companies.create (owner/admin/organization).
 */
import { ref, onMounted } from "vue";
import { companiesApi, type SectorBrief, type CompanyDetail } from "@/api/companies";
import ModalShell from "@/components/ModalShell.vue";
import { useI18n } from "@/composables/useI18n";
const { t } = useI18n();


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
  <ModalShell :open="true" size="md" @close="emit('close')">
    <template #header>
      <span class="acm-title">{{ t('Новая компания') }}</span>
    </template>

    <div class="acm-body">
      <label class="acm-field">
        <span class="acm-lbl">{{ t('Код') }} <i>*</i></span>
        <input v-model="code" @blur="normCode" type="text" class="acm-input" :placeholder="t('напр. ngmk')" autocomplete="off" spellcheck="false" />
        <span class="acm-hint">{{ t('латиница/цифры, нижний регистр — уникальный идентификатор') }}</span>
      </label>
      <label class="acm-field">
        <span class="acm-lbl">{{ t('Название (RU)') }} <i>*</i></span>
        <input v-model="nameRu" type="text" class="acm-input" :placeholder="t('АО «…»')" />
      </label>
      <label class="acm-field">
        <span class="acm-lbl">{{ t('Сектор') }}</span>
        <select v-model="sectorCode" class="acm-input">
          <option value="">{{ t('— не выбран —') }}</option>
          <option v-for="s in sectors" :key="s.code" :value="s.code">{{ s.name_ru }}</option>
        </select>
      </label>

      <div v-if="error" class="acm-err">{{ error }}</div>
    </div>

    <template #footer>
      <button class="acm-btn acm-btn-ghost" @click="emit('close')" :disabled="saving">{{ t('Отмена') }}</button>
      <button class="acm-btn acm-btn-primary" @click="submit" :disabled="saving">
        {{ saving ? "Создание…" : "Создать" }}
      </button>
    </template>
  </ModalShell>
</template>

<style scoped>
/* Обёртка/шапка/футер — из ModalShell (Teleport + ESC + фокус-трап + --z-top). */
.acm-title { font-size: 15px; font-weight: 600; color: var(--t1, #1E2A4A); }
.acm-body { display: flex; flex-direction: column; gap: 13px; }
.acm-field { display: flex; flex-direction: column; gap: 5px; }
.acm-lbl { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94A3B8); }
.acm-lbl i { color: #E24B4A; font-style: normal; }
.acm-input { font-size: 13px; color: var(--t1, #1E2A4A); background: var(--bg-soft, #FAFAFC); border: 1px solid rgba(15,23,60,.12); border-radius: 9px; padding: 9px 12px; outline: none; font-family: inherit; transition: border-color .16s cubic-bezier(.34,1.2,.64,1), box-shadow .16s cubic-bezier(.34,1.2,.64,1); }
.acm-input:focus { border-color: rgba(127,119,221,.5); box-shadow: 0 0 0 3px rgba(127,119,221,.10); }
.acm-hint { font-size: 11px; color: var(--t3, #94A3B8); }
.acm-err { font-size: 12px; color: #B91C1C; background: rgba(226,75,74,.08); border-radius: 8px; padding: 9px 11px; }
.acm-btn { font-size: 13px; font-weight: 500; border-radius: 9px; padding: 9px 18px; cursor: pointer; font-family: inherit; border: 1px solid transparent; transition: all .16s cubic-bezier(.34,1.2,.64,1); }
.acm-btn:disabled { opacity: .6; cursor: default; }
.acm-btn-ghost { background: transparent; border-color: rgba(15,23,60,.14); color: var(--t2, #475569); }
.acm-btn-ghost:hover:not(:disabled) { background: rgba(15,23,60,.04); }
.acm-btn-primary { background: linear-gradient(135deg, #534AB7, #7F77DD); color: #fff; box-shadow: 0 4px 14px rgba(83,74,183,.28); }
.acm-btn-primary:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 8px 20px rgba(83,74,183,.36); }
</style>
