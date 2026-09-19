-- ============================================================
-- Revenue Assurance: Data Quality & Anomaly Monitoring System
-- Schema
-- ============================================================
-- Models a subscription (SaaS-style) billing pipeline: customers on
-- plans, monthly invoices, and payments. Real billing pipelines
-- accumulate data-quality defects (missing fields, duplicate keys,
-- broken references, out-of-range values) and revenue anomalies
-- (sudden spikes/drops) that a revenue-assurance function must
-- continuously monitor for.
-- ============================================================

DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS invoices CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS plans CASCADE;

CREATE TABLE plans (
    plan_id         SERIAL PRIMARY KEY,
    plan_name       VARCHAR(50) NOT NULL,
    monthly_price   NUMERIC(10,2) NOT NULL,
    tax_rate_pct    NUMERIC(5,2) NOT NULL           -- expected valid range: 0-30
);

CREATE TABLE customers (
    customer_id     SERIAL PRIMARY KEY,
    customer_name   VARCHAR(100),                    -- nullable on purpose: completeness defects injected here
    signup_date     DATE NOT NULL,
    country         VARCHAR(50),
    status          VARCHAR(20) CHECK (status IN ('active','churned') OR status IS NULL)
);

CREATE TABLE subscriptions (
    subscription_id SERIAL PRIMARY KEY,
    customer_id     INTEGER REFERENCES customers(customer_id),
    plan_id         INTEGER REFERENCES plans(plan_id),
    start_date      DATE NOT NULL,
    end_date        DATE
);

-- Monthly invoices generated for each active subscription.
-- Intentionally NOT enforcing UNIQUE(subscription_id, billing_month) or
-- NOT NULL / CHECK constraints on amount here — those are exactly the
-- defects the data-quality rule engine (sql/02_data_quality_rules.sql)
-- is built to catch, mirroring how legacy billing systems accumulate
-- defects that predate stricter constraints.
CREATE TABLE invoices (
    invoice_id      SERIAL PRIMARY KEY,
    invoice_number  VARCHAR(20),                      -- should be unique; duplicates injected
    customer_id     INTEGER,                           -- FK not enforced: orphan rows injected on purpose
    subscription_id INTEGER,
    billing_month   VARCHAR(7) NOT NULL,               -- 'YYYY-MM'
    invoice_date    DATE,
    amount          NUMERIC(10,2),                      -- nullable / can be negative: validity defects injected
    tax_rate_pct    NUMERIC(6,2)
);

CREATE TABLE payments (
    payment_id      SERIAL PRIMARY KEY,
    invoice_id      INTEGER,                            -- FK not enforced: orphan rows injected on purpose
    payment_date    DATE,
    amount_paid     NUMERIC(10,2)
);

CREATE INDEX idx_invoices_customer ON invoices(customer_id);
CREATE INDEX idx_invoices_subscription ON invoices(subscription_id);
CREATE INDEX idx_payments_invoice ON payments(invoice_id);

-- ============================================================
-- Anomaly monitoring log — populated by the Python monitoring script
-- (scripts/anomaly_monitoring.py), not computed in SQL, since the
-- detection methods (rolling z-score, IQR, Isolation Forest) are
-- easier to express and iterate on in pandas/scikit-learn.
-- ============================================================
CREATE TABLE anomaly_flags (
    flag_id         SERIAL PRIMARY KEY,
    detected_at     TIMESTAMP DEFAULT now(),
    scope           VARCHAR(30) NOT NULL,   -- e.g. 'monthly_revenue', 'customer_invoice'
    reference_key   VARCHAR(50) NOT NULL,   -- billing_month or customer_id, depending on scope
    metric_value    NUMERIC(12,2),
    method          VARCHAR(30) NOT NULL,   -- 'zscore', 'iqr', 'isolation_forest'
    score           NUMERIC(10,4),
    description     TEXT
);
