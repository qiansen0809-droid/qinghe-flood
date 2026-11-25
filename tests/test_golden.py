from pathlib import Path
from app.domain import Service
from scripts.verify_golden import verify

def test_reference_hydrographs(tmp_path):
    service = Service(tmp_path / "golden.sqlite3", Path(__file__).resolve().parents[1] / "data")
    service.seed()
    assert [r["n"] for r in verify(service)] == [40] * 4

