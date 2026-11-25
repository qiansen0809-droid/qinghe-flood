"""SQLite interval schedules in UTC; a scheduler execution creates a draft forecast."""
from __future__ import annotations

from contextlib import closing
import json
import logging
from pathlib import Path
import sqlite3
import threading
import time

log = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, db: Path, service, poll_seconds: float):
        self.db = db
        self.service = service
        self.poll_seconds = poll_seconds
        self.stop_event = threading.Event()
        self.thread = None
        with closing(self.connect()) as conn, conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS job_schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT NOT NULL,
                interval_seconds INTEGER NOT NULL, next_run_at REAL NOT NULL,
                last_run_at REAL, last_run_id INTEGER, last_error TEXT,
                status TEXT NOT NULL DEFAULT 'waiting', active INTEGER NOT NULL DEFAULT 1
            )""")
            # The supported deployment uses one scheduler process per database.
            conn.execute("""UPDATE job_schedules SET last_error='服务在执行期间重启，请检查起报记录',
                status='interrupted' WHERE active=1 AND status='running'""")

    def connect(self):
        db = sqlite3.connect(str(self.db), timeout=15)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def decode(row):
        result = dict(row)
        payload = json.loads(result.pop('payload'))
        return {**payload, **result, 'active': bool(result['active'])}

    def list(self):
        with closing(self.connect()) as conn:
            rows = conn.execute('SELECT * FROM job_schedules ORDER BY id DESC')
            return [self.decode(row) for row in rows]

    def add(self, payload, interval_seconds, now=None):
        now = time.time() if now is None else now
        self.service.event_detail(payload['event_id'])
        if payload.get('plan_id') is not None:
            if not any(p['id'] == payload['plan_id'] and not p.get('deleted') for p in self.service.plans()):
                raise ValueError('调度方案版本不存在或已停用')
        if payload['ensemble'] and payload['event_id'] != 'event2':
            raise ValueError('15个配套降雨情景适用于 event2')
        with closing(self.connect()) as conn, conn:
            cur = conn.execute('INSERT INTO job_schedules(payload,interval_seconds,next_run_at) VALUES(?,?,?)',
                               (json.dumps(payload, ensure_ascii=False), interval_seconds, now + interval_seconds))
            return self.decode(conn.execute('SELECT * FROM job_schedules WHERE id=?', (cur.lastrowid,)).fetchone())

    def cancel(self, identifier):
        with closing(self.connect()) as conn, conn:
            changed = conn.execute("UPDATE job_schedules SET active=0,status='disabled' WHERE id=?", (identifier,))
            if not changed.rowcount:
                raise KeyError('找不到调度任务')
            return self.decode(conn.execute('SELECT * FROM job_schedules WHERE id=?', (identifier,)).fetchone())

    def tick(self, now=None):
        """Claim each due schedule once. Coalesce missed intervals into one forecast."""
        now = time.time() if now is None else now
        completed = []
        while not self.stop_event.is_set():
            with closing(self.connect()) as conn, conn:
                conn.execute('BEGIN IMMEDIATE')
                row = conn.execute("""SELECT * FROM job_schedules WHERE active=1 AND next_run_at<=?
                    AND status!='running' ORDER BY next_run_at,id LIMIT 1""", (now,)).fetchone()
                if row is None:
                    break
                conn.execute("""UPDATE job_schedules SET status='running', next_run_at=?,last_run_at=?
                             WHERE id=?""", (now+row['interval_seconds'], now, row['id']))
            payload = json.loads(row['payload'])
            payload['actor'] = f"scheduler:{row['id']}"
            run_id, error = None, None
            try:
                run_id = self.service.run(**payload)['id']
            except Exception as exc:
                log.exception('Schedule %s failed', row['id'])
                error = str(exc)
            with closing(self.connect()) as conn, conn:
                conn.execute("""UPDATE job_schedules SET last_run_id=?,last_error=?,
                    status=CASE WHEN active=0 THEN 'disabled' ELSE ? END WHERE id=?""",
                    (run_id,error,'failed' if error else 'waiting',row['id']))
            completed.append({'schedule_id':row['id'], 'run_id':run_id, 'error':error})
        return completed

    def _loop(self):
        while not self.stop_event.wait(self.poll_seconds):
            try:
                self.tick()
            except Exception:
                log.exception('Scheduler poll failed; retrying on next poll')

    def start(self):
        self.thread = threading.Thread(target=self._loop, name='qinghe-scheduler', daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join()

