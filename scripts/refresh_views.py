"""Refresh materialized views."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2  # noqa: E402
from etl.config import load_config  # noqa: E402

config = load_config()
conn = psycopg2.connect(config.pg.dsn)
cur = conn.cursor()
cur.execute("SELECT refresh_finops_views()")
conn.commit()
conn.close()
print("Views refreshed successfully")
