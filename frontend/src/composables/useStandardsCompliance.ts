/**
 * useStandardsCompliance — честный источник «внедрения стандартов» (МСФО + forensic)
 * для финансовых KPI. Раньше карточки FinKpiBand/FinKpiDrillModal показывали
 * ЗАХАРДКОЖЕННЫЕ «4/22 · 8/22» (фабрикация). Тут реальные данные:
 *   • МСФО «внедрено» = компания с непустой датой публикации в /ifrs-report-history;
 *   • forensic «проведён» = компания со статусом 'Завершён' + аудитор + годы
 *     (тот же предикат _forensic_really_done, что в backend forensic-overview).
 *
 * Состояние — модульный синглтон: грузится один раз, шарится между карточкой и
 * модалкой. Ошибки загрузки не фатальны (пустые множества → счётчики 0/—).
 */
import { ref } from "vue";
import { ifrsReportHistoryApi } from "@/api/ifrsReportHistory";
import { forensicApi } from "@/api/forensic";

const _msfoIds = ref<Set<string>>(new Set());       // company_id с опубликованной МСФО
const _forensicCodes = ref<Set<string>>(new Set()); // код компании с завершённым forensic-аудитом
const _loaded = ref(false);
let _loading: Promise<void> | null = null;

export function useStandardsCompliance() {
  function load(): Promise<void> {
    if (_loaded.value) return Promise.resolve();
    if (_loading) return _loading;
    _loading = (async () => {
      try {
        const [ifrs, forensic] = await Promise.all([
          ifrsReportHistoryApi.list().catch(() => ({ rows: [] })),
          forensicApi.overview().catch(() => ({ companies: [], kpis: null })),
        ]);
        const msfo = new Set<string>();
        for (const r of (ifrs.rows || [])) {
          if (r.published_on) msfo.add(String(r.company_id));
        }
        const fdone = new Set<string>();
        for (const co of (forensic.companies || [])) {
          const done = co.forensic === "Завершён"
            && !!(co.auditor || "").trim()
            && !!(co.aYears || "").trim();
          if (done && co.k) fdone.add(co.k.toLowerCase());
        }
        _msfoIds.value = msfo;
        _forensicCodes.value = fdone;
      } finally {
        _loaded.value = true;
      }
    })();
    return _loading;
  }

  return { msfoIds: _msfoIds, forensicCodes: _forensicCodes, loaded: _loaded, load };
}
