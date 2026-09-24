# Alternative OCI FinOps Cost Intelligence Platform 

A PostgreSQL + Grafana open source alternative to Oracle's ADW + Oracle Analytics Cloud stack for OCI cost analysis. Ingests OCI FOCUS (FinOps Open Cost & Usage Specification) reports and provides dashboards, budget tracking, and anomaly detection.

## Why This Exists

This is an alternative to another OCI FinOps project that you might have seen here:

https://blogs.oracle.com/futurestate/enhance-oci-cost-usage-analytics-using-oac

or here:

https://github.com/oracle-samples/usage-reports-to-adw

## Features

- **ETL Pipeline** — Incremental ingestion of OCI FOCUS cost reports from Object Storage
- **5 Grafana Dashboards** — Cost overview, service breakdown, budget vs. actual, anomaly monitor, compartment analysis
- **Anomaly Detection** — Statistical (rolling avg + stddev) and ML-based (Isolation Forest)
- **Budget Tracking** — Define budgets per service/compartment/region and track consumption
- **Notifications** — OCI Notifications Service + SMTP email for anomaly alerts
- **Infrastructure as Code** — Terraform modules for VCN, PostgreSQL DB System, Compute, IAM

## Quick Start (Local Development)

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- OCI CLI configured (`~/.oci/config`) with access to your tenancy's FOCUS reports

### 1. Start the local stack

```bash
cp .env.example .env
# Edit .env with your OCI tenancy details

docker compose up -d
# PostgreSQL: localhost:5432 (finops/changeme)
# Grafana:    http://localhost:3000 (admin/admin)
```

The database migrations run automatically on first start via Docker's init scripts.

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the ETL pipeline

```bash
# Preview what would be loaded
python -m etl.pipeline --dry-run

# Load all FOCUS reports for 2026
python -m etl.pipeline --year 2026

# Incremental load (skips already-loaded files)
python -m etl.pipeline
```

### 4. Load sample budgets

```bash
docker compose exec postgres psql -U finops -d oci_finops -f /docker-entrypoint-initdb.d/../seed/sample_budgets.sql
```

### 5. Run anomaly detection

```bash
python -m anomaly.runner          # Statistical only
python -m anomaly.runner --ml     # Statistical + ML
```

### 6. View dashboards

Open http://localhost:3000 and browse the **OCI FinOps** folder.

## Project Structure

```
oci-finops/
├── db/migrations/        # PostgreSQL schema (partitioned tables, indexes, mat views)
├── etl/                  # Python ETL pipeline (OCI SDK → CSV parse → COPY load)
├── anomaly/              # Cost anomaly detection (statistical + ML)
├── dashboard/grafana/    # Grafana provisioning and dashboard JSON
├── terraform/            # OCI infrastructure as code
├── tests/                # pytest test suite
├── docker-compose.yml    # Local dev: PostgreSQL + Grafana
└── Dockerfile            # ETL container image
```

## Deploying to OCI

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

terraform init
terraform plan
terraform apply
```

This provisions:
- VCN with public/private subnets
- OCI PostgreSQL DB System (2 OCPU, 32GB)
- Compute VM with Docker, cron-scheduled ETL, and Grafana
- IAM dynamic group + policies for Instance Principal auth
- ONS topic for anomaly alerts

## Running Tests

```bash
pytest                                    # All tests
pytest -v                                 # Verbose
pytest tests/test_focus_parser.py         # Specific module
pytest --cov=etl --cov=anomaly            # With coverage
```

## Acknowledgements

Inspired by architecture patterns from the [OCI A-Team FinOps addon](https://github.com/karthicgit/oci-landing-zone-operating-entities/tree/finops-addon/addons/oci-finops) (Oracle, UPL-1.0). This project is an independent reimplementation using a different technology stack (PostgreSQL + Grafana + Python).

## License

MIT
