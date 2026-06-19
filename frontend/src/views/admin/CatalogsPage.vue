<script setup lang="ts">
/**
 * Admin → Каталоги: единая страница для управления:
 *   • Направления (transformation directions)
 *   • Консультанты (consultancy firms)
 *
 * Permission gate: requires `companies.edit` OR `tasks.manage` OR owner.
 * Router-level check happens in routes meta — this page assumes the user
 * already passed it.
 */
import { ref, onMounted, computed } from "vue";
import { directionsApi, type DirectionBrief } from "@/api/directions";
import { consultantsApi, type ConsultantBrief } from "@/api/consultants";
import { useDirectionsStore } from "@/stores/directions";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import BIcon from "@/components/broadcasts/BIcon.vue";

const directionsStore = useDirectionsStore();
const toast = useToast();
const { confirmDialog, promptDialog } = useConfirm();

type Tab = "directions" | "consultants";
const activeTab = ref<Tab>("directions");

// ─── Directions ───────────────────────────────────────────────────
const directions = ref<DirectionBrief[]>([]);
const dirsLoading = ref(false);
const dirsError = ref<string | null>(null);
const dirEditor = ref<Partial<DirectionBrief & { isNew?: boolean }>>({});
const dirEditorOpen = ref(false);

async function loadDirections() {
  dirsLoading.value = true;
  dirsError.value = null;
  try {
    directions.value = await directionsApi.list();
  } catch (e: any) {
    dirsError.value = e?.response?.data?.detail || "Не удалось загрузить направления";
  } finally {
    dirsLoading.value = false;
  }
}

function openCreateDir() {
  dirEditor.value = {
    isNew: true,
    label: "",
    code: "",
    color: "#7F77DD",
    sort_order: 999,
    is_custom: true,
  };
  dirEditorOpen.value = true;
}

function openEditDir(d: DirectionBrief) {
  dirEditor.value = { ...d, isNew: false };
  dirEditorOpen.value = true;
}

async function saveDir() {
  const v = dirEditor.value;
  if (!v.label || !v.label.trim()) {
    toast.error("Название обязательно");
    return;
  }
  try {
    if (v.isNew) {
      await directionsApi.create({
        name_ru: v.label.trim(),
        code: (v.code || "").trim() || undefined,
        name_uz: v.name_uz || null,
        name_en: v.name_en || null,
        description: v.description || null,
        sort_order: v.sort_order ?? 999,
        color: v.color || null,
      });
    } else if (v.id) {
      await directionsApi.update(v.id, {
        name_ru: v.label,
        name_uz: v.name_uz,
        name_en: v.name_en,
        description: v.description,
        sort_order: v.sort_order,
        color: v.color,
      });
    }
    dirEditorOpen.value = false;
    await loadDirections();
    await directionsStore.reload();
    toast.success("Направление сохранено");
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Ошибка сохранения");
  }
}

async function deleteDir(d: DirectionBrief) {
  let usage: { tasks: number; projects: number } = { tasks: 0, projects: 0 };
  try {
    usage = await directionsApi.usage(d.id);
  } catch { /* fallthrough — treat as 0 */ }

  const total = usage.tasks + usage.projects;
  const otherDirs = directions.value.filter(x => x.id !== d.id);

  let reassignTo: string | undefined = undefined;
  if (total > 0) {
    const otherList = otherDirs.map((x, i) => `  ${i + 1}. ${x.label} (${x.code})`).join("\n");
    const userChoice = await promptDialog({
      message:
        `Направление «${d.label}» используется в ${usage.tasks} задачах и ${usage.projects} проектах.\n\n` +
        `Введите НОМЕР направления для переноса этих записей,\n` +
        `или оставьте пустым чтобы убрать направление (станет «без направления»),\n` +
        `или введите «-» для отмены:\n\n` + otherList,
    });
    if (userChoice === null || userChoice === "-") return;
    if (userChoice.trim()) {
      const idx = parseInt(userChoice.trim(), 10) - 1;
      if (idx < 0 || idx >= otherDirs.length || Number.isNaN(idx)) {
        toast.error("Неверный номер");
        return;
      }
      reassignTo = otherDirs[idx].code;
    }
  } else {
    if (!(await confirmDialog({
      message: `Удалить направление «${d.label}»?\n\nНи одна задача или проект не используют это направление — удаление безопасно.`,
      danger: true,
    }))) return;
  }

  try {
    await directionsApi.remove(d.id, reassignTo ? { reassignTo } : undefined);
    await loadDirections();
    await directionsStore.reload();
    toast.success("Направление удалено");
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Ошибка удаления");
  }
}

