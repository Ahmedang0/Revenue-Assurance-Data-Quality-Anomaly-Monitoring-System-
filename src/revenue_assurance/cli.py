"""Command-line entry point: `revenue-assurance <subcommand>`
(after `pip install -e .`) or `python -m revenue_assurance.cli <subcommand>`.

Subcommands:
    generate-data   Generate the synthetic dataset and write CSVs to data/
    dq-report       Run the rule-based DQ scorecard + issue breakdown (needs Postgres)
    anomaly-report  Run z-score, IQR, and Isolation Forest anomaly monitoring (needs Postgres)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from revenue_assurance.anomaly import isolation_forest_anomalies, iqr_outliers, rolling_zscore
from revenue_assurance.anomaly_store import store_isolation_forest_flags, store_iqr_flags, store_zscore_flags
from revenue_assurance.charts import (
    completeness_breakdown_chart,
    dq_scorecard_chart,
    invoice_amount_iqr_chart,
    isolation_forest_chart,
    monthly_revenue_zscore_chart,
)
from revenue_assurance.config import DEFAULT_DATA_DIR, DEFAULT_OUTPUT_DIR, ZSCORE_WINDOW
from revenue_assurance.data_generation import generate_dataset
from revenue_assurance.db import get_engine
from revenue_assurance.dq_queries import get_clean_invoices, get_completeness_breakdown, get_issue_detail, get_scorecard
from revenue_assurance.summary import anomaly_summary_text, dq_issue_detail_text

logger = logging.getLogger(__name__)


def _cmd_generate_data(args: argparse.Namespace) -> int:
    dataset = generate_dataset(n_customers=args.n_customers, seed=args.seed)
    args.data_dir.mkdir(parents=True, exist_ok=True)

    dataset.plans.to_csv(args.data_dir / "plans.csv", index=False)
    dataset.customers.to_csv(args.data_dir / "customers.csv", index=False)
    dataset.subscriptions.to_csv(args.data_dir / "subscriptions.csv", index=False)
    dataset.invoices.to_csv(args.data_dir / "invoices.csv", index=False)
    dataset.payments.to_csv(args.data_dir / "payments.csv", index=False)

    logger.info("Customers:     %d", len(dataset.customers))
    logger.info("Subscriptions: %d", len(dataset.subscriptions))
    logger.info("Invoices:      %d", len(dataset.invoices))
    logger.info("Payments:      %d", len(dataset.payments))
    logger.info("Wrote CSVs to %s", args.data_dir)
    return 0


def _cmd_dq_report(args: argparse.Namespace) -> int:
    engine = get_engine()

    logger.info("Fetching DQ scorecard...")
    scorecard = get_scorecard(engine)
    dq_scorecard_chart(scorecard, args.output_dir)

    logger.info("Fetching completeness breakdown...")
    breakdown = get_completeness_breakdown(engine)
    completeness_breakdown_chart(breakdown, args.output_dir)

    logger.info("Fetching issue detail...")
    issue_detail = get_issue_detail(engine)
    text = dq_issue_detail_text(issue_detail)
    (args.output_dir / "dq_issue_detail.txt").write_text(text)
    print(text)

    scorecard.to_csv(args.output_dir / "dq_scorecard_export.csv", index=False)
    logger.info("Done. DQ charts and reports saved to %s", args.output_dir)
    return 0


def _cmd_anomaly_report(args: argparse.Namespace) -> int:
    engine = get_engine()
    clean = get_clean_invoices(engine)
    logger.info("Loaded %d clean-ish invoice rows for anomaly monitoring.", len(clean))

    logger.info("Running monthly revenue z-score detection...")
    monthly = clean.groupby("billing_month")["amount"].sum().sort_index()
    zscore_result = rolling_zscore(monthly, window=args.zscore_window)
    monthly_revenue_zscore_chart(zscore_result, args.output_dir, window=args.zscore_window)
    store_zscore_flags(engine, zscore_result)

    logger.info("Running IQR outlier detection on invoice amounts...")
    iqr_result = iqr_outliers(clean["amount"])
    outliers = clean[iqr_result.outlier_mask]
    invoice_amount_iqr_chart(clean["amount"], iqr_result, args.output_dir)
    store_iqr_flags(engine, outliers, iqr_result.lower_fence, iqr_result.upper_fence)

    logger.info("Running Isolation Forest on per-customer invoice features...")
    feat = clean.copy()
    feat["expected_amount"] = feat["monthly_price"] * (1 + feat["tax_rate_pct"] / 100)
    feat["deviation_from_expected"] = feat["amount"] - feat["expected_amount"]
    feat["deviation_ratio"] = feat["amount"] / feat["expected_amount"]
    iso_result = isolation_forest_anomalies(
        feat[["amount", "deviation_from_expected", "deviation_ratio"]]
    )
    feat["anomaly_decision"] = iso_result.decision_score
    iso_anomalies = feat[iso_result.is_anomaly].sort_values("anomaly_decision")
    isolation_forest_chart(feat, iso_result, args.output_dir)
    store_isolation_forest_flags(engine, iso_anomalies, iso_result)

    text = anomaly_summary_text(zscore_result, iqr_result, outliers, iso_anomalies)
    (args.output_dir / "anomaly_summary.txt").write_text(text)
    print(text)

    logger.info("Done. Anomaly charts and reports saved to %s", args.output_dir)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="revenue-assurance",
        description="Revenue assurance: data quality checks + statistical anomaly monitoring.",
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_gen = subparsers.add_parser("generate-data", help="Generate the synthetic dataset")
    p_gen.add_argument("--n-customers", type=int, default=1500)
    p_gen.add_argument("--seed", type=int, default=7)
    p_gen.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    p_gen.set_defaults(func=_cmd_generate_data)

    p_dq = subparsers.add_parser("dq-report", help="Run the rule-based DQ scorecard (requires Postgres)")
    p_dq.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p_dq.set_defaults(func=_cmd_dq_report)

    p_anom = subparsers.add_parser("anomaly-report", help="Run statistical anomaly monitoring (requires Postgres)")
    p_anom.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    p_anom.add_argument("--zscore-window", type=int, default=ZSCORE_WINDOW)
    p_anom.set_defaults(func=_cmd_anomaly_report)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
