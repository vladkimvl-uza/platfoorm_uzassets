<script setup lang="ts">
import { onMounted, ref } from "vue";
import {
  sectorsAdminV2Api,
  COLOR_PALETTE, SECTOR_ICONS,
  type SectorAdmin,
} from "@/api/companiesAdminV2";

const sectors = ref<SectorAdmin[]>([]);
const editing = ref<SectorAdmin | null>(null);
const error = ref<string | null>(null);
const showCreate = ref(false);
const createForm = ref<{ code: string; name_ru: string; color_hex: string }>({ code: "", name_ru: "", color_hex: "#7F77DD" });

const aliasInput = ref("");

async function load() {
  try {
    sectors.value = await sectorsAdminV2Api.list();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  }
}

onMounted(load);

function startEdit(s: SectorAdmin) {
  editing.value = JSON.parse(JSON.stringify(s));
  aliasInput.value = "";
}

async function saveSector() {
  if (!editing.value) return;
  try {
    const updated = await sectorsAdminV2Api.update(editing.value.code, editing.value);
    const idx = sectors.value.findIndex(s => s.code === updated.code);
    if (idx >= 0) sectors.value[idx] = updated;
    editing.value = null;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  }
}

async function deleteSector(code: string) {
  if (!confirm(`Удалить сектор "${code}"?`)) return;
  try {
    await sectorsAdminV2Api.remove(code);
    await load();
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  }
}

async function createSector() {
  if (!createForm.value.code || !createForm.value.name_ru) return;
  try {
    await sectorsAdminV2Api.create(createForm.value as any);
    await load();
    showCreate.value = false;
    createForm.value = { code: "", name_ru: "", color_hex: "#7F77DD" };
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message;
  }
}

function addAlias() {
  if (!editing.value || !aliasInput.value.trim()) return;
  editing.value.aliases = [...(editing.value.aliases || []), aliasInput.value.trim()];
  aliasInput.value = "";
}
function removeAlias(a: string) {
  if (!editing.value) return;
  editing.value.aliases = (editing.value.aliases || []).filter(x => x !== a);
}

function gradientCss(s: SectorAdmin | null): string {
  if (!s || !s.color_hex) return "#7F77DD";
  if (s.color_secondary) return `linear-gradient(135deg, ${s.color_hex}, ${s.color_secondary})`;
  return s.color_hex;
}
</script>

