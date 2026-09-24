# OCI FinOps Grafana Dashboards

## Dashboards

| Dashboard | Description |
|-----------|-------------|
| Cost Overview | Total spend, daily trends, top services, charge categories |
| Service Breakdown | Per-service cost table, stacked area trends, unit price tracking |
| Budget vs Actual | Budget consumption gauges, projected spend, daily run rate |
| Anomaly Monitor | Anomaly timeline, severity breakdown, detail table |
| Compartment Analysis | Compartment cost bars, pie charts, trends, MoM comparison |

## Local Development

```bash
# From the project root:
docker compose up -d

# Grafana is available at http://localhost:3000
# Default login: admin / admin
```

## Provisioning

Dashboards are auto-provisioned from JSON files in `dashboards/`. The PostgreSQL datasource
is auto-configured via `provisioning/datasources/postgres.yml`.

To modify dashboards, edit them in Grafana and export the JSON, or edit the JSON files directly.

## Refreshing Materialized Views

Dashboard queries use materialized views for performance. After loading new data, refresh them:

```sql
SELECT refresh_finops_views();
```
