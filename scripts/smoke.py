"""Exercise the running HTTP service. Default base URL matches Compose."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--check-persistence", action="store_true")
    parser.add_argument("--record", type=Path, default=Path("build/smoke.json"))
    args = parser.parse_args()

    def api(path, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        req = Request(args.base.rstrip("/") + path, data=body, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=30) as response:
            return json.load(response)

    assert api("/health")["status"] == "ok"
    if args.check_persistence:
        saved = json.loads(args.record.read_text(encoding="utf8"))
        product = api(f"/api/runs/{saved['id']}")
        assert product["status"] == "issued"
        assert product["result_hash"] == saved["result_hash"]
        assert api(f"/api/runs/{saved['id']}/replay", {})["match"]
        print("Signed product survived restart and replay matched.")
        return
    api("/api/events/demo", {})
    assert len(api("/api/events")) >= 4
    product = api("/api/runs", {"event_id": "event2", "ensemble": True, "actor": "acceptance"})
    result = product["result"]
    assert len(result["forecast"]) == 40 and len(result["members"]) == 15
    assert all(l <= m <= h for l,m,h in zip(result["p05"],result["p50"],result["p95"]))
    rid = product["id"]
    assert any(a["run_id"] == rid for a in api("/api/alerts"))
    assert api(f"/api/runs/{rid}/issue", {"actor":"reviewer"})["status"] == "issued"
    assert api(f"/api/runs/{rid}/replay", {})["match"]
    validation = api("/api/runs", {"event_id":"event4"})["result"]
    assert abs(validation["metrics"]["dc"] - .99908455) < 1e-6
    evidence = {"id":rid, "result_hash":product["result_hash"], "steps":40, "members":15,
                "peak":result["peak"], "warning":result["warning"], "validation":validation["metrics"]}
    args.record.parent.mkdir(parents=True,exist_ok=True)
    args.record.write_text(json.dumps(evidence, indent=2, ensure_ascii=False),encoding="utf8")
    print("Data -> ensemble forecast -> alert -> signed product -> replay verified.")

if __name__ == "__main__":
    main()

