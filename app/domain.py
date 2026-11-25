"""SQLite repository and application operations for the Qinghe workbench."""
import csv
import hashlib
import json
import math
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .engine import forecast
from .quality import inspect_event, STATE_KEYS
from .xaj_model import PARAM_NAMES


def pack(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",",":"))


def digest(value):
    return hashlib.sha256(pack(value).encode()).hexdigest()


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def csv_rows(path):
    with path.open(encoding="utf-8-sig",newline="") as file:
        return list(csv.DictReader(file))


def label(value):
    if not isinstance(value,str) or not 1<=len(value.strip())<=128:
        raise ValueError("名称须为1至128字符")
    return value.strip()


def required(row, label):
    if row is None:
        raise KeyError(label)
    return row


def audit_row(db,actor,action,subject):
    db.execute("INSERT INTO history(at,actor,action,subject) VALUES(?,?,?,?)",
               (timestamp(),label(actor),action,str(subject)))


SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
 event_id TEXT PRIMARY KEY, payload TEXT NOT NULL, raw_csv TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS plans (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL, parameters TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0, UNIQUE(name,version));
CREATE UNIQUE INDEX IF NOT EXISTS one_active ON plans(active) WHERE active=1;
CREATE TABLE IF NOT EXISTS runs (
 id INTEGER PRIMARY KEY, event_id TEXT NOT NULL, plan_id INTEGER NOT NULL REFERENCES plans(id),
 status TEXT NOT NULL, created TEXT NOT NULL, snapshot TEXT NOT NULL, result TEXT NOT NULL,
 snapshot_hash TEXT NOT NULL, result_hash TEXT NOT NULL, issued_at TEXT, issued_by TEXT);
CREATE TABLE IF NOT EXISTS history (
 id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, subject TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL UNIQUE REFERENCES runs(id), level TEXT NOT NULL,
 message TEXT NOT NULL, created TEXT NOT NULL, read_at TEXT);
