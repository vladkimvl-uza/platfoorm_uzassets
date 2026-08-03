<script setup lang="ts">
/**
 * PmoTeam — команда и распределение (PMBOK 7, Team).
 *
 * Тоггл: «Загрузка» (computed из назначений задач — кто сколько везёт, кто
 * перегружен) и «RACI» (матрица ответственности activity × человек). Загрузка
 * считается вживую, без отдельной таблицы.
 */
import { ref, computed, watch, onMounted } from "vue";
import UzaStateBlock from "@/components/UZA/UzaStateBlock.vue";
import NoteAssigneePicker from "@/components/NoteAssigneePicker.vue";
import { useToast } from "@/composables/useToast";
import { useConfirm } from "@/composables/useConfirm";
import {
  pmoApi,
  type WorkloadResponse, type WorkloadPerson, type Capacity,
  type RaciEntry, type RaciRole,
} from "@/api/pmo";
import { useI18n } from "@/composables/useI18n";
import { getCurrentIntlLocale } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";

const { t } = useI18n();


const props = defineProps<{
  companyCode: string;
  canEdit?: boolean;
  year?: number;
  projects?: { id: string; title: string }[];
}>();

const toast = useToast();
const { confirmDialog } = useConfirm();

const view = ref<"workload" | "raci">("workload");

const loading = ref(true);
const error = ref<string | null>(null);
const wl = ref<WorkloadResponse | null>(null);
const raci = ref<RaciEntry[]>([]);

async function load() {
  loading.value = true; error.value = null;
  try {
    const [w, r] = await Promise.all([
      pmoApi.getWorkload(props.companyCode, props.year),
      pmoApi.listRaci(props.companyCode),
    ]);
    wl.value = w; raci.value = r;
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || t('Не удалось загрузить данные команды');
  } finally { loading.value = false; }
}
onMounted(load);
watch(() => [props.companyCode, props.year], load);

function avInitials(name?: string | null): string {
  const n = (name || "").trim();
  if (!n) return "?";
  const parts = n.split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}

const CAP: Record<Capacity, { l: string; c: string }> = {
  free: { l: i18nKey("Свободен"), c: "#94a3b8" },
  normal: { l: i18nKey("В норме"), c: "#1D9E75" },
  high: { l: i18nKey("Высокая"), c: "#D97706" },
  overload: { l: i18nKey("Перегрузка"), c: "#E24B4A" },
};
// ЧЕСТНОЕ ПОКРЫТИЕ. Загрузка считается только по задачам, где проставлен
// исполнитель. На проде это ~52 задачи из 1975: рейтинг ниже описывает
// меньшинство работы, и об этом надо сказать прямо, а не показывать его
// как полную картину команды.
const coverage = computed(() => {
  const w = wl.value;
  if (!w) return { assigned: 0, total: 0, pct: 0, enough: true };
  const total = w.total_open || 0;
  const assigned = Math.max(0, total - (w.unassigned_open || 0));
  const pct = total ? Math.round((assigned / total) * 100) : 0;
  return { assigned, total, pct, enough: pct >= 50 };
});

function loadPct(p: WorkloadPerson): number {
  const max = wl.value?.max_load || 1;
  return Math.round((p.load / max) * 100);
}

// ── RACI ──
const RACI_ROLES: { v: RaciRole; l: string; c: string }[] = [
  { v: "A", l: i18nKey("Ответственный (Accountable)"), c: "#1D9E75" },
  { v: "R", l: i18nKey("Исполнитель (Responsible)"), c: "#534AB7" },
  { v: "C", l: i18nKey("Консультируемый (Consulted)"), c: "#D97706" },
  { v: "I", l: i18nKey("Информируемый (Informed)"), c: "#378ADD" },
];
const RR = Object.fromEntries(RACI_ROLES.map(r => [r.v, r]));

