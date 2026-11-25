import csv
from pathlib import Path

import numpy as np
import pytest

from app.domain import Service
from app.engine import route_with_observations, shifted

DATA = Path(__file__).resolve().parents[1]/"data"


@pytest.fixture
def svc(tmp_path):
    service = Service(tmp_path/"test.sqlite", DATA)
    service.seed()
    return service


@pytest.mark.parametrize("event_id", ["event1","event2","event3","event4"])
def test_phase_one_golden_series(svc, event_id):
    result = svc.run(event_id)["result"]
    with (DATA/"golden"/f"{event_id}.csv").open(encoding="utf-8-sig") as f:
        expected = [float(row["expected_flow"]) for row in csv.DictReader(f)]
    np.testing.assert_allclose(result["forecast"], expected, atol=1e-8, rtol=0)
    assert result["metrics"]["dc"] > .99


def test_qc_archive_blocks_bad_forcing_but_keeps_missing_observations(svc):
    data = svc.event_detail("event1")
    lines = (DATA/"events/event1.csv").read_text(encoding="utf-8-sig").splitlines()
    first = lines[1].split(",")
    first[-1] = "-999"
    lines[1] = ",".join(first)
    warning = svc.ingest("partial","\n".join(lines),data["state"])
    assert warning["quality"] == "warning"
    run = svc.run("partial",correction=True)
    assert run["result"]["observed"][0] is None
    assert run["result"]["metrics"]["n"] == 39
    first[1] = "-2"
    lines[1] = ",".join(first)
    lines[2] = lines[1]
    failed = svc.ingest("broken","\n".join(lines),data["state"])
    assert failed["quality"] == "blocked"
    assert any("时刻" in x["reason"] for x in failed["issues"])
    with pytest.raises(ValueError, match="质控"):
        svc.run("broken")


def test_independent_version_and_replay_after_reimport(svc):
    initial = svc.plans()[0]
    p = {**initial["parameters"], "K":.9}
    a = svc.save_plan("备选",p)
    b = svc.save_plan("备选",{**p,"K":.95})
    assert b["version"] == a["version"]+1
    svc.activate(a["id"])
    saved = svc.run("event2")
    assert saved["snapshot"]["parameters"] == p
    svc.activate(b["id"])
    svc.delete_plan(a["id"])
    raw = (DATA/"events/event2.csv").read_text(encoding="utf-8-sig")
    svc.ingest("event2",raw,{**saved["snapshot"]["event"]["state"],"WU":0})
    assert svc.replay(saved["id"])["match"]
    assert svc.run("event2")["result_hash"] != saved["result_hash"]
    with pytest.raises(ValueError,match="先切换"):
        svc.delete_plan(b["id"])
    with pytest.raises(ValueError):
        svc.save_plan("坏方案",{**p,"X":.4,"KE":18})


def test_warning_ack_and_issue_are_durable_and_idempotent(svc):
    wet = svc.run("event2")
    assert wet["result"]["warning"] == "警戒水位"
    svc.run("event4")
    msg, = svc.notifications()
    assert msg["run_id"] == wet["id"]
    svc.read_notification(msg["id"],"值班员")
    first = svc.issue(wet["id"],"签发人")
    second = svc.issue(wet["id"],"其他人")
    assert first["status"] == "issued"
    assert second["issued_at"] == first["issued_at"]
    reopened = Service(svc.path,DATA)
    reopened.seed()
    assert len(reopened.plans()) == 1
    assert reopened.detail(wet["id"])["issued_by"] == "签发人"
    assert reopened.notifications()[0]["read_at"]
    assert sum(rec["action"]=="issue" for rec in reopened.audit()) == 1


def test_update_only_affects_future_steps(svc):
    p = svc.plans()[0]["parameters"]
    times = ["2023-07-01 00:00","2023-07-01 06:00","2023-07-01 12:00"]
    base = [10.,10.,10.]
    prior,post = route_with_observations(base,p,[10,30,10],times,None)
    assert prior[:2] == pytest.approx([10.,10.])
    assert post[1] == pytest.approx(20)
    assert prior[2] > 10
    prior,post = route_with_observations(base,p,[10,30,10],times,times[0])
    assert prior == pytest.approx(base)
    assert post == pytest.approx(base)


def test_scenarios_and_intervals(svc):
    run = svc.run("event2",ensemble=True,correction=True,cutoff="2023-07-16 12:00")
    result = run["result"]
    m = result["members"]
    assert len(m) == 15
    assert next(row for row in m if row["id"]=="S08")["forecast"] == result["forecast"]
    expected = np.quantile([s["forecast"] for s in m], [.05,.5,.95],axis=0)
    np.testing.assert_allclose(expected,[result["p05"],result["p50"],result["p95"]])
    assert svc.replay(run["id"])["match"]
    with pytest.raises(ValueError,match="event2"):
        svc.run("event4",ensemble=True)
    np.testing.assert_array_equal(shifted(np.array([1.,2.,4.]),2.,1),[0,2,4])

