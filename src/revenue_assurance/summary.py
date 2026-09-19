"""Text report builders. Pure string formatting from already-computed
inputs — no I/O, no DB, no plotting.
"""

from __future__ import annotations

import pandas as pd

from revenue_assurance.anomaly import IQRResult, ZScoreResult


def dq_issue_detail_text(issue_detail: dict) -> str:
    dup = issue_detail["duplicate_invoices"]
    orphan_inv = issue_detail["orphan_invoices"]
    orphan_pay = issue_detail["orphan_payments"]
    late = issue_detail["late_invoices"]
    invalid_amt = issue_detail["invalid_amounts"]
    invalid_tax = issue_detail["invalid_tax_rates"]

    lines = [
        "Data Quality Issue Detail",
        "=" * 40,
        f"Duplicate invoice numbers: {dup['n']} duplicate groups, ${dup['value_at_risk']:,.2f} at risk",
        f"Orphan invoices (bad customer FK): {orphan_inv['n']}, ${orphan_inv['value_at_risk']:,.2f} at risk",
        f"Orphan payments (bad invoice FK): {orphan_pay['n']}",
        f"Late invoices (>30 days after billing month): {late['n']}, avg {late['avg_days_late']:.1f} days late",
        f"Negative invoice amounts: {invalid_amt['n']}",
        f"Invalid tax rates (outside 0-30%): {invalid_tax['n']}",
    ]
    return "\n".join(lines)


def anomaly_summary_text(
    zscore_result: ZScoreResult,
    iqr_result: IQRResult,
    iqr_outliers: pd.DataFrame,
    iso_anomalies: pd.DataFrame,
) -> str:
    lines = [
        "Anomaly Monitoring — Summary",
        "=" * 40,
        "",
        "1. Monthly revenue z-score anomalies:",
    ]
    if len(zscore_result.anomalous_index) == 0:
        lines.append("   None detected.")
    else:
        for m in zscore_result.anomalous_index:
            lines.append(f"   {m}: revenue=${zscore_result.series[m]:,.2f}  z-score={zscore_result.zscore[m]:.2f}")

    lines += [
        "",
        f"2. IQR-based invoice outliers: {len(iqr_outliers):,} invoices flagged "
        f"(fences: ${iqr_result.lower_fence:.2f} - ${iqr_result.upper_fence:.2f})",
        f"   Total value flagged: ${iqr_outliers['amount'].sum():,.2f}",
        "",
        f"3. Isolation Forest anomalies: {len(iso_anomalies):,} invoices flagged",
        f"   Total value flagged: ${iso_anomalies['amount'].sum():,.2f}",
        "   Top 10 most anomalous:",
    ]
    top10 = iso_anomalies.nsmallest(10, "anomaly_decision")[["invoice_id", "customer_id", "amount", "expected_amount"]]
    lines.append(top10.to_string(index=False))

    return "\n".join(lines)
