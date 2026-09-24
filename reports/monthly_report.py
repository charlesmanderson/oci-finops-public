"""Monthly cost report generator.

Queries previous month's cost data grouped by customer/team,
generates an HTML email summary, and sends via SMTP.
"""

from __future__ import annotations

import argparse
import logging
import smtplib
import sys
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import psycopg2

from etl.config import AppConfig, NotificationConfig, load_config

logger = logging.getLogger(__name__)


def _get_report_month(today: date | None = None) -> tuple[date, date]:
    """Return (first_day, last_day) of the previous month."""
    if today is None:
        today = date.today()
    first_of_current = today.replace(day=1)
    last_of_prev = first_of_current - timedelta(days=1)
    first_of_prev = last_of_prev.replace(day=1)
    return first_of_prev, last_of_prev


def _query_report_data(dsn: str, start: date, end: date) -> dict:
    """Query all data needed for the monthly report."""
    conn = psycopg2.connect(dsn)
    try:
        cur = conn.cursor()

        # Previous-previous month for MoM comparison
        prev_start = (start - timedelta(days=1)).replace(day=1)
        prev_end = start - timedelta(days=1)

        # Tenancy totals (current and previous month)
        cur.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN cost_date BETWEEN %s AND %s THEN total_billed_cost END), 0),
                COALESCE(SUM(CASE WHEN cost_date BETWEEN %s AND %s THEN total_billed_cost END), 0)
            FROM mv_daily_cost_by_group
        """, (start, end, prev_start, prev_end))
        total_current, total_prev = cur.fetchone()

        # Group-level breakdown
        cur.execute("""
            WITH cur AS (
                SELECT group_name, sub_team,
                       SUM(total_billed_cost) AS billed
                FROM mv_daily_cost_by_group
                WHERE cost_date BETWEEN %s AND %s
                GROUP BY group_name, sub_team
            ),
            prev AS (
                SELECT group_name, sub_team,
                       SUM(total_billed_cost) AS billed
                FROM mv_daily_cost_by_group
                WHERE cost_date BETWEEN %s AND %s
                GROUP BY group_name, sub_team
            )
            SELECT
                CASE WHEN c.group_name = 'Internal'
                     THEN c.group_name || ' - ' || c.sub_team
                     ELSE c.group_name
                END AS display,
                c.billed,
                COALESCE(p.billed, 0) AS prev_billed
            FROM cur c
            LEFT JOIN prev p ON c.group_name = p.group_name
                            AND COALESCE(c.sub_team, '') = COALESCE(p.sub_team, '')
            ORDER BY c.billed DESC
        """, (start, end, prev_start, prev_end))
        groups = cur.fetchall()

        # Top 10 services tenancy-wide
        cur.execute("""
            SELECT servicename, SUM(total_billed_cost) AS billed
            FROM mv_daily_cost_by_group
            WHERE cost_date BETWEEN %s AND %s
            GROUP BY servicename
            ORDER BY billed DESC
            LIMIT 10
        """, (start, end))
        top_services = cur.fetchall()

        # Per-group top 5 services
        cur.execute("""
            WITH ranked AS (
                SELECT
                    CASE WHEN group_name = 'Internal'
                         THEN group_name || ' - ' || sub_team
                         ELSE group_name
                    END AS display,
                    servicename,
                    SUM(total_billed_cost) AS billed,
                    ROW_NUMBER() OVER (
                        PARTITION BY group_name, sub_team
                        ORDER BY SUM(total_billed_cost) DESC
                    ) AS rn
                FROM mv_daily_cost_by_group
                WHERE cost_date BETWEEN %s AND %s
                GROUP BY group_name, sub_team, servicename
            )
            SELECT display, servicename, billed
            FROM ranked
            WHERE rn <= 5
            ORDER BY display, billed DESC
        """, (start, end))
        group_services = cur.fetchall()

        return {
            "total_current": float(total_current),
            "total_prev": float(total_prev),
            "groups": [(g[0], float(g[1]), float(g[2])) for g in groups],
            "top_services": [(s[0], float(s[1])) for s in top_services],
            "group_services": [(s[0], s[1], float(s[2])) for s in group_services],
        }
    finally:
        conn.close()


def _mom_pct(current: float, previous: float) -> str:
    """Format month-over-month change as a percentage string."""
    if previous > 0:
        pct = ((current - previous) / previous) * 100
        arrow = "▲" if pct > 0 else "▼" if pct < 0 else "—"
        return f"{arrow} {pct:+.1f}%"
    return "N/A"


def _mom_color(current: float, previous: float) -> str:
    """Return HTML color for MoM change."""
    if previous <= 0:
        return "#6c757d"
    pct = ((current - previous) / previous) * 100
    if pct > 25:
        return "#dc3545"
    if pct > 10:
        return "#fd7e14"
    if pct > 0:
        return "#ffc107"
    return "#28a745"


def generate_html(data: dict, month_label: str) -> str:
    """Generate the HTML email body."""
    total_cur = data["total_current"]
    total_prev = data["total_prev"]
    mom = _mom_pct(total_cur, total_prev)
    mom_color = _mom_color(total_cur, total_prev)

    # -- Tenancy summary --
    html = f"""<html>
