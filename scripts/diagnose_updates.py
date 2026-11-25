"""Save paired forecast errors to explain the effect of each state update."""
import csv
import tempfile
from pathlib import Path
from app.domain import Service
from app.xaj_model import DT_H

ROOT = Path(__file__).resolve().parents[1]

def main():
    output = ROOT / "docs/evidence/rolling_steps.csv"
    with tempfile.TemporaryDirectory() as tmp, output.open("w", newline="", encoding="utf8") as stream:
        service = Service(Path(tmp)/"audit.db", ROOT/"data")
        service.seed()
        writer = csv.writer(stream)
        writer.writerow(["event","time","observed","base","rolling","shift","base_error","rolling_error","delta_squared_error"])
        for number in range(1,5):
            event = f"event{number}"
            product = service.run(event, correction=True)
            result = product["result"]
            pars = product["snapshot"]["parameters"]
            k = pars["KE"]*(1-pars["X"])
            carry = (k-DT_H/2)/(k+DT_H/2)
            previous_posterior_delta = 0
            rows = []
            for time,y,b,q,post in zip(result["times"],result["observed"],result["raw"],result["forecast"],result["posterior"]):
                shift = q-b
                assert abs(shift-carry*previous_posterior_delta)<1e-9
                previous_posterior_delta = post-b
                rows.append([event,time,y,b,q,shift,b-y,q-y,(q-y)**2-(b-y)**2])
            writer.writerows(rows)
            print(event,"carry",round(carry,5),"largest impact", max(rows,key=lambda row:abs(row[-1])), "delta SSE",sum(row[-1] for row in rows))
if __name__ == "__main__":
    main()

