"""Thin query layer over the rule-based DQ views defined in
sql/03_data_quality_rules.sql. Each function is a single, named query — the
actual DQ logic lives in SQL, not here, so this module is intentionally
free of business logic to keep the SQL as the single source of truth.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy.engine import Engine


def get_scorecard(engine: Engine) -> pd.DataFrame:
    return pd.read_sql("SELECT * FROM dq_scorecard ORDER BY score_pct", engine)


def get_completeness_breakdown(engine: Engine) -> pd.DataFrame:
    return pd.read_sql(
        "SELECT issue, COUNT(*) AS n FROM dq_completeness_invoices GROUP BY issue "
        "UNION ALL "
        "SELECT issue, COUNT(*) AS n FROM dq_completeness_customers GROUP BY issue "
        "ORDER BY n DESC",
        engine,
    )


def get_issue_detail(engine: Engine) -> dict:
    """Fetch scalar summary figures for each specific DQ issue type."""
    dup = pd.read_sql(
        "SELECT COUNT(*) AS n, COALESCE(SUM(total_amount_at_risk),0) AS value_at_risk "
        "FROM dq_duplicate_invoice_numbers", engine,
    ).iloc[0]
    orphan_inv = pd.read_sql(
        "SELECT COUNT(*) AS n, COALESCE(SUM(amount),0) AS value_at_risk FROM dq_orphan_invoices",
        engine,
    ).iloc[0]
    orphan_pay = pd.read_sql("SELECT COUNT(*) AS n FROM dq_orphan_payments", engine).iloc[0]
    late = pd.read_sql(
        "SELECT COUNT(*) AS n, AVG(days_late) AS avg_days_late FROM dq_late_invoices", engine,
    ).iloc[0]
    invalid_amt = pd.read_sql("SELECT COUNT(*) AS n FROM dq_invalid_amounts", engine).iloc[0]
    invalid_tax = pd.read_sql("SELECT COUNT(*) AS n FROM dq_invalid_tax_rate", engine).iloc[0]

    return {
        "duplicate_invoices": dup,
        "orphan_invoices": orphan_inv,
        "orphan_payments": orphan_pay,
        "late_invoices": late,
        "invalid_amounts": invalid_amt,
        "invalid_tax_rates": invalid_tax,
    }


def get_clean_invoices(engine: Engine) -> pd.DataFrame:
    """Rows that already pass basic DQ checks (non-null, positive amount, has
    a date) — feeds anomaly monitoring, which should look for *new*
    statistical anomalies rather than rediscovering the DQ engine's defects.
    """
    query = """
        SELECT i.invoice_id, i.customer_id, i.billing_month, i.invoice_date, i.amount,
               s.plan_id, p.monthly_price, p.tax_rate_pct
        FROM invoices i
        JOIN customers c ON c.customer_id = i.customer_id
        JOIN subscriptions s ON s.subscription_id = i.subscription_id
        JOIN plans p ON p.plan_id = s.plan_id
        WHERE i.amount IS NOT NULL AND i.amount > 0
          AND i.invoice_date IS NOT NULL
    """
    return pd.read_sql(query, engine)
