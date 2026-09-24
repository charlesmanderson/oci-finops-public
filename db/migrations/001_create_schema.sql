-- 001_create_schema.sql
-- Creates the main FOCUS reports table (partitioned by month on billingperiodstart)
-- and the ETL watermark tracking table.

BEGIN;

-- Main FOCUS cost reports table (partitioned)
CREATE TABLE IF NOT EXISTS oci_finops_reports (
    id                              BIGSERIAL       NOT NULL,
    -- FOCUS standard columns
    availabilityzone                TEXT,
    billedcost                      NUMERIC(20,10),
    billingaccountid                BIGINT,
    billingaccountname              TEXT,
    billingcurrency                 TEXT,
    billingperiodend                TIMESTAMPTZ,
    billingperiodstart              TIMESTAMPTZ     NOT NULL,
    chargecategory                  TEXT,
    chargedescription               TEXT,
    chargefrequency                 TEXT,
    chargeperiodend                 TIMESTAMPTZ,
    chargeperiodstart               TIMESTAMPTZ,
    chargesubcategory               TEXT,
    commitmentdiscountcategory      TEXT,
    commitmentdiscountid            TEXT,
    commitmentdiscountname          TEXT,
    commitmentdiscounttype          TEXT,
    effectivecost                   NUMERIC(20,10),
    invoiceissuer                   TEXT,
    listcost                        NUMERIC(20,10),
    listunitprice                   NUMERIC(20,10),
    pricingcategory                 TEXT,
    pricingquantity                 NUMERIC(20,10),
    pricingunit                     TEXT,
    provider                        TEXT,
    publisher                       TEXT,
    region                          TEXT,
    resourceid                      TEXT,
    resourcename                    TEXT,
    resourcetype                    TEXT,
    servicecategory                 TEXT,
    servicename                     TEXT,
    skuid                           TEXT,
    skupriceid                      TEXT,
    subaccountid                    TEXT,
    subaccountname                  TEXT,
    tags                            JSONB,
    usagequantity                   NUMERIC(20,10),
    usageunit                       TEXT,
    -- OCI-specific extension columns
    oci_referencenumber             TEXT,
    oci_compartmentid               TEXT,
    oci_compartmentname             TEXT,
    oci_overageflag                 TEXT,
    oci_unitpriceoverage            NUMERIC(20,10),
    oci_billedquantityoverage       NUMERIC(20,10),
    oci_costoverage                 NUMERIC(20,10),
    oci_attributedusage             NUMERIC(20,10),
    oci_attributedcost              NUMERIC(20,10),
    oci_backreferencenumber         TEXT,
    -- Metadata columns
    loaded_at                       TIMESTAMPTZ     DEFAULT NOW(),
    source_file                     TEXT
) PARTITION BY RANGE (billingperiodstart);

-- Create monthly partitions for 2024-2027 (extend as needed)
DO $$
DECLARE
    yr INT;
    mo INT;
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    FOR yr IN 2024..2027 LOOP
        FOR mo IN 1..12 LOOP
            partition_name := format('oci_finops_reports_%s_%s', yr, lpad(mo::text, 2, '0'));
            start_date := make_date(yr, mo, 1);
            end_date := (start_date + interval '1 month')::date;
            EXECUTE format(
                'CREATE TABLE IF NOT EXISTS %I PARTITION OF oci_finops_reports
                 FOR VALUES FROM (%L) TO (%L)',
                partition_name, start_date, end_date
            );
        END LOOP;
    END LOOP;
END $$;

-- ETL watermark: tracks which files have been ingested
CREATE TABLE IF NOT EXISTS etl_watermark (
    file_path   TEXT        PRIMARY KEY,
    file_size   BIGINT,
    loaded_at   TIMESTAMPTZ DEFAULT NOW(),
    row_count   INTEGER,
    status      TEXT        DEFAULT 'success'
);

COMMIT;
