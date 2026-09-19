"""Generates a synthetic SaaS subscription billing dataset with:
 (a) injected data-quality defects — completeness, validity, uniqueness,
     consistency (referential integrity), and timeliness issues — the
     kind a rule-based DQ engine should catch, and
 (b) injected revenue anomalies — statistically unusual but individually
     "valid" values (a demand-shock month, a handful of customers billed
     way outside their own normal pattern) — the kind that needs
     statistical monitoring (z-score/IQR/Isolation Forest), not simple
     rule checks, to catch.

Kept as pure functions returning DataFrames (no file I/O) so the generation
logic is unit-testable; `scripts`-style CSV writing is a thin wrapper in cli.py.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

PLANS = pd.DataFrame([
    {"plan_id": 1, "plan_name": "Starter",    "monthly_price": 9.00,  "tax_rate_pct": 5.0},
    {"plan_id": 2, "plan_name": "Growth",     "monthly_price": 29.00, "tax_rate_pct": 5.0},
    {"plan_id": 3, "plan_name": "Pro",        "monthly_price": 79.00, "tax_rate_pct": 5.0},
    {"plan_id": 4, "plan_name": "Enterprise", "monthly_price": 199.00, "tax_rate_pct": 5.0},
])

COUNTRIES = ["United States", "United Kingdom", "Germany", "UAE", "Egypt", "India", "Canada", "Australia"]

DEFAULT_MONTHS = [f"2023-{m:02d}" for m in range(1, 13)] + [f"2024-{m:02d}" for m in range(1, 13)]
ANOMALY_SHOCK_MONTH = "2024-07"


def _month_start(m: str) -> date:
    y, mo = map(int, m.split("-"))
    return date(y, mo, 1)


def _month_add(d: date, n: int) -> date:
    total = d.month - 1 + n
    y = d.year + total // 12
    m = total % 12 + 1
    return date(y, m, 1)


@dataclass
class GeneratedDataset:
    plans: pd.DataFrame
    customers: pd.DataFrame
    subscriptions: pd.DataFrame
    invoices: pd.DataFrame
    payments: pd.DataFrame


def generate_customers_and_subscriptions(
    n_customers: int, months: list[str], rng: np.random.Generator
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate customers (with injected completeness defects) and their 1:1 subscriptions."""
    plan_ids = rng.choice(PLANS["plan_id"], size=n_customers, p=[0.40, 0.32, 0.20, 0.08])
    signup_month_idx = rng.integers(0, len(months) - 4, size=n_customers)  # leave room for tenure
    is_churned = rng.random(n_customers) < 0.18

    customers, subscriptions = [], []
    for i in range(n_customers):
        cid = i + 1
        signup = _month_start(months[signup_month_idx[i]])
        churn_date = None
        if is_churned[i]:
            tenure_months = int(rng.integers(2, 18))
            churn_date = _month_add(signup, tenure_months)
            if churn_date > _month_start(months[-1]):
                churn_date = None

        customers.append({
            "customer_id": cid,
            "customer_name": f"Customer_{cid:05d}",
            "signup_date": signup,
            "country": rng.choice(COUNTRIES),
            "status": "churned" if churn_date else "active",
        })
        subscriptions.append({
            "subscription_id": cid,  # 1:1 for simplicity
            "customer_id": cid,
            "plan_id": int(plan_ids[i]),
            "start_date": signup,
            "end_date": churn_date,
        })

    customers_df = pd.DataFrame(customers)
    subs_df = pd.DataFrame(subscriptions)

    # --- Inject completeness defects into customers ---
    missing_name_idx = rng.choice(customers_df.index, size=int(0.02 * n_customers), replace=False)
    customers_df.loc[missing_name_idx, "customer_name"] = None
    missing_country_idx = rng.choice(customers_df.index, size=int(0.015 * n_customers), replace=False)
    customers_df.loc[missing_country_idx, "country"] = None

    return customers_df, subs_df


def generate_invoices(
    customers_df: pd.DataFrame,
    subs_df: pd.DataFrame,
    months: list[str],
    rng: np.random.Generator,
    shock_month: str = ANOMALY_SHOCK_MONTH,
) -> pd.DataFrame:
    """Generate monthly invoices per active subscription, with both revenue
    anomalies (shock month + rare outlier customers) and structural DQ
    defects (missing fields, negative amounts, duplicates, orphan FKs, late invoicing).
    """
    plan_lookup = PLANS.set_index("plan_id").to_dict("index")
    sub_lookup = subs_df.set_index("customer_id").to_dict("index")

    invoices = []
    invoice_id = 1

    for _, cust in customers_df.iterrows():
        cid = cust["customer_id"]
        sub = sub_lookup[cid]
        plan = plan_lookup[sub["plan_id"]]
        start = sub["start_date"]
        end = sub["end_date"] if sub["end_date"] else _month_start(months[-1])

        m = start
        while m <= end:
            billing_month = f"{m.year}-{m.month:02d}"
            if billing_month not in months:
                break

            base_amount = round(plan["monthly_price"] * (1 + plan["tax_rate_pct"] / 100), 2)
            amount = base_amount
            tax_rate = plan["tax_rate_pct"]
            invoice_date = m + timedelta(days=int(rng.integers(0, 3)))

            # --- Revenue anomaly: demand-shock month gets ~15% double-charged ---
            if billing_month == shock_month and rng.random() < 0.15:
                amount = round(base_amount * 2, 2)

            # --- Revenue anomaly: a rare customer billed way outside their own normal pattern ---
            if rng.random() < 0.004:
                amount = round(base_amount * rng.uniform(6, 12), 2)

            invoice_number = f"INV-{billing_month.replace('-', '')}-{cid:05d}"

            invoices.append({
                "invoice_id": invoice_id,
                "invoice_number": invoice_number,
                "customer_id": cid,
                "subscription_id": sub["subscription_id"],
                "billing_month": billing_month,
                "invoice_date": invoice_date,
                "amount": amount,
                "tax_rate_pct": tax_rate,
            })
            invoice_id += 1
            m = _month_add(m, 1)

    invoices_df = pd.DataFrame(invoices)
    invoices_df, next_id = _inject_invoice_dq_defects(invoices_df, rng, next_invoice_id=invoice_id)
    return invoices_df


