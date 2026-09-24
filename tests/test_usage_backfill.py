from datetime import date
import importlib
from etl.focus_parser import FOCUS_COLUMNS
from etl.usage_backfill import gap_days, UsageGroup, to_row, build_rows, focus_frontier, _delete_provisional, PROVISIONAL_PREFIX, fetch_usage
import etl.usage_backfill as ub

def test_gap_days_fills_after_frontier_through_today():
    assert gap_days(date(2026, 7, 30), date(2026, 8, 4)) == [
        date(2026, 7, 31), date(2026, 8, 1), date(2026, 8, 2),
        date(2026, 8, 3), date(2026, 8, 4),
    ]

def test_gap_days_empty_when_current():
    assert gap_days(date(2026, 8, 4), date(2026, 8, 4)) == []

def test_gap_days_empty_when_no_real_data():
    assert gap_days(None, date(2026, 8, 4)) == []


def _as_dict(row):
    cols = FOCUS_COLUMNS + ["tenancy_alias", "source_file"]
    return dict(zip(cols, row))

def test_to_row_maps_dimensions_costs_and_marker():
    g = UsageGroup(service="Compute", compartment_name="AcctA", region="us-x-1", amount=12.5)
    d = _as_dict(to_row("tenant-a", date(2026, 7, 31), g))
    assert len(to_row("tenant-a", date(2026, 7, 31), g)) == len(FOCUS_COLUMNS) + 2
    assert d["servicename"] == "Compute"
    assert d["oci_compartmentname"] == "AcctA"
    assert d["region"] == "us-x-1"
    assert d["billedcost"] == d["effectivecost"] == d["listcost"] == "12.5"
    assert d["chargecategory"] == "Usage"
    assert d["chargeperiodstart"].startswith("2026-07-31T00:00:00")
    assert d["billingperiodstart"].startswith("2026-07-01T00:00:00")
    assert d["tenancy_alias"] == "tenant-a"
    assert d["source_file"] == "usage-api://tenant-a/2026-07-31"
    assert d["oci_referencenumber"].startswith("usageapi-")

def test_to_row_synthetic_key_is_stable_and_distinct():
    g = UsageGroup("Compute", "AcctA", "us-x-1", 1.0)
    r1 = _as_dict(to_row("tenant-a", date(2026, 7, 31), g))["oci_referencenumber"]
    r2 = _as_dict(to_row("tenant-a", date(2026, 7, 31), g))["oci_referencenumber"]
    r3 = _as_dict(to_row("tenant-a", date(2026, 7, 31), UsageGroup("Storage", "AcctA", "us-x-1", 1.0)))["oci_referencenumber"]
    assert r1 == r2 and r1 != r3

def test_build_rows_one_per_group():
    groups = [UsageGroup("A", "c", "r", 1.0), UsageGroup("B", "c", "r", 2.0)]
    assert len(build_rows("tenant-a", date(2026, 7, 31), groups)) == 2


class _FakeCursor:
    def __init__(self, fetch=None):
        self.fetch = fetch
        self.calls = []
        self.rowcount = 7
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, params=None): self.calls.append((sql, params))
    def fetchone(self): return self.fetch

class _FakeConn:
    def __init__(self, cur): self._cur = cur; self.committed = False; self.rolled_back = False
    def cursor(self): return self._cur
    def commit(self): self.committed = True
    def rollback(self): self.rolled_back = True

def test_focus_frontier_returns_date_and_excludes_provisional():
    cur = _FakeCursor(fetch=[date(2026, 7, 30)])
    got = focus_frontier(_FakeConn(cur), "tenant-a", date(2026, 8, 4))
    assert got == date(2026, 7, 30)
    sql, params = cur.calls[0]
    assert "max(chargeperiodstart)" in sql.lower()
    assert "not like" in sql.lower()
    assert params[0] == "tenant-a"
    assert params[1] == PROVISIONAL_PREFIX + "%"

def test_focus_frontier_none_when_no_rows():
    assert focus_frontier(_FakeConn(_FakeCursor(fetch=[None])), "tenant-a", date(2026, 8, 4)) is None

def test_delete_provisional_uses_marker_and_returns_count():
    cur = _FakeCursor()
    n = _delete_provisional(_FakeConn(cur), "tenant-a")
    assert n == 7
    sql, params = cur.calls[0]
    assert "delete from oci_finops_reports" in sql.lower()
    assert params == ("tenant-a", PROVISIONAL_PREFIX + "%")


class _Item:
    def __init__(self, s, c, r, amt): self.service=s; self.compartment_name=c; self.region=r; self.computed_amount=amt
class _Resp:
    def __init__(self, items): self.data = type("D", (), {"items": items})
