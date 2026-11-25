"""Exercise backup and restore against a separately opened SQLite copy."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.domain import Service
from scripts.backup import backup

def main():
    root=ROOT/"build"
    root.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=root) as d:
        live=Path(d)/"live.db"
        copy=Path(d)/"recovered.db"
        service=Service(live,ROOT/"data")
        service.seed()
        rid=service.run("event2",ensemble=True)["id"]
        original=service.issue(rid,actor="reviewer")
        backup(live,copy)
        restored=Service(copy,ROOT/"data")
        product=restored.detail(rid)
        assert product["status"]=="issued"
        assert product["snapshot_hash"]==original["snapshot_hash"]
        assert product["result_hash"]==original["result_hash"]
        assert restored.replay(rid)["match"]
        print("Independent database backup restored signed ensemble product and replayed successfully.")
if __name__=="__main__":
    main()

