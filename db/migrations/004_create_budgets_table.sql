-- 004_create_budgets_table.sql
-- Budget definitions for budget vs. actual comparison.

BEGIN;

CREATE TABLE IF NOT EXISTS budgets (
    id                SERIAL        PRIMARY KEY,
    budget_name       TEXT          NOT NULL,
    service_name      TEXT,
    compartment_name  TEXT,
    region            TEXT,
    monthly_budget    NUMERIC(20,2) NOT NULL,
    effective_from    DATE          NOT NULL,
    effective_to      DATE,
    created_at        TIMESTAMPTZ   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_budgets_service
    ON budgets (service_name);

CREATE INDEX IF NOT EXISTS idx_budgets_compartment
    ON budgets (compartment_name);

CREATE INDEX IF NOT EXISTS idx_budgets_effective
    ON budgets (effective_from, effective_to);

COMMIT;