<head><style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #333; }}
  h1 {{ color: #1a73e8; font-size: 22px; }}
  h2 {{ color: #333; font-size: 16px; border-bottom: 1px solid #ddd; padding-bottom: 4px; margin-top: 24px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 16px; }}
  th {{ background: #f0f0f0; text-align: left; padding: 8px 12px; font-size: 13px; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #eee; font-size: 13px; }}
  .right {{ text-align: right; }}
  .footer {{ color: #999; font-size: 11px; margin-top: 32px; }}
</style></head>
<body>

<h1>OCI FinOps Monthly Report — {month_label}</h1>

<h2>Tenancy Summary</h2>
<table>
  <tr><th>Metric</th><th class="right">Value</th></tr>
  <tr><td>Total Spend</td><td class="right"><b>${total_cur:,.2f}</b></td></tr>
  <tr><td>Previous Month</td><td class="right">${total_prev:,.2f}</td></tr>
  <tr><td>MoM Change</td><td class="right" style="color:{mom_color}">{mom}</td></tr>
</table>
"""

    # -- Customer/Team Breakdown --
    html += """<h2>Customer / Team Breakdown</h2>
<table>
  <tr><th>Group</th><th class="right">Spend</th><th class="right">Prev Month</th><th class="right">MoM Change</th><th class="right">Share</th></tr>
"""
    for display, billed, prev_billed in data["groups"]:
        pct_mom = _mom_pct(billed, prev_billed)
        color = _mom_color(billed, prev_billed)
        share = (billed / total_cur * 100) if total_cur > 0 else 0
        html += f"""  <tr>
    <td>{display}</td>
    <td class="right">${billed:,.2f}</td>
    <td class="right">${prev_billed:,.2f}</td>
    <td class="right" style="color:{color}">{pct_mom}</td>
    <td class="right">{share:.1f}%</td>
  </tr>\n"""
    html += "</table>\n"

    # -- Top 10 Services --
    html += """<h2>Top 10 Services (Tenancy-Wide)</h2>
<table>
  <tr><th>Service</th><th class="right">Spend</th></tr>
"""
    for svc, billed in data["top_services"]:
        html += f'  <tr><td>{svc}</td><td class="right">${billed:,.2f}</td></tr>\n'
    html += "</table>\n"

    # -- Per-Group Detail --
    html += "<h2>Per-Customer / Team Detail (Top 5 Services)</h2>\n"
    current_group = None
    for display, svc, billed in data["group_services"]:
        if display != current_group:
            if current_group is not None:
                html += "</table>\n"
            current_group = display
            html += f"""<h3 style="font-size:14px;margin-top:16px;margin-bottom:4px">{display}</h3>
<table>
  <tr><th>Service</th><th class="right">Spend</th></tr>
"""
        html += f'  <tr><td>{svc}</td><td class="right">${billed:,.2f}</td></tr>\n'
    if current_group is not None:
        html += "</table>\n"

    html += """<p class="footer">Generated by OCI FinOps Cost Intelligence Platform</p>
</body></html>"""

    return html


def generate_text(data: dict, month_label: str) -> str:
    """Generate the plain-text email body."""
    total_cur = data["total_current"]
    total_prev = data["total_prev"]
    mom = _mom_pct(total_cur, total_prev)

    lines = [
        f"OCI FinOps Monthly Report — {month_label}",
        "=" * 50,
        "",
        "TENANCY SUMMARY",
        f"  Total Spend:    ${total_cur:,.2f}",
        f"  Previous Month: ${total_prev:,.2f}",
        f"  MoM Change:     {mom}",
        "",
        "CUSTOMER / TEAM BREAKDOWN",
        f"  {'Group':<30s} {'Spend':>12s} {'MoM':>10s} {'Share':>7s}",
        "  " + "-" * 62,
    ]
    for display, billed, prev_billed in data["groups"]:
        pct_mom = _mom_pct(billed, prev_billed)
        share = (billed / total_cur * 100) if total_cur > 0 else 0
        lines.append(f"  {display:<30s} ${billed:>11,.2f} {pct_mom:>10s} {share:>6.1f}%")

    lines += ["", "TOP 10 SERVICES", f"  {'Service':<40s} {'Spend':>12s}", "  " + "-" * 54]
    for svc, billed in data["top_services"]:
        lines.append(f"  {svc:<40s} ${billed:>11,.2f}")

    lines += ["", "---", "Generated by OCI FinOps Cost Intelligence Platform"]
    return "\n".join(lines)


def send_report(config: NotificationConfig, subject: str, text: str, html: str) -> bool:
    """Send the monthly report via SMTP."""
    if not config.smtp_host or not config.smtp_to:
        logger.warning("SMTP not configured, skipping monthly report email")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = config.smtp_from
        msg["To"] = config.smtp_to

        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
            server.starttls()
            if config.smtp_user and config.smtp_password:
                server.login(config.smtp_user, config.smtp_password)
            server.sendmail(config.smtp_from, config.smtp_to.split(","), msg.as_string())

        logger.info("Monthly report sent to %s", config.smtp_to)
        return True

    except Exception as e:
        logger.error("Failed to send monthly report: %s", e, exc_info=True)
        return False


def run_monthly_report(config: AppConfig, dry_run: bool = False) -> bool:
    """Generate and send the monthly cost report."""
    start, end = _get_report_month()
    month_label = start.strftime("%B %Y")
    logger.info("Generating monthly report for %s", month_label)

    data = _query_report_data(config.pg.dsn, start, end)

    html = generate_html(data, month_label)
    text = generate_text(data, month_label)

    subject = f"OCI FinOps Monthly Report — {month_label}"

    if dry_run:
        print(html)
        logger.info("Dry run — report not sent")
        return True

    return send_report(config.notification, subject, text, html)


def main():
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="Generate and send OCI monthly cost report")
    parser.add_argument("--dry-run", action="store_true", help="Print HTML to stdout without sending")
    args = parser.parse_args()

    config = load_config()
    ok = run_monthly_report(config, dry_run=args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