def _inject_invoice_dq_defects(
    invoices_df: pd.DataFrame, rng: np.random.Generator, next_invoice_id: int
) -> tuple[pd.DataFrame, int]:
    """Inject structural (non-statistical) data-quality defects into a clean invoice frame."""
    idx = invoices_df.index
    n_clean = len(invoices_df)

    # Completeness: missing invoice_date / amount
    missing_date_idx = rng.choice(idx, size=int(0.01 * n_clean), replace=False)
    invoices_df.loc[missing_date_idx, "invoice_date"] = None

    missing_amount_idx = rng.choice(idx, size=int(0.008 * n_clean), replace=False)
    invoices_df.loc[missing_amount_idx, "amount"] = None

    # Validity: negative amounts (refund miscoded as invoice), invalid tax rate
    negative_amount_idx = rng.choice(idx, size=int(0.006 * n_clean), replace=False)
    invoices_df.loc[negative_amount_idx, "amount"] = -invoices_df.loc[negative_amount_idx, "amount"].abs()

    bad_tax_idx = rng.choice(idx, size=int(0.005 * n_clean), replace=False)
    invoices_df.loc[bad_tax_idx, "tax_rate_pct"] = rng.choice([-5.0, 55.0, 150.0], size=len(bad_tax_idx))

    # Timeliness: invoice_date far later than billing month (SLA breach beyond 30 days)
    late_idx = rng.choice(idx, size=int(0.01 * n_clean), replace=False)
    for i in late_idx:
        bm = _month_start(invoices_df.loc[i, "billing_month"])
        invoices_df.loc[i, "invoice_date"] = bm + timedelta(days=int(rng.integers(45, 120)))

    # Uniqueness: duplicate a batch of invoices (double-billing defect)
    dup_source_idx = rng.choice(idx, size=int(0.007 * n_clean), replace=False)
    dup_rows = invoices_df.loc[dup_source_idx].copy()
    dup_rows["invoice_id"] = range(next_invoice_id, next_invoice_id + len(dup_rows))
    next_invoice_id += len(dup_rows)

    # Consistency: orphan invoices referencing a non-existent customer_id / subscription_id
    orphan_idx = rng.choice(idx, size=int(0.004 * n_clean), replace=False)
    invoices_df.loc[orphan_idx, "customer_id"] = invoices_df.loc[orphan_idx, "customer_id"] + 900000
    invoices_df.loc[orphan_idx, "subscription_id"] = invoices_df.loc[orphan_idx, "subscription_id"] + 900000

    invoices_df = pd.concat([invoices_df, dup_rows], ignore_index=True)
    return invoices_df, next_invoice_id


def generate_payments(invoices_df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Generate one payment per payable invoice, with ~1.5% missing and a batch of orphans."""
    payments = []
    payment_id = 1
    valid_invoices = invoices_df[invoices_df["amount"].notna() & (invoices_df["amount"] > 0)]
    payable = valid_invoices.sample(frac=0.985, random_state=int(rng.integers(0, 2**31 - 1)))

    for _, inv in payable.iterrows():
        pay_date = (
            pd.to_datetime(inv["invoice_date"]) + pd.Timedelta(days=int(rng.integers(0, 10)))
            if pd.notna(inv["invoice_date"]) else None
        )
        payments.append({
            "payment_id": payment_id,
            "invoice_id": inv["invoice_id"],
            "payment_date": pay_date.date() if pay_date is not None else None,
            "amount_paid": inv["amount"],
        })
        payment_id += 1

    payments_df = pd.DataFrame(payments)

    # Consistency: a batch of orphan payments referencing a non-existent invoice_id
    orphan_pay_idx = rng.choice(payments_df.index, size=int(0.003 * len(payments_df)), replace=False)
    payments_df.loc[orphan_pay_idx, "invoice_id"] = payments_df.loc[orphan_pay_idx, "invoice_id"] + 900000

    return payments_df


def generate_dataset(
    n_customers: int = 1500,
    months: list[str] | None = None,
    seed: int = 7,
) -> GeneratedDataset:
    """Generate the full synthetic dataset: plans, customers, subscriptions, invoices, payments."""
    months = months or DEFAULT_MONTHS
    rng = np.random.default_rng(seed)

    customers_df, subs_df = generate_customers_and_subscriptions(n_customers, months, rng)
    invoices_df = generate_invoices(customers_df, subs_df, months, rng)
    payments_df = generate_payments(invoices_df, rng)

    return GeneratedDataset(
        plans=PLANS.copy(),
        customers=customers_df,
        subscriptions=subs_df,
        invoices=invoices_df,
        payments=payments_df,
    )
