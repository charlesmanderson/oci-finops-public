"""Anomaly notification via OCI Notifications Service and SMTP email."""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from etl.config import NotificationConfig

logger = logging.getLogger(__name__)


def _format_anomaly_text(anomalies: list[dict]) -> str:
    """Format anomalies into a human-readable text summary."""
    lines = [f"OCI FinOps Alert: {len(anomalies)} cost anomali{'es' if len(anomalies) != 1 else 'y'} detected\n"]

    for a in anomalies:
        lines.append(f"  Tenancy:   {a.get('tenancy_alias', 'N/A')}")
        lines.append(f"  Service:   {a.get('service_name', 'N/A')}")
        lines.append(f"  Date:      {a.get('detection_date', 'N/A')}")
        lines.append(f"  Type:      {a.get('anomaly_type', 'N/A')}")
        lines.append(f"  Severity:  {a.get('severity', 'N/A')}")
        lines.append(f"  Actual:    ${a.get('metric_value', 0):,.2f}")
        lines.append(f"  Expected:  ${a.get('expected_value', 0):,.2f}")
        deviation = float(a.get('metric_value', 0)) - float(a.get('expected_value', 0))
        lines.append(f"  Deviation: ${deviation:,.2f} (score: {a.get('deviation_score', 0):.2f})")
        lines.append("")

    return "\n".join(lines)


def _format_anomaly_html(anomalies: list[dict]) -> str:
    """Format anomalies into an HTML email body."""
    rows = ""
    for a in anomalies:
        severity = a.get("severity", "low")
        color = {"critical": "#dc3545", "high": "#fd7e14", "medium": "#ffc107", "low": "#0d6efd"}.get(severity, "#6c757d")
        deviation = float(a.get("metric_value", 0)) - float(a.get("expected_value", 0))
        rows += f"""<tr>
            <td>{a.get('tenancy_alias', 'N/A')}</td>
            <td>{a.get('detection_date', '')}</td>
            <td>{a.get('service_name', 'N/A')}</td>
            <td>{a.get('anomaly_type', 'N/A')}</td>
            <td style="color:{color};font-weight:bold">{severity.upper()}</td>
            <td style="text-align:right">${a.get('metric_value', 0):,.2f}</td>
            <td style="text-align:right">${a.get('expected_value', 0):,.2f}</td>
            <td style="text-align:right">${deviation:,.2f}</td>
        </tr>"""

    return f"""<html><body>
    <h2>OCI FinOps Alert: {len(anomalies)} Cost Anomal{'ies' if len(anomalies) != 1 else 'y'} Detected</h2>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-family:sans-serif">
        <tr style="background:#f0f0f0">
            <th>Tenancy</th><th>Date</th><th>Service</th><th>Type</th><th>Severity</th>
            <th>Actual</th><th>Expected</th><th>Deviation</th>
        </tr>
        {rows}
    </table>
    </body></html>"""


def notify_ons(config: NotificationConfig, anomalies: list[dict]) -> bool:
    """Send anomaly alert via OCI Notifications Service."""
    if not config.ons_topic_ocid:
        logger.debug("ONS topic OCID not configured, skipping")
        return False

    try:
        import oci

        try:
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            client = oci.ons.NotificationDataPlaneClient(config={}, signer=signer)
        except Exception:
            oci_config = oci.config.from_file()
            client = oci.ons.NotificationDataPlaneClient(oci_config)

        message = oci.ons.models.MessageDetails(
            title=f"OCI FinOps: {len(anomalies)} cost anomalies detected",
            body=_format_anomaly_text(anomalies),
        )
        client.publish_message(config.ons_topic_ocid, message)
        logger.info("ONS notification sent to topic %s", config.ons_topic_ocid)
        return True

    except Exception as e:
        logger.error("Failed to send ONS notification: %s", e, exc_info=True)
        return False


def notify_email(config: NotificationConfig, anomalies: list[dict]) -> bool:
    """Send anomaly alert via SMTP email."""
    if not config.smtp_host or not config.smtp_to:
        logger.debug("SMTP not configured, skipping email notification")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"OCI FinOps Alert: {len(anomalies)} cost anomalies detected"
        msg["From"] = config.smtp_from
        msg["To"] = config.smtp_to

        msg.attach(MIMEText(_format_anomaly_text(anomalies), "plain"))
        msg.attach(MIMEText(_format_anomaly_html(anomalies), "html"))

        with smtplib.SMTP(config.smtp_host, config.smtp_port) as server:
            server.starttls()
            if config.smtp_user and config.smtp_password:
                server.login(config.smtp_user, config.smtp_password)
            server.sendmail(config.smtp_from, config.smtp_to.split(","), msg.as_string())

        logger.info("Email notification sent to %s", config.smtp_to)
        return True

    except Exception as e:
        logger.error("Failed to send email notification: %s", e, exc_info=True)
        return False


def send_notifications(config: NotificationConfig, anomalies: list[dict]) -> bool:
    """Send anomaly notifications via all configured channels."""
    if not anomalies:
        logger.debug("No anomalies to notify about")
        return True

    ons_ok = notify_ons(config, anomalies)
    email_ok = notify_email(config, anomalies)

    if not ons_ok and not email_ok:
        logger.warning("No notification channels succeeded")
        return False

    return True
