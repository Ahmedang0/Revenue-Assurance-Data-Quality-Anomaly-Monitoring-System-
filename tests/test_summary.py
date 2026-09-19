"""Unit tests for revenue_assurance.summary — pure string formatting."""

from __future__ import annotations

import pandas as pd

from revenue_assurance.anomaly import iqr_outliers, rolling_zscore
from revenue_assurance.summary import anomaly_summary_text, dq_issue_detail_text


def test_dq_issue_detail_text_includes_all_figures():
    issue_detail = {
        "duplicate_invoices": {"n": 5, "value_at_risk": 123.45},
        "orphan_invoices": {"n": 3, "value_at_risk": 67.89},
        "orphan_payments": {"n": 2},
        "late_invoices": {"n": 4, "avg_days_late": 42.0},
        "invalid_amounts": {"n": 1},
        "invalid_tax_rates": {"n": 6},
    }
    text = dq_issue_detail_text(issue_detail)

    assert "5 duplicate groups" in text
    assert "$123.45" in text
    assert "42.0 days late" in text


def test_anomaly_summary_text_reports_no_zscore_anomalies():
    series = pd.Series([100.0, 105.0, 110.0, 108.0, 112.0])
    zscore_result = rolling_zscore(series, window=3, threshold=2.5)
    iqr_result = iqr_outliers(series)
    empty_outliers = pd.DataFrame({"amount": []})
    empty_iso = pd.DataFrame({
        "invoice_id": [], "customer_id": [], "amount": [], "expected_amount": [], "anomaly_decision": [],
    })

    text = anomaly_summary_text(zscore_result, iqr_result, empty_outliers, empty_iso)

    assert "None detected." in text
