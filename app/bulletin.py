"""Portable, signed-off forecast product for the teaching basin."""
from pydantic import BaseModel


class FlowAtTime(BaseModel):
    time: str
    discharge: float


class Bulletin(BaseModel):
    bulletin_id: str
    title: str
    event_id: str
    run_id: int
    station: str
    signed_by: str
    signed_at: str
    discharge_unit: str
    time_step_hours: int
    warning_level: str
    peak_discharge: float
    peak_time: str
    summary: str
    series: list[FlowAtTime]
    snapshot_sha256: str
    result_sha256: str


def make_bulletin(product: dict) -> Bulletin:
    rid = product["id"]
    result = product["result"]
    series = [FlowAtTime(time=t, discharge=q) for t,q in zip(result["times"],result["forecast"],strict=True)]
    return Bulletin(
        bulletin_id=f"QH-{rid:08d}", title="青河水文站洪水预报公报（教学）",
        event_id=product["event_id"], run_id=rid, station="青河水文站",
        signed_by=product["issued_by"], signed_at=product["issued_at"],
        discharge_unit="m³/s", time_step_hours=6, warning_level=result["warning"],
        peak_discharge=result["peak"], peak_time=result["peak_time"], series=series,
        summary=(f"{series[0].time} 至 {series[-1].time} 共 {len(series)} 个时段，"
                 f"预计 {result['peak_time']} 洪峰流量 {result['peak']:.1f} m³/s。判别结果为{result['warning']}。"),
        snapshot_sha256=product["snapshot_hash"], result_sha256=product["result_hash"],
    )