const raciItems = computed(() => {
  const seen = new Set<string>(); const out: string[] = [];
  for (const e of raci.value) if (!seen.has(e.item_label)) { seen.add(e.item_label); out.push(e.item_label); }
  return out;
});
const raciPersons = computed(() => {
  const seen = new Set<string>(); const out: string[] = [];
  for (const e of raci.value) if (!seen.has(e.person_name)) { seen.add(e.person_name); out.push(e.person_name); }
  return out;
});
function cellEntries(item: string, person: string): RaciEntry[] {
  return raci.value.filter(e => e.item_label === item && e.person_name === person);
}

// add-form
const addOpen = ref(false);
const fItem = ref("");
const fPersonId = ref<string | null>(null);
const fPersonName = ref<string | null>(null);
const fRole = ref<RaciRole>("R");
const fProject = ref<string | null>(null);
const saving = ref(false);

function openAdd(presetItem?: string) {
  fItem.value = presetItem || "";
  fPersonId.value = null; fPersonName.value = null; fRole.value = "R"; fProject.value = null;
  addOpen.value = true;
}
async function addRaci() {
  if (!fItem.value.trim()) { toast.error(t('Укажите активность/результат')); return; }
  if (!fPersonName.value?.trim()) { toast.error(t('Укажите человека')); return; }
  saving.value = true;
  try {
    await pmoApi.createRaci(props.companyCode, {
      item_label: fItem.value.trim(),
      person_name: fPersonName.value.trim(),
      person_id: fPersonId.value,
      role: fRole.value,
      project_id: fProject.value,
    });
    addOpen.value = false;
    await load();
    toast.success(t('Назначение добавлено'));
  } catch (e: any) { toast.error(e?.response?.data?.detail || t('Не удалось добавить')); }
  finally { saving.value = false; }
}
async function removeEntry(e: RaciEntry) {
  try { await pmoApi.deleteRaci(e.id); await load(); }
  catch (err: any) { toast.error(err?.response?.data?.detail || t('Не удалось удалить')); }
}
async function clearItem(item: string) {
  if (!(await confirmDialog({ message: t('Удалить все назначения по «{value0}»?', { value0: item }), danger: true }))) return;
  const ids = raci.value.filter(e => e.item_label === item).map(e => e.id);
  try { for (const id of ids) await pmoApi.deleteRaci(id); await load(); toast.success(t('Строка удалена')); }
  catch (e: any) { toast.error(t('Не удалось удалить')); }
}
</script>

