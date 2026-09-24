-- sample_budgets.sql
-- Example budget entries for development and testing.
-- Service names must match FOCUS report servicename values (e.g. COMPUTE, DATABASE).

INSERT INTO budgets (budget_name, service_name, compartment_name, region, monthly_budget, effective_from, effective_to)
VALUES
    ('Overall Cloud Budget', NULL, NULL, NULL, 10000.00, '2026-01-01', NULL),
    ('Compute Budget', 'COMPUTE', NULL, NULL, 3000.00, '2026-01-01', NULL),
    ('Block Storage Budget', 'BLOCK_STORAGE', NULL, NULL, 1000.00, '2026-01-01', NULL),
    ('Object Storage Budget', 'OBJECTSTORE', NULL, NULL, 500.00, '2026-01-01', NULL),
    ('Database Budget', 'DATABASE', NULL, NULL, 2000.00, '2026-01-01', NULL),
    ('Customer Compartment Budget', NULL, 'EXAMPLE_CMP', NULL, 2000.00, '2026-01-01', NULL),
    ('Primary Compartment Budget', NULL, 'primary-cmp', NULL, 5000.00, '2026-01-01', NULL),
    ('US Ashburn Budget', NULL, NULL, 'us-ashburn-1', 4000.00, '2026-01-01', NULL)
ON CONFLICT DO NOTHING;
