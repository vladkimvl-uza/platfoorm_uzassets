-- BP 2025 annual fact backfill from NSBU PL reports.
-- Only fills `fact` where it is currently NULL — never overwrites user input.
-- Ran 2026-05-23 per explicit user approval.
--
-- Per-company best-source pick (editor > firebase > raw NSBU) via DISTINCT ON.
-- 9 metrics mapped 1:1 by line_code: revenue, cogs, grossProfit, opProfit,
-- finIncome, finCost, pbt, tax, profit. Other BP metrics (opExpenses /
-- sub-items) not in NSBU PL — стают NULL.

BEGIN;

-- Snapshot BEFORE
SELECT 'BEFORE: bp_records 2025 annual with fact' AS scope,
       COUNT(*) FILTER (WHERE fact IS NOT NULL) AS with_fact,
       COUNT(*) FILTER (WHERE fact IS NULL)     AS without_fact,
       COUNT(*) AS total_rows
FROM bp_records WHERE year=2025 AND period='annual';

WITH ranked AS (
  SELECT DISTINCT ON (fr.company_id, fl.line_code)
    fr.company_id,
    fl.line_code AS metric,
    fl.value
  FROM financial_reports fr
  JOIN financial_lines fl ON fl.report_id = fr.id
  WHERE fr.year = 2025
    AND fr.report_type = 'PL'
    AND fr.standard = 'NSBU'
    AND fl.value IS NOT NULL
    AND fl.line_code IN ('revenue','cogs','grossProfit','opProfit','finIncome','finCost','pbt','tax','profit')
  ORDER BY fr.company_id, fl.line_code,
    CASE fr.source
      WHEN 'nsbu-editor'         THEN 1
      WHEN 'firebase_sparse_fix' THEN 2
      WHEN 'NSBU'                THEN 3
      ELSE 9
    END
)
INSERT INTO bp_records (id, company_id, year, period, metric, fact, created_at, updated_at)
SELECT gen_random_uuid(), r.company_id, 2025, 'annual', r.metric, r.value, NOW(), NOW()
FROM ranked r
ON CONFLICT (company_id, year, period, metric) DO UPDATE
  SET fact = EXCLUDED.fact,
      updated_at = NOW()
  WHERE bp_records.fact IS NULL;

-- Snapshot AFTER
SELECT 'AFTER: bp_records 2025 annual with fact' AS scope,
       COUNT(*) FILTER (WHERE fact IS NOT NULL) AS with_fact,
       COUNT(*) FILTER (WHERE fact IS NULL)     AS without_fact,
       COUNT(*) AS total_rows
FROM bp_records WHERE year=2025 AND period='annual';

-- Per-company breakdown AFTER
SELECT c.name_ru,
       COUNT(*) FILTER (WHERE br.fact IS NOT NULL) AS with_fact,
       COUNT(*) FILTER (WHERE br.plan IS NOT NULL) AS with_plan
FROM bp_records br
JOIN companies c ON c.id = br.company_id
WHERE br.year=2025 AND br.period='annual'
GROUP BY c.name_ru
ORDER BY c.name_ru;

COMMIT;
