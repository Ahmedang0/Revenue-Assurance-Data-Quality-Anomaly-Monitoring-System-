"""Writes anomaly detection results to the `anomaly_flags` table. Separated
from anomaly.py (the pure detection math) so the math stays testable without
a database, and this module — which does nothing but I/O — doesn't need
its own elaborate tests beyond an integration check.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from revenue_assurance.anomaly import IsolationForestResult, ZScoreResult


def store_zscore_flags(engine: Engine, result: ZScoreResult) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM anomaly_flags WHERE scope = 'monthly_revenue'"))
        for m in result.anomalous_index:
            conn.execute(
                text(
                    "INSERT INTO anomaly_flags (scope, reference_key, metric_value, method, score, description) "
                    "VALUES ('monthly_revenue', :m, :v, 'zscore', :z, :desc)"
                ),
                {
                    "m": m, "v": float(result.series[m]), "z": float(result.zscore[m]),
                    "desc": f"Monthly revenue z-score {result.zscore[m]:.2f} vs rolling baseline",
                },
            )


def store_iqr_flags(engine: Engine, outliers: pd.DataFrame, lower: float, upper: float) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM anomaly_flags WHERE scope = 'invoice_iqr'"))
        for _, row in outliers.iterrows():
            score = (row["amount"] - upper) if row["amount"] > upper else (lower - row["amount"])
            conn.execute(
                text(
                    "INSERT INTO anomaly_flags (scope, reference_key, metric_value, method, score, description) "
                    "VALUES ('invoice_iqr', :ref, :v, 'iqr', :score, :desc)"
                ),
                {
                    "ref": str(row["invoice_id"]), "v": float(row["amount"]), "score": float(score),
                    "desc": f"Invoice {row['invoice_id']} (customer {row['customer_id']}) outside IQR fences",
                },
            )


def store_isolation_forest_flags(
    engine: Engine, anomalies: pd.DataFrame, result: IsolationForestResult
) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM anomaly_flags WHERE scope = 'customer_invoice'"))
        for idx, row in anomalies.iterrows():
            conn.execute(
                text(
                    "INSERT INTO anomaly_flags (scope, reference_key, metric_value, method, score, description) "
                    "VALUES ('customer_invoice', :ref, :v, 'isolation_forest', :score, :desc)"
                ),
                {
                    "ref": str(row["customer_id"]), "v": float(row["amount"]),
                    "score": float(result.decision_score[idx]),
                    "desc": f"Invoice {row['invoice_id']} billed ${row['amount']:.2f} vs expected ${row['expected_amount']:.2f}",
                },
            )
