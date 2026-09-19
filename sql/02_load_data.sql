-- Load generated CSVs. Run from project root with:
--   psql -d revenue_assurance_dq -f sql/02_load_data.sql

\copy plans(plan_id, plan_name, monthly_price, tax_rate_pct) FROM 'data/plans.csv' WITH (FORMAT csv, HEADER true);

\copy customers(customer_id, customer_name, signup_date, country, status) FROM 'data/customers.csv' WITH (FORMAT csv, HEADER true, FORCE_NULL(customer_name, country));

\copy subscriptions(subscription_id, customer_id, plan_id, start_date, end_date) FROM 'data/subscriptions.csv' WITH (FORMAT csv, HEADER true, FORCE_NULL(end_date));

\copy invoices(invoice_id, invoice_number, customer_id, subscription_id, billing_month, invoice_date, amount, tax_rate_pct) FROM 'data/invoices.csv' WITH (FORMAT csv, HEADER true, FORCE_NULL(invoice_date, amount));

\copy payments(payment_id, invoice_id, payment_date, amount_paid) FROM 'data/payments.csv' WITH (FORMAT csv, HEADER true, FORCE_NULL(payment_date, amount_paid));

SELECT setval('plans_plan_id_seq', (SELECT MAX(plan_id) FROM plans));
SELECT setval('customers_customer_id_seq', (SELECT MAX(customer_id) FROM customers));
SELECT setval('subscriptions_subscription_id_seq', (SELECT MAX(subscription_id) FROM subscriptions));
SELECT setval('invoices_invoice_id_seq', (SELECT MAX(invoice_id) FROM invoices));
SELECT setval('payments_payment_id_seq', (SELECT MAX(payment_id) FROM payments));
