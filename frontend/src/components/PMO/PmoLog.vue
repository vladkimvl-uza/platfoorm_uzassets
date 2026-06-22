<script setup lang="ts">
/**
 * PmoLog — журнал PMO (PMBOK 7): извлечённые уроки + запросы на изменение.
 *
 * Тоггл между двумя реестрами. Поиск, фильтры (тип/статус/проект), сортировка,
 * упоминания пользователей (пикер), связь с проектами портфеля. Премиум-UX:
 * тосты, мягкое подтверждение удаления, каскадные анимации.
 */
import { ref, computed, watch, onMounted } from "vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import NoteAssigneePicker from "@/components/NoteAssigneePicker.vue";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import {
  pmoApi, type Lesson, type LessonPayload, type LessonKind,
  type ChangeItem, type ChangePayload, type ChangeKind, type ChangeStatus,
} from "@/api/pmo";

const props = defineProps<{
  companyCode: string;
  canEdit?: boolean;
  projects?: { id: string; title: string }[];
}>();

const toast = useToast();
const { confirmDialog } = useConfirm();

const tab = ref<"lessons" | "changes">("lessons");

const L_KINDS: { v: LessonKind; l: string; c: string }[] = [
  { v: "success", l: "Сработало", c: "#1D9E75" },
  { v: "problem", l: "Проблема", c: "#E24B4A" },
  { v: "recommendation", l: "Рекомендация", c: "#7C6FF7" },
];
const LK = Object.fromEntries(L_KINDS.map(k => [k.v, k]));

const C_KINDS: { v: ChangeKind; l: string }[] = [
  { v: "scope", l: "Содержание" }, { v: "schedule", l: "Сроки" },
  { v: "cost", l: "Стоимость" }, { v: "quality", l: "Качество" }, { v: "other", l: "Прочее" },
];
const CK = Object.fromEntries(C_KINDS.map(k => [k.v, k]));
const C_STATUSES: { v: ChangeStatus; l: string; c: string }[] = [
  { v: "proposed", l: "Предложено", c: "#D97706" },
  { v: "approved", l: "Одобрено", c: "#1D9E75" },
  { v: "rejected", l: "Отклонено", c: "#E24B4A" },
  { v: "implemented", l: "Внедрено", c: "#534AB7" },
];
const CS = Object.fromEntries(C_STATUSES.map(s => [s.v, s]));

const loading = ref(true);
const error = ref<string | null>(null);
const lessons = ref<Lesson[]>([]);
const changes = ref<ChangeItem[]>([]);

const projectMap = computed(() => new Map((props.projects || []).map(p => [p.id, p.title])));
function projTitle(id: string | null): string | null {
  if (!id) return null;
  return projectMap.value.get(id) || "Проект";
}
function avInitials(name?: string | null): string {
  const n = (name || "").trim();
  if (!n) return "?";
  const parts = n.split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}

async function load() {
  loading.value = true; error.value = null;
  try {
    const [ls, ch] = await Promise.all([
      pmoApi.listLessons(props.companyCode),
      pmoApi.listChanges(props.companyCode),
    ]);
    lessons.value = ls; changes.value = ch;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "Не удалось загрузить журнал";
  } finally { loading.value = false; }
}
onMounted(load);
watch(() => props.companyCode, load);

// ── Поиск / фильтры / сортировка ──
const search = ref("");
const filterKind = ref<string>("");        // lessons: '' | success | problem | recommendation
const filterStatus = ref<string>("");      // changes: '' | proposed | ...
const filterProject = ref<string>("");     // '' | project_id | '__none__'
const sortKey = ref<"date" | "kind" | "title" | "status">("date");
const sortDir = ref<"asc" | "desc">("desc");

function toggleSort(k: "date" | "kind" | "title" | "status") {
  if (sortKey.value === k) sortDir.value = sortDir.value === "asc" ? "desc" : "asc";
  else { sortKey.value = k; sortDir.value = k === "title" ? "asc" : "desc"; }
}

function _matchProject(pid: string | null): boolean {
  if (!filterProject.value) return true;
  if (filterProject.value === "__none__") return !pid;
  return pid === filterProject.value;
}
function _matchSearch(...fields: (string | null | undefined)[]): boolean {
  const q = search.value.trim().toLowerCase();
  if (!q) return true;
  return fields.some(f => (f || "").toLowerCase().includes(q));
}
function _dir<T>(cmp: number): number { return sortDir.value === "asc" ? cmp : -cmp; }

