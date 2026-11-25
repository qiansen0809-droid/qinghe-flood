"""Generate the report tables and retained data in an isolated teaching database."""
from pathlib import Path
import csv
import json
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.domain import Service
from scripts.verify_golden import verify

def save_csv(path, records):
    with path.open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

def main():
    target=ROOT/"docs"/"evidence"
    target.mkdir(exist_ok=True)
    dbdir=ROOT/"build"
    dbdir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dbdir) as tmp:
        service=Service(Path(tmp)/"report.db",ROOT/"data")
        service.seed()
        comparison=verify(service)
        save_csv(target/"golden.csv", comparison)
        run=service.run("event2",ensemble=True,actor="demo")
        res=run["result"]
        rows=[{"time":t,"observed":res["observed"][i],"base":res["forecast"][i],
               "p05":res["p05"][i],"p50":res["p50"][i],"p95":res["p95"][i]}
              for i,t in enumerate(res["times"])]
        save_csv(target/"event2_interval.csv",rows)
        members=[{k:m[k] for k in ("id","factor","lag","peak")} for m in res["members"]]
        save_csv(target/"event2_member_peaks.csv",members)
        issued=service.issue(run["id"],actor="demo-review")
        replay=service.replay(run["id"],actor="demo-review")
        correction=[]
        for e in ["event1","event2","event3","event4"]:
            raw=service.run(e)["result"]
            corrected=service.run(e,correction=True)["result"]
            correction.append({"event":e,"dc_base":raw["metrics"]["dc"],"dc_rolling":corrected["metrics"]["dc"],
                               "rmse_base":raw["metrics"]["rmse"],"rmse_rolling":corrected["metrics"]["rmse"]})
        save_csv(target/"rolling.csv",correction)
        evidence=dict(product_status=issued["status"],replay_match=replay["match"],peak=res["peak"],
                      warning=res["warning"],n_members=len(members),
                      member_alert=sum(m["peak"]>=500 for m in members),
                      member_high=sum(m["peak"]>=900 for m in members))
        (target/"outcome.json").write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    # Report tables are generated after the measurements have been saved.
    with (target/"rolling.csv").open(encoding="utf8") as f:
        outputs=list(csv.DictReader(f))
    lines=[r"\begin{tabular}{lrrrr}\toprule 场次 & 基线 DC & 滚动 DC & 基线 RMSE & 滚动 RMSE\\\midrule"]
    for row in outputs:
        lines.append(row["event"]+" & "+" & ".join(f"{float(row[k]):.6f}" for k in ("dc_base","dc_rolling","rmse_base","rmse_rolling"))+r" \\")
    lines.append(r"\bottomrule\end{tabular}")
    (target/"rolling.tex").write_text("\n".join(lines),encoding="utf8")
    print(json.dumps(evidence,ensure_ascii=False))

if __name__=="__main__":
    main()