<template>
  <div class="sa-wrap">
    <div v-if="error" class="sa-error">{{ error }} <button @click="error = null">×</button></div>

    <div class="sa-card">
      <div class="sa-card-hd">
        <span class="sa-card-ttl">Сектора · {{ sectors.length }}</span>
        <button class="sa-btn sa-btn-primary" @click="showCreate = true">+ Сектор</button>
      </div>

      <div class="sa-list">
        <div v-for="s in sectors" :key="s.code" class="sa-row uza-side-stripe-host">
          <span class="uza-stripe-el" :style="{ '--stripe-color': s.color_hex || '#888780' }" />
          <span class="sa-icn" :style="{ background: gradientCss(s) }">
            <i v-if="s.icon_name" :class="`ti ti-${s.icon_name}`" style="font-size: 18px; color: #fff" aria-hidden="true"></i>
            <span v-else style="color: #fff; font-size: 12px; font-weight: 500;">{{ s.code.slice(0, 2).toUpperCase() }}</span>
          </span>
          <div class="sa-info">
            <div class="sa-name">
              {{ s.name_ru }}
              <span v-if="s.short_badge" class="sa-bdg" :style="{ background: s.color_hex || '#888780' }">{{ s.short_badge }}</span>
            </div>
            <div class="sa-sub">{{ s.code }} · {{ s.companies_count }} компаний</div>
          </div>
          <div class="sa-actions">
            <button class="sa-btn sa-btn-ghost" @click="startEdit(s)">Редактировать</button>
            <button class="sa-btn sa-btn-red" :disabled="s.companies_count > 0" @click="deleteSector(s.code)">×</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Edit panel -->
    <div v-if="editing" class="sa-card sa-edit-card">
      <div class="sa-card-hd">
        <span class="sa-card-ttl">Редактирование: {{ editing.name_ru }}</span>
        <div style="display:flex;gap:6px">
          <button class="sa-btn sa-btn-ghost" @click="editing = null">Отмена</button>
          <button class="sa-btn sa-btn-primary" @click="saveSector">Сохранить</button>
        </div>
      </div>

      <div class="sa-edit-body">
        <div class="sa-grid-2">
          <div class="sa-f">
            <label>Название (RU)</label>
            <input v-model="editing.name_ru"/>
          </div>
          <div class="sa-f">
            <label>Short badge</label>
            <input v-model="editing.short_badge" maxlength="8" placeholder="MINE" class="sa-mono"/>
          </div>
          <div class="sa-f">
            <label>Название (UZ)</label>
            <input v-model="editing.name_uz"/>
          </div>
          <div class="sa-f">
            <label>Название (EN)</label>
            <input v-model="editing.name_en"/>
          </div>
        </div>

        <div class="sa-section-l">Цвет</div>
        <div class="sa-grid-2">
          <div>
            <div class="sa-mini-l">Primary</div>
            <div class="sa-row-flex">
              <button v-for="col in COLOR_PALETTE.slice(0, 8)" :key="col"
                      class="sa-swatch" :class="{ active: editing.color_hex === col }"
                      :style="{ background: col }" @click="editing.color_hex = col"></button>
              <input v-model="editing.color_hex" class="sa-hex"/>
            </div>
          </div>
          <div>
            <div class="sa-mini-l">Secondary (gradient)</div>
            <div class="sa-row-flex">
              <button v-for="col in COLOR_PALETTE.slice(0, 8)" :key="col"
                      class="sa-swatch" :class="{ active: editing.color_secondary === col }"
                      :style="{ background: col }" @click="editing.color_secondary = col"></button>
              <input v-model="editing.color_secondary" class="sa-hex" placeholder="(none)"/>
            </div>
          </div>
        </div>

        <div class="sa-section-l" style="margin-top: 12px">Иконка (Tabler)</div>
        <div class="sa-icons">
          <button v-for="ic in SECTOR_ICONS" :key="ic"
                  class="sa-icon-btn" :class="{ active: editing.icon_name === ic }"
                  @click="editing.icon_name = ic" :title="ic">
            <i :class="`ti ti-${ic}`" style="font-size: 16px;" aria-hidden="true"></i>
          </button>
          <button class="sa-icon-btn" :class="{ active: !editing.icon_name }" @click="editing.icon_name = null">—</button>
        </div>

        <div class="sa-section-l" style="margin-top: 12px">Aliases</div>
        <div class="sa-chips">
          <span v-for="a in (editing.aliases || [])" :key="a" class="sa-chip">
            {{ a }} <button @click="removeAlias(a)">×</button>
          </span>
          <input v-model="aliasInput" @keydown.enter="addAlias" placeholder="+ alias" class="sa-chip-input"/>
        </div>

        <div class="sa-section-l" style="margin-top: 14px">Превью</div>
        <div class="sa-preview">
          <span class="sa-icn" :style="{ background: gradientCss(editing) }">
            <i v-if="editing.icon_name" :class="`ti ti-${editing.icon_name}`" style="font-size: 18px; color: #fff" aria-hidden="true"></i>
          </span>
          <div style="flex:1">
            <div class="sa-name">
              {{ editing.name_ru }}
              <span v-if="editing.short_badge" class="sa-bdg" :style="{ background: editing.color_hex || '#888780' }">{{ editing.short_badge }}</span>
            </div>
            <div class="sa-sub">{{ editing.code }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create modal -->
    <div v-if="showCreate" class="sa-modal-back" @click.self="showCreate = false">
      <div class="sa-modal">
        <div class="sa-modal-hd">Новый сектор</div>
        <div class="sa-modal-body">
          <div class="sa-f">
            <label>Code (latin)</label>
            <input v-model="createForm.code" class="sa-mono" placeholder="construction"/>
          </div>
          <div class="sa-f">
            <label>Название (RU)</label>
            <input v-model="createForm.name_ru" placeholder="Строительство"/>
          </div>
          <div class="sa-f">
            <label>Цвет</label>
            <div class="sa-row-flex">
              <button v-for="col in COLOR_PALETTE.slice(0, 8)" :key="col"
                      class="sa-swatch" :class="{ active: createForm.color_hex === col }"
                      :style="{ background: col }" @click="createForm.color_hex = col"></button>
              <input v-model="createForm.color_hex" class="sa-hex"/>
            </div>
          </div>
        </div>
        <div class="sa-modal-foot">
          <button class="sa-btn sa-btn-ghost" @click="showCreate = false">Отмена</button>
          <button class="sa-btn sa-btn-primary" @click="createSector" :disabled="!createForm.code || !createForm.name_ru">Создать</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sa-wrap { padding: 0; }
.sa-error { background: rgba(226,75,74,.08); color: #A32D2D; padding: 8px 14px; border-radius: 6px; margin-bottom: 10px; display: flex; justify-content: space-between; font-size: 12px; }
.sa-error button { background: transparent; border: 0; color: inherit; cursor: pointer; }
.sa-card { background: #fff; border: 0.5px solid rgba(0,0,0,.06); border-radius: 12px; overflow: hidden; margin-bottom: 12px; }
.sa-card-hd { padding: 12px 16px; border-bottom: 0.5px solid rgba(0,0,0,.06); background: #FAFAFC; display: flex; justify-content: space-between; align-items: center; }
.sa-card-ttl { font-size: 11px; color: #888780; text-transform: uppercase; letter-spacing: .07em; font-weight: 500; }

.sa-btn { border: 0; padding: 5px 12px; border-radius: 6px; font-size: 11px; font-family: inherit; font-weight: 500; cursor: pointer; }
.sa-btn-primary { background: #7F77DD; color: #fff; }
.sa-btn-ghost { background: transparent; border: 0.5px solid rgba(0,0,0,.12); color: #5F5E5A; }
.sa-btn-red { background: rgba(226,75,74,.12); color: #A32D2D; padding: 5px 10px; }
.sa-btn-red:disabled { opacity: .3; cursor: not-allowed; }

.sa-list { padding: 12px 16px; display: flex; flex-direction: column; gap: 8px; }
.sa-row { background: #FAFAFC; border-radius: 8px; padding: 10px 12px 10px 18px; display: flex; align-items: center; gap: 10px; position: relative; overflow: hidden; }
/* sa-row top-stripe удалён — индикатор сектора теперь боковая полоска (.uza-stripe-el) */
.sa-icn { width: 36px; height: 36px; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.sa-info { flex: 1; min-width: 0; }
.sa-name { font-size: 12.5px; color: #1E2A4A; font-weight: 500; display: flex; align-items: center; gap: 6px; }
.sa-bdg { color: #fff; padding: 1px 5px; border-radius: 3px; font-size: 9px; font-weight: 600; letter-spacing: .04em; }
.sa-sub { font-size: 10.5px; color: #888780; }
.sa-actions { display: flex; gap: 5px; }

.sa-edit-body { padding: 14px 16px; }
.sa-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.sa-f { display: flex; flex-direction: column; gap: 3px; margin-bottom: 8px; }
.sa-f label { font-size: 9.5px; color: #888780; text-transform: uppercase; letter-spacing: .06em; }
.sa-f input { padding: 5px 9px; border: 0.5px solid rgba(0,0,0,.12); border-radius: 5px; font-size: 11.5px; outline: none; font-family: inherit; background: #fff; color: #1E2A4A; }
.sa-mono { font-family: monospace !important; text-transform: uppercase; }

.sa-section-l { font-size: 9.5px; color: #888780; text-transform: uppercase; letter-spacing: .07em; font-weight: 500; margin-bottom: 6px; margin-top: 6px; }
.sa-mini-l { font-size: 9.5px; color: #888780; margin-bottom: 4px; }
.sa-row-flex { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
.sa-swatch { width: 22px; height: 22px; border-radius: 5px; border: 0; cursor: pointer; }
.sa-swatch.active { border: 2px solid #1E2A4A; }
.sa-hex { font-family: monospace; padding: 4px 8px; border: 0.5px solid rgba(0,0,0,.1); border-radius: 5px; font-size: 11px; width: 90px; }

.sa-icons { display: flex; gap: 4px; flex-wrap: wrap; }
.sa-icon-btn { width: 28px; height: 28px; background: #fff; border: 0.5px solid rgba(0,0,0,.12); border-radius: 5px; cursor: pointer; display: flex; align-items: center; justify-content: center; color: #888780; font-family: inherit; font-size: 11px; }
.sa-icon-btn.active { border: 2px solid #7F77DD; color: #534AB7; background: rgba(127,119,221,.08); }

.sa-chips { display: flex; gap: 5px; flex-wrap: wrap; }
.sa-chip { background: rgba(55,138,221,.1); color: #185FA5; padding: 3px 9px; border-radius: 5px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; }
.sa-chip button { background: transparent; border: 0; color: inherit; cursor: pointer; font-size: 12px; }
.sa-chip-input { border: 0.5px dashed rgba(0,0,0,.2); background: transparent; padding: 3px 9px; border-radius: 5px; font-size: 11px; outline: none; }

.sa-preview { background: #fff; border-radius: 7px; padding: 10px 12px; display: flex; align-items: center; gap: 10px; border: 0.5px solid rgba(0,0,0,.08); }

.sa-modal-back { position: fixed; inset: 0; background: rgba(15,18,40,.45); backdrop-filter: blur(8px); z-index: 1000; display: flex; align-items: center; justify-content: center; padding: 20px; }
.sa-modal { background: #fff; border-radius: 14px; width: 100%; max-width: 480px; box-shadow: 0 24px 64px rgba(15,23,60,.18); }
.sa-modal-hd { padding: 16px 20px; border-bottom: 0.5px solid rgba(0,0,0,.06); font-size: 15px; font-weight: 500; }
.sa-modal-body { padding: 16px 20px; }
.sa-modal-foot { padding: 12px 20px; border-top: 0.5px solid rgba(0,0,0,.06); display: flex; justify-content: flex-end; gap: 8px; }
</style>