<template>
  <div class="tm">
    <UzaStateBlock v-if="error" state="error" variant="banner" :text="error" dismissible @dismiss="error = null" />

    <div class="tm-bar">
      <div class="tm-seg">
        <button :class="{ on: view === 'workload' }" @click="view = 'workload'">{{ t('Загрузка') }}</button>
        <button :class="{ on: view === 'raci' }" @click="view = 'raci'">RACI <span v-if="raci.length" class="tm-n">{{ raci.length }}</span></button>
      </div>
      <button v-if="canEdit && view === 'raci'" class="tm-add" @click="openAdd()">{{ t('+ Назначение') }}</button>
    </div>

    <UzaStateBlock v-if="loading" state="loading" :text="t('Загрузка данных команды…')" />

    <template v-else>
      <!-- ── Загрузка ── -->
      <div v-if="view === 'workload'">
        <div v-if="wl && coverage.total && !coverage.enough" class="tm-cover">
          <span class="tm-cover-badge">{{ t('Данных недостаточно') }}</span>
          <span class="tm-cover-txt">
            {{ t('Исполнитель проставлен у {value0} из {value1} открытых задач ({value2}%).', {
              value0: coverage.assigned, value1: coverage.total, value2: coverage.pct,
            }) }}
            {{ t('Загрузка ниже посчитана только по ним — остальная работа в расчёт не входит.') }}
          </span>
        </div>
        <div v-if="wl" class="tm-stats">
          <div class="tm-stat"><span class="tm-stat-n">{{ wl.total_people }}</span><span class="tm-stat-l">{{ t('в команде') }}</span></div>
          <div class="tm-stat"><span class="tm-stat-n">{{ wl.total_open }}</span><span class="tm-stat-l">{{ t('открытых задач') }}</span></div>
          <div class="tm-stat" :class="{ 'tm-stat-warn': wl.unassigned_open > 0 }"><span class="tm-stat-n">{{ wl.unassigned_open }}</span><span class="tm-stat-l">{{ t('без исполнителя') }}</span></div>
        </div>

        <UzaStateBlock v-if="!wl || !wl.people.length" state="empty" variant="block" :title="t('Нет назначений')" :text="t('Назначьте исполнителей на задачи — здесь появится их загрузка и сигналы перегрузки.')" />
        <div v-else class="tm-people">
          <div v-for="(p, i) in wl.people" :key="p.person_id || p.name" class="tm-person" :style="{ animationDelay: Math.min(i*0.03, 0.4)+'s' }">
            <div class="tm-av" :style="{ background: 'linear-gradient(135deg, ' + CAP[p.capacity].c + ', ' + CAP[p.capacity].c + 'cc)' }">{{ avInitials(p.name) }}</div>
            <div class="tm-pmain">
              <div class="tm-prow">
                <span class="tm-pname">{{ p.name }}</span>
                <span class="tm-cap" :style="{ color: CAP[p.capacity].c, background: CAP[p.capacity].c + '18' }">{{ t(CAP[p.capacity].l) }}</span>
              </div>
              <div class="tm-loadbar"><span class="tm-loadbar-fill" :style="{ width: loadPct(p) + '%', background: CAP[p.capacity].c }"></span></div>
              <div class="tm-pmeta">
                <span class="tm-m">{{ t('Загрузка') }} <b>{{ p.load }}</b></span>
                <span class="tm-m">{{ t('Открыто') }} <b>{{ p.open }}</b></span>
                <span class="tm-m" :class="{ 'tm-m-bad': p.overdue > 0 }">{{ t('Просрочено') }} <b>{{ p.overdue }}</b></span>
                <span class="tm-m tm-m-ok">{{ t('Завершено') }} <b>{{ p.done }}</b></span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="wl && wl.people.length" class="tm-foot">{{ t('Загрузка = сумма весов открытых задач исполнителя. Считается из назначений задач на') }} {{ new Date(wl.as_of).toLocaleDateString(getCurrentIntlLocale()) }}.</div>
      </div>

      <!-- ── RACI ── -->
      <div v-else>
        <UzaStateBlock v-if="!raci.length" state="empty" variant="block" :title="t('Матрица RACI пуста')" :text="t('Добавьте назначения: для каждой активности укажите, кто Ответственный (A), Исполнитель (R), Консультируемый (C), Информируемый (I).')" />
        <template v-else>
          <div class="tm-legend">
            <span v-for="r in RACI_ROLES" :key="r.v" class="tm-leg"><span class="tm-leg-b" :style="{ color: r.c, background: r.c + '1a' }">{{ r.v }}</span>{{ t(r.l) }}</span>
          </div>
          <div class="tm-mxwrap">
            <table class="tm-mx">
              <thead>
                <tr>
                  <th class="tm-mx-corner">{{ t('Активность / результат') }}</th>
                  <th v-for="pn in raciPersons" :key="pn" class="tm-mx-ph"><span>{{ pn }}</span></th>
                  <th v-if="canEdit" class="tm-mx-act"></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in raciItems" :key="item" class="tm-mx-row">
                  <td class="tm-mx-il">{{ item }}</td>
                  <td v-for="pn in raciPersons" :key="pn" class="tm-mx-c">
                    <span
                      v-for="e in cellEntries(item, pn)" :key="e.id"
                      class="tm-rb" :style="{ color: RR[e.role]?.c, background: RR[e.role]?.c + '1a' }"
                      :title="canEdit ? t('{value0} — клик чтобы убрать', { value0: t(RR[e.role]?.l || '') }) : t(RR[e.role]?.l || '')"
                      @click="canEdit && removeEntry(e)"
                    >{{ e.role }}</span>
                  </td>
                  <td v-if="canEdit" class="tm-mx-act">
                    <button class="tm-ia" :title="t('Добавить в строку')" @click="openAdd(item)"><svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1 V11 M1 6 H11" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg></button>
                    <button class="tm-ia tm-ia-del" :title="t('Удалить строку')" @click="clearItem(item)"><svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M3 3 L13 13 M13 3 L3 13" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg></button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
    </template>

    <!-- add modal -->
    <Transition name="tm-modal">
      <div v-if="addOpen" class="tm-ov" @click.self="addOpen = false">
        <div class="tm-modal">
          <div class="tm-mh">{{ t('Назначение ответственности') }}</div>
          <div class="tm-mb">
            <div class="tm-f"><label>{{ t('Активность / результат') }}</label><input v-model="fItem" :placeholder="t('Например: Утверждение бюджета')" /></div>
            <div class="tm-f"><label>{{ t('Человек') }}</label>
              <NoteAssigneePicker :id="fPersonId" :name="fPersonName" :placeholder="t('Выбрать пользователя')"
                :company-code="companyCode" allow-custom
                @update:id="fPersonId = $event" @update:name="fPersonName = $event" />
            </div>
            <div class="tm-f"><label>{{ t('Роль') }}</label>
              <div class="tm-roles">
                <button v-for="r in RACI_ROLES" :key="r.v" type="button" class="tm-role" :class="{ on: fRole === r.v }" :style="fRole === r.v ? { color: r.c, background: r.c + '1a', borderColor: r.c + '66' } : {}" @click="fRole = r.v">
                  <b>{{ r.v }}</b> {{ t(r.l).split(" ")[0] }}
                </button>
              </div>
            </div>
            <div v-if="projects && projects.length" class="tm-f"><label>{{ t('Проект (опционально)') }}</label>
              <select v-model="fProject"><option :value="null">{{ t('— без проекта —') }}</option><option v-for="p in projects" :key="p.id" :value="p.id">{{ p.title }}</option></select>
            </div>
          </div>
          <div class="tm-mf"><button class="tm-bg" @click="addOpen = false">{{ t('Отмена') }}</button><button class="tm-b" :disabled="saving" @click="addRaci">{{ saving ? t('Сохраняю…') : t('Добавить') }}</button></div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.tm { padding: 4px 2px 24px; }
