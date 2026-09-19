-- ============================================================
-- Data Quality Rule Engine
-- ============================================================
-- One view per classic DQ dimension: Completeness, Uniqueness,
-- Validity, Consistency (referential integrity), Timeliness.
-- Each returns the offending rows plus a summary view rolling
-- everything up into a per-dimension score out of 100.
-- ============================================================

-- ------------------------------------------------------------
-- COMPLETENESS: required fields that are NULL
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dq_completeness_customers AS
SELECT customer_id, 'missing_name' AS issue FROM customers WHERE customer_name IS NULL
UNION ALL
SELECT customer_id, 'missing_country' FROM customers WHERE country IS NULL;

CREATE OR REPLACE VIEW dq_completeness_invoices AS
SELECT invoice_id, 'missing_invoice_date' AS issue FROM invoices WHERE invoice_date IS NULL
UNION ALL
SELECT invoice_id, 'missing_amount' FROM invoices WHERE amount IS NULL;

-- ------------------------------------------------------------
-- UNIQUENESS: invoice_number should be unique but isn't
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dq_duplicate_invoice_numbers AS
SELECT invoice_number, COUNT(*) AS occurrences, ARRAY_AGG(invoice_id) AS invoice_ids,
       SUM(amount) AS total_amount_at_risk
FROM invoices
WHERE invoice_number IS NOT NULL
GROUP BY invoice_number
HAVING COUNT(*) > 1;

-- ------------------------------------------------------------
-- VALIDITY: values outside their allowed business range
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dq_invalid_amounts AS
SELECT invoice_id, amount, 'negative_amount' AS issue
FROM invoices WHERE amount < 0;

CREATE OR REPLACE VIEW dq_invalid_tax_rate AS
SELECT invoice_id, tax_rate_pct, 'tax_rate_out_of_range' AS issue
FROM invoices WHERE tax_rate_pct < 0 OR tax_rate_pct > 30;

-- ------------------------------------------------------------
-- CONSISTENCY: referential integrity across tables
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dq_orphan_invoices AS
SELECT i.invoice_id, i.customer_id, i.subscription_id, i.amount
FROM invoices i
LEFT JOIN customers c ON c.customer_id = i.customer_id
WHERE c.customer_id IS NULL;

CREATE OR REPLACE VIEW dq_orphan_payments AS
SELECT p.payment_id, p.invoice_id, p.amount_paid
FROM payments p
LEFT JOIN invoices i ON i.invoice_id = p.invoice_id
WHERE p.invoice_id IS NOT NULL AND i.invoice_id IS NULL;

-- ------------------------------------------------------------
-- TIMELINESS: invoices generated well after their billing month
-- (>30 days is treated as an SLA breach)
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dq_late_invoices AS
SELECT invoice_id, billing_month, invoice_date,
       (invoice_date - TO_DATE(billing_month || '-01', 'YYYY-MM-DD')) AS days_late
FROM invoices
WHERE invoice_date IS NOT NULL
  AND invoice_date - TO_DATE(billing_month || '-01', 'YYYY-MM-DD') > 30;

-- ------------------------------------------------------------
-- DQ SCORECARD: one row per dimension, % of invoice rows clean
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW dq_scorecard AS
WITH totals AS (SELECT COUNT(*)::numeric AS n_invoices FROM invoices),
     completeness_bad AS (SELECT COUNT(DISTINCT invoice_id) AS n FROM dq_completeness_invoices),
     uniqueness_bad AS (SELECT COALESCE(SUM(occurrences - 1), 0) AS n FROM dq_duplicate_invoice_numbers),
     validity_bad AS (
        SELECT COUNT(*) AS n FROM (
            SELECT invoice_id FROM dq_invalid_amounts
            UNION
            SELECT invoice_id FROM dq_invalid_tax_rate
        ) v
     ),
     consistency_bad AS (SELECT COUNT(*) AS n FROM dq_orphan_invoices),
     timeliness_bad AS (SELECT COUNT(*) AS n FROM dq_late_invoices)
SELECT 'Completeness' AS dimension, n_invoices, completeness_bad.n AS defective_rows,
       ROUND(100 * (1 - completeness_bad.n / n_invoices), 2) AS score_pct
FROM totals, completeness_bad
UNION ALL
SELECT 'Uniqueness', n_invoices, uniqueness_bad.n,
       ROUND(100 * (1 - uniqueness_bad.n / n_invoices), 2)
FROM totals, uniqueness_bad
UNION ALL
SELECT 'Validity', n_invoices, validity_bad.n,
       ROUND(100 * (1 - validity_bad.n / n_invoices), 2)
FROM totals, validity_bad
UNION ALL
SELECT 'Consistency', n_invoices, consistency_bad.n,
       ROUND(100 * (1 - consistency_bad.n / n_invoices), 2)
FROM totals, consistency_bad
UNION ALL
SELECT 'Timeliness', n_invoices, timeliness_bad.n,
       ROUND(100 * (1 - timeliness_bad.n / n_invoices), 2)
FROM totals, timeliness_bad;
