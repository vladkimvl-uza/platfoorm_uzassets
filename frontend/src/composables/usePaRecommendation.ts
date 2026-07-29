/**
 * paGenerateRecommendation — 1:1 port of legacy function (line 22294).
 *
 * Returns an HTML string with a short text recommendation based on
 * the company's overall deviation and best/worst categories.
 *
 * Logic (verbatim from legacy):
 *   1. companyDeviation < -3 + bestCats → "Лидер рейтинга. Хорошие практики..."
 *   2. companyDeviation > 10 + worstCats → "Сосредоточиться на ... — потенциал экономии..."
 *   3. worstCats[0] > 0 → "Точечная оптимизация по ..."
 *   4. else → "Закупки в пределах нормы."
 */
import { paFmtMoneyShort } from "@/api/procurement_analysis";
import type { CategoryDeviation, CompanyRatingRow } from "@/api/procurement_analysis";
import { t } from "@/locale/i18n";
import { i18nKey } from "@/locale/keys";

function escHtml(s: string): string {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function catName(d: CategoryDeviation): string {
  return d.category_name || t("категория {id}", { id: d.category_id });
}

export function paGenerateRecommendation(co: CompanyRatingRow): string {
  if (co.company_deviation < -3 && co.best_cats.length) {
    const top = co.best_cats[0];
    return t(
      i18nKey("Лидер рейтинга. Хорошие практики по <b>{category}</b> ({percent}% к рынку) — рассмотреть как образец для других компаний."),
      { category: escHtml(catName(top)), percent: top.deviation_pct.toFixed(1) },
    );
  }

  if (co.company_deviation > 10 && co.worst_cats.length) {
    const top2 = co.worst_cats.slice(0, 2);
    const names = top2.map((d) => escHtml(catName(d))).join(t(" и "));
    const sav = paFmtMoneyShort(Math.max(0, co.sum_dev));
    return t("Сосредоточиться на <b>{categories}</b> — потенциал экономии {amount} сум.", {
      categories: names,
      amount: sav,
    });
  }

  if (co.worst_cats.length) {
    const top1 = co.worst_cats[0];
    if (top1.deviation_pct > 0) {
      return t("Точечная оптимизация по <b>{category}</b> ({percent}% к рынку).", {
        category: escHtml(catName(top1)),
        percent: `${top1.deviation_pct >= 0 ? "+" : ""}${top1.deviation_pct.toFixed(1)}`,
      });
    }
  }

  return t("Закупки в пределах нормы. Продолжать мониторинг динамики цен.");
}

/**
 * Long recommendation for the company drill modal.
 * Mirrors legacy `rec` block in paShowCompanyModal (line 22380+).
 */
export function paGenerateCompanyRecommendation(
  co: CompanyRatingRow,
  worst: { categoryName: string; deviationPct: number } | null,
): string {
  const devPct = co.company_deviation;
  const overpay = Math.max(0, co.sum_dev);
  const redCount = co.above_count;

  if (devPct >= 10 && worst) {
    return t(
      i18nKey('Среднее отклонение <b style="color:#C53030">+{deviation}%</b> требует внимания. Особое отклонение в категории <b>{category}</b> ({worstDeviation}%). Рекомендуется аудит закупочных процедур и пересмотр поставщиков по топ-3 проблемным категориям. Потенциал экономии при переходе на средние цены — <b>{amount} сум/год</b>.'),
      {
        deviation: devPct.toFixed(1),
        category: escHtml(worst.categoryName),
        worstDeviation: `${worst.deviationPct >= 0 ? "+" : ""}${worst.deviationPct.toFixed(1)}`,
        amount: paFmtMoneyShort(overpay),
      },
    );
  }

  if (devPct >= 0) {
    return t(
      i18nKey('Среднее отклонение <b style="color:#B07415">+{deviation}%</b> — в пределах нормы. По {redCount} категориям из {categoryCount} закупка выше рынка. Рекомендуется мониторинг этих категорий и сравнение поставщиков с лидерами рейтинга.'),
      { deviation: devPct.toFixed(1), redCount, categoryCount: co.cat_count },
    );
  }

  return t(
    i18nKey('Среднее отклонение <b style="color:#0F6E56">{deviation}%</b> — закупки эффективнее рынка. Хорошие закупочные практики — стоит задокументировать методику и поделиться с другими компаниями. Экономия за период составила <b>{amount} сум</b>.'),
    { deviation: devPct.toFixed(1), amount: paFmtMoneyShort(Math.abs(co.sum_dev)) },
  );
}
