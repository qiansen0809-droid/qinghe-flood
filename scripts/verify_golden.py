"""Compare all Phase II base curves with the archived Phase I reference."""
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from app.domain import Service


def verify(service):
    reports = []
    for number in range(1, 5):
        event = f"event{number}"
        with (ROOT / "data" / "golden" / f"{event}.csv").open(encoding="utf-8-sig") as source:
            reference = list(csv.DictReader(source))
        product = service.run(event)["result"]
        actual = np.asarray(product["forecast"])
        expected = np.array([float(row["expected_flow"]) for row in reference])
        np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-8)
        reports.append({"event": event, "n": len(actual),
                        "max_abs_difference": float(np.abs(actual - expected).max()),
                        **product["metrics"]})
    return reports

