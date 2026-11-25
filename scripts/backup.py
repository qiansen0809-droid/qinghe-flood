"""Consistent SQLite backup, including committed pages in a WAL file."""
import argparse
import sqlite3
from pathlib import Path
from contextlib import closing

def backup(source, dest):
    source = Path(source).resolve(strict=True)
    dest = Path(dest)
    # Exclusive creation protects an existing backup from accidental replacement.
    dest.touch(exist_ok=False)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as live:
            with closing(sqlite3.connect(dest)) as copy:
                live.backup(copy)
                if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise RuntimeError("Backup failed SQLite integrity_check")
    except BaseException:
        dest.unlink()
        raise

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()
    backup(args.source, args.destination)