// ─── Consultants ──────────────────────────────────────────────────
const consultants = ref<ConsultantBrief[]>([]);
const consLoading = ref(false);
const consError = ref<string | null>(null);
const consEditor = ref<Partial<ConsultantBrief & { isNew?: boolean }>>({});
const consEditorOpen = ref(false);
const showInactive = ref(false);
const visibleConsultants = computed(() =>
  showInactive.value ? consultants.value : consultants.value.filter(c => c.is_active !== false),
);

async function loadConsultants() {
  consLoading.value = true;
  consError.value = null;
  try {
    consultants.value = await consultantsApi.listAll();
  } catch (e: any) {
    consError.value = e?.response?.data?.detail || "Не удалось загрузить консультантов";
  } finally {
    consLoading.value = false;
  }
}

function openCreateCons() {
  consEditor.value = {
    isNew: true, name_ru: "", code: "", abbr: "", color_hex: "#7F77DD",
    is_big4: false, is_active: true,
  };
  consEditorOpen.value = true;
}

function openEditCons(c: ConsultantBrief) {
  consEditor.value = { ...c, isNew: false };
  consEditorOpen.value = true;
}

async function saveCons() {
  const v = consEditor.value;
  if (!v.name_ru || !v.name_ru.trim()) {
    toast.error("Название обязательно");
    return;
  }
  try {
    if (v.isNew) {
      await consultantsApi.create({
        name: v.name_ru.trim(),
        code: (v.code || "").trim() || undefined,
        name_en: v.name_en || null,
        abbr: v.abbr || null,
        color: v.color_hex || null,
        is_big4: !!v.is_big4,
        is_active: v.is_active !== false,
      });
    } else if (v.id) {
      await consultantsApi.update(v.id, {
        name: v.name_ru,
        name_en: v.name_en,
        abbr: v.abbr,
        color: v.color_hex,
        is_big4: v.is_big4,
        is_active: v.is_active,
      });
    }
    consEditorOpen.value = false;
    await loadConsultants();
    toast.success("Консультант сохранён");
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Ошибка сохранения");
  }
}

async function toggleConsActive(c: ConsultantBrief) {
  try {
    await consultantsApi.update(c.id, { is_active: !c.is_active });
    await loadConsultants();
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Ошибка");
  }
}

async function hardDeleteCons(c: ConsultantBrief) {
  let assignments = 0;
  try {
    const u = await consultantsApi.usage(c.id);
    assignments = u.assignments;
  } catch { /* fall through */ }

  const msg = assignments > 0
    ? `УДАЛИТЬ ПОЛНОСТЬЮ «${c.name_ru}»?\n\n` +
      `Будут также удалены ${assignments} привязок к задачам/проектам (каскадно).\n` +
      `Это необратимо.\n\n` +
      `Если хочешь сохранить историю — закрой «Активен» вместо полного удаления.`
    : `УДАЛИТЬ ПОЛНОСТЬЮ «${c.name_ru}»?\n\n` +
      `Ни одной активной привязки нет — удаление безопасно. Это необратимо.`;

  if (!(await confirmDialog({ message: msg, danger: true }))) return;
  try {
    await consultantsApi.remove(c.id, { hard: true });
    await loadConsultants();
    toast.success("Консультант удалён");
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || "Ошибка удаления");
  }
}

onMounted(() => {
  loadDirections();
  loadConsultants();
});
</script>

