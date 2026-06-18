<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useConfirm } from "@/composables/useConfirm";

const { confirmDialog } = useConfirm();

const props = defineProps<{
  companies: { id: string; code: string; name_ru: string; name_short: string | null }[];
  selectedCompanyId: string;
  years: number[];
  selectedYear: number | null;
  balanceText: string;
  balanceStatus: "neutral" | "ok" | "bad";
  /** lock status of the active year (null = not loaded) */
  lockStatus: string | null;
}>();

const emit = defineEmits<{
  "update:selectedCompanyId": [id: string];
  "update:selectedYear": [year: number];
  "create-year": [year: number];
  "delete-year": [];
  "lock-year": [];
  "unlock-year": [];
  "export-csv": [];
  "toggle-history": [];
}>();

const pillClass = computed(() => ({
  "fm-pill": true,
  "fm-pill-ok": props.balanceStatus === "ok",
  "fm-pill-bad": props.balanceStatus === "bad",
  "fm-pill-neutral": props.balanceStatus === "neutral",
}));

// Inline +Год form
const addingYear = ref(false);
const newYearInput = ref<string>("");
function showAddForm() {
  newYearInput.value = String(new Date().getFullYear());
  addingYear.value = true;
}
function cancelAdd() {
  addingYear.value = false;
  newYearInput.value = "";
}
function submitAdd() {
  const y = Number(newYearInput.value);
  if (!Number.isFinite(y) || y < 2000 || y > 2100) return;
  emit("create-year", y);
  addingYear.value = false;
}

// Year actions menu
const menuOpen = ref(false);
function toggleMenu() { menuOpen.value = !menuOpen.value; }
function closeMenu() { menuOpen.value = false; }
function onDocClick(e: MouseEvent) {
  const t = e.target as HTMLElement;
  if (!t.closest(".fm-yr-menu")) menuOpen.value = false;
}
onMounted(() => document.addEventListener("click", onDocClick));
onBeforeUnmount(() => document.removeEventListener("click", onDocClick));

async function clickDelete() {
  closeMenu();
  if (props.selectedYear == null) return;
  if (!(await confirmDialog({ message: `Удалить год ${props.selectedYear} и все ячейки безвозвратно?`, danger: true }))) return;
  emit("delete-year");
}
async function clickLock() {
  closeMenu();
  if (props.lockStatus === "locked" || props.lockStatus === "approved") {
    emit("unlock-year");
  } else {
    if (!(await confirmDialog(`Заблокировать год ${props.selectedYear} от изменений?`))) return;
    emit("lock-year");
  }
}

const isLocked = computed(() => props.lockStatus === "locked" || props.lockStatus === "approved");
const canExport = computed(() => !!props.selectedCompanyId && !!props.selectedYear);
</script>

<template>
  <header class="fm-header">
    <div class="fm-header-left">
      <div class="fm-eyebrow">Финансы · Модель</div>
      <h1 class="fm-title">Финансовая модель</h1>
      <div class="fm-subline">НСБУ форма №1 · 87 строк баланса + 27 строк P&amp;L</div>
    </div>

    <div class="fm-header-center">
      <label class="fm-fld">
        <span class="fm-fld-lbl">Компания:</span>
        <select
          class="fm-select fm-select-co"
          :value="selectedCompanyId"
          @change="emit('update:selectedCompanyId', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">— выбрать —</option>
          <option v-for="c in companies" :key="c.id" :value="c.id">
            {{ c.name_short || c.name_ru }}
          </option>
        </select>
      </label>

      <label class="fm-fld">
        <span class="fm-fld-lbl">Год:</span>
        <select
          class="fm-select fm-select-yr"
          :value="selectedYear ?? ''"
          :disabled="!selectedCompanyId"
          @change="emit('update:selectedYear', Number(($event.target as HTMLSelectElement).value))"
        >
          <option v-if="years.length === 0" value="">—</option>
          <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
        </select>
      </label>

      <!-- Inline +Год form OR show button -->
      <template v-if="selectedCompanyId">
        <form v-if="addingYear" class="fm-yr-add" @submit.prevent="submitAdd">
          <input
            v-model="newYearInput"
            class="fm-select fm-select-yr"
            type="number"
            min="2000" max="2100"
            autofocus
            @keydown.escape="cancelAdd"
          />
          <button type="submit" class="fm-btn-ghost fm-btn-add-ok">✓</button>
          <button type="button" class="fm-btn-ghost fm-btn-add-no" @click="cancelAdd">×</button>
        </form>
        <button v-else class="fm-btn-ghost" type="button" @click="showAddForm" title="Добавить год">
          + Год
        </button>
      </template>

      <!-- Year actions menu (⋯ next to year picker) -->
      <div v-if="selectedYear" class="fm-yr-menu">
        <button
          type="button"
          class="fm-btn-icon"
          :class="{ on: menuOpen }"
          @click.stop="toggleMenu"
          :title="`Действия с годом ${selectedYear}`"
        >⋯</button>
        <div v-if="menuOpen" class="fm-yr-menu-pop" @click.stop>
          <button class="fm-yr-menu-item" @click="clickLock">
            {{ isLocked ? "🔓 Разблокировать" : "🔒 Заблокировать" }}
          </button>
          <div class="fm-yr-menu-sep"></div>
          <button class="fm-yr-menu-item fm-yr-menu-danger" @click="clickDelete" :disabled="isLocked">
            × Удалить год {{ selectedYear }}
          </button>
        </div>
      </div>
    </div>

    <div class="fm-header-right">
      <span :class="pillClass">
        <span class="fm-pill-dot"></span>
        {{ balanceText }}
      </span>
      <button
        class="fm-btn-ghost"
        :disabled="!canExport"
        @click="emit('export-csv')"
        title="Скачать CSV"
      >⌃ Excel</button>
      <button
        class="fm-btn-ghost"
        :disabled="!canExport"
        @click="emit('toggle-history')"
        title="История изменений"
      >↩ История</button>
    </div>
  </header>
