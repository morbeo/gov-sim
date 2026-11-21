"""Revision handling against a real PostgreSQL. Set BGFIN_TEST_DSN to run,
e.g. BGFIN_TEST_DSN=postgresql://postgres@/bgfin_test?host=/tmp"""

import os
import uuid

import pytest

from bgfin import store
from bgfin.config import SeriesSpec
from bgfin.model import Obs, SeriesData

DSN = os.environ.get("BGFIN_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="BGFIN_TEST_DSN not set")


@pytest.fixture()
def conn():
    c = store.connect(DSN)
    store.migrate(c)
    c.execute("INSERT INTO source (code, name, institution) VALUES ('test', 'Test', 'Test') ON CONFLICT DO NOTHING")
    c.commit()
    yield c
    c.rollback()
    c.close()


def _series(conn):
    spec = SeriesSpec(indicator=None, source="test", geo="BG", frequency="Q")
    sd = SeriesData(source_key=f"t.{uuid.uuid4().hex}", dataset="t", geo="BG", unit="%", frequency="Q")
    return store.upsert_series(conn, spec, sd)


def test_revisions_are_appended_not_overwritten(conn):
    sid = _series(conn)
    c1 = store.save_observations(conn, sid, [Obs("2026-Q1", 0.6, "p", "preliminary"),
                                             Obs("2026-Q2", 0.5, "p", "preliminary")], None, None)
    assert c1 == {"new": 2, "revised": 0, "unchanged": 0, "vanished": 0}
    # same data again: idempotent
    c2 = store.save_observations(conn, sid, [Obs("2026-Q1", 0.6, "p", "preliminary"),
                                             Obs("2026-Q2", 0.5, "p", "preliminary")], None, None)
    assert c2["unchanged"] == 2 and c2["new"] == 0
    # value revised, then status finalised with same value
    store.save_observations(conn, sid, [Obs("2026-Q1", 0.7, "p", "preliminary")], None, None)
    store.save_observations(conn, sid, [Obs("2026-Q1", 0.7, None, "actual")], None, None)
    rows = conn.execute("SELECT value, obs_type, revision, superseded_at IS NULL AS cur FROM observation "
                        "WHERE series_id = %s AND period = '2026-01-01' ORDER BY revision", (sid,)).fetchall()
    assert [(r["value"], r["obs_type"], r["revision"], r["cur"]) for r in rows] == [
        (0.6, "preliminary", 0, False), (0.7, "preliminary", 1, False), (0.7, "actual", 2, True)]
    first_seen = conn.execute("SELECT min(retrieved_at) AS t FROM observation WHERE series_id = %s",
                              (sid,)).fetchone()["t"]
    as_of = conn.execute("SELECT value FROM obs_as_of(%s) WHERE series_id = %s AND period = '2026-01-01'",
                         (first_seen, sid)).fetchone()
    assert as_of["value"] == 0.6


def test_forecast_vintages_coexist(conn):
    sid = _series(conn)
    store.save_observations(conn, sid, [Obs("2027", 2.6, None, "forecast", "WEO-2026-10")], None, None)
    c = store.save_observations(conn, sid, [Obs("2027", 2.2, None, "forecast", "WEO-2027-04")], None, None)
    assert c["new"] == 1 and c["revised"] == 0
    n = conn.execute("SELECT count(*) AS n FROM observation WHERE series_id = %s AND superseded_at IS NULL",
                     (sid,)).fetchone()["n"]
    assert n == 2


def test_vanished_values_are_flagged_not_deleted(conn):
    sid = _series(conn)
    store.save_observations(conn, sid, [Obs("2026-Q1", 1.0), Obs("2026-Q2", 2.0)], None, None)
    c = store.save_observations(conn, sid, [Obs("2026-Q2", 2.0)], None, None, full_history=True)
    assert c["vanished"] == 1
    assert conn.execute("SELECT count(*) AS n FROM observation WHERE series_id = %s", (sid,)).fetchone()["n"] == 2
    assert conn.execute("SELECT count(*) AS n FROM quality_issue WHERE series_id = %s AND "
                        "check_name = 'vanished_observation'", (sid,)).fetchone()["n"] == 1
