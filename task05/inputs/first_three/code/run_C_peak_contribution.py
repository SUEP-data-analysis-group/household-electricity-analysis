# -*- coding: utf-8 -*-
"""Task05 第三步：峰时贡献 + 四个案例（按 task04 字节承接，不重选日期）

输出：
  out/C_peak_contribution.csv          小时峰 363 个区间 × 13 台逐行明细 + 分钟峰明细
  out/C_peak_summary.csv               两种汇总口径：等权典型峰时占比 / 峰时段累计能量占比
  out/C_case_peak.csv                  四案例的峰小时与分钟峰贡献
  out/C_reconcile.json                 机读核验
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
T4 = INP / "task04"
OUT = BASE / "out"
OUT.mkdir(parents=True, exist_ok=True)
TZ = "Asia/Shanghai"

panel_def = json.loads((T1 / "panel_definition.json").read_text(encoding="utf-8"))
dev13 = {p["panel_id"]: p["devices"] for p in panel_def["panels"]}["panel13"]

hp = pd.read_csv(D2 / "hourly_panel13.csv")
hp["timestamp"] = pd.to_datetime(hp["timestamp"], utc=True)
hp["hour_complete"] = hp["hour_complete"].astype(str).str.lower().map({"true": True, "false": False})
ha = pd.read_csv(D2 / "hourly_appliance.csv")
ha["timestamp"] = pd.to_datetime(ha["timestamp"], utc=True)
ha["hour_complete"] = ha["hour_complete"].astype(str).str.lower().map({"true": True, "false": False})

power = pd.read_csv(STD / "power_minute.csv.gz")
power["timestamp"] = pd.to_datetime(power["timestamp"], utc=True)
power = power.set_index("timestamp").sort_index()
panel = pd.read_csv(STD / "panel_minute.csv.gz")
panel["timestamp"] = pd.to_datetime(panel["timestamp"], utc=True)
p13 = panel[panel["panel_id"] == "panel13"].set_index("timestamp").sort_index()
p13["panel_complete"] = p13["panel_complete"].astype(str).str.lower().map({"true": True, "false": False})

ext = pd.read_csv(T4 / "daily_extrema_times.csv")
ext["date"] = pd.to_datetime(ext["date"], utc=True)
ext["hour_start"] = pd.to_datetime(ext["hour_start"], utc=True)
peaks = ext[ext["kind"] == "peak"].copy()
assert len(peaks) == 363, len(peaks)

manifest = pd.read_csv(T4 / "case_manifest.csv")
case_ids = manifest["case_id"].tolist()


def hour_block(ts):
    """返回该小时的 {设备kWh, 面板kWh, 是否13台完整}"""
    hrow = hp[hp["timestamp"] == ts]
    if len(hrow) == 0 or not bool(hrow["hour_complete"].iloc[0]):
        return None, None, False
    e_panel = float(hrow["energy_kwh"].iloc[0])
    sub = ha[(ha["timestamp"] == ts)]
    sub = sub[sub["appliance_id"].isin(dev13)]
    ok = len(sub) == 13 and bool(sub["hour_complete"].all()) and sub["energy_kwh"].notna().all()
    vals = sub.set_index("appliance_id")["energy_kwh"].reindex(dev13)
    return vals.astype(float).to_dict(), e_panel, ok


# ---------- 小时峰逐区间明细 ----------
rows = []
ok_hours = 0
mismatch = []
for _, r in peaks.iterrows():
    ts = r["hour_start"]
    v, e_panel, ok = hour_block(ts)
    if not ok:
        mismatch.append(ts.isoformat())
        continue
    ok_hours += 1
    sum_dev = sum(v.values())
    if abs(sum_dev - e_panel) > 1e-6:
        mismatch.append(ts.isoformat() + " sum!=panel")
    for d in dev13:
        rows.append(dict(level="hour_peak", date=r["date"].tz_convert(TZ).strftime("%Y-%m-%d"),
                         timestamp=ts.tz_convert(TZ).strftime("%Y-%m-%d %H:%M"),
                         hour=r["hour"], appliance_id=d, value_kw=v[d], panel_kw=e_panel,
                         share=v[d] / e_panel if e_panel else np.nan,
                         tied_count=int(r["tied_count"]), weight=float(r["weight"]),
                         case_id=""))

peak_hour_df = pd.DataFrame(rows)
assert ok_hours == 363, ok_hours

# ---------- 两种汇总口径 ----------
# 口径1：逐日先按 1/tied_count 等权，再跨天等权平均（典型峰时设备占比）
day_share = (peak_hour_df.assign(w_share=lambda x: x["share"] * x["weight"])
             .groupby(["date", "appliance_id"])[["w_share", "weight"]].sum().reset_index())
day_share["w_share"] /= day_share["weight"]
typical = day_share.groupby("appliance_id")["w_share"].mean()

# 口径2：峰时段累计能量占比（分母为能量加权）
peak_energy = peak_hour_df.groupby("appliance_id")[["value_kw", "panel_kw"]].sum()
peak_energy["share_energy_weighted"] = peak_energy["value_kw"] / peak_energy["panel_kw"]

summary = pd.DataFrame({
    "appliance_id": dev13,
    "typical_peak_share_equal_weight": [typical.get(d, np.nan) for d in dev13],
    "peak_period_energy_share": [peak_energy.loc[d, "share_energy_weighted"] for d in dev13],
    "peak_period_energy_kwh": [peak_energy.loc[d, "value_kw"] for d in dev13],
})
summary["n_peak_hours"] = 363
summary["n_days"] = peak_hour_df["date"].nunique()
summary.to_csv(OUT / "C_peak_summary.csv", index=False, encoding="utf-8-sig")

# ---------- 分钟峰（四案例） ----------
def minute_block(ts):
    if ts not in power.index:
        return None, None
    prow = p13.loc[[ts]] if ts in p13.index else None
    if prow is None or not bool(prow["panel_complete"].iloc[0]):
        return None, None
    vals = power.loc[ts, dev13].astype(float)
    return vals.to_dict(), float(prow["panel_power_w"].iloc[0])


case_rows = []
case_hour_rows = []
for _, c in manifest.iterrows():
    cid = c["case_id"]
    minute_ts = [pd.Timestamp(x, tz="UTC") if pd.Timestamp(x).tzinfo is None
                 else pd.Timestamp(x).tz_convert("UTC") for x in json.loads(c["minute_record_peak_times"])]
    peak_hours = [pd.Timestamp(x).tz_convert("UTC") for x in json.loads(c["peak_hour_starts"])]
    for ts in minute_ts:
        v, e_panel = minute_block(ts)
        if v is None:
            continue
        for d in dev13:
            case_rows.append(dict(level="minute_peak", case_id=cid,
                                  date=c["date"], timestamp=ts.tz_convert(TZ).strftime("%Y-%m-%d %H:%M"),
                                  appliance_id=d, value_w=v[d], panel_w=e_panel,
                                  share=v[d] / e_panel if e_panel else np.nan, tied_count=1, weight=1.0))
    for ts in peak_hours:
        v, e_panel, ok = hour_block(ts)
        if not ok:
            continue
        for d in dev13:
            case_hour_rows.append(dict(level="case_hour_peak", case_id=cid, date=c["date"],
                                       timestamp=ts.tz_convert(TZ).strftime("%Y-%m-%d %H:%M"),
                                       appliance_id=d, value_kw=v[d], panel_kw=e_panel,
                                       share=v[d] / e_panel if e_panel else np.nan,
                                       tied_count=None, weight=1.0))

case_df = pd.DataFrame(case_rows + case_hour_rows)
case_df.to_csv(OUT / "C_case_peak.csv", index=False, encoding="utf-8-sig")

# 分钟峰明细并入主表
minute_peak_df = pd.DataFrame(case_rows)
minute_peak_df = minute_peak_df.rename(columns={"value_w": "value_kw", "panel_w": "panel_kw"})
minute_peak_df["value_kw"] = minute_peak_df["value_kw"] / 1000.0
minute_peak_df["panel_kw"] = minute_peak_df["panel_kw"] / 1000.0

all_peak = pd.concat([peak_hour_df, minute_peak_df], ignore_index=True, sort=False)
all_peak.to_csv(OUT / "C_peak_contribution.csv", index=False, encoding="utf-8-sig")

# ---------- 核验 ----------
checks = {
    "peak_hours_363_inherited": len(peaks) == 363,
    "peak_hours_all_13_complete": ok_hours == 363,
    "peak_hours_sum_dev_eq_panel": len(mismatch) == 0,
    "weights_sum_to_1_per_day": bool(abs(peaks.groupby("date")["weight"].sum() - 1.0).max() < 1e-9),
    "days_covered_352": int(peak_hour_df["date"].nunique()) == 352,
    "typical_share_sum_eq_1": bool(abs(summary["typical_peak_share_equal_weight"].sum() - 1.0) < 1e-9),
    "energy_weighted_share_sum_eq_1": bool(abs(summary["peak_period_energy_share"].sum() - 1.0) < 1e-9),
    "cases_4_inherited": len(case_ids) == 4 and case_ids == ["C01", "C02", "C03", "C04"],
    "minute_peak_rows_4cases": int(minute_peak_df["case_id"].nunique()) == 4,
    "minute_peak_share_sum_eq_1_per_case": bool(
        abs(minute_peak_df.groupby("case_id")["share"].sum() - 1.0).max() < 1e-9),
}

recon = {
    "node": "C(step3)",
    "generated_by": "run_C_peak_contribution.py",
    "input_task04_files": {
        "daily_extrema_times.csv": int(len(ext)),
        "peak_rows": int(len(peaks)),
        "tied_days": int(peaks.groupby("date").size().gt(1).sum()),
        "max_tied_count": int(peaks["tied_count"].max()),
        "case_manifest.csv": case_ids,
    },
    "peak_hours_used": ok_hours,
    "mismatch": mismatch[:10],
    "weights_rule": "逐日 1/tied_count 等权后再跨天等权平均；与能量加权口径分列",
    "checks": checks,
    "all_pass": all(checks.values()),
}
(OUT / "C_reconcile.json").write_text(json.dumps(recon, ensure_ascii=False, indent=2), encoding="utf-8")

print("峰小时区间：%d，全部13台完整：%d" % (len(peaks), ok_hours))
print("并列峰日数：%d" % int(peaks.groupby("date").size().gt(1).sum()))
print("\n两种峰时口径：")
print(summary.sort_values("peak_period_energy_share", ascending=False).to_string(index=False))
print("\n四案例分钟峰：")
print(minute_peak_df[minute_peak_df["appliance_id"].isin(dev13)]
      .sort_values(["case_id", "share"], ascending=[True, False])
      .groupby("case_id").head(4)[["case_id", "date", "timestamp", "appliance_id", "share"]].to_string(index=False))
print("\nchecks:", json.dumps(checks, ensure_ascii=False))
print("all_pass =", recon["all_pass"])

