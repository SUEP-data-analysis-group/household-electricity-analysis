# -*- coding: utf-8 -*-
"""Task05 前三步 —— B 节点：三种分母的贡献主表 + 数值对账

输出：
  out/B_contribution_panel13.csv            主结果(352完整日) + 补充结果(510284分钟)
  out/B_contribution_panel14_supplement.csv 14台独立补充
  out/B_hour_reconcile.csv                  8448 小时键逐设备对账摘要
  out/B_reconcile.json                      机读核验
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
INP = BASE / "inputs"
STD = INP / "standardized"
D2 = INP / "task02"
T1 = INP / "task01"
OUT = BASE / "out"
OUT.mkdir(parents=True, exist_ok=True)

DATA_VERSION = "cn_obee_v1_noimpute_v1.0.0"
PANEL_VERSION = "v1.0.0"
START = pd.Timestamp("2021-05-31 00:00:00+08:00")
END = pd.Timestamp("2022-06-01 00:00:00+08:00")
TZ = "Asia/Shanghai"
TOL_ABS = 1e-6      # kWh
TOL_SHARE = 1e-9    # 占比合计

panel_def = json.loads((T1 / "panel_definition.json").read_text(encoding="utf-8"))
dev_by_panel = {p["panel_id"]: p["devices"] for p in panel_def["panels"]}
dev13 = dev_by_panel["panel13"]
dev14 = dev_by_panel["panel14"]

panel = pd.read_csv(STD / "panel_minute.csv.gz")
panel["timestamp"] = pd.to_datetime(panel["timestamp"], utc=True)
power = pd.read_csv(STD / "power_minute.csv.gz")
power["timestamp"] = pd.to_datetime(power["timestamp"], utc=True)
panel = panel[(panel["timestamp"] >= START) & (panel["timestamp"] < END)].copy()
power = power[(power["timestamp"] >= START) & (power["timestamp"] < END)].copy()
panel["panel_complete"] = panel["panel_complete"].astype(str).str.lower().map({"true": True, "false": False})
panel["local_date"] = panel["timestamp"].dt.tz_convert(TZ).dt.date
power = power.set_index("timestamp").sort_index()

p13 = panel[panel["panel_id"] == "panel13"].sort_values("timestamp").reset_index(drop=True)
p14 = panel[panel["panel_id"] == "panel14"].sort_values("timestamp").reset_index(drop=True)

daily = pd.read_csv(D2 / "daily_panel13.csv")
daily["t"] = pd.to_datetime(daily["date"], utc=True)
daily["day"] = daily["t"].dt.tz_convert(TZ).dt.date
complete_days = set(daily.loc[daily["day_complete"] == True, "day"])

m_main = p13["panel_complete"].to_numpy() & p13["local_date"].isin(complete_days).to_numpy()
m13 = p13["panel_complete"].to_numpy()
m14 = p14["panel_complete"].to_numpy()

# 14 台严格完整日（独立于 panel13 的日集合）
c14 = p14.loc[m14, ["timestamp", "local_date"]]
c14_counts = c14.groupby("local_date").size()
days14 = set(c14_counts[c14_counts == 1440].index)
m14_days = m14 & p14["local_date"].isin(days14).to_numpy()


def energies(mask_vec, ts, devices, panel_w):
    """返回 (设备能量dict, 面板能量, 设备缺失值数)"""
    idx = ts.to_numpy()[mask_vec]
    sub = power.loc[idx]
    out = {}
    for d in devices:
        col = sub[d]
        out[d] = float(col.sum(skipna=True) / 60000.0)
    e_panel = float(panel_w[mask_vec].sum() / 60000.0)
    nulls = {d: int(sub[d].isna().sum()) for d in devices}
    return out, e_panel, nulls, len(idx)


rows13 = []
recon = {}

# ---------- 主结果：352 完整日 ----------
e_main, ep_main, null_main, n_main = energies(m_main, p13["timestamp"], dev13, p13["panel_power_w"].to_numpy())
share_main = {d: (e_main[d] / ep_main if ep_main else np.nan) for d in dev13}
for d in dev13:
    rows13.append(dict(sample_scope="panel13_complete_352d", panel_id="panel13", panel_version=PANEL_VERSION,
                       appliance_id=d, energy_kwh=round(e_main[d], 9), denominator_kwh=round(ep_main, 9),
                       share=round(share_main[d], 9), minutes=n_main, n_days=352,
                       data_version=DATA_VERSION, role="主结果", denominator_note="352完整日×1440=506880分钟"))

# 面板自身也落一行，便于 sum 校验
rows13.append(dict(sample_scope="panel13_complete_352d", panel_id="panel13", panel_version=PANEL_VERSION,
                   appliance_id="__panel13__", energy_kwh=round(ep_main, 9), denominator_kwh=round(ep_main, 9),
                   share=1.0, minutes=n_main, n_days=352, data_version=DATA_VERSION, role="面板合计",
                   denominator_note="13台分项之和的目标值"))

# ---------- 补充结果：全期共同有效 510284 分钟 ----------
e_sup, ep_sup, null_sup, n_sup = energies(m13, p13["timestamp"], dev13, p13["panel_power_w"].to_numpy())
share_sup = {d: (e_sup[d] / ep_sup if ep_sup else np.nan) for d in dev13}
for d in dev13:
    rows13.append(dict(sample_scope="panel13_all_common_valid", panel_id="panel13", panel_version=PANEL_VERSION,
                       appliance_id=d, energy_kwh=round(e_sup[d], 9), denominator_kwh=round(ep_sup, 9),
                       share=round(share_sup[d], 9), minutes=n_sup, n_days=len(complete_days),
                       data_version=DATA_VERSION, role="补充结果",
                       denominator_note="全期共同有效分钟，勿与主结果混用"))
rows13.append(dict(sample_scope="panel13_all_common_valid", panel_id="panel13", panel_version=PANEL_VERSION,
                   appliance_id="__panel13__", energy_kwh=round(ep_sup, 9), denominator_kwh=round(ep_sup, 9),
                   share=1.0, minutes=n_sup, n_days=len(complete_days), data_version=DATA_VERSION,
                   role="面板合计", denominator_note="补充范围目标值"))

cont13 = pd.DataFrame(rows13)
cont13.to_csv(OUT / "B_contribution_panel13.csv", index=False, encoding="utf-8-sig")

# ---------- panel14 独立补充 ----------
rows14 = []
def panel14_block(mask_vec, scope, note):
    e, ep, nulls, n = energies(mask_vec, p14["timestamp"], dev14, p14["panel_power_w"].to_numpy())
    # 同一 14 台有效集合内重算 13 台参考
    e13ref = {}
    ts = p14["timestamp"].to_numpy()[mask_vec]
    sub = power.loc[ts]
    for d in dev13:
        e13ref[d] = float(sub[d].sum(skipna=True) / 60000.0)
    for d in dev14:
        rows14.append(dict(sample_scope=scope, panel_id="panel14", panel_version=PANEL_VERSION, appliance_id=d,
                           energy_kwh=round(e[d], 9), denominator_kwh=round(ep, 9),
                           share=round(e[d] / ep, 9) if ep else np.nan, minutes=n,
                           n_days=len(days14) if scope.endswith("148d") else len(days14),
                           data_version=DATA_VERSION,
                           role="14台补充" if d not in e13ref else "14台补充(13台成员)",
                           denominator_note=note))
        rows14.append(dict(sample_scope=scope, panel_id="panel14_same_set_ref13", panel_version=PANEL_VERSION,
                           appliance_id=d, energy_kwh=round(e13ref[d], 9) if d in e13ref else np.nan,
                           denominator_kwh=round(sum(e13ref.values()), 9) if d in e13ref else np.nan,
                           share=round(e13ref[d] / sum(e13ref.values()), 9) if d in e13ref and sum(e13ref.values()) else np.nan,
                           minutes=n, n_days=len(days14), data_version=DATA_VERSION,
                           role="同集合13台参考（不可与352日主排名直接比较比例变化）",
                           denominator_note=note))
    rows14.append(dict(sample_scope=scope, panel_id="panel14", panel_version=PANEL_VERSION, appliance_id="__panel14__",
                       energy_kwh=round(ep, 9), denominator_kwh=round(ep, 9), share=1.0, minutes=n,
                       n_days=len(days14), data_version=DATA_VERSION, role="面板合计",
                       denominator_note=note))
    return e, ep, e13ref, n

e14all, ep14all, ref13_all, n14all = panel14_block(m14, "panel14_all_common_valid", "217643个共同有效分钟，止于2021-11-09 18:38")
e14d, ep14d, ref13_d, n14d = panel14_block(m14_days, "panel14_complete_148d", "148个严格完整日×1440")
cont14 = pd.DataFrame(rows14)
cont14.to_csv(OUT / "B_contribution_panel14_supplement.csv", index=False, encoding="utf-8-sig")

# ---------- 8448 小时键对账 ----------
ha = pd.read_csv(D2 / "hourly_appliance.csv")
ha["timestamp"] = pd.to_datetime(ha["timestamp"], utc=True)
ha["hour_complete"] = ha["hour_complete"].astype(str).str.lower().map({"true": True, "false": False})
main_hours = set(p13.loc[m_main, "timestamp"].dt.floor("h").unique())
ha_main = ha[(ha["timestamp"].isin(main_hours)) & (ha["hour_complete"] == True)]

hour_rows = []
for d in dev13:
    sub = ha_main[ha_main["appliance_id"] == d]
    e_hour = float(sub["energy_kwh"].sum())
    e_min = e_main[d]
    hour_rows.append(dict(appliance_id=d, hour_keys=int(sub["timestamp"].nunique()), rows=int(len(sub)),
                          energy_from_hourly_kwh=round(e_hour, 9), energy_from_minute_kwh=round(e_min, 9),
                          abs_diff_kwh=abs(e_hour - e_min), rel_diff=abs(e_hour - e_min) / e_min if e_min else np.nan))
hour_df = pd.DataFrame(hour_rows)
hour_df.to_csv(OUT / "B_hour_reconcile.csv", index=False, encoding="utf-8-sig")

# ---------- 与 task02 完整日合计对账 ----------
task02_day_total = float(daily.loc[daily["day_complete"] == True, "energy_kwh"].sum())

sum_dev_main = sum(e_main.values())
sum_share_main = sum(share_main.values())
sum_dev_sup = sum(e_sup.values())
sum_share_sup = sum(share_sup.values())
sum_dev14 = sum(e14all.values())
sum_dev14d = sum(e14d.values())

checks = {
    "main_minutes_506880": n_main == 506880,
    "main_device_null_values": sum(null_main.values()) == 0,
    "main_sum_devices_eq_panel_abs_le_1e-6": abs(sum_dev_main - ep_main) <= TOL_ABS,
    "main_share_sum_eq_1_le_1e-9": abs(sum_share_main - 1.0) <= TOL_SHARE,
    "main_panel_matches_task02_day_total_le_1e-6": abs(ep_main - task02_day_total) <= TOL_ABS,
    "supp_minutes_510284": n_sup == 510284,
    "supp_sum_devices_eq_panel_abs_le_1e-6": abs(sum_dev_sup - ep_sup) <= TOL_ABS,
    "supp_share_sum_eq_1_le_1e-9": abs(sum_share_sup - 1.0) <= TOL_SHARE,
    "panel14_minutes_217643": n14all == 217643,
    "panel14_sum_devices_eq_panel_le_1e-6": abs(sum_dev14 - ep14all) <= TOL_ABS,
    "panel14_148d_minutes_213120": (n14d == 213120),
    "panel14_148d_sum_le_1e-6": abs(sum_dev14d - ep14d) <= TOL_ABS,
    "hour_keys_8448": len(main_hours) == 8448,
    "hour_reconcile_rows_109824": len(ha_main) == 109824,
    "hour_vs_minute_max_abs_diff_le_1e-6": bool(hour_df["abs_diff_kwh"].max() <= 1e-6),
    "separate_denominators": True,  # 主/补充/panel14 各自独立分母，已在表中分 scope 标注
}

recon = {
    "node": "B",
    "generated_by": "run_B_contribution.py",
    "tolerances": {"abs_kwh": TOL_ABS, "share_sum": TOL_SHARE},
    "main_scope": {
        "sample_scope": "panel13_complete_352d",
        "minutes": n_main, "days": 352,
        "panel_energy_kwh": ep_main,
        "sum_device_energy_kwh": sum_dev_main,
        "diff_kwh": sum_dev_main - ep_main,
        "task02_complete_day_total_kwh": task02_day_total,
        "share_sum": sum_share_main,
    },
    "supplement_scope": {
        "sample_scope": "panel13_all_common_valid",
        "minutes": n_sup,
        "panel_energy_kwh": ep_sup,
        "sum_device_energy_kwh": sum_dev_sup,
        "diff_kwh": sum_dev_sup - ep_sup,
        "share_sum": sum_share_sup,
    },
    "panel14": {
        "all_common_valid": {"minutes": n14all, "panel_energy_kwh": ep14all, "sum_device_kwh": sum_dev14,
                             "last_common_valid": p14.loc[m14, "timestamp"].max().tz_convert(TZ).strftime("%Y-%m-%d %H:%M")},
        "complete_148d": {"minutes": n14d, "days": len(days14), "panel_energy_kwh": ep14d, "sum_device_kwh": sum_dev14d},
    },
    "hourly_reconcile": {"hour_keys": len(main_hours), "rows": int(len(ha_main)),
                         "max_abs_diff_kwh": float(hour_df["abs_diff_kwh"].max()),
                         "worst_appliance": str(hour_df.loc[hour_df["abs_diff_kwh"].idxmax(), "appliance_id"])},
    "checks": checks,
    "all_pass": all(checks.values()),
}
(OUT / "B_reconcile.json").write_text(json.dumps(recon, ensure_ascii=False, indent=2), encoding="utf-8")

print("=== 主结果 352 完整日 ===")
print("面板电量 %.6f kWh；分项之和 %.6f kWh；差 %.3e；task02 日合计 %.6f kWh" %
      (ep_main, sum_dev_main, sum_dev_main - ep_main, task02_day_total))
print("占比合计 %.9f" % sum_share_main)
print("\n=== 补充 510284 分钟 ===")
print("面板电量 %.6f kWh；分项之和 %.6f kWh；占比合计 %.9f" % (ep_sup, sum_dev_sup, sum_share_sup))
print("\n=== panel14 ===")
print("全期 %d 分钟 %.6f kWh；148完整日 %d 分钟 %.6f kWh" % (n14all, ep14all, n14d, ep14d))
print("\n=== 8448 小时键对账 ===")
print(hour_df.to_string(index=False))
print("\nchecks:", json.dumps(checks, ensure_ascii=False))
print("all_pass =", recon["all_pass"])

print("\n=== 主结果 13 台排名 ===")
print(cont13[cont13["sample_scope"] == "panel13_complete_352d"]
      .query("appliance_id != '__panel13__'")
      .sort_values("energy_kwh", ascending=False)
      [["appliance_id", "energy_kwh", "share"]].to_string(index=False))

