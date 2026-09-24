"""One-shot script that injects a $tenancy template variable and a tenancy
filter into every panel SQL across all dashboard JSONs.

Idempotent: re-running is a no-op (it detects the existing tenancy variable
and the existing filter snippet, and skips them).

Run from project root:
    python scripts/add_tenancy_to_dashboards.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

DASH_DIR = Path(__file__).resolve().parent.parent / "dashboard" / "grafana" / "dashboards"

# Tables/views that now carry tenancy_alias and should be filtered.
TABLES_WITH_TENANCY = (
    "oci_finops_reports",
    "mv_daily_cost_by_service",
    "mv_daily_cost_by_compartment",
    "mv_monthly_cost_summary",
    "mv_cost_by_region",
    "mv_daily_cost_by_group",
    "cost_anomalies",
)

TENANCY_VAR = {
    "name": "tenancy",
    "type": "query",
    "label": "Tenancy",
    "query": "SELECT alias FROM tenancies WHERE is_active ORDER BY alias",
    "datasource": {"type": "grafana-postgresql-datasource", "uid": "oci-finops-pg"},
    "multi": True,
    "includeAll": True,
    "current": {"text": "All", "value": "$__all"},
    "allValue": "",
}

TENANCY_FILTER = "AND ('${tenancy:raw}' = '' OR tenancy_alias IN ($tenancy))"


def inject_template_variable(dash: dict) -> bool:
    """Add the tenancy variable at index 0 of templating.list. Returns True if changed."""
    templating = dash.setdefault("templating", {"list": []})
    var_list = templating.setdefault("list", [])
    if any(v.get("name") == "tenancy" for v in var_list):
        return False
    var_list.insert(0, dict(TENANCY_VAR))
    return True


def needs_tenancy_filter(sql: str) -> bool:
    if TENANCY_FILTER in sql:
        return False
    # only inject if the SQL references one of the tenancy-bearing tables
    sql_lower = sql.lower()
    return any(t in sql_lower for t in TABLES_WITH_TENANCY)


def inject_filter_into_sql(sql: str) -> str:
    """Inject AND ('${tenancy:raw}' = '' OR tenancy_alias IN ($tenancy)) into the
    main SELECT. Strategy:

    1. If the SQL has a WHERE clause for the outer query, append our filter just
       before GROUP BY / ORDER BY / LIMIT (or end of string).
    2. If no WHERE, insert WHERE just before those keywords (we change AND to nothing).

    The injected filter starts with "AND " so we need a WHERE somewhere; for
    cases without WHERE we strip the leading "AND " and add "WHERE ".

    Note: only the first occurrence is patched. If a query has subqueries with
    their own WHERE clauses, this may not catch everything; we still handle the
    outer SELECT, which is what dashboards use.
    """
    if not needs_tenancy_filter(sql):
        return sql

    # Find the end of the outer query (before GROUP BY / ORDER BY / LIMIT / closing paren)
    # Use case-insensitive search for clause boundaries.
    pattern = re.compile(r"(\s+)(GROUP\s+BY|ORDER\s+BY|LIMIT)\b", re.IGNORECASE)
    m = pattern.search(sql)
    insert_pos = m.start() if m else len(sql)

    prefix = sql[:insert_pos]
    suffix = sql[insert_pos:]

    # Decide whether to use "AND " or "WHERE " based on whether the outer query
    # already has WHERE. Search for WHERE *before* insert_pos.
    has_where = re.search(r"\bWHERE\b", prefix, re.IGNORECASE) is not None
    snippet = " " + TENANCY_FILTER if has_where else " WHERE " + TENANCY_FILTER[4:]  # strip "AND "

    return prefix + snippet + suffix


def patch_panel_sql(panel: dict) -> int:
    """Patch all rawSql fields in panel.targets. Returns count of patched queries."""
    count = 0
    for target in panel.get("targets", []) or []:
        sql = target.get("rawSql")
        if not sql:
            continue
        new_sql = inject_filter_into_sql(sql)
        if new_sql != sql:
            target["rawSql"] = new_sql
            count += 1
    # Recurse into nested panels (rows can contain panels)
    for sub in panel.get("panels", []) or []:
        count += patch_panel_sql(sub)
    return count


def process(path: Path) -> dict:
    dash = json.loads(path.read_text())
    var_added = inject_template_variable(dash)
    sql_patches = 0
    for panel in dash.get("panels", []) or []:
        sql_patches += patch_panel_sql(panel)
    if var_added or sql_patches:
        path.write_text(json.dumps(dash, indent=2) + "\n")
    return {"file": path.name, "var_added": var_added, "sql_patches": sql_patches}


def main() -> int:
    files = sorted(DASH_DIR.glob("*.json"))
    if not files:
        print(f"No dashboard JSONs in {DASH_DIR}", file=sys.stderr)
        return 1
    results = [process(f) for f in files]
    print(f"{'file':<32} {'var_added':<10} {'sql_patches':>11}")
    for r in results:
        print(f"{r['file']:<32} {str(r['var_added']):<10} {r['sql_patches']:>11}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
