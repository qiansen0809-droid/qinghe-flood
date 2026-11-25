"""Run the Phase I hydrology model and causal river-state assimilation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import numpy as np
from .xaj_model import simulate, DT_H

STATIONS = ("青岭", "石林", "溪口", "龙潭", "白沙", "梅溪")
WEIGHTS = np.array([.22, .18, .15, .17, .13, .15])
GAIN = 0.5


def route_with_observations(inflow, params, observed, times, cutoff):
    """Publish a prior first; update channel outflow state only for subsequent steps."""
    ke, x = params["KE"], params["X"]
    d = DT_H / 2
    denom = ke * (1 - x) + d
    a, b, c = (d-ke*x)/denom, (d+ke*x)/denom, (ke*(1-x)-d)/denom
    prior, posterior = [], []
    horizon = datetime.fromisoformat(cutoff) if cutoff else None
    if horizon is not None and horizon.tzinfo:
        raise ValueError("校正截止时刻使用本地无时区时间")
    for t, current in enumerate(inflow):
        predicted = float(current if t == 0 else a*current + b*inflow[t-1] + c*posterior[-1])
        prior.append(predicted)
        available = observed[t] is not None and (horizon is None or datetime.fromisoformat(times[t]) <= horizon)
        posterior.append(predicted + GAIN * (observed[t]-predicted) if available else predicted)
    return prior, posterior


def shifted(rain, factor, lag):
    out = np.zeros_like(rain)
    for i in range(len(rain)):
        j = i-lag
        if 0 <= j < len(rain):
            out[i] = rain[j]*factor
    return out


def forecast(snapshot):
    obs = snapshot["event"]
    params = snapshot["parameters"]
    rain = np.asarray(obs["rain"], float)
    evap = obs["em"]
    times, observed = obs["times"], obs["observed"]

    def member(forcing):
        out = simulate(forcing, evap, params, obs["state"])
        raw = out["Q"].tolist()
        if snapshot["correction"]:
            curve, posterior = route_with_observations(out["Q_in"], params, observed, times, snapshot["cutoff"])
        else:
            curve, posterior = raw, raw
        return curve, raw, posterior

    curve, raw, post = member(rain)
    peak = float(max(curve))
    hit = [item for item in snapshot["thresholds"] if peak >= item["flow"]]
    warning = max(hit, key=lambda x:x["flow"])["level"] if hit else "正常"
    results = dict(times=times, observed=observed, raw=raw, forecast=curve, posterior=post,
                   peak=peak, peak_time=times[int(np.argmax(curve))], warning=warning,
                   p05=[], p50=[], p95=[], members=[], thresholds=snapshot["thresholds"])
    valid = [i for i in range(len(curve)) if observed[i] is not None]
    if valid:
        y = np.array([observed[i] for i in valid])
        err = np.array(curve)[valid]-y
        sst = np.sum((y-y.mean())**2)
        results["metrics"] = {"n":len(y), "rmse":float(np.sqrt(np.mean(err**2))),
                              "dc":float(1-np.sum(err**2)/sst) if sst>0 else None}
    else:
        results["metrics"] = {"n":0, "rmse":None, "dc":None}
    if snapshot["ensemble"]:
        def evaluate(s):
            line = member(shifted(rain,s["factor"],s["lag"]))[0]
            return {**s, "forecast":line, "peak":max(line)}
        with ThreadPoolExecutor(max_workers=4) as pool:
            members = list(pool.map(evaluate, snapshot["scenarios"]))
        bands = np.percentile([s["forecast"] for s in members], [5,50,95], axis=0)
        results.update(members=members,p05=bands[0].tolist(),p50=bands[1].tolist(),p95=bands[2].tolist())
    return results

