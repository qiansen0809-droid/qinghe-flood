# -*- coding: utf-8 -*-
"""
=============================================================
 青河流域 · 新安江模型正向模拟程序（教学版 v2）
 河海大学《软件工程》课程 · 第8章 软件工程应用案例 配套数据包
 （学生版：不含参数真值，率定结果请自行评定）
-------------------------------------------------------------
 时段长 Δt = 6 h，流域面积 F = 2000 km²
 模型结构：三层蒸散发 → 蓄满产流 → 三水源划分 → 分水源汇流 → 河道演算
   地表径流 RS：线性水库（CS）        ※ v2 起不再使用单位线
   壤中流  RI：线性水库（CI）
   地下径流 RG：线性水库（CG）
   总出流 Q 经马斯京根法演算至出口断面（KE, X）
=============================================================
"""
# 作业扩展：面积加权守恒；禁止静默截断初始蓄量；约束河道系数。
# original/xaj_model.py 保留未经修改的教学源程序。
import numpy as np

# ---------------- 流域与时段常量 ----------------
F_BASIN = 2000.0                  # 流域面积 (km²)
DT_H    = 6.0                     # 时段长 (h)
U_CONV  = F_BASIN / (3.6 * DT_H)  # 换算系数: 1 mm/时段 ≈ 92.6 m³/s

# 模型参数表（16 个）
PARAM_NAMES = ["K", "WUM", "WLM", "WDM", "C", "B", "IM",
               "SM", "EX", "KI", "KG", "CS", "CI", "CG", "KE", "X"]

# 参数读取：从 CSV 参数文件（如 params_initial.csv）读入 16 个参数
def load_params(path="params_initial.csv"):
    """读取参数文件，返回参数字典。CSV 需含“参数”“参数值”两列。"""
    import csv
    prm = {}
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = row["参数"].strip()
            if name in PARAM_NAMES:
                prm[name] = float(row["参数值"])
    missing = [k for k in PARAM_NAMES if k not in prm]
    if missing:
        raise ValueError(f"参数文件缺少参数: {missing}")
    return prm



# ---------------- 1. 三层蒸散发 ----------------
def evapotranspire(P, EP, WU, WL, WD, prm):
    """P: 时段降雨(mm); EP: 时段蒸散发能力(mm); 返回 (E, WU, WL, WD)"""
    WUM, WLM, C = prm["WUM"], prm["WLM"], prm["C"]
    if WU + P >= EP:
        EU, EL, ED = EP, 0.0, 0.0
    else:
        EU = WU + P
        if WL >= C * WLM:
            EL, ED = min((EP - EU) * WL / WLM, WL), 0.0
        elif WL >= C * (EP - EU):
            EL, ED = C * (EP - EU), 0.0
        else:
            EL = WL
            ED = min(C * (EP - EU) - EL, WD)   # 深层蒸散发不超过深层蓄水
    WU = WU + P - EU
    WL = WL - EL
    WD = WD - ED
    return EU + EL + ED, WU, WL, WD


# ---------------- 2. 蓄满产流 ----------------
def runoff(PE, W, prm):
    """PE: 时段净雨(mm); W: 时段初（降雨前）流域土壤蓄水(mm)
       返回 (R, RIM, FR, W_over)；W_over 为超过 WM 的异常滞蓄（正常为 0）"""
    WM = prm["WUM"] + prm["WLM"] + prm["WDM"]
    B, IM = prm["B"], prm["IM"]
    W_over = max(W - WM, 0.0)   # 土层串层溢出的水，直接产流
    W = min(W, WM)
    if PE <= 0.0:
        return W_over, 0.0, 0.0, W_over
    WMM = WM * (1.0 + B)
    A0 = WMM * (1.0 - (1.0 - W / WM) ** (1.0 / (1.0 + B)))
    if PE + A0 < WMM:
        R = PE - WM + W + WM * (1.0 - (PE + A0) / WMM) ** (1.0 + B)
    else:
        R = PE - (WM - W)
    R = max(R, 0.0) + W_over
    RIM = PE * IM               # 不透水面积直接产流
    FR = max(R - W_over, 0.0) / PE   # 透水面积产流比（供水水源划分用）
    return R, RIM, FR, W_over


