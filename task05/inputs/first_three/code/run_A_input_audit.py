# -*- coding: utf-8 -*-
"""Task05 前三步 —— A 节点：输入锁定与样本集合（可复现脚本）

输出：
  out/A_input_inventory.csv        输入清单（路径/版本/SHA-256/行数/字节）
  out/A_sample_support.csv         样本支持表（scope / 分钟数 / 日数 / 首末时刻）
  out/A_sample_day_list_panel13.csv 主完整日逐日名单
  out/A_time_axis_check.csv        三个应展示时间点的逐分钟证据
  out/A_audit.json                 机读核验结果
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[1]      # 交付包根目录，直接运行即可
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


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def rows_of(path):
    if path.suffix == ".gz":
        with __import__("gzip").open(path, "rt", encoding="utf-8") as f:
            return sum(1 for _ in f) - 1
    with open(path, "r", encoding="utf-8", newline="") as f:
        return sum(1 for _ in f) - 1


# ---------- 1. 输入清单 ----------
inputs = [
    (STD / "panel_minute.csv.gz", "task01 固定面板分钟功率与联合完整性", "分钟级功率/完整性", "面板 min 与分项求和"),
    (STD / "power_minute.csv.gz", "task01 分设备分钟功率（无插补）", "分钟级功率", "每台设备分子"),
    (T1 / "panel_definition.json", "task01 面板设备名单", "设备名单/版本", "13台/14台具体ID"),
    (D2 / "daily_panel13.csv", "task02 日级支持表", "日完整性", "352 完整日集合"),
    (D2 / "hourly_appliance.csv", "task02 分设备小时电量", "小时级电量", "峰时/小时对账"),
    (D2 / "hourly_panel13.csv", "task02 面板小时电量", "小时级电量", "8448 小时键对账"),
]

inv = []
for path, role, level, use in inputs:
    inv.append({
        "file": path.name,
        "role": role,
        "granularity": level,
        "used_for": use,
        "abs_path": str(path),
        "data_version": DATA_VERSION,
        "bytes": path.stat().st_size,
        "rows": rows_of(path),
        "sha256": sha256_of(path),
    })
inv_df = pd.DataFrame(inv)
inv_df.to_csv(OUT / "A_input_inventory.csv", index=False, encoding="utf-8-sig")
print("输入清单：")
print(inv_df[["file", "rows", "bytes", "sha256"]].to_string(index=False))

# ---------- 2. 读取面板与设备功率 ----------
panel_def = json.loads((T1 / "panel_definition.json").read_text(encoding="utf-8"))
dev13 = None
dev14 = None
for p in panel_def["panels"]:
    if p["panel_id"] == "panel13":
        dev13 = p["devices"]
    if p["panel_id"] == "panel14":
        dev14 = p["devices"]
assert dev13 and dev14 and len(dev13) == 13 and len(dev14) == 14 and set(dev13) <= set(dev14)

panel = pd.read_csv(STD / "panel_minute.csv.gz")
panel["timestamp"] = pd.to_datetime(panel["timestamp"], utc=True)
power = pd.read_csv(STD / "power_minute.csv.gz")
power["timestamp"] = pd.to_datetime(power["timestamp"], utc=True)

# 主区间左闭右开，剔除末端单条 2022-06-01 00:00
panel = panel[(panel["timestamp"] >= START) & (panel["timestamp"] < END)].copy()
power = power[(power["timestamp"] >= START) & (power["timestamp"] < END)].copy()

for c in ["panel_complete", "source_present"]:
    src = panel if c == "panel_complete" else power
    if src[c].dtype != bool:
        src[c] = src[c].astype(str).str.strip().str.lower().map({"true": True, "false": False})

panel["local_date"] = panel["timestamp"].dt.tz_convert(TZ).dt.date
p13 = panel[panel["panel_id"] == "panel13"].sort_values("timestamp").reset_index(drop=True)
p14 = panel[panel["panel_id"] == "panel14"].sort_values("timestamp").reset_index(drop=True)
assert len(p13) == 527040, len(p13)
assert p13["timestamp"].is_unique and p14["timestamp"].is_unique
assert power["timestamp"].is_unique and len(power) == 527040

# ---------- 3. 三个样本集合 ----------
# 3.1 主集合：task02 day_complete=True 的 352 个严格完整日
daily = pd.read_csv(D2 / "daily_panel13.csv")
daily["date"] = pd.to_datetime(daily["date"], utc=True).dt.tz_convert(TZ)
daily["day"] = daily["date"].dt.date
complete_days = sorted(daily.loc[daily["day_complete"] == True, "day"].tolist())
assert len(complete_days) == 352, len(complete_days)

m_main = p13["panel_complete"].to_numpy() & p13["local_date"].isin(complete_days).to_numpy()
n_main = int(m_main.sum())
assert n_main == 506880, n_main

# 3.2 panel13 全期共同有效分钟
m13_all = p13["panel_complete"].to_numpy()
n13_all = int(m13_all.sum())
assert n13_all == 510284, n13_all

# 3.3 panel14
m14_all = p14["panel_complete"].to_numpy()
n14_all = int(m14_all.sum())
assert n14_all == 217643, n14_all
p14_days = p14.loc[m14_all, ["timestamp", "local_date"]].copy()
n_minutes_per_day = p14_days.groupby("local_date").size()
days14_complete = sorted(n_minutes_per_day[n_minutes_per_day == 1440].index.tolist())
assert len(days14_complete) == 148, len(days14_complete)
last14 = p14.loc[m14_all, "timestamp"].max()

# 3.4 缺测与排除原因
excluded_13 = int((~m13_all).sum())
excluded_main = int((~m_main).sum())
partial_days = sorted(set(p13.loc[~p13["local_date"].isin(complete_days), "local_date"].tolist()))

def local(ts):
    return pd.Timestamp(ts).tz_convert(TZ).strftime("%Y-%m-%d %H:%M:%S+08:00")


valid_inside_excluded = int((m13_all & ~m_main).sum())

support = [
    {
        "sample_scope": "panel13_complete_352d",
        "panel_id": "panel13",
        "panel_version": PANEL_VERSION,
        "devices": len(dev13),
        "n_samples": n_main,
        "n_units": 352,
        "unit": "严格完整日(每24完整小时)",
        "first": local(p13.loc[m_main, "timestamp"].min()),
        "last": local(p13.loc[m_main, "timestamp"].max()),
        "excluded_minutes": excluded_main,
        "excluded_minutes_note": "%d 个不完整日的全部分钟；其中仍有效的 %d 个不进入主分母" % (len(partial_days), valid_inside_excluded),
        "definition": "task02 daily_panel13.day_complete=True 的352日，逐分钟内panel_complete=True",
        "role": "主结果分母",
    },
    {
        "sample_scope": "panel13_all_common_valid",
        "panel_id": "panel13",
        "panel_version": PANEL_VERSION,
        "devices": len(dev13),
        "n_samples": n13_all,
        "n_units": len(partial_days),
        "unit": "全期共同有效分钟(含 %d 个不完整日内的有效分钟)" % (valid_inside_excluded,),
        "first": local(p13.loc[m13_all, "timestamp"].min()),
        "last": local(p13.loc[m13_all, "timestamp"].max()),
        "excluded_minutes": excluded_13,
        "excluded_minutes_note": "整段内非共同有效分钟，不补0不外推",
        "definition": "panel_complete=True 的全部分钟，另命名 sample_scope，不沿用上一种集合分母",
        "role": "补充结果分母（不与主结果混用）",
    },
    {
        "sample_scope": "panel14_all_common_valid",
        "panel_id": "panel14",
        "panel_version": PANEL_VERSION,
        "devices": len(dev14),
        "n_samples": n14_all,
        "n_units": len(days14_complete),
        "unit": "全期共同有效分钟 + %d 个严格完整日（两种口径分别声明）" % (len(days14_complete),),
        "first": local(p14.loc[m14_all, "timestamp"].min()),
        "last": local(last14),
        "excluded_minutes": int((~m14_all).sum()),
        "excluded_minutes_note": "14台共同有效止于 %s，之后到期末全部无效" % (local(last14),),
        "definition": "14台同时可用的分钟，独立分母，不借用 panel13",
        "role": "独立补充面板",
    },
]
sup_df = pd.DataFrame(support)
sup_df.to_csv(OUT / "A_sample_support.csv", index=False, encoding="utf-8-sig")
print("\n样本支持表：")
print(sup_df[["sample_scope", "n_samples", "n_units", "first", "last", "excluded_minutes"]].to_string(index=False))
# 主完整日逐日名单
day_list = pd.DataFrame({"date": [d.isoformat() for d in complete_days],
                         "is_complete": True})
day_list["task02_energy_kwh"] = daily.set_index("day").loc[complete_days, "energy_kwh"].to_numpy()
day_list.to_csv(OUT / "A_sample_day_list_panel13.csv", index=False, encoding="utf-8-sig")

# ---------- 4. 三个应展示的时间点 ----------
def minute_probe(ts_str):
    ts = pd.Timestamp(ts_str).tz_convert("UTC")
    prow = p13.loc[p13["timestamp"] == ts]
    powr = power.loc[power["timestamp"] == ts]
    sum13 = float(powr[dev13].sum(axis=1).iloc[0]) if len(powr) else np.nan
    return {
        "timestamp": ts_str,
        "panel_complete": bool(prow["panel_complete"].iloc[0]) if len(prow) else None,
        "panel_power_w": float(prow["panel_power_w"].iloc[0]) if len(prow) else np.nan,
        "sum13_w": sum13,
        "abs_diff_w": abs(sum13 - float(prow["panel_power_w"].iloc[0])) if len(prow) else np.nan,
        "n_device_null": int(powr[dev13].isna().sum().sum()) if len(powr) else None,
    }


hour_probe_rows = []
for label, h in [("正常完整小时", "2021-05-31 00:00:00+08:00"),
                 ("部分缺测小时", "2021-06-01 13:00:00+08:00"),
                 ("跨午夜峰小时", "2021-07-12 23:00:00+08:00")]:
    hr = pd.Timestamp(h)
    hstart = hr.tz_convert("UTC")
    hend = hstart + pd.Timedelta(hours=1)
    seg = p13[(p13["timestamp"] >= hstart) & (p13["timestamp"] < hend)]
    mp = minute_probe(h)
    mp["label"] = label
    mp["hour_label"] = h
    mp["interval"] = "[%s, %s)" % (hr.strftime("%Y-%m-%d %H:%M"), (hr + pd.Timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"))
    mp["valid_minutes_in_hour"] = int(seg["panel_complete"].sum())
    mp["rows_in_hour"] = int(len(seg))
    hdf = pd.read_csv(D2 / "hourly_panel13.csv")
    hdf["timestamp"] = pd.to_datetime(hdf["timestamp"], utc=True)
    hrow = hdf[hdf["timestamp"] == hstart]
    mp["task02_hour_complete"] = bool(hrow["hour_complete"].iloc[0]) if len(hrow) else None
    mp["task02_energy_kwh"] = float(hrow["energy_kwh"].iloc[0]) if len(hrow) and pd.notna(hrow["energy_kwh"].iloc[0]) else np.nan
    mp["task02_valid_duration_energy_kwh"] = float(hrow["valid_duration_energy_kwh"].iloc[0]) if len(hrow) else np.nan
    hour_probe_rows.append(mp)

demo_df = pd.DataFrame(hour_probe_rows)
demo_df.to_csv(OUT / "A_time_axis_check.csv", index=False, encoding="utf-8-sig")
print("\n时间轴抽检：")
print(demo_df[["label", "hour_label", "interval", "valid_minutes_in_hour", "task02_hour_complete",
               "task02_energy_kwh", "task02_valid_duration_energy_kwh"]].to_string(index=False))

# ---------- 5. A 节点机读核验 ----------
audit = {
    "node": "A",
    "generated_by": "run_A_input_audit.py",
    "main_period": "[2021-05-31 00:00, 2022-06-01 00:00) Asia/Shanghai",
    "rows_in_period": int(len(p13)),
    "panel13_common_valid_minutes": n13_all,
    "panel13_complete_days": len(complete_days),
    "panel13_complete_days_minutes": n_main,
    "panel14_common_valid_minutes": n14_all,
    "panel14_complete_days": len(days14_complete),
    "panel14_last_common_valid": last14.isoformat(),
    "devices_panel13": dev13,
    "devices_panel14_only": sorted(set(dev14) - set(dev13)),
    "checks": {
        "period_minutes_527040": len(p13) == 527040,
        "main_minutes_506880": n_main == 506880,
        "panel13_valid_510284": n13_all == 510284,
        "panel14_valid_217643": n14_all == 217643,
        "panel14_days_148": len(days14_complete) == 148,
        "timestamp_unique": bool(p13["timestamp"].is_unique and power["timestamp"].is_unique),
        "no_end_leak": bool((p13["timestamp"] < END).all()),
        "device_list_13_and_14": len(dev13) == 13 and len(dev14) == 14,
    },
    "all_pass": all([len(p13) == 527040, n_main == 506880, n13_all == 510284,
                     n14_all == 217643, len(days14_complete) == 148]),
}
(OUT / "A_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
print("\nA 节点核验：" + json.dumps(audit["checks"], ensure_ascii=False))
print("all_pass =", audit["all_pass"])