const shownLessons = computed(() => {
  let arr = lessons.value.filter(it =>
    (!filterKind.value || it.kind === filterKind.value) &&
    _matchProject(it.project_id) &&
    _matchSearch(it.title, it.description, it.recommendation, it.owner_name),
  );
  arr = [...arr].sort((a, b) => {
    if (sortKey.value === "title") return _dir(a.title.localeCompare(b.title));
    if (sortKey.value === "kind") return _dir((a.kind).localeCompare(b.kind));
    return _dir(a.created_at.localeCompare(b.created_at));
  });
  return arr;
});

const shownChanges = computed(() => {
  let arr = changes.value.filter(it =>
    (!filterStatus.value || it.status === filterStatus.value) &&
    (!filterKind.value || it.kind === filterKind.value) &&
    _matchProject(it.project_id) &&
    _matchSearch(it.title, it.description, it.impact, it.requested_by, it.decided_by),
  );
  arr = [...arr].sort((a, b) => {
    if (sortKey.value === "title") return _dir(a.title.localeCompare(b.title));
    if (sortKey.value === "kind") return _dir(a.kind.localeCompare(b.kind));
    if (sortKey.value === "status") return _dir(a.status.localeCompare(b.status));
    return _dir(a.created_at.localeCompare(b.created_at));
  });
  return arr;
});

function resetFilters() {
  search.value = ""; filterKind.value = ""; filterStatus.value = ""; filterProject.value = "";
}
const hasFilters = computed(() => !!(search.value || filterKind.value || filterStatus.value || filterProject.value));

watch(tab, () => { filterKind.value = ""; filterStatus.value = ""; sortKey.value = "date"; sortDir.value = "desc"; });

// ── Урок: форма ──
type LForm = LessonPayload & { owner_id: string | null; project_id: string | null };
const lBlank = (): LForm => ({ kind: "recommendation", title: "", description: "", recommendation: "", owner_id: null, owner_name: "", project_id: null });
const lForm = ref<LForm>(lBlank());
const lEditId = ref<string | null>(null);
const lOpen = ref(false);
const saving = ref(false);
function lCreate() { lForm.value = lBlank(); lEditId.value = null; lOpen.value = true; }
function lEdit(it: Lesson) {
  lForm.value = { kind: it.kind, title: it.title, description: it.description || "", recommendation: it.recommendation || "", owner_id: it.owner_id || null, owner_name: it.owner_name || "", project_id: it.project_id || null };
  lEditId.value = it.id; lOpen.value = true;
}
async function lSave() {
  if (!lForm.value.title?.trim()) { toast.error("Название урока обязательно"); return; }
  saving.value = true; error.value = null;
  try {
    if (lEditId.value) await pmoApi.updateLesson(lEditId.value, lForm.value);
    else await pmoApi.createLesson(props.companyCode, lForm.value);
    lOpen.value = false; await load();
    toast.success(lEditId.value ? "Урок сохранён" : "Урок добавлен");
  } catch (e: any) { toast.error(e?.response?.data?.detail || "Не удалось сохранить урок"); }
  finally { saving.value = false; }
}
async function lRemove(it: Lesson) {
  if (!(await confirmDialog({ message: `Удалить урок «${it.title}»?`, danger: true }))) return;
  try { await pmoApi.deleteLesson(it.id); await load(); toast.success("Урок удалён"); }
  catch (e: any) { toast.error(e?.response?.data?.detail || "Не удалось удалить"); }
}

