"""Daily probe for a tenancy's FOCUS report availability.

Lists `FOCUS Reports/*.csv.gz` in the tenancy's bucket and logs the count. On the
first transition from zero to non-zero, drops a flag file so cron mail / grep can
spot it.

The tenancy is selected by alias (must exist in the `tenancies` table):

    /usr/bin/python3.11 scripts/focus_probe.py --alias <tenancy-alias>

The alias may also be supplied via FOCUS_PROBE_ALIAS. State and flag file paths
default to /var/log/oci-finops/focus_probe_<alias>.{state.json,DETECTED.flag} and
can be overridden with FOCUS_PROBE_STATE / FOCUS_PROBE_FLAG.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make `etl` importable when invoked as `python scripts/focus_probe.py`
# from the project root (which is how cron invokes it).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from etl.config import load_config, load_tenancies  # noqa: E402
from etl.loader import get_connection                # noqa: E402
from etl.oci_client import OciObjectStorageClient    # noqa: E402

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe a tenancy for FOCUS report availability")
    parser.add_argument(
        "--alias",
        default=os.environ.get("FOCUS_PROBE_ALIAS"),
        help="Tenancy alias to probe (or set FOCUS_PROBE_ALIAS)",
    )
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    alias = args.alias
    if not alias:
        logger.error("No tenancy alias given (--alias or FOCUS_PROBE_ALIAS)")
        return 1

    state_file = Path(os.environ.get(
        "FOCUS_PROBE_STATE",
        f"/var/log/oci-finops/focus_probe_{alias}.state.json",
    ))
    flag_file = Path(os.environ.get(
        "FOCUS_PROBE_FLAG",
        f"/var/log/oci-finops/focus_probe_{alias}.DETECTED.flag",
    ))

    config = load_config()
    conn = get_connection(config.pg)
    try:
        tenancies = [t for t in load_tenancies(conn) if t.alias == alias]
    finally:
        conn.close()

    if not tenancies:
        logger.error("Tenancy '%s' not found in tenancies table", alias)
        return 1

    client = OciObjectStorageClient(tenancies[0])
    try:
        files = client.list_focus_reports()
    except Exception as e:
        logger.error("Failed to list bucket for %s: %s", alias, e)
        return 2

    prev_state: dict = {}
    if state_file.exists():
        try:
            prev_state = json.loads(state_file.read_text())
        except Exception:
            pass

    new_count = len(files)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state = {
        "tenancy": alias,
        "count": new_count,
        "last_checked": now,
        "first_file": files[0].name if files else None,
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2) + "\n")

    prev_count = prev_state.get("count", -1)

    if prev_count <= 0 and new_count > 0:
        logger.warning("*** FOCUS REPORTS DETECTED in %s: %d files ***", alias, new_count)
        logger.warning("First: %s", files[0].name)
        logger.warning("They will be ingested on the next scheduled ETL run (cron at :00 every 6 hours).")
        flag_file.write_text(
            f"detected_at={now}\ncount={new_count}\nfirst_file={files[0].name}\n"
        )
    elif new_count > 0:
        logger.info("%s: %d FOCUS files available (unchanged)", alias, new_count)
    else:
        logger.info(
            "%s: 0 FOCUS files (still waiting; previously checked at %s)",
            alias, prev_state.get("last_checked", "never"),
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