# ---------------- 3. 三水源划分（自由水蓄水库） ----------------
def split_sources(R_perm, FR, S, prm):
    """R_perm: 透水面积产流 R-W_over(mm); S: 自由水蓄水(mm)
       返回 (RS, RI, RG, S_new)"""
    SM, EX, KI, KG = prm["SM"], prm["EX"], prm["KI"], prm["KG"]
    S = min(max(S, 0.0), SM)   # 容错：率定中 SM 变小时自由水蓄量不越界
    if R_perm <= 0.0 or FR <= 0.0:
        return 0.0, 0.0, 0.0, S
    SMM = SM * (1.0 + EX)
    AU = SMM * (1.0 - (1.0 - S / SM) ** (1.0 / (1.0 + EX)))
    if R_perm + AU < SMM:
        RB = FR * (R_perm - (SM - S) + SM * (1.0 - (R_perm + AU) / SMM) ** (1.0 + EX))
    else:
        RB = FR * (R_perm - SM + S)
    RI = KI * S * FR
    RG = KG * S * FR
    if RI + RG > RB:          # 壤中流+地下径流不超过总出流，等比缩减保证守恒
        f = RB / (RI + RG)
        RI, RG = RI * f, RG * f
    RS = max(RB - RI - RG, 0.0)
    # 自由水蓄量更新（流域平均口径）：ΔS = 产流量 - 三水源出流；
    # 超过 SM 的溢出部分补回地表径流，保证水量守恒
    S_raw = S + R_perm - RB
    S_new = min(max(S_raw, 0.0), SM)
    RS = RS + max(S_raw - SM, 0.0)
    return RS, RI, RG, S_new


# ---------------- 4. 汇流（三水源均为线性水库） ----------------
def route(RS_s, RI, RG, QS0, QI0, QG0, prm):
    """RS_s/RI/RG: 三水源产流序列(mm); QS0/QI0/QG0: 初始出流(m³/s)
       返回 (QS, QI, QG)，单位 m³/s
       线性水库: Q(t)=C·Q(t-1)+(1-C)·U·I(t)，地表/壤中/地下分别用 CS/CI/CG"""
    n = len(RS_s)
    CS, CI, CG = prm["CS"], prm["CI"], prm["CG"]
    QS = np.zeros(n); QI = np.zeros(n); QG = np.zeros(n)
    qs, qi, qg = QS0, QI0, QG0
    for t in range(n):
        qs = CS * qs + (1.0 - CS) * U_CONV * RS_s[t]
        qi = CI * qi + (1.0 - CI) * U_CONV * RI[t]
        qg = CG * qg + (1.0 - CG) * U_CONV * RG[t]
        QS[t], QI[t], QG[t] = qs, qi, qg
    return QS, QI, QG


def muskingum(I, KE, x, dt_h=DT_H):
    """马斯京根河道演算：KE 为河段传播时间(h)，x 为楔蓄权重(0~0.5)"""
    dt = dt_h
    den = KE - KE * x + 0.5 * dt
    C0 = (0.5 * dt - KE * x) / den
    C1 = (0.5 * dt + KE * x) / den
    C2 = (KE - KE * x - 0.5 * dt) / den
    O = np.zeros(len(I))
    O[0] = I[0]
    for t in range(1, len(I)):
        O[t] = C0 * I[t] + C1 * I[t - 1] + C2 * O[t - 1]
    return O