.tm-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.tm-seg { display: inline-flex; gap: 2px; background: var(--bg2, #fafafc); border-radius: 9px; padding: 2px; border: 1px solid var(--border, rgba(99,102,180,.12)); }
.tm-seg button { padding: 6px 13px; border: none; background: transparent; border-radius: 7px; font-size: var(--fs-sm, 11.5px); font-weight: 500; color: var(--t3, #94a3b8); cursor: pointer; font-family: inherit; transition: all .14s var(--ease-standard); }
.tm-seg button.on { background: #fff; color: var(--p-deep, #534ab7); box-shadow: 0 1px 3px rgba(15,23,60,.1); }
.tm-n { font-size: 9px; font-weight: 700; opacity: .65; }
.tm-add { margin-left: auto; padding: 7px 14px; border-radius: 9px; border: 1px solid var(--p, #7c6ff7); background: var(--p, #7c6ff7); color: #fff; font-size: var(--fs-sm, 11.5px); font-weight: 500; cursor: pointer; font-family: inherit; transition: transform .15s; }
.tm-add:hover { transform: translateY(-1px); }

/* stats */
.tm-cover {
  display: flex; align-items: flex-start; gap: 9px; flex-wrap: wrap;
  background: rgba(217,119,6,.07); border: 1px solid rgba(217,119,6,.22);
  border-radius: 11px; padding: 10px 13px; margin-bottom: 12px;
}
.tm-cover-badge {
  font-size: 9.5px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase;
  color: #B45309; background: rgba(217,119,6,.14); border-radius: 999px;
  padding: 3px 9px; white-space: nowrap; flex-shrink: 0;
}
.tm-cover-txt { font-size: 11.5px; color: var(--t2, #4B5468); line-height: 1.5; }
.tm-stats { display: flex; gap: 8px; margin-bottom: 14px; }
.tm-stat { display: flex; flex-direction: column; align-items: center; min-width: 92px; padding: 8px 12px; border: 1px solid var(--border, rgba(99,102,180,.12)); border-radius: 11px; background: var(--bg1, #fff); }
.tm-stat-n { font-size: 19px; font-weight: 400; color: var(--t1, #1e2a4a); font-variant-numeric: tabular-nums; }
.tm-stat-l { font-size: 9px; text-transform: uppercase; letter-spacing: .05em; color: var(--t3, #94a3b8); margin-top: 1px; }
.tm-stat-warn { border-top: 2px solid #E24B4A; }

/* people */
.tm-people { display: flex; flex-direction: column; gap: 8px; }
.tm-person { display: flex; align-items: center; gap: 13px; padding: 12px 14px; border: 1px solid var(--border, rgba(99,102,180,.1)); border-radius: 13px; background: var(--bg1, #fff); animation: tmIn .4s var(--ease-out, cubic-bezier(.16,1,.3,1)) both; transition: box-shadow .2s, transform .2s; }
.tm-person:hover { box-shadow: 0 6px 16px rgba(15,23,60,.06); transform: translateY(-1px); }
.tm-av { width: 38px; height: 38px; border-radius: 50%; color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; flex-shrink: 0; }
.tm-pmain { flex: 1; min-width: 0; }
.tm-prow { display: flex; align-items: center; gap: 9px; margin-bottom: 6px; }
.tm-pname { font-size: 13px; font-weight: 500; color: var(--t1, #1e2a4a); }
.tm-cap { font-size: 9.5px; font-weight: 700; padding: 2px 8px; border-radius: 8px; }
.tm-loadbar { height: 6px; border-radius: 3px; background: rgba(30,42,74,.07); overflow: hidden; margin-bottom: 6px; }
.tm-loadbar-fill { display: block; height: 100%; border-radius: 3px; transition: width .6s var(--ease-out, cubic-bezier(.16,1,.3,1)); }
.tm-pmeta { display: flex; flex-wrap: wrap; gap: 12px; }
.tm-m { font-size: 11px; color: var(--t3, #94a3b8); }
.tm-m b { color: var(--t1, #1e2a4a); font-weight: 600; font-variant-numeric: tabular-nums; }
.tm-m-bad b { color: #E24B4A; }
.tm-m-ok b { color: #1D9E75; }
.tm-foot { margin-top: 12px; font-size: 10.5px; color: var(--t3, #94a3b8); }

/* RACI legend + matrix */
.tm-legend { display: flex; flex-wrap: wrap; gap: 14px; margin-bottom: 12px; }
.tm-leg { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: var(--t2, #475569); }
.tm-leg-b { font-size: 10px; font-weight: 800; width: 18px; height: 18px; border-radius: 5px; display: inline-flex; align-items: center; justify-content: center; }
.tm-mxwrap { overflow-x: auto; border: 1px solid var(--border, rgba(99,102,180,.1)); border-radius: 12px; animation: tmIn .35s var(--ease-out) both; }
.tm-mx { border-collapse: collapse; width: 100%; font-size: var(--fs-sm, 11.5px); }
.tm-mx th, .tm-mx td { border-bottom: 1px solid var(--border, rgba(99,102,180,.08)); border-right: 1px solid var(--border, rgba(99,102,180,.06)); padding: 9px 11px; }
.tm-mx thead th { background: var(--bg2, #fafafc); font-weight: 600; color: var(--t2, #475569); position: sticky; top: 0; }
.tm-mx-corner { text-align: left; min-width: 200px; }
.tm-mx-ph { text-align: center; min-width: 74px; }
.tm-mx-ph span { display: inline-block; max-width: 110px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; }
.tm-mx-il { font-weight: 500; color: var(--t1, #1e2a4a); }
.tm-mx-c { text-align: center; }
.tm-mx-row:hover { background: rgba(124,111,247,.03); }
.tm-rb { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 6px; font-size: 11px; font-weight: 800; margin: 1px; cursor: default; transition: transform .12s; }
.tm-mx-act { white-space: nowrap; text-align: right; }
.tm-ia { background: none; border: none; cursor: pointer; color: var(--t3, #94a3b8); padding: 4px; border-radius: 6px; transition: all .14s; }
.tm-ia:hover { background: rgba(124,111,247,.1); color: var(--p-deep, #534ab7); }
.tm-ia-del:hover { background: rgba(226,75,74,.1); color: #E24B4A; }

/* clickable role chips when editable */
.tm-mx td .tm-rb { cursor: pointer; }
.tm-mx td .tm-rb:hover { transform: scale(1.12); }

@keyframes tmIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

/* modal */
.tm-ov { position: fixed; inset: 0; z-index: var(--z-modal, 9100); background: rgba(15,18,40,.45); -webkit-backdrop-filter: blur(7px); backdrop-filter: blur(7px); display: flex; align-items: center; justify-content: center; padding: 20px; }
.tm-modal { background: var(--bg1, #fff); border-radius: 14px; width: min(480px, 96vw); max-height: 92dvh; overflow: hidden; display: flex; flex-direction: column; box-shadow: var(--shl); }
.tm-mh { padding: 14px 18px; font-size: var(--fs-md, 13px); font-weight: 600; color: var(--t1, #1e2a4a); border-bottom: 1px solid var(--border, rgba(99,102,180,.12)); }
.tm-mb { padding: 14px 18px; overflow-y: auto; display: flex; flex-direction: column; gap: 11px; }
.tm-f { display: flex; flex-direction: column; gap: 5px; }
.tm-f label { font-size: var(--fs-2xs, 9px); text-transform: uppercase; letter-spacing: .04em; color: var(--t3, #94a3b8); font-weight: 600; }
.tm-f input, .tm-f select { padding: 8px 11px; border: 1px solid var(--border, rgba(99,102,180,.16)); border-radius: 8px; font-size: 12.5px; font-family: inherit; outline: none; background: var(--bg1, #fff); color: var(--t1, #1e2a4a); transition: border-color .15s; }
.tm-f input:focus, .tm-f select:focus { border-color: #7c6ff7; }
.tm-roles { display: flex; flex-wrap: wrap; gap: 6px; }
.tm-role { display: inline-flex; align-items: center; gap: 5px; padding: 6px 11px; border: 1px solid var(--border, rgba(99,102,180,.18)); border-radius: 9px; background: var(--bg1, #fff); color: var(--t2, #475569); font-size: 11px; font-family: inherit; cursor: pointer; transition: all .15s; }
.tm-role b { font-weight: 800; }
.tm-role:hover { border-color: rgba(124,111,247,.45); }
.tm-mf { padding: 12px 18px; border-top: 1px solid var(--border, rgba(99,102,180,.12)); display: flex; justify-content: flex-end; gap: 8px; background: var(--bg2, #fafafc); }
.tm-b { padding: 8px 16px; border-radius: 9px; border: none; background: linear-gradient(135deg, #7f77dd, #6b62cc); color: #fff; font-size: var(--fs-sm, 11.5px); font-weight: 500; cursor: pointer; font-family: inherit; box-shadow: 0 2px 8px rgba(127,119,221,.28); }
.tm-b:disabled { opacity: .5; }
.tm-bg { padding: 8px 16px; border-radius: 9px; border: 1px solid var(--border, rgba(99,102,180,.18)); background: transparent; color: var(--t2, #475569); font-size: var(--fs-sm, 11.5px); cursor: pointer; font-family: inherit; }
.tm-modal-enter-active { transition: opacity .2s ease; }
.tm-modal-enter-active .tm-modal { transition: transform .32s var(--ease-out, cubic-bezier(.16,1,.3,1)), opacity .2s ease; }
.tm-modal-leave-active { transition: opacity .16s ease; }
.tm-modal-enter-from { opacity: 0; }
.tm-modal-enter-from .tm-modal { transform: scale(.95) translateY(14px); opacity: 0; }
.tm-modal-leave-to { opacity: 0; }

@media (max-width: 560px) { .tm-pmeta { gap: 8px; } }

/* Доступность: пользователю с настройкой «меньше движения» анимации не нужны —
   в PMO их много (каскады строк, полосы Гантта, всплытие модалок). */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .001ms !important;
    scroll-behavior: auto !important;
  }
}
</style>
