-- BP 2025 annual: nullify plan'ы которые явно введены не в той шкале
-- (fact/plan > 5×) — fact из NSBU корректный, оставляем; plan убираем
-- чтобы юзеры увидели "—" в Δ и перевводили план в правильной шкале.
-- Ран 2026-05-23 по user feedback (option 2).

BEGIN;

-- BEFORE
SELECT 'BEFORE: anomalous rows (fact/plan > 5)' AS scope, COUNT(*) cnt
FROM bp_records
WHERE year=2025 AND period='annual'
  AND plan IS NOT NULL AND fact IS NOT NULL
  AND (fact / NULLIF(plan, 0)) > 5;

-- The actual cleanup
UPDATE bp_records
SET plan = NULL,
    updated_at = NOW()
WHERE year=2025
  AND period='annual'
  AND plan IS NOT NULL
  AND fact IS NOT NULL
  AND (fact / NULLIF(plan, 0)) > 5;

-- AFTER
SELECT 'AFTER: anomalous rows (fact/plan > 5)' AS scope, COUNT(*) cnt
FROM bp_records
WHERE year=2025 AND period='annual'
  AND plan IS NOT NULL AND fact IS NOT NULL
  AND (fact / NULLIF(plan, 0)) > 5;

-- Verify each affected row
SELECT c.name_ru, br.metric, br.plan, br.fact
FROM bp_records br
JOIN companies c ON c.id = br.company_id
WHERE br.year=2025 AND br.period='annual'
  AND br.metric IN ('finIncome','finCost','fxLoss','fxIncome','tax')
  AND c.name_ru IN (
    'АО «Региональные электрические сети»',
    'АО «Национальные электрические сети Узбекистана»',
    'ГП «Навоийуран»',
    'Узкимёсаноат',
    'АО «Узметкомбинат»',
    'АО «Узбекуголь»'
  )
ORDER BY c.name_ru, br.metric;

COMMIT;