"""


class Service:
    def __init__(self,db_path,data_dir):
        self.path=Path(db_path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.data=Path(data_dir)
        engine_sources = [Path(__file__).with_name(name).read_bytes()
                          for name in ("engine.py","xaj_model.py")]
        self.engine_hash = hashlib.sha256(b"\0".join(engine_sources)).hexdigest()
        with self.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript(SCHEMA)

    @contextmanager
    def connection(self,write=False):
        db=sqlite3.connect(self.path, timeout=30)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def seed(self):
        """Install sample events once; restarting never replaces operator data."""
        with self.connection(True) as db:
            if not db.execute("SELECT 1 FROM plans LIMIT 1").fetchone():
                p=json.loads((self.data/"frozen_parameters.json").read_text(encoding="utf-8-sig"))["parameters"]
                db.execute("INSERT INTO plans(name,version,parameters,active) VALUES(?,1,?,1)",
                           ("一期率定参数",pack(p)))
                audit_row(db,"system","seed_plan",1)
            for ix in csv_rows(self.data/"events_index.csv"):
                name=ix["场次编号"]
                if db.execute("SELECT 1 FROM events WHERE event_id=?",(name,)).fetchone():
                    continue
                raw=(self.data/"events"/f"{name}.csv").read_text(encoding="utf-8-sig")
                state={k:float(ix[f"初始{k}({'m³/s' if k.startswith('Q') else 'mm'})"]) for k in STATE_KEYS}
                self._put_event(db,name,raw,state,"system")

    def _put_event(self,db,event_id,raw,state,actor):
        doc=inspect_event(raw,state)
        db.execute("INSERT INTO events(event_id,payload,raw_csv,updated) VALUES(?,?,?,?) "
                   "ON CONFLICT(event_id) DO UPDATE SET payload=excluded.payload,raw_csv=excluded.raw_csv,updated=excluded.updated",
                   (event_id,pack(doc),raw,timestamp()))
        audit_row(db,actor,"ingest",event_id)
        return dict(event_id=event_id,**{k:doc[k] for k in ("count","quality","issues")})

    def ingest(self,event_id,csv_text,state,actor="operator"):
        with self.connection(True) as db:
            return self._put_event(db,label(event_id),csv_text,state,actor)

    def events(self):
        with self.connection() as db:
            rows=db.execute("SELECT event_id,payload,updated FROM events ORDER BY event_id").fetchall()
        out=[]
        for row in rows:
            doc=json.loads(row["payload"])
            out.append(dict(event_id=row["event_id"], updated=row["updated"],
                            **{k:doc[k] for k in ("count","quality","issues")}))
        return out

    def event_detail(self,event_id):
        with self.connection() as db:
            row=required(db.execute("SELECT * FROM events WHERE event_id=?",(event_id,)).fetchone(),event_id)
            return {"event_id":event_id,"updated":row["updated"],**json.loads(row["payload"])}

    @staticmethod
    def _plan(row):
        return dict(id=row["id"], name=row["name"], version=row["version"],
                    parameters=json.loads(row["parameters"]), active=bool(row["active"]), deleted=bool(row["deleted"]))

    def plans(self):
        with self.connection() as db:
            return [self._plan(row) for row in db.execute("SELECT * FROM plans WHERE deleted=0 ORDER BY id DESC")]

    def save_plan(self,name,parameters,actor="operator"):
        name=label(name)
        if not isinstance(parameters,dict) or set(parameters)!=set(PARAM_NAMES):
            raise ValueError("方案须包含16项新安江参数")
        p={k:float(v) for k,v in parameters.items()}
        for row in csv_rows(self.data/"params_initial.csv"):
            lo,hi=map(float,row["参考范围"].split("~"))
            if not lo <= p[row["参数"]] <= hi:
                raise ValueError(f'{row["参数"]} 须在 [{lo}, {hi}] 内')
        if not 2*p["KE"]*p["X"]<=6<=2*p["KE"]*(1-p["X"]):
            raise ValueError("KE 与 X 不满足六小时河道稳定条件")
        with self.connection(True) as db:
            ver=db.execute("SELECT COALESCE(MAX(version),0)+1 FROM plans WHERE name=?",(name,)).fetchone()[0]
            pid=db.execute("INSERT INTO plans(name,version,parameters) VALUES(?,?,?)",(name,ver,pack(p))).lastrowid
            audit_row(db,actor,"create_plan_version",pid)
            return self._plan(db.execute("SELECT * FROM plans WHERE id=?",(pid,)).fetchone())

    def activate(self,plan_id,actor="operator"):
        with self.connection(True) as db:
            required(db.execute("SELECT id FROM plans WHERE id=? AND deleted=0",(plan_id,)).fetchone(),plan_id)
            db.execute("UPDATE plans SET active=0 WHERE active=1")
            db.execute("UPDATE plans SET active=1 WHERE id=?",(plan_id,))
            audit_row(db,actor,"activate",plan_id)
            return self._plan(db.execute("SELECT * FROM plans WHERE id=?",(plan_id,)).fetchone())

    def delete_plan(self,plan_id,actor="operator"):
        with self.connection(True) as db:
            plan=required(db.execute("SELECT * FROM plans WHERE id=? AND deleted=0",(plan_id,)).fetchone(),plan_id)
            if plan["active"]:
                raise ValueError("先切换到其他方案，再删除当前启用的版本")
            db.execute("UPDATE plans SET deleted=1 WHERE id=?",(plan_id,))
            audit_row(db,actor,"delete_plan",plan_id)
            return {"id":plan_id,"deleted":True}

    def _rules(self):
        levels=[dict(level=r["项目"],flow=float(r["相应流量(m³/s)"])) for r in csv_rows(self.data/"thresholds.csv")]
        scenarios=[dict(id=r["情景编号"],base=r["基准场次"],factor=float(r["降雨缩放系数"]),lag=int(r["雨型时移(时段)"]))
                   for r in csv_rows(self.data/"scenarios.csv")]
        return levels,scenarios

    def run(self,event_id,plan_id=None,correction=False,ensemble=False,actor="operator",cutoff=None):
        with self.connection() as db:
            db.execute("BEGIN")
            row=required(db.execute("SELECT * FROM events WHERE event_id=?",(event_id,)).fetchone(),event_id)
            event=json.loads(row["payload"])
            source_hash=hashlib.sha256(row["raw_csv"].encode()).hexdigest()
            if event["quality"]=="blocked":
                raise ValueError("场次存在阻断型质控问题，请修正后重新入库")
            plan=required(db.execute("SELECT * FROM plans WHERE deleted=0 AND " +
                    ("active=1" if plan_id is None else "id=?"), () if plan_id is None else (plan_id,)).fetchone(),"方案")
            levels,scenarios=self._rules()
            if ensemble and any(s["base"]!=event_id for s in scenarios):
                raise ValueError("所附15个集合情景以event2为基准")
            if cutoff and not correction:
                raise ValueError("校正截止时间只适用于已启用状态校正的预报")
            snapshot=dict(event=event,event_id=event_id,source_sha256=source_hash,parameters=json.loads(plan["parameters"]),
                          plan_id=plan["id"],plan_name=plan["name"],plan_version=plan["version"],engine_hash=self.engine_hash,
                          correction=bool(correction),ensemble=bool(ensemble),cutoff=cutoff,
                          thresholds=levels,scenarios=scenarios if ensemble else [])
        result=forecast(snapshot)
        with self.connection(True) as db:
            run_id=db.execute("INSERT INTO runs(event_id,plan_id,status,created,snapshot,result,snapshot_hash,result_hash) "
                              "VALUES(?,?,'draft',?,?,?,?,?)",(event_id,plan["id"],timestamp(),pack(snapshot),pack(result),
                              digest(snapshot),digest(result))).lastrowid
            audit_row(db,actor,"forecast",run_id)
            if result["warning"]!="正常":
                msg=f"{event_id} 预计在 {result['peak_time']} 达到 {result['peak']:.1f} m³/s，触及{result['warning']}阈值"
                db.execute("INSERT INTO messages(run_id,level,message,created) VALUES(?,?,?,?)",
                           (run_id,result["warning"],msg,timestamp()))
                audit_row(db,"system","notify",run_id)
        return self.detail(run_id)

    @staticmethod
    def _summary(row):
        return {k:row[k] for k in ("id","event_id","plan_id","status","created","issued_at","issued_by","snapshot_hash","result_hash")}

    def runs(self):
        with self.connection() as db:
            return [self._summary(row) for row in db.execute(
                "SELECT id,event_id,plan_id,status,created,issued_at,issued_by,snapshot_hash,result_hash FROM runs ORDER BY id DESC")]

    def detail(self,run_id):
        with self.connection() as db:
            row=required(db.execute("SELECT * FROM runs WHERE id=?",(run_id,)).fetchone(),run_id)
            return {**self._summary(row),"snapshot":json.loads(row["snapshot"]),"result":json.loads(row["result"])}

    def issue(self,run_id,actor="operator"):
        with self.connection(True) as db:
            row=required(db.execute("SELECT status FROM runs WHERE id=?",(run_id,)).fetchone(),run_id)
            if row["status"]=="draft":
                db.execute("UPDATE runs SET status='issued',issued_by=?,issued_at=? WHERE id=?",(label(actor),timestamp(),run_id))
                audit_row(db,actor,"issue",run_id)
        return self.detail(run_id)

    def replay(self,run_id,actor="operator"):
        old=self.detail(run_id)
        snap=old["snapshot"]
        if digest(snap)!=old["snapshot_hash"] or digest(old["result"])!=old["result_hash"]:
            raise ValueError("历史快照或结果摘要不一致")
        if snap["engine_hash"]!=self.engine_hash:
            raise ValueError("模型代码版本已变化，请使用原版本回放")
        actual=digest(forecast(snap))
        with self.connection(True) as db:
            audit_row(db,actor,"replay",run_id)
        return {"run_id":run_id,"match":actual==old["result_hash"],"result_hash":actual,"snapshot_hash":old["snapshot_hash"]}

    def notifications(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM messages ORDER BY id DESC")]

    def read_notification(self,notification_id,actor="operator"):
        with self.connection(True) as db:
            row=required(db.execute("SELECT * FROM messages WHERE id=?",(notification_id,)).fetchone(),notification_id)
            if row["read_at"] is None:
                db.execute("UPDATE messages SET read_at=? WHERE id=?",(timestamp(),notification_id))
                audit_row(db,actor,"read_notification",notification_id)
            return dict(db.execute("SELECT * FROM messages WHERE id=?",(notification_id,)).fetchone())

    def audit(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM history ORDER BY id DESC")]