// ── Изменение: форма ──
type CForm = ChangePayload & { project_id: string | null };
const cBlank = (): CForm => ({ kind: "scope", title: "", description: "", impact: "", requested_by: "", status: "proposed", decided_by: "", project_id: null });
const cForm = ref<CForm>(cBlank());
const cEditId = ref<string | null>(null);
const cOpen = ref(false);
function cCreate() { cForm.value = cBlank(); cEditId.value = null; cOpen.value = true; }
function cEdit(it: ChangeItem) {
  cForm.value = { kind: it.kind, title: it.title, description: it.description || "", impact: it.impact || "", requested_by: it.requested_by || "", status: it.status, decided_by: it.decided_by || "", project_id: it.project_id || null };
  cEditId.value = it.id; cOpen.value = true;
}
async function cSave() {
  if (!cForm.value.title?.trim()) { toast.error("Название изменения обязательно"); return; }
  saving.value = true; error.value = null;
  try {
    if (cEditId.value) await pmoApi.updateChange(cEditId.value, cForm.value);
    else await pmoApi.createChange(props.companyCode, cForm.value);
    cOpen.value = false; await load();
    toast.success(cEditId.value ? "Изменение сохранено" : "Изменение добавлено");
  } catch (e: any) { toast.error(e?.response?.data?.detail || "Не удалось сохранить"); }
  finally { saving.value = false; }
}
async function cRemove(it: ChangeItem) {
  if (!(await confirmDialog({ message: `Удалить изменение «${it.title}»?`, danger: true }))) return;
  try { await pmoApi.deleteChange(it.id); await load(); toast.success("Изменение удалено"); }
  catch (e: any) { toast.error(e?.response?.data?.detail || "Не удалось удалить"); }
}

const fmtDt = (s: string | null) => s ? new Date(s).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "2-digit" }) : "—";
</script>