class _FakeUsageClient:
    def __init__(self, items): self._items = items; self.last = None
    def request_summarized_usages(self, details): self.last = details; return _Resp(self._items)

def test_fetch_usage_maps_items_and_sets_request_params():
    cli = _FakeUsageClient([_Item("Compute", "AcctA", "us-x-1", 3.5), _Item("Storage", "AcctB", "us-x-1", None)])
    groups = fetch_usage(cli, "ocid1.tenancy.oc1..example", date(2026, 7, 31))
    assert [(g.service, g.compartment_name, g.amount) for g in groups] == [
        ("Compute", "AcctA", 3.5), ("Storage", "AcctB", 0.0),
    ]
    d = cli.last
    assert d.granularity == "DAILY" and d.query_type == "COST"
    assert d.compartment_depth == 1
    assert d.group_by == ["service", "compartmentName", "region"]


class _Ten:
    def __init__(self, alias): self.alias = alias; self.tenancy_ocid = "ocid1.tenancy.oc1..example"

def _patch(monkeypatch, frontier, groups, loaded):
    monkeypatch.setattr(ub, "_delete_provisional", lambda conn, a: loaded.setdefault("deleted", []).append(a) or 0)
    monkeypatch.setattr(ub, "focus_frontier", lambda conn, a, today: frontier)
    monkeypatch.setattr(ub, "fetch_usage", lambda cli, ocid, day: groups)
    monkeypatch.setattr(ub, "build_usage_client", lambda t: object())
    monkeypatch.setattr(ub, "bulk_load", lambda conn, rows: loaded.__setitem__("rows", rows) or len(rows))

def test_backfill_fills_gap_and_deletes_first(monkeypatch):
    loaded = {}
    _patch(monkeypatch, date(2026, 7, 30), [UsageGroup("A", "c", "r", 1.0)], loaded)
    conn = _FakeConn(_FakeCursor())
    out = ub.backfill(conn, [_Ten("tenant-a")], today=date(2026, 8, 1), enabled=True)
    assert loaded["deleted"] == ["tenant-a"]
    assert len(loaded["rows"]) == 2  # 2 gap days (07-31, 08-01) x 1 group
    assert out["tenancies"][0]["rows"] == 2

def test_backfill_empty_gap_commits_delete(monkeypatch):
    loaded = {}
    _patch(monkeypatch, date(2026, 8, 1), [], loaded)
    conn = _FakeConn(_FakeCursor())
    ub.backfill(conn, [_Ten("tenant-a")], today=date(2026, 8, 1), enabled=True)
    assert "rows" not in loaded           # bulk_load not called
    assert conn.committed is True         # delete still committed

def test_backfill_disabled_is_noop(monkeypatch):
    conn = _FakeConn(_FakeCursor())
    out = ub.backfill(conn, [_Ten("tenant-a")], today=date(2026, 8, 1), enabled=False)
    assert out["tenancies"] == []
    assert conn.committed is False


def test_usage_api_backfill_toggle(monkeypatch):
    import etl.config as cfg
    monkeypatch.setenv("USAGE_API_BACKFILL", "0")
    importlib.reload(cfg)
    assert cfg.EtlConfig().usage_api_backfill is False
    monkeypatch.setenv("USAGE_API_BACKFILL", "1")
    importlib.reload(cfg)
    assert cfg.EtlConfig().usage_api_backfill is True
    monkeypatch.delenv("USAGE_API_BACKFILL", raising=False)
    importlib.reload(cfg)  # default on
    assert cfg.EtlConfig().usage_api_backfill is True


def test_run_etl_invokes_backfill_and_refreshes(monkeypatch):
    import etl.pipeline as pipe

    calls = {"backfill": False, "refresh": False}
    class _Conn:
        def cursor(self): raise AssertionError("no direct cursor use in this test")
        def close(self): pass
    monkeypatch.setattr(pipe, "get_connection", lambda pg: _Conn())
    monkeypatch.setattr(pipe, "load_tenancies", lambda conn: [])
    monkeypatch.setattr(pipe, "refresh_materialized_views",
                        lambda conn: calls.__setitem__("refresh", True))
    def _fake_backfill(conn, tenancies, enabled=True):
        calls["backfill"] = True
        return {"tenancies": [{"tenancy": "tenant-a", "gap_days": 1, "rows": 5, "error": None}]}
    monkeypatch.setattr(pipe, "backfill", _fake_backfill)

    from etl.config import load_config
    agg = pipe.run_etl(load_config(), dry_run=False)
    assert calls["backfill"] is True
    assert calls["refresh"] is True            # refreshed due to provisional rows
    assert agg["usage_backfill"]["tenancies"][0]["rows"] == 5