<template>
  <div class="cat-page">
    <header class="cat-header">
      <div>
        <div class="cat-eyebrow">Администрирование</div>
        <h1 class="cat-title">Каталоги</h1>
        <p class="cat-sub">Управление направлениями трансформации и консультационными фирмами</p>
      </div>
      <div class="cat-tabs">
        <button :class="['cat-tab', { active: activeTab === 'directions' }]" @click="activeTab = 'directions'">
          Направления <span class="cat-tab-count">{{ directions.length }}</span>
        </button>
        <button :class="['cat-tab', { active: activeTab === 'consultants' }]" @click="activeTab = 'consultants'">
          Консультанты <span class="cat-tab-count">{{ consultants.filter(c => c.is_active !== false).length }}</span>
        </button>
      </div>
    </header>

    <!-- ════════════ DIRECTIONS ════════════ -->
    <section v-if="activeTab === 'directions'" class="cat-panel">
      <div class="cat-toolbar">
        <button class="cat-btn-primary" @click="openCreateDir"><BIcon name="plus" :size="14" /> Новое направление</button>
        <button class="cat-btn-ghost" @click="loadDirections" :disabled="dirsLoading"><BIcon name="refresh" :size="13" /> Обновить</button>
      </div>

      <div v-if="dirsLoading" class="cat-state">Загрузка…</div>
      <div v-else-if="dirsError" class="cat-state cat-state-err">{{ dirsError }}</div>
      <div v-else class="cat-list">
        <div v-for="d in directions" :key="d.id" class="cat-row">
          <div class="cat-row-color" :style="{ background: d.color }"></div>
          <div class="cat-row-main">
            <div class="cat-row-name">{{ d.label }}
              <span v-if="!d.is_custom" class="cat-row-tag" title="Встроенное направление">встроенное</span>
              <span v-else class="cat-row-tag cat-row-tag-custom">кастомное</span>
            </div>
            <div class="cat-row-meta">
              <code>{{ d.code }}</code>
              <span v-if="d.name_en">· EN: {{ d.name_en }}</span>
              <span v-if="d.name_uz">· UZ: {{ d.name_uz }}</span>
              <span>· sort: {{ d.sort_order }}</span>
            </div>
            <div v-if="d.description" class="cat-row-desc">{{ d.description }}</div>
          </div>
          <div class="cat-row-actions">
            <button class="cat-btn-icon" title="Редактировать" @click="openEditDir(d)"><BIcon name="edit" :size="14" /></button>
            <button class="cat-btn-icon cat-btn-icon-danger"
                    :title="d.is_custom ? 'Удалить' : 'Удалить встроенное направление (с переносом записей)'"
                    @click="deleteDir(d)"><BIcon name="trash" :size="14" /></button>
          </div>
        </div>
      </div>
    </section>

    <!-- ════════════ CONSULTANTS ════════════ -->
    <section v-if="activeTab === 'consultants'" class="cat-panel">
      <div class="cat-toolbar">
        <button class="cat-btn-primary" @click="openCreateCons"><BIcon name="plus" :size="14" /> Новый консультант</button>
        <button class="cat-btn-ghost" @click="loadConsultants" :disabled="consLoading"><BIcon name="refresh" :size="13" /> Обновить</button>
        <label class="cat-checkbox">
          <input type="checkbox" v-model="showInactive" />
          <span>Показать неактивные</span>
        </label>
      </div>

      <div v-if="consLoading" class="cat-state">Загрузка…</div>
      <div v-else-if="consError" class="cat-state cat-state-err">{{ consError }}</div>
      <div v-else class="cat-list">
        <div v-for="c in visibleConsultants" :key="c.id"
             class="cat-row" :class="{ 'cat-row-inactive': c.is_active === false }">
          <div class="cat-row-color" :style="{ background: c.color_hex || '#7F77DD' }">
            <span v-if="c.abbr" class="cat-row-abbr">{{ c.abbr }}</span>
          </div>
          <div class="cat-row-main">
            <div class="cat-row-name">{{ c.name_ru }}
              <span v-if="c.is_big4" class="cat-row-tag cat-row-tag-big4">Big-4</span>
              <span v-if="c.is_active === false" class="cat-row-tag">неактивен</span>
            </div>
            <div class="cat-row-meta">
              <code>{{ c.code }}</code>
              <span v-if="c.name_en">· EN: {{ c.name_en }}</span>
            </div>
          </div>
          <div class="cat-row-actions">
            <button class="cat-btn-icon" :title="c.is_active === false ? 'Активировать' : 'Деактивировать'"
                    @click="toggleConsActive(c)">
              <BIcon :name="c.is_active === false ? 'refresh' : 'power'" :size="14" />
            </button>
            <button class="cat-btn-icon" title="Редактировать" @click="openEditCons(c)"><BIcon name="edit" :size="14" /></button>
            <button class="cat-btn-icon cat-btn-icon-danger" title="Удалить полностью"
                    @click="hardDeleteCons(c)"><BIcon name="trash" :size="14" /></button>
          </div>
        </div>
      </div>
    </section>

    <!-- ════════════ Direction editor modal ════════════ -->
    <div v-if="dirEditorOpen" class="cat-modal-bg" @click.self="dirEditorOpen = false">
      <div class="cat-modal">
        <header class="cat-modal-head">
          <h2>{{ dirEditor.isNew ? "Новое направление" : "Редактирование направления" }}</h2>
          <button class="cat-x" @click="dirEditorOpen = false">×</button>
        </header>
        <div class="cat-modal-body">
          <label class="cat-fld">
            <span>Название (RU) *</span>
            <input v-model="dirEditor.label" type="text" placeholder="Стратегическое управление" />
          </label>
          <label v-if="dirEditor.isNew" class="cat-fld">
            <span>Код (a-z, 0-9, _) — авто-генерация если пусто</span>
            <input v-model="dirEditor.code" type="text" placeholder="strategy" />
          </label>
          <div class="cat-fld-row">
            <label class="cat-fld">
              <span>Название (UZ)</span>
              <input v-model="dirEditor.name_uz" type="text" />
            </label>
            <label class="cat-fld">
              <span>Название (EN)</span>
              <input v-model="dirEditor.name_en" type="text" />
            </label>
          </div>
          <label class="cat-fld">
            <span>Описание</span>
            <textarea v-model="dirEditor.description" rows="2"></textarea>
          </label>
          <div class="cat-fld-row">
            <label class="cat-fld cat-fld-narrow">
              <span>Цвет</span>
              <input v-model="dirEditor.color" type="color" />
            </label>
            <label class="cat-fld">
              <span>Порядок</span>
              <input v-model.number="dirEditor.sort_order" type="number" />
            </label>
          </div>
        </div>
        <footer class="cat-modal-foot">
          <button class="cat-btn-ghost" @click="dirEditorOpen = false">Отмена</button>
          <button class="cat-btn-primary" @click="saveDir">Сохранить</button>
        </footer>
      </div>
    </div>

    <!-- ════════════ Consultant editor modal ════════════ -->
    <div v-if="consEditorOpen" class="cat-modal-bg" @click.self="consEditorOpen = false">
      <div class="cat-modal">
        <header class="cat-modal-head">
          <h2>{{ consEditor.isNew ? "Новый консультант" : "Редактирование консультанта" }}</h2>
          <button class="cat-x" @click="consEditorOpen = false">×</button>
        </header>
        <div class="cat-modal-body">
          <label class="cat-fld">
            <span>Название (RU) *</span>
            <input v-model="consEditor.name_ru" type="text" placeholder="PwC Узбекистан" />
          </label>
          <label v-if="consEditor.isNew" class="cat-fld">
            <span>Код — авто-генерация если пусто</span>
            <input v-model="consEditor.code" type="text" placeholder="pwc" />
          </label>
          <div class="cat-fld-row">
            <label class="cat-fld">
              <span>Аббревиатура (для бейджа)</span>
              <input v-model="consEditor.abbr" type="text" maxlength="6" placeholder="PwC" />
            </label>
            <label class="cat-fld">
              <span>Название (EN)</span>
              <input v-model="consEditor.name_en" type="text" />
            </label>
          </div>
          <div class="cat-fld-row">
            <label class="cat-fld cat-fld-narrow">
              <span>Цвет бейджа</span>
              <input v-model="consEditor.color_hex" type="color" />
            </label>
            <label class="cat-fld cat-fld-narrow cat-fld-check">
              <input v-model="consEditor.is_big4" type="checkbox" />
              <span>Big-4</span>
            </label>
            <label class="cat-fld cat-fld-narrow cat-fld-check">
              <input v-model="consEditor.is_active" type="checkbox" />
              <span>Активен</span>
            </label>
          </div>
        </div>
        <footer class="cat-modal-foot">
          <button class="cat-btn-ghost" @click="consEditorOpen = false">Отмена</button>
          <button class="cat-btn-primary" @click="saveCons">Сохранить</button>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cat-page { padding: 24px 28px; max-width: 1280px; margin: 0 auto; font-family: -apple-system, system-ui, sans-serif; }