<template>
  <div class="pl">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />

    <div class="pl-bar">
      <div class="pl-seg">
        <button :class="{ on: tab === 'lessons' }" @click="tab = 'lessons'">Уроки <span class="pl-n">{{ lessons.length }}</span></button>
        <button :class="{ on: tab === 'changes' }" @click="tab = 'changes'">Изменения <span class="pl-n">{{ changes.length }}</span></button>
      </div>
      <button v-if="canEdit && tab === 'lessons'" class="pl-add" @click="lCreate">+ Урок</button>
      <button v-if="canEdit && tab === 'changes'" class="pl-add" @click="cCreate">+ Изменение</button>
    </div>

    <!-- Toolbar: поиск + фильтры + сортировка -->
    <div v-if="!loading" class="pl-tools">
      <div class="pl-search">
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.6" /><path d="M11 11 L14 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" /></svg>
        <input v-model="search" type="text" placeholder="Поиск…" />
        <button v-if="search" class="pl-sx" @click="search = ''">×</button>
      </div>

      <!-- kind chips -->
      <div class="pl-fchips">
        <button class="pl-fchip" :class="{ on: !filterKind }" @click="filterKind = ''">Все</button>
        <template v-if="tab === 'lessons'">
          <button v-for="k in L_KINDS" :key="k.v" class="pl-fchip" :class="{ on: filterKind === k.v }" :style="filterKind === k.v ? { background: k.c + '1a', color: k.c, borderColor: k.c + '55' } : {}" @click="filterKind = k.v">{{ k.l }}</button>
        </template>
        <template v-else>
          <button v-for="k in C_KINDS" :key="k.v" class="pl-fchip" :class="{ on: filterKind === k.v }" @click="filterKind = k.v">{{ k.l }}</button>
        </template>
      </div>

      <!-- status chips (changes) -->
      <div v-if="tab === 'changes'" class="pl-fchips">
        <button v-for="s in C_STATUSES" :key="s.v" class="pl-fchip" :class="{ on: filterStatus === s.v }" :style="filterStatus === s.v ? { background: s.c + '1a', color: s.c, borderColor: s.c + '55' } : {}" @click="filterStatus = filterStatus === s.v ? '' : s.v">{{ s.l }}</button>
      </div>

      <!-- project filter -->
      <select v-if="projects && projects.length" v-model="filterProject" class="pl-psel">
        <option value="">Все проекты</option>
        <option value="__none__">Без проекта</option>
        <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.title }}</option>
      </select>

      <!-- sort -->
      <div class="pl-sort">
        <span class="pl-sort-l">Сортировка</span>
        <button class="pl-sbtn" :class="{ on: sortKey === 'date' }" @click="toggleSort('date')">Дата <span v-if="sortKey === 'date'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
        <button class="pl-sbtn" :class="{ on: sortKey === 'title' }" @click="toggleSort('title')">Название <span v-if="sortKey === 'title'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
        <button class="pl-sbtn" :class="{ on: sortKey === 'kind' }" @click="toggleSort('kind')">Тип <span v-if="sortKey === 'kind'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
        <button v-if="tab === 'changes'" class="pl-sbtn" :class="{ on: sortKey === 'status' }" @click="toggleSort('status')">Статус <span v-if="sortKey === 'status'">{{ sortDir === 'asc' ? '↑' : '↓' }}</span></button>
      </div>

      <button v-if="hasFilters" class="pl-reset" @click="resetFilters">Сбросить</button>
    </div>

    <UzaStateBlock v-if="loading" state="loading" text="Загрузка журнала…" />

    <template v-else>
      <!-- ── Уроки ── -->
      <div v-if="tab === 'lessons'" class="pl-wrap">
        <UzaStateBlock v-if="!lessons.length" state="empty" variant="block" title="Уроков пока нет" text="Фиксируйте, что сработало, что пошло не так и какие рекомендации на будущее." />
        <UzaStateBlock v-else-if="!shownLessons.length" state="empty" variant="block" title="Ничего не найдено" text="Измените фильтры или поисковый запрос." />
        <table v-else class="uza-table pl-tbl">
          <thead><tr><th>Тип</th><th>Урок</th><th>Проект</th><th>Ответственный</th><th>Дата</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(it, i) in shownLessons" :key="it.id" class="pl-row" :style="{ animationDelay: Math.min(i*0.025, 0.35)+'s' }">
              <td><span class="pl-kind" :style="{ color: LK[it.kind]?.c, background: LK[it.kind]?.c + '1a' }">{{ LK[it.kind]?.l }}</span></td>
              <td>
                <div class="pl-title">{{ it.title }}</div>
                <div v-if="it.description" class="pl-sub">{{ it.description }}</div>
                <div v-if="it.recommendation" class="pl-rec">→ {{ it.recommendation }}</div>
              </td>
              <td><span v-if="projTitle(it.project_id)" class="pl-proj">{{ projTitle(it.project_id) }}</span><span v-else class="pl-dash">—</span></td>
              <td>
                <span v-if="it.owner_name" class="pl-owner"><span class="pl-av">{{ avInitials(it.owner_name) }}</span>{{ it.owner_name }}</span>
                <span v-else class="pl-dash">—</span>
              </td>
              <td class="is-mono">{{ fmtDt(it.created_at) }}</td>
              <td style="text-align:right; white-space:nowrap">
                <button v-if="canEdit" class="pl-ia" title="Править" @click="lEdit(it)"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
                <button v-if="canEdit" class="pl-ia pl-ia-del" title="Удалить" @click="lRemove(it)"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- ── Изменения ── -->
      <div v-else class="pl-wrap">
        <UzaStateBlock v-if="!changes.length" state="empty" variant="block" title="Запросов на изменение нет" text="Фиксируйте изменения содержания/сроков/стоимости и решения по ним." />
        <UzaStateBlock v-else-if="!shownChanges.length" state="empty" variant="block" title="Ничего не найдено" text="Измените фильтры или поисковый запрос." />
        <table v-else class="uza-table pl-tbl">
          <thead><tr><th>Тип</th><th>Изменение</th><th>Проект</th><th>Инициатор</th><th>Статус</th><th>Решение</th><th></th></tr></thead>
          <tbody>
            <tr v-for="(it, i) in shownChanges" :key="it.id" class="pl-row" :style="{ animationDelay: Math.min(i*0.025, 0.35)+'s' }">
              <td><span class="pl-ck">{{ CK[it.kind]?.l }}</span></td>
              <td>
                <div class="pl-title">{{ it.title }}</div>
                <div v-if="it.description" class="pl-sub">{{ it.description }}</div>
                <div v-if="it.impact" class="pl-rec">Влияние: {{ it.impact }}</div>
              </td>
              <td><span v-if="projTitle(it.project_id)" class="pl-proj">{{ projTitle(it.project_id) }}</span><span v-else class="pl-dash">—</span></td>
              <td><span v-if="it.requested_by" class="pl-owner"><span class="pl-av">{{ avInitials(it.requested_by) }}</span>{{ it.requested_by }}</span><span v-else class="pl-dash">—</span></td>
              <td><span class="pl-stat" :style="{ color: CS[it.status]?.c, background: CS[it.status]?.c + '1a' }">{{ CS[it.status]?.l }}</span></td>
              <td class="pl-dec">{{ it.decided_by || "—" }}<template v-if="it.decided_at"><br><span class="is-mono pl-decdt">{{ fmtDt(it.decided_at) }}</span></template></td>
              <td style="text-align:right; white-space:nowrap">
                <button v-if="canEdit" class="pl-ia" title="Править" @click="cEdit(it)"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>
                <button v-if="canEdit" class="pl-ia pl-ia-del" title="Удалить" @click="cRemove(it)"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg></button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <!-- Модалка урока -->
    <Transition name="pl-modal">
      <div v-if="lOpen" class="pl-ov" @click.self="lOpen = false">
        <div class="pl-modal">
          <div class="pl-mh">{{ lEditId ? "Правка урока" : "Новый урок" }}</div>
          <div class="pl-mb">
            <div class="pl-f2">
              <div class="pl-f"><label>Тип</label><select v-model="lForm.kind"><option v-for="k in L_KINDS" :key="k.v" :value="k.v">{{ k.l }}</option></select></div>
              <div class="pl-f"><label>Проект</label>
                <select v-model="lForm.project_id">
                  <option :value="null">— без проекта —</option>
                  <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.title }}</option>
                </select>
              </div>
            </div>
            <div class="pl-f"><label>Название</label><input v-model="lForm.title" placeholder="Кратко суть" /></div>
            <div class="pl-f"><label>Описание / ситуация</label><textarea v-model="lForm.description" rows="2"></textarea></div>
            <div class="pl-f"><label>Рекомендация на будущее</label><textarea v-model="lForm.recommendation" rows="2"></textarea></div>
            <div class="pl-f"><label>Ответственный</label>
              <NoteAssigneePicker :id="lForm.owner_id || null" :name="lForm.owner_name || null" placeholder="Упомянуть пользователя"
                @update:id="lForm.owner_id = $event" @update:name="lForm.owner_name = $event || ''" />
            </div>
          </div>
          <div class="pl-mf"><button class="pl-bg" @click="lOpen = false">Отмена</button><button class="pl-b" :disabled="saving" @click="lSave">{{ saving ? "Сохраняю…" : "Сохранить" }}</button></div>
        </div>
      </div>
    </Transition>

    <!-- Модалка изменения -->
    <Transition name="pl-modal">
      <div v-if="cOpen" class="pl-ov" @click.self="cOpen = false">
        <div class="pl-modal">
          <div class="pl-mh">{{ cEditId ? "Правка изменения" : "Новый запрос на изменение" }}</div>
          <div class="pl-mb">
            <div class="pl-f2">
              <div class="pl-f"><label>Тип</label><select v-model="cForm.kind"><option v-for="k in C_KINDS" :key="k.v" :value="k.v">{{ k.l }}</option></select></div>
              <div class="pl-f"><label>Статус</label><select v-model="cForm.status"><option v-for="s in C_STATUSES" :key="s.v" :value="s.v">{{ s.l }}</option></select></div>
            </div>
            <div class="pl-f"><label>Проект</label>
              <select v-model="cForm.project_id">
                <option :value="null">— без проекта —</option>
                <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.title }}</option>
              </select>
            </div>
            <div class="pl-f"><label>Название</label><input v-model="cForm.title" placeholder="Что меняется" /></div>
            <div class="pl-f"><label>Описание</label><textarea v-model="cForm.description" rows="2"></textarea></div>
            <div class="pl-f"><label>Влияние (сроки/стоимость/риски)</label><textarea v-model="cForm.impact" rows="2"></textarea></div>
            <div class="pl-f2">
              <div class="pl-f"><label>Инициатор</label>
                <NoteAssigneePicker :id="null" :name="cForm.requested_by || null" placeholder="Упомянуть" @update:name="cForm.requested_by = $event || ''" />
              </div>
              <div class="pl-f"><label>Решение принял</label>
                <NoteAssigneePicker :id="null" :name="cForm.decided_by || null" placeholder="Упомянуть" @update:name="cForm.decided_by = $event || ''" />
              </div>
            </div>
          </div>
          <div class="pl-mf"><button class="pl-bg" @click="cOpen = false">Отмена</button><button class="pl-b" :disabled="saving" @click="cSave">{{ saving ? "Сохраняю…" : "Сохранить" }}</button></div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.pl { padding: 4px 2px 24px; }
