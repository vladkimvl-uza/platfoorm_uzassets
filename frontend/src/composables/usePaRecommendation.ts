/**
 *
 * Returns an HTML string with a short text recommendation based on
 * the company's overall deviation and best/worst categories.
 *
 *   1. companyDeviation < -3 + bestCats → "Лидер рейтинга. Хорошие практики..."
 *   2. companyDeviation > 10 + worstCats → "Сосредоточиться на ... — потенциал экономии..."
 *   3. worstCats[0] > 0 → "Точечная оптимизация по ..."
 *   4. else → "Закупки в пределах нормы."
 */
import { paFmtMoneyShort } from "@/api/procurement_analysis";
import type { CategoryDeviation, CompanyRatingRow } from "@/api/procurement_analysis";

function escHtml(s: string): string {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function catName(d: CategoryDeviation): string {
  return d.category_name || `категория ${d.category_id}`;
}

export function paGenerateRecommendation(co: CompanyRatingRow): string {
  if (co.company_deviation < -3 && co.best_cats.length) {
    const top = co.best_cats[0];
    return (
      "Лидер рейтинга. Хорошие практики по <b>" +
      escHtml(catName(top)) +
      "</b> (" +
      top.deviation_pct.toFixed(1) +
      "% к рынку) — рассмотреть как образец для других компаний."
    );
  }

  if (co.company_deviation > 10 && co.worst_cats.length) {
    const top2 = co.worst_cats.slice(0, 2);
    const names = top2.map((d) => escHtml(catName(d))).join(" и ");
    const sav = paFmtMoneyShort(Math.max(0, co.sum_dev));
    return (
      "Сосредоточиться на <b>" + names + "</b> — потенциал экономии " + sav + " сум."
    );
  }

  if (co.worst_cats.length) {
    const top1 = co.worst_cats[0];
    if (top1.deviation_pct > 0) {
      return (
        "Точечная оптимизация по <b>" +
        escHtml(catName(top1)) +
        "</b> (" +
        (top1.deviation_pct >= 0 ? "+" : "") +
        top1.deviation_pct.toFixed(1) +
        "% к рынку)."
      );
    }
  }

  return "Закупки в пределах нормы. Продолжать мониторинг динамики цен.";
}

/**
 * Long recommendation for the company drill modal.
 */
export function paGenerateCompanyRecommendation(
  co: CompanyRatingRow,
  worst: { categoryName: string; deviationPct: number } | null,
): string {
  const devPct = co.company_deviation;
  const overpay = Math.max(0, co.sum_dev);
  const redCount = co.above_count;

  if (devPct >= 10 && worst) {
    return (
      'Среднее отклонение <b style="color:#C53030">+' +
      devPct.toFixed(1) +
      "%</b> требует внимания. Особое отклонение в категории <b>" +
      escHtml(worst.categoryName) +
      "</b> (" +
      (worst.deviationPct >= 0 ? "+" : "") +
      worst.deviationPct.toFixed(1) +
      "%). Рекомендуется аудит закупочных процедур и пересмотр поставщиков по топ-3 проблемным категориям. Потенциал экономии при переходе на средние цены — <b>" +
      paFmtMoneyShort(overpay) +
      " сум/год</b>."
    );
  }

  if (devPct >= 0) {
    return (
      'Среднее отклонение <b style="color:#B07415">+' +
      devPct.toFixed(1) +
      "%</b> — в пределах нормы. По " +
      redCount +
      " категориям из " +
      co.cat_count +
      " закупка выше рынка. Рекомендуется мониторинг этих категорий и сравнение поставщиков с лидерами рейтинга."
    );
  }

  return (
    'Среднее отклонение <b style="color:#0F6E56">' +
    devPct.toFixed(1) +
    "%</b> — закупки эффективнее рынка. Хорошие закупочные практики — стоит задокументировать методику и поделиться с другими компаниями. Экономия за период составила <b>" +
    paFmtMoneyShort(Math.abs(co.sum_dev)) +
    " сум</b>."
  );
}
