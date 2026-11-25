"""Draw the report figure from previously saved CSV, without re-running forecasts."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
root=Path(__file__).resolve().parents[1]
def rows(name):
    with (root/"docs"/"evidence"/name).open(encoding="utf8") as stream:
        return list(csv.DictReader(stream))
def main():
    available={f.name for f in font_manager.fontManager.ttflist}
    for name in ("Microsoft YaHei","Noto Sans CJK SC","SimHei"):
        if name in available:
            plt.rcParams["font.family"]=name
            break
    else:
        raise SystemExit("Install Microsoft YaHei or Noto Sans CJK SC for Chinese figure labels.")
    plt.rcParams.update({"pdf.fonttype":42,"font.size":9,"axes.spines.top":False,"axes.spines.right":False})
    data=rows("event2_interval.csv"); peaks=rows("event2_member_peaks.csv")
    fig,(a,b)=plt.subplots(1,2,figsize=(9.4,3.45),layout="constrained",gridspec_kw={"width_ratios":[1.35,1]})
    t=[i*6 for i in range(len(data))]
    def series(key):return [float(p[key]) for p in data]
    a.fill_between(t,series("p05"),series("p95"),color="#e0e9ee",edgecolor="#657482",hatch="///",linewidth=.6,label="P05–P95")
    a.plot(t,series("base"),color="#074775",linewidth=1.8,label="基准")
    a.scatter(t,series("observed"),s=13,facecolors="white",edgecolors="#151515",linewidths=.7,zorder=4,label="观测")
    a.set(xlabel="距起点（h）",ylabel="流量（m³/s）",title="第二场洪水的逐时段情景区间")
    for delay,style,marker in [(-2,"--","s"),(0,"-","o"),(2,":","^")]:
        group=[r for r in peaks if int(r["lag"])==delay]
        b.plot([float(r["factor"]) for r in group],[float(r["peak"]) for r in group],linestyle=style,marker=marker,ms=4,label=f"时移 {delay:+d} 步")
    for threshold in (500,900): b.axhline(threshold,color="#444",lw=.7,ls="-.")
    b.set(xlabel="降雨倍率",ylabel="成员洪峰（m³/s）",title="降雨量级与峰值响应")
    for axis in (a,b):
        axis.legend(fontsize=7,frameon=False);axis.grid(axis="y",alpha=.2);axis.set_axisbelow(True)
    target=root/"docs/figures";target.mkdir(exist_ok=True)
    fig.savefig(target/"ensemble.pdf",bbox_inches="tight");plt.close(fig)
if __name__=="__main__":main()