# ---------------- 正向模拟主程序 ----------------
def simulate(P, EM, prm, state0):
    """
    P, EM : 等长序列，时段降雨 / 蒸发皿蒸发 (mm/6h)
    prm   : 参数字典（16 个参数）
    state0: 初始状态 {"WU","WL","WD","S","QS","QI","QG"}
    返回   : dict，含 Q(出口断面流量, 经河道演算, m³/s)、QS/QI/QG(流域汇流后)、
             Q_in(河道演算前)、R、E、W、S 等过程
    """
    P = np.asarray(P, float); EM = np.asarray(EM, float)
    n = len(P)
    if n == 0 or EM.shape != P.shape or P.ndim != 1:
        raise ValueError("P and EM must be nonempty equal-length 1D arrays")
    if not np.all(np.isfinite(P)) or not np.all(np.isfinite(EM)) or np.any(P < 0) or np.any(EM < 0):
        raise ValueError("P and EM must be finite and nonnegative")
    if any(state0[k] < 0 or state0[k] > prm[cap] for k,cap in [("WU","WUM"),("WL","WLM"),("WD","WDM"),("S","SM")]):
        raise ValueError("Initial storage exceeds capacity; silent clipping is forbidden")
    if not 0 <= prm["IM"] < 1 or any(not 0 <= prm[k] < 1 for k in ["CS","CI","CG"]):
        raise ValueError("Invalid fraction or reservoir coefficient")
    if prm["KI"] < 0 or prm["KG"] < 0 or prm["KI"]+prm["KG"] > 1:
        raise ValueError("Invalid source coefficients")
    if not (0 <= prm["X"] <= 0.5 and 2*prm["KE"]*prm["X"] <= DT_H <= 2*prm["KE"]*(1-prm["X"])):
        raise ValueError("Muskingum nonnegative coefficient condition violated")
    WM = prm["WUM"] + prm["WLM"] + prm["WDM"]
    # 初始状态容错：不超过各层容量
    WU = min(state0["WU"], prm["WUM"]); WL = min(state0["WL"], prm["WLM"])
    WD = min(state0["WD"], prm["WDM"]); S = min(state0["S"], prm["SM"])
    QS0 = state0.get("QS", 0.0); QI0, QG0 = state0["QI"], state0["QG"]
    E_a = np.zeros(n); R_a = np.zeros(n); W_a = np.zeros(n); S_a = np.zeros(n)
    RSs = np.zeros(n); RIa = np.zeros(n); RGa = np.zeros(n)
    for t in range(n):
        W0 = WU + WL + WD                 # 时段初（降雨前）蓄水 → 产流公式用它
        EP = prm["K"] * EM[t]
        E, WU, WL, WD = evapotranspire(P[t], EP, WU, WL, WD, prm)
        PE = P[t] - E
        R, RIM, FR, W_over = runoff(max(PE, 0.0), W0, prm)
        # 更新流域蓄水：W' = W0 + PE - R（PE 可为负，旱期蓄水真实消耗）
        W_new = min(W0, WM) + PE - (R - W_over)
        W_new = min(max(W_new, 0.0), WM)
        WU = min(W_new, prm["WUM"])
        WL = min(max(W_new - WU, 0.0), prm["WLM"])
        WD = max(W_new - WU - WL, 0.0)
        # 三水源划分（仅透水面积产流部分）
        RS, RI, RG, S = split_sources(R - W_over, FR, S, prm)
        RSs[t] = (1-prm["IM"])*(RS + W_over) + RIM   # 不透水产流与串层溢出直接进入地表
        RIa[t], RGa[t] = (1-prm["IM"])*RI, (1-prm["IM"])*RG
        E_a[t], R_a[t], W_a[t], S_a[t] = (1-prm["IM"])*E + prm["IM"]*min(P[t], EP), (1-prm["IM"])*R + RIM, W_new, S
    QS, QI, QG = route(RSs, RIa, RGa, QS0, QI0, QG0, prm)
    Q_in = QS + QI + QG                     # 流域出口（入库断面）流量
    Q = muskingum(Q_in, prm["KE"], prm["X"])  # 河道演算至青河水文站
    return {"Q": Q, "Q_in": Q_in, "QS": QS, "QI": QI, "QG": QG,
            "R": R_a, "E": E_a, "W": W_a, "S": S_a,
            "RS_mm": RSs, "RI_mm": RIa, "RG_mm": RGa,
            "state_end": {"WU": WU, "WL": WL, "WD": WD, "S": S,
                          "QS": QS[-1], "QI": QI[-1], "QG": QG[-1]}}


# ---------------- 精度评定 ----------------
def dc_coefficient(Q_obs, Q_sim):
    """确定性系数 DC = 1 - Σ(Qobs-Qsim)²/Σ(Qobs-Q̄obs)²"""
    Q_obs = np.asarray(Q_obs, float); Q_sim = np.asarray(Q_sim, float)
    return 1.0 - np.sum((Q_obs - Q_sim) ** 2) / np.sum((Q_obs - Q_obs.mean()) ** 2)

def rmse(Q_obs, Q_sim):
    return float(np.sqrt(np.mean((np.asarray(Q_obs) - np.asarray(Q_sim)) ** 2)))


if __name__ == "__main__":
    # 自检：课件第 3 节算例（WM=100, B=0.3, W0=80, P=40, E=4）
    prm = {**load_params(), "WUM": 20.0, "WLM": 60.0, "WDM": 20.0, "B": 0.3}  # 课件算例演示参数（WM=100, B=0.3）
    R, RIM, FR, _ = runoff(36.0, 80.0, prm)
    print(f"算例验证: R={R:.2f} mm (课件值 16.4), FR={FR:.3f} (课件值 0.45)")
