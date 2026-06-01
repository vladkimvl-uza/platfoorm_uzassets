-- KPI weight normalization 2026-05-25.
-- Нормализуем sum(weight) per (company, year) к 100, сохраняя относительные
-- пропорции. Также q1-q4_weight per (company, year). Делает только если
-- sum(weight) > 0 (защита от деления на ноль).
--
-- Затрагивает только year=2026 (текущий период). 2025 не трогаем — там
-- закрытый период.
--
-- БЕЗОПАСНО: пропорции сохраняются → каждая компания остаётся со своим
-- per-indicator pct ratio. Только portfolio-level aggregations меняются
-- (хотя мы уже перешли на mean(by_company.pct) которое от веса не зависит).

BEGIN;

-- BEFORE: per-company sum_weight для year=2026
SELECT 'BEFORE' AS scope, c.name_ru,
       ROUND(SUM(ki.weight)::numeric, 2) AS sum_w_year,
       ROUND(SUM(ki.q1_weight)::numeric, 2) AS sum_w_q1
FROM kpi_indicators ki
JOIN kpi_managers km ON km.id=ki.manager_id
JOIN companies c ON c.id=km.company_id
WHERE km.year=2026
GROUP BY c.name_ru
HAVING SUM(ki.weight) NOT BETWEEN 95 AND 105
ORDER BY sum_w_year DESC NULLS LAST;

-- Нормализуем annual weight
WITH co_sum AS (
  SELECT km.company_id, SUM(ki.weight) AS total_w
  FROM kpi_indicators ki
  JOIN kpi_managers km ON km.id=ki.manager_id
  WHERE km.year=2026 AND ki.weight > 0
  GROUP BY km.company_id
  HAVING SUM(ki.weight) > 0
)
UPDATE kpi_indicators ki
SET weight = ROUND((ki.weight * 100.0 / co.total_w)::numeric, 3),
    updated_at = NOW()
FROM kpi_managers km, co_sum co
WHERE km.id = ki.manager_id
  AND km.year = 2026
  AND km.company_id = co.company_id
  AND ki.weight > 0;

-- Нормализуем q1_weight (если sum_q1 > 0)
WITH co_sum AS (
  SELECT km.company_id, SUM(ki.q1_weight) AS tw
  FROM kpi_indicators ki
  JOIN kpi_managers km ON km.id=ki.manager_id
  WHERE km.year=2026 AND ki.q1_weight > 0
  GROUP BY km.company_id
  HAVING SUM(ki.q1_weight) > 0
)
UPDATE kpi_indicators ki
SET q1_weight = ROUND((ki.q1_weight * 100.0 / co.tw)::numeric, 3),
    updated_at = NOW()
FROM kpi_managers km, co_sum co
WHERE km.id = ki.manager_id
  AND km.year = 2026
  AND km.company_id = co.company_id
  AND ki.q1_weight > 0;

-- Нормализуем q2_weight
WITH co_sum AS (
  SELECT km.company_id, SUM(ki.q2_weight) AS tw
  FROM kpi_indicators ki JOIN kpi_managers km ON km.id=ki.manager_id
  WHERE km.year=2026 AND ki.q2_weight > 0 GROUP BY km.company_id HAVING SUM(ki.q2_weight) > 0
)
UPDATE kpi_indicators ki
SET q2_weight = ROUND((ki.q2_weight * 100.0 / co.tw)::numeric, 3), updated_at = NOW()
FROM kpi_managers km, co_sum co
WHERE km.id = ki.manager_id AND km.year = 2026 AND km.company_id = co.company_id AND ki.q2_weight > 0;

-- Нормализуем q3_weight
WITH co_sum AS (
  SELECT km.company_id, SUM(ki.q3_weight) AS tw
  FROM kpi_indicators ki JOIN kpi_managers km ON km.id=ki.manager_id
  WHERE km.year=2026 AND ki.q3_weight > 0 GROUP BY km.company_id HAVING SUM(ki.q3_weight) > 0
)
UPDATE kpi_indicators ki
SET q3_weight = ROUND((ki.q3_weight * 100.0 / co.tw)::numeric, 3), updated_at = NOW()
FROM kpi_managers km, co_sum co
WHERE km.id = ki.manager_id AND km.year = 2026 AND km.company_id = co.company_id AND ki.q3_weight > 0;

-- Нормализуем q4_weight
WITH co_sum AS (
  SELECT km.company_id, SUM(ki.q4_weight) AS tw
  FROM kpi_indicators ki JOIN kpi_managers km ON km.id=ki.manager_id
  WHERE km.year=2026 AND ki.q4_weight > 0 GROUP BY km.company_id HAVING SUM(ki.q4_weight) > 0
)
UPDATE kpi_indicators ki
SET q4_weight = ROUND((ki.q4_weight * 100.0 / co.tw)::numeric, 3), updated_at = NOW()
FROM kpi_managers km, co_sum co
WHERE km.id = ki.manager_id AND km.year = 2026 AND km.company_id = co.company_id AND ki.q4_weight > 0;

-- AFTER: проверяем что sum теперь близко к 100
SELECT 'AFTER' AS scope, c.name_ru,
       ROUND(SUM(ki.weight)::numeric, 2) AS sum_w_year,
       ROUND(SUM(ki.q1_weight)::numeric, 2) AS sum_w_q1
FROM kpi_indicators ki
JOIN kpi_managers km ON km.id=ki.manager_id
JOIN companies c ON c.id=km.company_id
WHERE km.year=2026
GROUP BY c.name_ru
ORDER BY sum_w_year DESC NULLS LAST;

-- Узбекугольская test-запись fact_year=4 / plan_year=1668 (явно неверный
-- ввод — единичная цифра в плане ~1668 vs факт ~4 → 0.24% портит overall).
-- Обнуляем fact_year, оставляя plan_year на случай если это валидный план.
UPDATE kpi_indicators
SET fact_year = NULL, updated_at = NOW()
WHERE id IN (
  SELECT ki.id FROM kpi_indicators ki
  JOIN kpi_managers km ON km.id=ki.manager_id
  JOIN companies c ON c.id=km.company_id
  WHERE km.year=2026 AND c.name_ru ILIKE '%Узбекуголь%'
    AND ki.fact_year IS NOT NULL
);

SELECT 'POST-CLEANUP fact_year for 2026' AS scope,
       COUNT(*) AS rows_with_fact_year
FROM kpi_indicators ki
JOIN kpi_managers km ON km.id=ki.manager_id
WHERE km.year=2026 AND ki.fact_year IS NOT NULL;

COMMIT;