.cat-header { display: flex; justify-content: space-between; align-items: flex-end; gap: 24px; margin-bottom: 22px; flex-wrap: wrap; }
.cat-eyebrow { font-size: 10px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .08em; }
.cat-title { font-size: 24px; font-weight: 500; color: var(--t1, #1E2A4A); margin: 4px 0 2px; letter-spacing: -.01em; }
.cat-sub { font-size: 13px; color: var(--t3, var(--t-muted)); margin: 0; }
.cat-tabs { display: flex; gap: 4px; background: #F3F4F8; border-radius: 10px; padding: 3px; }
.cat-tab {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border-radius: 8px;
  font-size: 12px; font-weight: 500; color: var(--t3, var(--t-muted));
  background: transparent; border: none; cursor: pointer; font-family: inherit;
}
.cat-tab.active { background: white; color: var(--t1, #1E2A4A); box-shadow: 0 1px 3px rgba(15,23,60,.08); }
.cat-tab-count { padding: 1px 7px; background: rgba(127,119,221,.12); color: var(--p-deep); border-radius: 6px; font-size: 10.5px; }

.cat-panel { background: #F6F7FB; border: 0.5px solid var(--border-hard); border-radius: 14px; padding: 16px 18px; }
.cat-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.cat-btn-primary {
  padding: 7px 14px; border-radius: 8px; border: none;
  background: #7F77DD; color: white; font-size: 12px; font-weight: 500;
  cursor: pointer; font-family: inherit;
  display: inline-flex; align-items: center; gap: 6px;
}
.cat-btn-primary:hover { background: #6E66D0; }
.cat-btn-ghost {
  padding: 7px 12px; border-radius: 8px;
  background: transparent; border: 0.5px solid var(--border-hard); color: var(--t3, var(--t-muted));
  font-size: 12px; font-weight: 500; cursor: pointer; font-family: inherit;
  display: inline-flex; align-items: center; gap: 6px;
}
.cat-btn-ghost:hover { border-color: #7F77DD; color: var(--p-deep); }
.cat-checkbox { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--t3, var(--t-muted)); margin-left: auto; }

.cat-list { display: flex; flex-direction: column; gap: 8px; }
.cat-row {
  display: grid; grid-template-columns: 44px 1fr auto;
  gap: 14px; align-items: center;
  padding: 12px 14px; border-radius: 12px;
  border: 0.5px solid var(--border-hard, #E5E7EB);
  background: #fff;
  transition: transform .16s var(--ease-standard, cubic-bezier(.34,1.2,.64,1)), box-shadow .16s, border-color .16s;
}
.cat-row:hover {
  transform: translateY(-1px);
  border-color: rgba(127,119,221,.4);
  box-shadow: 0 4px 16px rgba(15,23,60,.07), 0 1px 3px rgba(15,23,60,.05);
}
.cat-row-inactive { opacity: 0.55; }
.cat-row-color {
  width: 40px; height: 40px; border-radius: 11px;
  display: flex; align-items: center; justify-content: center;
  color: white; font-size: 11px; font-weight: 700;
  box-shadow: 0 2px 8px rgba(15,23,60,.12);
}
.cat-row-abbr { letter-spacing: .02em; }
.cat-row-name { font-size: 14px; font-weight: 500; color: var(--t1, #1E2A4A); }
.cat-row-tag {
  display: inline-block; margin-left: 8px;
  font-size: 9.5px; font-weight: 500; color: var(--t3, var(--t-muted));
  background: #F3F4F8; padding: 1px 7px; border-radius: 5px;
  letter-spacing: .04em; text-transform: uppercase;
}
.cat-row-tag-custom { background: rgba(127,119,221,.14); color: var(--p-deep); }
.cat-row-tag-big4 { background: rgba(239,159,39,.14); color: #B27015; }
.cat-row-meta { font-size: 11px; color: var(--t3, var(--t-muted)); margin-top: 2px; }
.cat-row-meta code { background: #F3F4F8; padding: 1px 5px; border-radius: 4px; font-size: 10.5px; }
.cat-row-desc { font-size: 11.5px; color: var(--p-deep); margin-top: 4px; max-width: 560px; }
.cat-row-actions { display: flex; gap: 4px; }
.cat-btn-icon {
  width: 28px; height: 28px;
  background: transparent; border: 0.5px solid var(--border-hard);
  border-radius: 6px; cursor: pointer; font-size: 14px; color: var(--t3, var(--t-muted));
  display: inline-flex; align-items: center; justify-content: center; font-family: inherit;
}
.cat-btn-icon:hover { border-color: #7F77DD; color: var(--p-deep); }
.cat-btn-icon-danger:hover { border-color: var(--sev-high); color: #B91C1C; background: rgba(226,75,74,.06); }

.cat-state { padding: 40px; text-align: center; font-size: 13px; color: var(--t3, var(--t-muted)); }
.cat-state-err { color: var(--sev-high); }

/* Modal */
.cat-modal-bg {
  position: fixed; inset: 0; z-index: 1000;
  background: rgba(15,18,40,.45); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center; padding: 24px;
}
.cat-modal {
  background: white; border-radius: 14px;
  width: 100%; max-width: 520px; max-height: 90vh; overflow-y: auto;
  box-shadow: 0 24px 64px rgba(15,23,60,.18), 0 8px 24px rgba(15,23,60,.08);
  animation: catModalIn .35s var(--ease-standard);
}
@keyframes catModalIn { from { opacity: 0; transform: translateY(8px) scale(.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
.cat-modal-head { padding: 18px 20px 6px; display: flex; justify-content: space-between; align-items: center; border-bottom: 0.5px solid #F0F0F4; }
.cat-modal-head h2 { font-size: 15px; font-weight: 500; color: var(--t1, #1E2A4A); margin: 0; }
.cat-x { background: transparent; border: none; font-size: 22px; color: var(--t3, var(--t-muted)); cursor: pointer; font-family: inherit; }
.cat-x:hover { color: var(--sev-high); }
.cat-modal-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.cat-modal-foot { padding: 12px 20px 18px; display: flex; justify-content: flex-end; gap: 8px; }

.cat-fld { display: flex; flex-direction: column; gap: 6px; flex: 1; }
.cat-fld > span:first-child { font-size: 10.5px; font-weight: 500; color: var(--t3, var(--t-muted)); text-transform: uppercase; letter-spacing: .04em; }
.cat-fld input[type="text"], .cat-fld input[type="number"], .cat-fld textarea {
  padding: 8px 10px; border: 0.5px solid var(--border-hard); border-radius: 7px;
  font-size: 12.5px; font-family: inherit; color: var(--t1, #1E2A4A);
  background: var(--bg2, #FAFAFC); outline: none;
}
.cat-fld input:focus, .cat-fld textarea:focus { border-color: #7F77DD; background: white; }
.cat-fld input[type="color"] { padding: 1px; width: 56px; height: 32px; cursor: pointer; }
.cat-fld-row { display: flex; gap: 10px; }
.cat-fld-narrow { flex: 0 0 auto; }
.cat-fld-check { flex-direction: row; align-items: center; gap: 6px; padding: 8px 10px; border: 0.5px solid var(--border-hard); border-radius: 7px; background: var(--bg2, #FAFAFC); cursor: pointer; }
.cat-fld-check span { font-size: 12px; color: var(--t1, #1E2A4A); text-transform: none; letter-spacing: 0; }

/* ═══════════ MOBILE (Phase 2) ═══════════ */
@media (max-width: 768px) {
  .cat-page { padding: 14px 12px; }
  .cat-toolbar { flex-wrap: wrap; }
  .cat-fld-row { flex-wrap: wrap; }
}
</style>
