"""Chart-generating functions. Each takes already-computed data (a
DataFrame, a Series, or an anomaly-detection result) and an output
directory, and returns the path of the PNG it wrote. None of these
functions touch the database or run detection themselves — that
separation is what makes charts.py safe to leave untested for anything
beyond "did it write a file" (tests/test_charts.py) while the real logic
in anomaly.py gets proper unit tests.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from revenue_assurance.anomaly import IsolationForestResult, IQRResult, ZScoreResult

logger = logging.getLogger(__name__)

sns.set_theme(style="whitegrid", palette="deep")
plt.rcParams["figure.dpi"] = 120


def _save(fig: plt.Figure, output_dir: Path, filename: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    logger.info("Wrote %s", path)
    return path


def dq_scorecard_chart(scorecard: pd.DataFrame, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 5.5))
    colors = ["#dc2626" if s < 99 else "#059669" for s in scorecard["score_pct"]]
    bars = ax.barh(scorecard["dimension"], scorecard["score_pct"], color=colors)
    ax.set_xlim(95, 100)
    ax.set_title("Data Quality Scorecard by Dimension")
    ax.set_xlabel("Score (% of rows passing)")
    for bar, score in zip(bars, scorecard["score_pct"]):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height() / 2, f"{score:.2f}%", va="center")
    return _save(fig, output_dir, "04_dq_scorecard.png")


def completeness_breakdown_chart(breakdown: pd.DataFrame, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(breakdown["issue"], breakdown["n"], color="#f59e0b")
    ax.set_title("Completeness Issues by Type")
    ax.set_ylabel("Records affected")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    return _save(fig, output_dir, "05_completeness_breakdown.png")


def monthly_revenue_zscore_chart(result: ZScoreResult, output_dir: Path, window: int) -> Path:
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.plot(result.series.index, result.series.values, marker="o", color="#2563eb", label="Monthly revenue")
    ax.plot(result.rolling_mean.index, result.rolling_mean.values, color="#94a3b8", linestyle="--",
             label=f"{window}-month rolling mean (prior months only)")
    for i, m in enumerate(result.anomalous_index):
        ax.scatter(m, result.series[m], color="#dc2626", s=140, zorder=5,
                    label="Anomaly" if i == 0 else None)
    ax.set_title("Monthly Revenue with Rolling Z-Score Anomaly Detection")
    ax.set_ylabel("Revenue ($)")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    ax.legend()
    return _save(fig, output_dir, "01_monthly_revenue_zscore.png")


def invoice_amount_iqr_chart(amounts: pd.Series, result: IQRResult, output_dir: Path) -> Path:
    fig, ax = plt.subplots(figsize=(9, 6))
    sns.boxplot(y=amounts, ax=ax, color="#7c3aed")
    ax.set_title(f"Invoice Amount Distribution (IQR fences: ${result.lower_fence:.2f} - ${result.upper_fence:.2f})")
    ax.set_ylabel("Invoice amount ($)")
    return _save(fig, output_dir, "02_invoice_amount_iqr.png")


def isolation_forest_chart(
    features: pd.DataFrame, result: IsolationForestResult, output_dir: Path
) -> Path:
    """`features` must include `expected_amount` and `amount` columns."""
    normal = features[~result.is_anomaly]
    anomalies = features[result.is_anomaly]

    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.scatter(normal["expected_amount"], normal["amount"], alpha=0.25, s=15, color="#94a3b8", label="Normal")
    ax.scatter(anomalies["expected_amount"], anomalies["amount"], alpha=0.8, s=40, color="#dc2626", label="Anomaly (Isolation Forest)")
    max_val = features["expected_amount"].max()
    ax.plot([0, max_val], [0, max_val], color="#2563eb", linestyle="--", linewidth=1, label="Expected = billed")
    ax.set_title("Invoice Amount vs. Expected Plan Charge — Isolation Forest Anomalies")
    ax.set_xlabel("Expected amount per plan ($)")
    ax.set_ylabel("Actual billed amount ($)")
    ax.legend()
    return _save(fig, output_dir, "03_isolation_forest_anomalies.png")
