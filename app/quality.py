"""Validate teaching CSVs without silently filling bad forcing values."""
import csv
import io
import math
from datetime import datetime, timedelta
import numpy as np
from .engine import STATIONS, WEIGHTS

STATE_KEYS = ("WU","WL","WD","S","QS","QI","QG")
P_COLS = [f"P_{s}(mm)" for s in STATIONS]
EM_COL = "蒸发皿EM(mm)"
Q_COL = "实测流量Q(m3/s)"


def inspect_event(text, state):
    if not isinstance(text, str) or not text.strip() or len(text)>2_000_000:
        raise ValueError("CSV 不能为空且不得超过 200 万字符")
    if not isinstance(state,dict) or set(state)!=set(STATE_KEYS):
        raise ValueError("初始状态须包含 WU/WL/WD/S/QS/QI/QG")
    state = {k:float(state[k]) for k in STATE_KEYS}
    if not all(math.isfinite(v) and v>=0 for v in state.values()):
        raise ValueError("初始蓄量和流量须为非负有限数值")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    cols = reader.fieldnames or []
    required = ["时间",*P_COLS,EM_COL,Q_COL]
    if len(cols)!=len(set(cols)) or any(c not in cols for c in required):
        raise ValueError("CSV 表头重复或缺少时间、六站雨量、蒸发皿EM、实测流量Q")
    flags, times, observed, rain, em = [], [], [], [], []
    prev = None
    for line,row in enumerate(reader,2):
        if line>20001:
            raise ValueError("单场最多 20000 个时段")
        def flag(col,reason,severity="error"):
            flags.append(dict(row=line,column=col,reason=reason,severity=severity))
        if None in row:
            flag("CSV","列数超过表头")
        stamp = (row.get("时间") or "").strip()
        try:
            when = datetime.fromisoformat(stamp)
            if when.tzinfo:
                raise ValueError()
            if prev is not None and when-prev != timedelta(hours=6):
                flag("时间","时刻乱序、重复或步长非6小时")
            prev = when
            stamp = when.isoformat(sep=" ",timespec="seconds")
        except ValueError:
            flag("时间","无效本地时刻")
        times.append(stamp)
        def value(col):
            raw = (row.get(col) or "").strip()
            severity = "warning" if col==Q_COL else "error"
            if raw in ("","-999","-999.0"):
                flag(col,"缺测",severity)
                return None
            try:
                number=float(raw)
                if not math.isfinite(number) or number<0: raise ValueError()
                return number
            except ValueError:
                flag(col,"数值异常",severity)
                return None
        station=[value(col) for col in P_COLS]
        rain.append(None if None in station else float(np.dot(station,WEIGHTS)))
        observed.append(value(Q_COL))
        em.append(value(EM_COL))
    if not times:
        raise ValueError("CSV 缺少数据行")
    status="blocked" if any(f["severity"]=="error" for f in flags) else ("warning" if flags else "ok")
    return dict(times=times,rain=rain,observed=observed,em=em,state=state,
                issues=flags,quality=status,count=len(times))

