"""任务二独立核验脚本。

用途：用与 run_task02.py 不同的计算路径（pandas resample + 直接从原始分钟表出发），
重算小时/日电量与完整性，再与三份东西对照：
  1) data/derived/task02/ 下本次产出的派生表
  2) task01/reports/strict_hourly_check.csv、strict_daily_check.csv（任务一的独立核验结果）
  3) 原始 power_minute.csv.gz 的设备列（检查 13 台分项之和能否还原面板电量）

只读不写派生表，唯一输出是 reports/verify_task02.txt。
运行：python task02/verify_task02.py
"""
from __future__ import annotations

import gzip
import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

TASK_DIR = Path(__file__).resolve().parent
REPO = TASK_DIR.parent
CFG = json.loads((TASK_DIR / "config.json").read_text(encoding="utf-8"))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--source-root", type=Path, default=REPO,
                    help="包含标准分钟表和 task01 核验表的项目根目录")
ARGS = parser.parse_args()
SOURCE_ROOT = ARGS.source_root.resolve()

DATA = SOURCE_ROOT / "data" / "standardized" / CFG["data_version"]
DERIVED = REPO / CFG["derive_dir"]
T01 = SOURCE_ROOT / "task01" / "reports"
OUT = TASK_DIR / "reports" / "verify_task02.txt"

PANEL = CFG["panel_id"]
TZ = CFG["timezone"]
def _ts(x: str) -> pd.Timestamp:
    t = pd.Timestamp(x)
    return t.tz_localize(TZ) if t.tzinfo is None else t.tz_convert(TZ)


START = _ts(CFG["analysis_start"])
END = _ts(CFG["analysis_end_exclusive"])
DIV = float(CFG["w_per_minute_to_kwh_divisor"])
MPH = int(CFG["minutes_per_hour"])
HPD = int(CFG["hours_per_day"])

lines: list[str] = []
fails: list[str] = []


def say(msg: str = "") -> None:
    lines.append(msg)
    print(msg)


