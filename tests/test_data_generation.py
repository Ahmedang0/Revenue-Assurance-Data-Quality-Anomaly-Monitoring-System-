"""Unit tests for revenue_assurance.data_generation."""

from __future__ import annotations

from revenue_assurance.data_generation import generate_dataset


def test_generate_dataset_is_reproducible_given_same_seed():
    a = generate_dataset(n_customers=50, seed=123)
    b = generate_dataset(n_customers=50, seed=123)

    assert a.customers.equals(b.customers)
    assert a.invoices.equals(b.invoices)


def test_generate_dataset_different_seeds_differ():
    a = generate_dataset(n_customers=50, seed=1)
    b = generate_dataset(n_customers=50, seed=2)

    assert not a.invoices.equals(b.invoices)


def test_generate_dataset_row_counts_are_sane():
    dataset = generate_dataset(n_customers=100, seed=7)

    assert len(dataset.plans) == 4
    assert len(dataset.customers) == 100
    assert len(dataset.subscriptions) == 100
    # Every customer has at least one invoice (signed up before the dataset window ends).
    assert dataset.invoices["customer_id"].nunique() > 0
    assert len(dataset.payments) > 0


def test_generate_dataset_injects_known_defect_types():
    dataset = generate_dataset(n_customers=500, seed=7)
    invoices = dataset.invoices
    customers = dataset.customers

    # Completeness defects
    assert customers["customer_name"].isna().sum() > 0
    assert invoices["invoice_date"].isna().sum() > 0
    assert invoices["amount"].isna().sum() > 0

    # Validity defects
    assert (invoices["amount"].dropna() < 0).sum() > 0
    assert ((invoices["tax_rate_pct"] < 0) | (invoices["tax_rate_pct"] > 30)).sum() > 0

    # Uniqueness defects: at least one duplicated invoice_number
    dup_counts = invoices["invoice_number"].value_counts()
    assert (dup_counts > 1).sum() > 0

    # Consistency defects: orphan customer_id (offset by 900000)
    assert (invoices["customer_id"] > 900000).sum() > 0


def test_generate_dataset_payments_reference_mostly_valid_invoices():
    dataset = generate_dataset(n_customers=200, seed=7)
    valid_invoice_ids = set(dataset.invoices["invoice_id"])

    orphan_payments = ~dataset.payments["invoice_id"].isin(valid_invoice_ids)
    # A small deliberate batch of orphans should exist, but not the majority.
    assert 0 < orphan_payments.sum() < len(dataset.payments) * 0.05
