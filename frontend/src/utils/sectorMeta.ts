/**
 * sectorMeta.ts
 * ─────────────────────────────────────────────────────────────────
 * Единый источник истины для отображения секторов.
 *
 * Архитектура:
 *   • Цвета и канонические коды — здесь (frontend constants)
 *   • RU-имена (label/short) — БЕРУТСЯ ИЗ БД через companies store
 *   • Нормализация любого raw кода → один из 5 canonical buckets
 *
 * Использование в компонентах:
 *   const meta = useSectorMeta();
 *   ...
 *   const m = meta.byCode(someCode);
 *   // m: { code, label, short, color }
 *
 * Если в Companies admin изменить name_ru у сектора («Энергетика» →
 * «Энергетика и КХ») — этот хелпер автоматически подхватит новое имя
 * везде где он используется, без правок кода.
 */

import { computed } from "vue";
import { useCompaniesStore } from "@/stores/companies";
import { canonSectorCode, sectorDisplayName, sectorShortLabel } from "@/utils/displayNames";
import { i18nKey } from "@/locale/keys";
import { t } from "@/locale/i18n";


// ─── Канонические 5 секторов в порядке отображения ───
export const SECTOR_ORDER = ["mining", "oilgas", "energy", "transport", "other"] as const;
export type SectorCode = typeof SECTOR_ORDER[number];

// ─── Цвета на canonical код (палитра UzAssets) ───
export const SECTOR_COLORS: Record<SectorCode, string> = {
  mining:    "#7F77DD",
  oilgas:    "#1D9E75",
  energy:    "#EF9F27",
  transport: "#378ADD",
  other:     "#888780",
};

// ─── Hardcoded fallback RU names — used ONLY when companies store
// hasn't loaded yet or when the sector isn't in DB. Once the store
// loads, these are overridden by sector.name_ru from the API.
const FALLBACK_LABELS: Record<SectorCode, string> = {
  mining:    i18nKey("Горнодобывающий"),
  oilgas:    i18nKey("Нефтегазовый"),
  energy:    i18nKey("Энергетика"),
  transport: i18nKey("Транспорт и коммуникации"),
  other:     i18nKey("Другой сектор"),
};

export interface SectorMetaEntry {
  /** Canonical 5-bucket code: mining/oilgas/energy/transport/other */
  code: SectorCode;
  /** Full RU label — from DB if loaded, else hardcoded fallback */
  label: string;
  /** Short label for compact UI — derived from `label` automatically */
  short: string;
  /** Brand colour for this sector */
  color: string;
}

/**
 * Composable that returns sector metadata helpers.
 * Call once in `<script setup>` and use `.byCode(rawCode)` everywhere.
 *
 *   const meta = useSectorMeta();
 *   const m = meta.byCode(co.sector_code);
 *   // m.label, m.short, m.color, m.code
 */
export function useSectorMeta() {
  const companies = useCompaniesStore();

  /**
   * Map from canonical code to {label, short, color}.
   * Reactive — updates when companies store loads sectors[] or when
   * admin edits a sector's name_ru in Companies admin.
   */
  const byCodeMap = computed<Record<SectorCode, SectorMetaEntry>>(() => {
    const result = {} as Record<SectorCode, SectorMetaEntry>;
    for (const code of SECTOR_ORDER) {
      // Try to find a real sector row whose code normalizes to this bucket
      let label = t(FALLBACK_LABELS[code]);
      for (const sec of companies.sectors) {
        if (canonSectorCode(sec.code) === code && sec.name_ru) {
          label = sectorDisplayName(sec);
          break;
        }
      }
      result[code] = {
        code,
        label,
        short: sectorShortLabel(label),
        color: SECTOR_COLORS[code],
      };
    }
    return result;
  });

  /** Lookup metadata for ANY raw sector code (normalizes internally). */
  function byCode(raw: string | null | undefined): SectorMetaEntry {
    const code = canonSectorCode(raw) as SectorCode;
    return byCodeMap.value[code];
  }

  /** Full list of all 5 sectors in display order. */
  const list = computed<SectorMetaEntry[]>(() =>
    SECTOR_ORDER.map(code => byCodeMap.value[code])
  );

  return {
    SECTOR_ORDER,
    SECTOR_COLORS,
    byCode,
    byCodeMap,
    list,
    canonCode: canonSectorCode,
  };
}