.pl-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.pl-seg { display: inline-flex; gap: 2px; background: var(--bg2, #fafafc); border-radius: 9px; padding: 2px; border: 1px solid var(--border, rgba(99,102,180,.12)); }
.pl-seg button { padding: 6px 13px; border: none; background: transparent; border-radius: 7px; font-size: var(--fs-sm, 11.5px); font-weight: 500; color: var(--t3, #94a3b8); cursor: pointer; font-family: inherit; transition: all .14s var(--ease-standard); }
.pl-seg button.on { background: #fff; color: var(--p-deep, #534ab7); box-shadow: 0 1px 3px rgba(15,23,60,.1); }
.pl-n { font-size: 9px; font-weight: 700; opacity: .65; }
.pl-add { margin-left: auto; padding: 7px 14px; border-radius: 9px; border: 1px solid var(--p, #7c6ff7); background: var(--p, #7c6ff7); color: #fff; font-size: var(--fs-sm, 11.5px); font-weight: 500; cursor: pointer; font-family: inherit; transition: transform .15s; }
.pl-add:hover { transform: translateY(-1px); }

/* toolbar */
.pl-tools { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid var(--border, rgba(99,102,180,.1)); }
.pl-search { position: relative; display: flex; align-items: center; gap: 7px; height: 30px; padding: 0 9px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 8px; background: var(--bg1, #fff); color: var(--t3, #94a3b8); transition: all .16s; }
.pl-search:focus-within { border-color: #7c6ff7; box-shadow: 0 0 0 3px rgba(124,111,247,.1); }
.pl-search input { border: none; outline: none; background: transparent; font-size: 12px; font-family: inherit; color: var(--t1, #1e2a4a); width: 130px; }
.pl-sx { border: none; background: rgba(99,102,180,.1); color: var(--t3, #94a3b8); width: 17px; height: 17px; border-radius: 50%; cursor: pointer; font-size: 13px; line-height: 1; }
.pl-fchips { display: inline-flex; gap: 4px; flex-wrap: wrap; }
.pl-fchip { padding: 5px 10px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 14px; background: var(--bg1, #fff); color: var(--t2, #475569); font-size: 11px; font-weight: 500; cursor: pointer; font-family: inherit; transition: all .15s; }
.pl-fchip:hover { border-color: rgba(124,111,247,.5); }
.pl-fchip.on { background: rgba(124,111,247,.12); color: var(--p-deep, #534ab7); border-color: rgba(124,111,247,.4); }
.pl-psel, .pl-sbtn { font-family: inherit; }
.pl-psel { height: 30px; padding: 0 8px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 8px; background: var(--bg1, #fff); color: var(--t2, #475569); font-size: 11.5px; cursor: pointer; max-width: 160px; }
.pl-sort { display: inline-flex; align-items: center; gap: 4px; }
.pl-sort-l { font-size: 9px; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94a3b8); font-weight: 600; margin-right: 2px; }
.pl-sbtn { padding: 5px 9px; border: 1px solid transparent; border-radius: 7px; background: var(--bg2, #fafafc); color: var(--t2, #475569); font-size: 11px; font-weight: 500; cursor: pointer; transition: all .15s; }
.pl-sbtn:hover { background: rgba(124,111,247,.08); }
.pl-sbtn.on { background: rgba(124,111,247,.14); color: var(--p-deep, #534ab7); font-weight: 600; }
.pl-reset { padding: 5px 11px; border: none; border-radius: 7px; background: transparent; color: var(--t3, #94a3b8); font-size: 11px; cursor: pointer; font-family: inherit; }
.pl-reset:hover { color: #e24b4a; }

.pl-wrap { overflow-x: auto; animation: plIn .35s var(--ease-out) both; }
.pl-tbl { font-size: var(--fs-sm, 11.5px); min-width: 760px; }
.pl-row { animation: plRowIn .4s var(--ease-out) both; transition: background .14s; }
.pl-row:hover { background: rgba(124,111,247,.04); }
.pl-kind, .pl-stat { font-size: var(--fs-2xs, 9px); font-weight: 700; padding: 2px 7px; border-radius: 6px; white-space: nowrap; }
.pl-ck { font-size: var(--fs-2xs, 9px); font-weight: 600; padding: 2px 6px; border-radius: 5px; background: rgba(124,111,247,.1); color: var(--p-deep, #534ab7); white-space: nowrap; }
.pl-title { font-weight: 500; color: var(--t1, #1e2a4a); }
.pl-sub { font-size: var(--fs-xs, 10.5px); color: var(--t3, #94a3b8); margin-top: 2px; max-width: 440px; }
.pl-rec { font-size: var(--fs-xs, 10px); color: var(--p-deep, #534ab7); font-weight: 600; margin-top: 3px; }
.pl-proj { display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 8px; border-radius: 10px; background: rgba(127,119,221,.1); color: var(--p-deep, #534ab7); max-width: 130px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pl-owner { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: var(--t1, #1e2a4a); }
.pl-av { width: 19px; height: 19px; border-radius: 50%; background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 8.5px; font-weight: 700; flex-shrink: 0; }
.pl-dash { color: var(--t3, #cbd5e1); }
.pl-dec { font-size: var(--fs-xs, 10.5px); color: var(--t2, #475569); }
.pl-decdt { color: var(--t3, #94a3b8); font-size: 9.5px; }
.pl-ia { background: none; border: none; cursor: pointer; color: var(--t3, #94a3b8); padding: 4px; border-radius: 6px; transition: all .14s; }
.pl-ia:hover { background: rgba(124,111,247,.08); color: var(--p-deep, #534ab7); }
.pl-ia-del:hover { background: rgba(226,75,74,.08); color: #E24B4A; }
@keyframes plIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@keyframes plRowIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

.pl-ov { position: fixed; inset: 0; z-index: var(--z-modal, 9100); background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(7px); backdrop-filter: blur(7px); display: flex; align-items: center; justify-content: center; padding: 20px; }
.pl-modal { background: var(--bg1, #fff); border-radius: 14px; width: min(560px, 96vw); max-height: 92dvh; overflow: hidden; display: flex; flex-direction: column; box-shadow: var(--shl); }
.pl-mh { padding: 14px 18px; font-size: var(--fs-md, 13px); font-weight: 600; color: var(--t1, #1e2a4a); border-bottom: 1px solid var(--border, rgba(99,102,180,.12)); }
.pl-mb { padding: 14px 18px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.pl-f { display: flex; flex-direction: column; gap: 4px; }
.pl-f2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.pl-f label { font-size: var(--fs-2xs, 9px); text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); font-weight: 600; }
.pl-f input, .pl-f select, .pl-f textarea { padding: 7px 10px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 8px; font-size: var(--fs-base, 12px); font-family: inherit; outline: none; background: var(--bg1, #fff); color: var(--t1, #1e2a4a); transition: border-color .15s; }
.pl-f input:focus, .pl-f select:focus, .pl-f textarea:focus { border-color: #7c6ff7; }
.pl-f textarea { resize: vertical; }
.pl-mf { padding: 12px 18px; border-top: 1px solid var(--border, rgba(99,102,180,.12)); display: flex; justify-content: flex-end; gap: 8px; background: var(--bg2, #fafafc); }
.pl-b { padding: 8px 16px; border-radius: 9px; border: 1px solid var(--p, #7c6ff7); background: var(--p, #7c6ff7); color: #fff; font-size: var(--fs-sm, 11.5px); font-weight: 500; cursor: pointer; font-family: inherit; }
.pl-b:disabled { opacity: .5; }
.pl-bg { padding: 8px 16px; border-radius: 9px; border: 1px solid var(--border, rgba(99,102,180,.18)); background: transparent; color: var(--t2, #475569); font-size: var(--fs-sm, 11.5px); cursor: pointer; font-family: inherit; }

/* modal anim */
.pl-modal-enter-active { transition: opacity .2s ease; }
.pl-modal-enter-active .pl-modal { transition: transform .32s var(--ease-out, cubic-bezier(.16,1,.3,1)), opacity .2s ease; }
.pl-modal-leave-active { transition: opacity .16s ease; }
.pl-modal-enter-from { opacity: 0; }
.pl-modal-enter-from .pl-modal { transform: scale(.95) translateY(14px); opacity: 0; }
.pl-modal-leave-to { opacity: 0; }

@media (max-width: 560px) { .pl-f2 { grid-template-columns: 1fr; } }
</style>
