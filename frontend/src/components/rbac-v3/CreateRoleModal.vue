<script setup lang="ts">
import { ref } from 'vue';
import { rolesApiExt, levelsToPermissions } from '@/api/rbacV3';
import type { AccessLevel } from '@/composables/usePermissions';
import ModuleSelectGrid from './ModuleSelectGrid.vue';
import ModalShell from '@/components/ModalShell.vue';

const props = defineProps<{
  prefillFromCode?: string; // when "duplicate" — copy permissions from this role
  prefillName?: string;
  prefillDescription?: string;
  prefillLevels?: Record<string, AccessLevel>;
}>();
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'created', code: string): void;
}>();

const code = ref('');
const nameRu = ref(props.prefillName || '');
const description = ref(props.prefillDescription || '');
const levels = ref<Record<string, AccessLevel>>(props.prefillLevels || {});
const saving = ref(false);
const error = ref<string | null>(null);

function setAll(level: AccessLevel) {
  const next: Record<string, AccessLevel> = {};
  // Use MODULE_REGISTRY to ensure all keys exist
  import('@/composables/usePermissions').then(m => {
    for (const mod of m.MODULE_REGISTRY) next[mod.code] = level;
    levels.value = next;
  });
}

async function submit() {
  if (!code.value.trim() || !nameRu.value.trim()) {
    error.value = 'Code и название обязательны';
    return;
  }
  if (!/^[a-z][a-z0-9_]*$/.test(code.value.trim())) {
    error.value = 'Code: только lowercase, цифры, _ (начинается с буквы)';
    return;
  }
  saving.value = true; error.value = null;
  try {
    const permission_codes = levelsToPermissions(levels.value);
    const r = await rolesApiExt.create({
      code: code.value.trim(),
      name_ru: nameRu.value.trim(),
      description_ru: description.value.trim() || undefined,
      permission_codes,
    });
    emit('created', r.code);
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Не удалось создать роль';
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <ModalShell :open="true" size="lg" @close="emit('close')">
    <template #header>
      <div class="rv3-modal-hd">
        {{ prefillFromCode ? 'Дублировать роль ' + prefillFromCode : 'Новая роль' }}
      </div>
    </template>

    <div class="rv3-form-grid">
      <div>
        <div class="rv3-edit-label">Code (slug)</div>
        <input v-model="code" class="rv3-input" placeholder="mining_analyst" autofocus />
        <div class="rv3-input-hint">только lowercase, цифры, _ (начинается с буквы)</div>
      </div>
      <div>
        <div class="rv3-edit-label">Название</div>
        <input v-model="nameRu" class="rv3-input" placeholder="Аналитик горнодобывающей отрасли" />
      </div>
    </div>

    <div class="rv3-edit-label" style="margin-top:14px">Описание</div>
    <textarea v-model="description" class="rv3-textarea" placeholder="Назначение роли" />

    <div class="rv3-edit-label" style="margin-top:14px;display:flex;align-items:center;justify-content:space-between">
      <span>Доступ к модулям</span>
      <div style="display:flex;gap:4px;">
        <button class="rv3-quick-btn rv3-quick-admin" type="button" @click="setAll('admin')">ВСЕ ADMIN</button>
        <button class="rv3-quick-btn" type="button" @click="setAll('read')">ВСЕ READ</button>
        <button class="rv3-quick-btn" type="button" @click="setAll('none')">СБРОС</button>
      </div>
    </div>
    <ModuleSelectGrid
      :model-value="levels"
      :editable="true"
      :columns="4"
      @update:model-value="(v) => levels = v"
    />

    <div v-if="error" class="rv3-form-err">{{ error }}</div>

    <template #footer>
      <button class="rv3-btn rv3-btn-ghost" @click="emit('close')" :disabled="saving">Отмена</button>
      <button class="rv3-save" :disabled="saving" @click="submit">
        {{ saving ? 'Создание...' : 'Создать роль' }}
      </button>
    </template>
  </ModalShell>
</template>

<style scoped>
/* Обёртка/шапка/футер — из ModalShell (Teleport + ESC + фокус-трап + --z-top). */
.rv3-modal-hd { font-size: 15px; font-weight: 500; letter-spacing: -.01em; }
.rv3-form-grid {
  display: grid; grid-template-columns: 1fr 2fr; gap: 14px;
}
@media (max-width: 560px) { .rv3-form-grid { grid-template-columns: 1fr; } }
.rv3-edit-label {
  font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted));
  letter-spacing: .06em; text-transform: uppercase; margin-bottom: 5px;
}
.rv3-input, .rv3-textarea {
  width: 100%; padding: 8px 12px;
  border: 0.5px solid var(--border-hard); border-radius: 8px;
  font-size: 12px; color: var(--t1, #1E2A4A); outline: none;
  font-family: inherit;
}
.rv3-textarea { resize: vertical; min-height: 48px; }
.rv3-input-hint { margin-top: 4px; font-size: 10px; color: var(--t3, var(--t-muted)); }
.rv3-quick-btn {
  padding: 4px 11px;
  background: rgba(124,111,247,.10); color: #534AB7;
  border: none; border-radius: 999px;
  font-size: 9.5px; font-weight: 600;
  letter-spacing: .04em; cursor: pointer; font-family: var(--font);
  transition: background .14s;
}
.rv3-quick-btn:hover { background: rgba(124,111,247,.20); }
.rv3-quick-admin { background: rgba(29,158,117,.12) !important; color: #1D9E75 !important; }
.rv3-quick-admin:hover { background: rgba(29,158,117,.22) !important; }
.rv3-form-err {
  margin-top: 12px; padding: 8px 11px;
  background: rgba(226,75,74,.08); border: 0.5px solid rgba(226,75,74,.3);
  border-radius: 7px; font-size: 11.5px; color: #A82C2B;
}
.rv3-btn { padding: 7px 14px; border-radius: 8px; font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit; }
.rv3-btn-ghost { background: transparent; border: 1px solid var(--border-hard); color: var(--t1, #1E2A4A); }
.rv3-save {
  padding: 7px 14px;
  background: var(--green); color: #fff; border: none; border-radius: 8px;
  font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit;
}
.rv3-save:disabled { background: var(--border-hard); color: var(--t3, var(--t-muted)); cursor: not-allowed; }
</style>
