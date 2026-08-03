<script setup lang="ts">
/**
 * UnitCostCompanyModal — модальная обёртка над UnitCostCompanyPanel (editor
 * продуктов компании: выпуск, удельный расход, норма, статьи, импорт, комментарии).
 * Всё содержимое и расчёт живут в панели; здесь — ModalShell, шапка, футер,
 * dirty-guard. Та же панель встроена во вкладку воркспейса (1:1, общий бэкенд).
 */
import { computed, onMounted, ref } from "vue";
import { useI18n } from "@/composables/useI18n";
import ModalShell from "@/components/ModalShell.vue";
import UnitCostCompanyPanel from "@/components/UnitCost/UnitCostCompanyPanel.vue";
import { type UCCompany, type UCPrices, type UCWorld } from "@/api/unitCost";
import { useCompaniesStore } from "@/stores/companies";

const props = defineProps<{
  open: boolean; company: UCCompany | null;
  prices: UCPrices; world: UCWorld | null; fuelLabels: Record<string, string>;
  year: number; quarter: string;
}>();
const emit = defineEmits<{ (e: "close"): void; (e: "saved"): void }>();
const { t } = useI18n();
const companiesStore = useCompaniesStore();
onMounted(() => { void companiesStore.ensureLoaded(); });
const displayCompanyName = computed(() =>
  companiesStore.getCompanyName(props.company?.code) || props.company?.name || "");
const displaySectorName = computed(() => {
  const sectorCode = companiesStore.findSectorCode(props.company?.code || "");
  return (sectorCode && companiesStore.getSectorName(sectorCode)) || props.company?.sector || "";
});

const panel = ref<InstanceType<typeof UnitCostCompanyPanel> | null>(null);
const dirty = ref(false);
const saving = ref(false);
function doSave() { panel.value?.save(); }
</script>

<template>
  <ModalShell :open="open && !!company" size="lg" :dirty="dirty" @close="emit('close')">
    <template v-if="company" #header>
      <div class="ucm-head">
        <div class="ucm-eyebrow">{{ t("Удельная себестоимость") }}</div>
        <h2 class="ucm-title"><span class="ucm-dot" :style="{ background: company.color }" />{{ displayCompanyName }}</h2>
        <div class="ucm-meta">{{ displaySectorName }}</div>
      </div>
    </template>

    <UnitCostCompanyPanel ref="panel" variant="modal" :open="open"
      :company="company" :prices="prices" :world="world" :fuel-labels="fuelLabels"
      :year="year" :quarter="quarter"
      @update:dirty="dirty = $event" @update:saving="saving = $event" @saved="emit('saved')" />

    <template #footer>
      <span class="ucm-hint">{{ t("энергонормы предзаполнены из отчёта энергоёмкости · остальное — вручную") }}</span>
      <button class="ucm-cancel" type="button" @click="emit('close')">{{ t("Отмена") }}</button>
      <button class="ucm-save" type="button" :disabled="!dirty || saving" @click="doSave">
        {{ saving ? t("Сохранение…") : t("Сохранить") }}
      </button>
    </template>
  </ModalShell>
</template>

<style scoped>
.ucm-head { display: flex; flex-direction: column; gap: 2px; }
.ucm-eyebrow { font-size: 9.5px; font-weight: 600; letter-spacing: .07em; text-transform: uppercase; color: var(--t3,#94A3B8); }
.ucm-title { font-size: 16px; font-weight: 600; margin: 2px 0 0; color: var(--t1,#1E2A4A); display: flex; align-items: center; gap: 8px; }
.ucm-dot { width: 10px; height: 10px; border-radius: 50%; }
.ucm-meta { font-size: 11px; color: var(--t3,#94A3B8); }
.ucm-hint { margin-right: auto; font-size: 10px; color: var(--t3,#94A3B8); font-style: italic; }
.ucm-cancel { font-size: 12.5px; font-weight: 600; font-family: inherit; color: var(--t2,#4B5468); background: transparent;
  border: 1px solid var(--border-hard,#E5E7EB); border-radius: 10px; padding: 9px 18px; cursor: pointer; }
.ucm-save { font-size: 12.5px; font-weight: 600; font-family: inherit; color: #fff;
  background: linear-gradient(135deg,#8B7FFF 0%,#6C5CE7 100%); border: none; border-radius: 10px; padding: 9px 22px; cursor: pointer;
  box-shadow: 0 3px 12px rgba(108,92,231,.34); transition: transform .14s, box-shadow .14s, opacity .14s; }
.ucm-save:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 18px rgba(108,92,231,.45); }
.ucm-save:disabled { opacity: .5; cursor: default; box-shadow: none; }
</style>