</template>

<style scoped>
.fm-header {
  padding: 14px 18px;
  border-bottom: 0.5px solid #F1EFE8;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 14px;
  align-items: center;
}
.fm-header-left { min-width: 0; }
.fm-eyebrow {
  font-size: 10px; font-weight: 500;
  color: var(--t3, var(--t-muted)); letter-spacing: .08em; text-transform: uppercase;
}
.fm-title {
  font-size: 17px; font-weight: 500;
  letter-spacing: -.015em; color: var(--t1, #1E2A4A);
  margin: 3px 0 0 0;
}
.fm-subline { font-size: 11px; color: var(--t3, var(--t-muted)); margin-top: 3px; }

.fm-header-center {
  display: flex;
  align-items: center;
  gap: 8px;
}
.fm-fld {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.fm-fld-lbl { font-size: 10.5px; color: var(--t3, var(--t-muted)); }
.fm-select {
  height: 28px;
  padding: 0 8px;
  border: 0.5px solid var(--border-hard);
  border-radius: 7px;
  font-size: 11.5px;
  font-family: inherit;
  background: var(--bg1, #fff);
  color: var(--t1, #1E2A4A);
  outline: none;
}
.fm-select:focus { border-color: #7F77DD; }
.fm-select:disabled { opacity: .5; cursor: not-allowed; }
.fm-select-co { min-width: 220px; }
.fm-select-yr { min-width: 90px; font-variant-numeric: tabular-nums; }

.fm-yr-add { display: inline-flex; gap: 3px; align-items: center; }
.fm-btn-add-ok { color: #0F6E56; padding: 0 8px; }
.fm-btn-add-no { color: var(--t3, var(--t-muted)); padding: 0 8px; }

.fm-yr-menu { position: relative; }
.fm-btn-icon {
  width: 28px; height: 28px;
  background: transparent;
  border: 1px solid var(--border-hard);
  border-radius: 7px;
  color: var(--t3, var(--t-muted));
  cursor: pointer;
  font-family: inherit;
  font-size: 14px;
  line-height: 1;
}
.fm-btn-icon:hover:not(:disabled), .fm-btn-icon.on {
  background: rgba(127, 119, 221, .08);
  color: var(--p-deep);
  border-color: #7F77DD;
}
.fm-yr-menu-pop {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  background: var(--bg1, #fff);
  border: 0.5px solid var(--border-hard);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(15, 23, 60, .10);
  padding: 4px;
  min-width: 200px;
  z-index: 50;
}
.fm-yr-menu-item {
  display: block;
  width: 100%;
  padding: 7px 12px;
  background: transparent;
  border: none;
  border-radius: 5px;
  color: var(--t1, #1E2A4A);
  font-size: 11.5px;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
}
.fm-yr-menu-item:hover:not(:disabled) { background: rgba(127, 119, 221, .08); color: var(--p-deep); }
.fm-yr-menu-item:disabled { opacity: .4; cursor: not-allowed; }
.fm-yr-menu-danger { color: #C0322F; }
.fm-yr-menu-danger:hover:not(:disabled) { background: rgba(226, 75, 74, .06); color: #C0322F; }
.fm-yr-menu-sep { height: 0.5px; background: #F1EFE8; margin: 4px 0; }

.fm-header-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.fm-pill {
  height: 28px;
  padding: 0 11px;
  border-radius: 7px;
  font-size: 11px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 6px;
}
.fm-pill-ok { background: rgba(29, 158, 117, .10); color: #0F6E56; }
.fm-pill-ok .fm-pill-dot {
  width: 6px; height: 6px; background: var(--green); border-radius: 50%;
  animation: fmPulse 2s infinite;
}
.fm-pill-bad { background: rgba(226, 75, 74, .10); color: #C0322F; }
.fm-pill-bad .fm-pill-dot { width: 6px; height: 6px; background: var(--sev-high); border-radius: 50%; }
.fm-pill-neutral { background: rgba(136, 135, 128, .10); color: var(--t3, var(--t-muted)); }
.fm-pill-neutral .fm-pill-dot { width: 6px; height: 6px; background: #C8C7C0; border-radius: 50%; }
.fm-btn-ghost {
  height: 28px;
  padding: 0 11px;
  background: transparent;
  border: 1px solid var(--border-hard);
  border-radius: 7px;
  font-size: 11px;
  color: var(--t1, #1E2A4A);
  font-family: inherit;
  cursor: pointer;
}
.fm-btn-ghost:disabled, .fm-btn-icon:disabled { opacity: .45; cursor: not-allowed; }
.fm-btn-ghost:hover:not(:disabled) {
  background: rgba(127, 119, 221, .05);
  border-color: #7F77DD;
  color: var(--p-deep);
}
@keyframes fmPulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: .5; transform: scale(1.3); }
}
</style>
