/**
 * useScenarios.ts — Pack 7.40
 * ─────────────────────────────────────────────────────────────────
 * Singleton-композбл для работы со сценариями макропоказателей.
 *
 * ВАЖНО — изолирован от глобального состояния:
 *   Активный сценарий хранится здесь, но НЕ влияет на глобальную
 *   конвертацию (useCurrencyConverter), Финансы / Tax / EE / BP /
 *   Дашборд и т.д. Эти блоки продолжают показывать ФАКТ.
 *
 *   Сценарий используется только внутри вкладки «Сценарии и прогнозы»
 *   админки. Будущие endpoint'ы (/forecast в Pack 7.43) будут получать
 *   scenario_id явно как query-параметр.
 *
 * Состояние:
 *   • scenarios       — список всех сценариев (после load())
 *   • activeId        — id выбранного сейчас сценария (для просмотра/редактирования)
 *   • loading, error  — UI флаги
 *
 * Действия:
 *   • load()                    — загрузить полный список с сервера
 *   • setActiveId(id)           — переключить активный
 *   • create(payload)           — создать новый custom сценарий
 *   • update(id, payload)       — обновить метаданные
 *   • remove(id)                — удалить (только custom)
 *   • upsertOverride(id, y, p)  — записать override для года
 *   • clearOverride(id, y)      — стереть override на год (вернуть к базе)
 */
import { computed, readonly, ref } from "vue";
import {
  scenariosApi,
  type Scenario,
  type ScenarioCreate,
  type ScenarioOverride,
  type ScenarioOverrideUpsert,
  type ScenarioUpdate,
} from "@/api/scenarios";
import { t } from "@/locale/i18n";


const _scenarios = ref<Scenario[]>([]);
const _activeId = ref<string | null>(null);
const _loading = ref(false);
const _error = ref<string | null>(null);
let _loaded = false;

async function load(force = false): Promise<void> {
  if (_loaded && !force) return;
  _loading.value = true;
  _error.value = null;
  try {
    const data = await scenariosApi.list();
    _scenarios.value = data;
    _loaded = true;
    // Default active scenario: first seeded (Базовый) if nothing chosen yet
    if (_activeId.value == null && data.length > 0) {
      const base = data.find((s) => s.code === "base") || data[0];
      _activeId.value = base.id;
    }
  } catch (err: any) {
    _error.value =
      err?.response?.data?.detail ||
      err?.message || t('Не удалось загрузить сценарии');
    throw err;
  } finally {
    _loading.value = false;
  }
}

function setActiveId(id: string | null): void {
  _activeId.value = id;
}

async function create(payload: ScenarioCreate): Promise<Scenario> {
  const created = await scenariosApi.create(payload);
  _scenarios.value.push(created);
  _scenarios.value.sort(
    (a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code),
  );
  return created;
}

async function update(id: string, payload: ScenarioUpdate): Promise<Scenario> {
  const updated = await scenariosApi.update(id, payload);
  const idx = _scenarios.value.findIndex((s) => s.id === id);
  if (idx >= 0) {
    // Сохраняем уже загруженные overrides
    updated.overrides = _scenarios.value[idx].overrides;
    _scenarios.value[idx] = updated;
  }
  return updated;
}

async function remove(id: string): Promise<void> {
  await scenariosApi.remove(id);
  _scenarios.value = _scenarios.value.filter((s) => s.id !== id);
  if (_activeId.value === id) {
    const base = _scenarios.value.find((s) => s.code === "base") || _scenarios.value[0];
    _activeId.value = base?.id ?? null;
  }
}

async function upsertOverride(
  scenarioId: string,
  year: number,
  payload: ScenarioOverrideUpsert,
): Promise<ScenarioOverride> {
  const ov = await scenariosApi.upsertOverride(scenarioId, year, payload);
  const scenario = _scenarios.value.find((s) => s.id === scenarioId);
  if (scenario) {
    const idx = scenario.overrides.findIndex((o) => o.year === year);
    if (idx >= 0) scenario.overrides[idx] = ov;
    else {
      scenario.overrides.push(ov);
      scenario.overrides.sort((a, b) => a.year - b.year);
    }
  }
  return ov;
}

async function clearOverride(scenarioId: string, year: number): Promise<void> {
  await scenariosApi.deleteOverride(scenarioId, year);
  const scenario = _scenarios.value.find((s) => s.id === scenarioId);
  if (scenario) {
    scenario.overrides = scenario.overrides.filter((o) => o.year !== year);
  }
}

/** Утилита: для активного сценария взять override для года, или null */
function overrideForYear(scenarioId: string | null, year: number): ScenarioOverride | null {
  if (!scenarioId) return null;
  const scenario = _scenarios.value.find((s) => s.id === scenarioId);
  if (!scenario) return null;
  return scenario.overrides.find((o) => o.year === year) ?? null;
}

export function useScenarios() {
  const activeScenario = computed(() =>
    _activeId.value ? _scenarios.value.find((s) => s.id === _activeId.value) ?? null : null,
  );

  return {
    scenarios: readonly(_scenarios),
    activeId: readonly(_activeId),
    activeScenario,
    loading: readonly(_loading),
    error: readonly(_error),

    load,
    setActiveId,
    create,
    update,
    remove,
    upsertOverride,
    clearOverride,
    overrideForYear,
  };
}
