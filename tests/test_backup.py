import sqlite3
import pytest
from scripts.backup import backup

def test_backup_keeps_committed_data_and_existing_copies(tmp_path):
    source = tmp_path / "live.sqlite3"
    destination = tmp_path / "copy.sqlite3"
    conn = sqlite3.connect(source)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE sample(v)")
        conn.execute("INSERT INTO sample VALUES (9)")
        conn.commit()
        backup(source, destination)
    finally:
        conn.close()
    replica = sqlite3.connect(destination)
    try:
        assert replica.execute("SELECT v FROM sample").fetchone()[0] == 9
    finally:
        replica.close()
    with pytest.raises(FileExistsError):
        backup(source, destination)