def check(name: str, ok: bool, detail: str) -> None:
    say(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    if not ok:
        fails.append(name)


def close(a, b):
    return np.allclose(np.asarray(a, dtype=float), np.asarray(b, dtype=float),
                       atol=1e-9, rtol=1e-10, equal_nan=True)


say("=" * 78)
say(f"任务二独立核验  {datetime.now():%Y-%m-%d %H:%M:%S}")
say(f"数据版本 {CFG['data_version']}  面板 {PANEL}/{CFG['panel_version']}")
say(f"区间 [{START}, {END})")
say("=" * 78)

# ---------------------------------------------------------------- 1. 原始分钟表
say("\n[1] 从 panel_minute.csv.gz 重新出发（不读任何派生表）")
pm = pd.read_csv(
    DATA / "panel_minute.csv.gz",
    usecols=["timestamp", "panel_id", "panel_complete", "panel_power_w"],
    compression="gzip",
)
pm = pm[pm["panel_id"] == PANEL].copy()
pm["ts"] = pd.to_datetime(pm["timestamp"], utc=True).dt.tz_convert(TZ)
pm = pm[(pm["ts"] >= START) & (pm["ts"] < END)].sort_values("ts").reset_index(drop=True)
say(f"  窗口内分钟行数 {len(pm)}（期望 527040）")
check("分钟行数", len(pm) == 527040, f"{len(pm)} 行")

valid = pm["panel_complete"].fillna(False).astype(bool) & pm["panel_power_w"].notna()
pm["kwh"] = np.where(valid, pm["panel_power_w"] / DIV, np.nan)
pm = pm.set_index("ts")

say(f"  有效分钟 {int(valid.sum())}，不可用 {int((~valid).sum())} "
    f"({(~valid).mean() * 100:.2f}%)")

# ------------------------------------------------- 2. resample 重算（与主程序不同路径）
say("\n[2] 用 resample 重算小时（主程序用的是 floor + groupby，两者独立）")
hour_energy = pm["kwh"].resample(f"{MPH}min", label="left", closed="left").sum(min_count=1)
hour_valid = pm["kwh"].notna().resample(f"{MPH}min", label="left", closed="left").sum()
hour_complete = hour_valid == MPH
say(f"  重算小时槽 {len(hour_energy)}，完整小时 {int(hour_complete.sum())}")

# ---------------------------------------------------------------- 3. 对照派生表
say("\n[3] 与本次产出 hourly_panel13.csv 对照")
h = pd.read_csv(DERIVED / "hourly_panel13.csv")
h["timestamp"] = pd.to_datetime(h["timestamp"], utc=True).dt.tz_convert(TZ)
h = h.set_index("timestamp").sort_index()
check("小时行数", len(h) == len(hour_energy), f"派生 {len(h)} / 重算 {len(hour_energy)}")
check("完整小时数", int(h["hour_complete"].sum()) == int(hour_complete.sum()),
      f"派生 {int(h['hour_complete'].sum())} / 重算 {int(hour_complete.sum())}")

mine = hour_complete.reindex(h.index)
check("逐小时完整标记一致", bool((mine.values == h["hour_complete"].values).all()),
      "逐行比对 8784 个槽")

d_energy = (hour_energy.reindex(h.index) - h["valid_duration_energy_kwh"]).abs().max()
check("逐小时有效时长电量差", float(d_energy) < 1e-9, f"最大绝对差 {float(d_energy):.3e} kWh")
d_umin = (hour_valid.reindex(h.index) - h["usable_minutes"]).abs().max()
check("逐小时有效分钟数", float(d_umin) == 0, f"最大差 {float(d_umin):.0f} 分钟")
check("完整小时目标与空值位置", close(h.energy_kwh, hour_energy.where(hour_complete)), "不完整小时严格电量为空")
check("严格小时平均负荷", close(h.mean_power_kw, hour_energy.where(hour_complete)), "完整小时 kW 与 1h 电量数值相等；其余为空")
check("不完整小时平均负荷掩码", h.loc[~h.hour_complete, "mean_power_kw"].isna().all(),
      f"{int((~h.hour_complete).sum())} 个不完整小时均为空")
observed = hour_energy / (hour_valid / MPH).replace(0, np.nan)
check("有效片段诊断均值", close(h.observed_duration_mean_power_kw, observed),
      "部分小时均值只保存在 observed_duration_mean_power_kw")
check("全缺失小时不写零", h.loc[h.usable_minutes.eq(0), "valid_duration_energy_kwh"].isna().all(),
      "NaN 位置单独核验")

# -------------------------------------------------------- 4. 对照任务一核验表
say("\n[4] 与 task01/reports 的独立核验表对照")
t1h = pd.read_csv(T01 / "strict_hourly_check.csv")
t1h["timestamp"] = pd.to_datetime(t1h["timestamp"], utc=True).dt.tz_convert(TZ)
t1h = t1h[t1h["panel_id"] == PANEL].set_index("timestamp").sort_index()

check("完整小时数 vs task01", int(t1h["hour_complete"].sum()) == int(hour_complete.sum()),
      f"task01 {int(t1h['hour_complete'].sum())} / 重算 {int(hour_complete.sum())}")
check("完整标记逐行 vs task01",
      bool((t1h["hour_complete"].reindex(h.index).values == h["hour_complete"].values).all()),
      f"{int(h.hour_complete.sum())} 个 True + {int((~h.hour_complete).sum())} 个 False 逐行一致")
cmp = (t1h["valid_duration_energy_kwh"].reindex(h.index) - h["valid_duration_energy_kwh"]).abs()
check("逐小时电量 vs task01", float(cmp.max()) < 1e-12, f"最大绝对差 {float(cmp.max()):.3e} kWh")
check("严格负荷及空值 vs task01", close(h.mean_power_kw, t1h.mean_power_kw.reindex(h.index)), "逐行核验含 NaN")

t1d = pd.read_csv(T01 / "strict_daily_check.csv")
t1d["date"] = pd.to_datetime(t1d["date"], utc=True).dt.tz_convert(TZ)
t1d = t1d[t1d["panel_id"] == PANEL].set_index("date").sort_index()

# ------------------------------------------------------------- 5. 重算自然日
say("\n[5] 用小时结果重算自然日（24/24 严格判完整）")
day_energy = hour_energy.resample("1D", label="left", closed="left").sum(min_count=1)
day_complete_hours = hour_complete.resample("1D", label="left", closed="left").sum()
day_complete = day_complete_hours == HPD
say(f"  自然日 {len(day_energy)}，完整日 {int(day_complete.sum())}")

d = pd.read_csv(DERIVED / "daily_panel13.csv")
d["date"] = pd.to_datetime(d["date"], utc=True).dt.tz_convert(TZ)
d = d.set_index("date").sort_index()
check("自然日行数", len(d) == len(day_energy), f"派生 {len(d)} / 重算 {len(day_energy)}")
check("完整日数", int(d["day_complete"].sum()) == int(day_complete.sum()),
      f"派生 {int(d['day_complete'].sum())} / 重算 {int(day_complete.sum())}")
check("完整日数 vs task01", int(t1d["day_complete"].sum()) == int(day_complete.sum()),
      f"task01 {int(t1d['day_complete'].sum())} / 重算 {int(day_complete.sum())}")
check("逐日完整标记一致",
      bool((day_complete.reindex(d.index).values == d["day_complete"].values).all()),
      "366 天逐行比对")
d_energy_day = (day_energy.reindex(d.index) - d["valid_duration_energy_kwh"]).abs().max()
check("逐日电量", float(d_energy_day) < 1e-9, f"最大绝对差 {float(d_energy_day):.3e} kWh")
check("逐日电量 vs task01",
      float((t1d["valid_duration_energy_kwh"].reindex(d.index) - d["valid_duration_energy_kwh"]).abs().max()) < 1e-9,
      "与 task01 日表逐日一致")
check("严格日电量空值及负荷", close(d.energy_kwh, day_energy.where(day_complete))
      and close(d.mean_power_kw, day_energy.where(day_complete) / HPD), "完整日/不完整日全部位置")

total = float(d.loc[d["day_complete"], "energy_kwh"].sum())
mean = float(d.loc[d["day_complete"], "energy_kwh"].mean())
median = float(d.loc[d["day_complete"], "energy_kwh"].median())
peak_day = d.loc[d["day_complete"], "energy_kwh"].idxmax()
low_day = d.loc[d["day_complete"], "energy_kwh"].idxmin()
say(f"  完整日合计 {total:.2f} kWh，日均 {mean:.4f}，中位 {median:.4f}")
say(f"  最高 {peak_day:%Y-%m-%d} {d.loc[peak_day, 'energy_kwh']:.4f} kWh；"
    f"最低 {low_day:%Y-%m-%d} {d.loc[low_day, 'energy_kwh']:.4f} kWh")

# ------------------------------------------------- 6. 典型曲线独立重算
say("\n[6] 24 小时典型曲线独立重算")
ok_days = d.index[d["day_complete"]]
day_flag = pd.Series(d["day_complete"].values, index=d.index)
keep_hour = hour_complete & day_flag.reindex(hour_complete.index.normalize()).values
prof = hour_energy[keep_hour].groupby(hour_energy[keep_hour].index.hour).mean()
tp = pd.read_csv(DERIVED / "typical_hourly_profile.csv").set_index("hour")
gap = (prof - tp["mean_kwh"]).abs().max()
check("典型曲线逐时均值", float(gap) < 1e-9, f"最大绝对差 {float(gap):.3e} kWh")
say(f"  重算峰值 {int(prof.idxmax())} 时 {prof.max():.4f} kWh；"
    f"谷值 {int(prof.idxmin())} 时 {prof.min():.4f} kWh；参与天数 {len(ok_days)}")

# ------------------------------------------------- 7. 分项可加性抽查
say("\n[7] 分项可加性抽查（原始 power_minute 的设备列，不走面板汇总列）")
pw = pd.read_csv(DATA / "power_minute.csv.gz", compression="gzip")
pw["ts"] = pd.to_datetime(pw["timestamp"], utc=True).dt.tz_convert(TZ)
pw = pw[(pw["ts"] >= START) & (pw["ts"] < END)].set_index("ts")
app_cols = [c for c in pw.columns if c.endswith("_w") and c != "rice_cooker_w"]
say(f"  panel13 口径设备列 {len(app_cols)} 个：{', '.join(c.rstrip('_w') for c in app_cols)}")
check("设备列数量", len(app_cols) == 13, f"{len(app_cols)} 列")

done = h.index[h["hour_complete"]]
picks = [done[0], done[len(done) // 4], done[len(done) // 2], done[3 * len(done) // 4], done[-1]]
worst = 0.0
for ts in picks:
    seg = pw.loc[ts:ts + pd.Timedelta(hours=1) - pd.Timedelta(minutes=1), app_cols]
    seg = seg.dropna(how="all")
    s = float(np.nansum(seg.values)) / DIV
    e = float(h.loc[ts, "valid_duration_energy_kwh"])
    worst = max(worst, abs(s - e))
    say(f"    {ts:%Y-%m-%d %H:%M}  分项和 {s:.6f}  面板 {e:.6f}  差 {abs(s - e):.2e}")
check("分项之和 vs 面板电量", worst < 1e-6, f"抽查 5 小时最大差 {worst:.2e} kWh")

# ------------------------------------------------- 8. 月度支持独立重算
say("\n[8] 月度支持独立重算")
ms = pd.read_csv(DERIVED / "monthly_support.csv")
# 先转成不带时区的本地日期再取月份，避免 to_period 的时区告警；月份归属按 Asia/Shanghai 本地日期
local_day = d.index.tz_localize(None)
cal = d.groupby(local_day.to_period("M")).size()
comp = d[d["day_complete"]].groupby(local_day[d["day_complete"].values].to_period("M")).size()
ms["ym"] = ms["year_month"]
bad = []
for _, row in ms.iterrows():
    p = pd.Period(row["ym"], freq="M")
    c_ok = int(comp.get(p, 0))
    if c_ok != int(row["complete_days"]):
        bad.append(f"{row['ym']} 派生 {int(row['complete_days'])} vs 重算 {c_ok}")
check("各月完整天数", not bad, "13 行逐月一致" if not bad else "; ".join(bad))
full_months = ms["complete_month_energy_kwh"].notna().sum()
check("可发布完整月电量月数", int(full_months) == 10, f"{int(full_months)} 个完整月")
say(f"  不完整月：{', '.join(ms.loc[ms['complete_month_energy_kwh'].isna(), 'ym'])}（只给完整日均值）")

# ------------------------------------------------- 9. 周统计独立重算
say("\n[9] 周统计独立重算（周一起始，7/7 完整日）")
wks = pd.read_csv(DERIVED / "weekly_support.csv")
wk_src = pd.DataFrame({
    "c": d["day_complete"].astype(int).to_numpy(),
    "e": d["valid_duration_energy_kwh"].to_numpy(),
}, index=local_day.to_period("W-SUN"))
wk_g = wk_src.groupby(level=0)
calc = pd.DataFrame({
    "cal": wk_g.size(),
    "comp": wk_g["c"].sum(),
    "e": wk_g["e"].sum(min_count=1),
})
calc["ok"] = (calc["cal"] == 7) & (calc["comp"] == 7)
check("周数", len(calc) == len(wks), f"派生 {len(wks)} / 重算 {len(calc)}")
check("完整周数", int(calc["ok"].sum()) == int(wks["week_complete"].sum()),
      f"派生 {int(wks['week_complete'].sum())} / 重算 {int(calc['ok'].sum())}")
wk_e = float(np.nanmax(np.abs(calc["e"].where(calc["ok"]).to_numpy()
                            - wks["week_energy_kwh"].to_numpy())))
check("各完整周电量", wk_e < 1e-9, f"最大绝对差 {wk_e:.3e} kWh")
say(f"  完整周合计 {float(wks['week_energy_kwh'].sum()):.1f} kWh，"
    f"周均 {float(wks['week_energy_kwh'].mean()):.1f} kWh")

# ------------------------------------------------- 补充：月/季节曲线、全量分项与版本清单
say("\n[补充] 分组曲线与全量分项核验")
complete_samples = hour_energy.loc[keep_hour].to_frame("energy_kwh")
complete_samples["hour"] = complete_samples.index.hour
season_map = {m: name for name, months in {"spring": [3, 4, 5], "summer": [6, 7, 8],
              "autumn": [9, 10, 11], "winter": [12, 1, 2]}.items() for m in months}
complete_samples["year_month"] = complete_samples.index.strftime("%Y-%m")
complete_samples["season_period"] = [f"{t.year - (t.month <= 2)}_{season_map[t.month]}" for t in complete_samples.index]
for field, filename, expected_rows in [("year_month", "monthly_typical_hourly_profile.csv", 312),
                                       ("season_period", "seasonal_typical_hourly_profile.csv", 120)]:
    delivered = pd.read_csv(DERIVED / filename, float_precision="round_trip")
    expected = complete_samples.groupby([field, "hour"]).energy_kwh.agg(
        n_days="size", mean_kwh="mean", median_kwh="median", min_kwh="min", max_kwh="max")
    expected["p25_kwh"] = complete_samples.groupby([field, "hour"]).energy_kwh.quantile(.25)
    expected["p75_kwh"] = complete_samples.groupby([field, "hour"]).energy_kwh.quantile(.75)
    actual = delivered.set_index([field, "hour"]).sort_index()
    check(filename + " 完整网格", len(actual) == expected_rows and actual.index.equals(expected.index),
          f"{expected_rows} 行；年月份/季节时期不合并边界")
    check(filename + " 数值与分位数", all(close(actual[c], expected[c]) for c in expected.columns),
          "均值、中位数、分位数、极值和样本数逐行一致")
    check(filename + " 固定日期集合", delivered.groupby(field).n_days.nunique().eq(1).all()
          and delivered.drop_duplicates(field).n_days.sum() == len(ok_days), "每期 24 小时使用同一组完整日")

devices = [c for c in pw.columns if c.endswith("_w") and c != "rice_cooker_w"]
app = pd.read_csv(DERIVED / "hourly_appliance.csv", float_precision="round_trip")
app["timestamp"] = pd.to_datetime(app.timestamp, utc=True).dt.tz_convert(TZ)
check("全部分项记录完整", len(app) == len(h)*13 and set(app.appliance_id) == set(devices),
      f"{len(app)} 条，13 台设备")
for device in devices:
    expected_count = pw[device].resample("h").count()
    expected_value = (pw[device] / DIV).resample("h").sum(min_count=1)
    actual = app.loc[app.appliance_id.eq(device)].set_index("timestamp").sort_index()
    check("分项全量 " + device, actual.index.equals(h.index)
          and close(actual.usable_minutes, expected_count)
          and close(actual.valid_duration_energy_kwh, expected_value)
          and close(actual.energy_kwh, expected_value.where(expected_count.eq(MPH))),
          "8784 小时，含空值位置")

manifest = json.loads((DERIVED / "derivation_manifest.json").read_text(encoding="utf-8"))


def manifest_path(raw: str) -> Path:
    """Resolve archived source locations against the current task01 checkout."""
    normalized = raw.replace("\\", "/")
    # Keep original absolute paths in the provenance record, but use the selected
    # source root for verification after a clone or move to another computer.
    for prefix in ("data/standardized/", "task01/reports/"):
        start = normalized.find(prefix)
        if start >= 0 and (start == 0 or normalized[start - 1] == "/"):
            return SOURCE_ROOT / normalized[start:]
    path = Path(raw)
    return path if path.is_absolute() else REPO / path


for record in manifest["inputs"] + manifest["output_files"]:
    path = manifest_path(record["path"])
    with path.open("rb") as stream:
        hasher = hashlib.sha256()
        for block in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(block)
        actual_hash = hasher.hexdigest()
    check("清单校验 " + path.name, actual_hash == record["sha256"], "SHA-256 一致")
check("六张图均存在", len(list((TASK_DIR / "reports/figures").glob("*.png"))) == 6, "总体、月度及季节曲线均已生成")

# ------------------------------------------------- 10. 完整性小结
say("\n[10] 结论")
say(f"  完整小时 {int(hour_complete.sum())}；完整日 {int(day_complete.sum())}；"
    f"完整日合计 {total:.2f} kWh")
if fails:
    say(f"  存在 {len(fails)} 项未通过：{', '.join(fails)}")
else:
    say("  全部核验项通过（ALL PASS）")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"\n报告已写入 {OUT}")
sys.exit(1 if fails else 0)
