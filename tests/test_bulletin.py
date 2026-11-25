from pathlib import Path
from fastapi.testclient import TestClient
from app.api import create_app

DATA = Path(__file__).resolve().parents[1]/"data"


def test_bulletin_requires_issue_and_matches_stored_series(tmp_path):
    with TestClient(create_app(tmp_path/"product.sqlite", DATA, enable_scheduler=False)) as client:
        draft = client.post("/api/runs",json={"event_id":"event2"}).json()
        url = f"/api/runs/{draft['id']}/bulletin"
        assert client.get(url).status_code == 409
        assert client.get("/api/runs/9999/bulletin").status_code == 404
        issued = client.post(f"/api/runs/{draft['id']}/issue",json={"actor":"钱森"}).json()
        response = client.get(url)
        assert response.status_code == 200
        doc = response.json()
        assert doc["bulletin_id"] in response.headers["content-disposition"]
        assert "attachment" in response.headers["content-disposition"]
        assert doc["signed_by"] == "钱森"
        assert doc["signed_at"] == issued["issued_at"]
        assert doc["warning_level"] == "警戒水位"
        assert doc["result_sha256"] == issued["result_hash"]
        assert doc["series"] == [{"time":t,"discharge":q} for t,q in
                                  zip(issued["result"]["times"],issued["result"]["forecast"])]
        assert doc["peak_discharge"] == max(p["discharge"] for p in doc["series"])
        assert client.get(url).content == response.content

