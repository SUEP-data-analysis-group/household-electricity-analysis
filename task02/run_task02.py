"""task02 按小时和日期统计用电量（严格版，不插补、不跨缺口积分）。

Usage (from project root):
    python task02/run_task02.py
    python task02/run_task02.py --skip-appliance   # 跳过逐设备小时表，速度更快

规则（与 task02/README.md 一致）：
  * 分析区间 [2021-05-31 00:00, 2022-06-01 00:00)，文件末端 2022-06-01 00:00 单条排除。
  * 有效分钟 = panel_complete 为真且 panel_power_w 非空；每有效分钟贡献 P_W/60000 kWh。
  * 小时完整 = 该自然小时 60/60 分钟有效；日完整 = 24/24 个完整小时。
  * 缺口不进积分：不按相邻有效点的时间间隔延长样本，不按覆盖率放大。
  * energy_kwh 只在完整时段有值；不完整时段保留 valid_duration_energy_kwh 与覆盖度。
"""

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT
CONFIG_PATH = Path(__file__).with_name("config.json")
C = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

VERSION = C["data_version"]
TZ = C["timezone"]
PANEL_ID = C["panel_id"]
STD = ROOT / "data/standardized" / VERSION
DERIVE = ROOT / C["derive_dir"]
REPORTS = ROOT / "task02" / "reports"
FIGS = REPORTS / "figures"
DIVISOR = C["w_per_minute_to_kwh_divisor"]
MPH = C["minutes_per_hour"]
HPD = C["hours_per_day"]

START = pd.Timestamp(C["analysis_start"]).tz_convert(TZ)
END = pd.Timestamp(C["analysis_end_exclusive"]).tz_convert(TZ)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def recorded_path(path):
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_panel():
    df = pd.read_csv(STD / "panel_minute.csv.gz")
    df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.tz_convert(TZ)
    df = df.loc[df["panel_id"].eq(PANEL_ID)].copy()
    df = df.set_index("timestamp").sort_index()
    df = df.loc[(df.index >= START) & (df.index < END)]
    if not df.index.is_unique:
        raise SystemExit("panel 分钟索引不唯一")
    valid = df["panel_complete"].fillna(False) & df["panel_power_w"].notna()
    return df, valid


def build_hourly(df: pd.DataFrame, valid: pd.Series) -> pd.DataFrame:
    lab = df.index.floor("h")
    en = df["panel_power_w"].where(valid) / DIVISOR
    usable = valid.astype("int64")

    # 用 to_numpy() 逐位对应，避免 pandas 按标签对齐把整点那一分钟的值广播到整小时
    hourly = pd.DataFrame({"usable": usable.to_numpy(), "en": en.to_numpy()}, index=lab)
    grouped = hourly.groupby(level=0)
    out = pd.DataFrame({
        "usable_minutes": grouped["usable"].sum(),
        "valid_duration_energy_kwh": grouped["en"].sum(min_count=1),
        "row_count": grouped["en"].size(),
    })

    full_hours = pd.date_range(START.floor("h"), (END - pd.Timedelta(minutes=1)).floor("h"), freq="h")
    out = out.reindex(full_hours)
    out["usable_minutes"] = out["usable_minutes"].fillna(0).astype("int64")
    out["row_count"] = out["row_count"].fillna(0).astype("int64")

    out["expected_minutes"] = MPH
    out["coverage"] = out["usable_minutes"] / MPH
    out["hour_complete"] = (out["usable_minutes"] == MPH) & (out["row_count"] == MPH)

    out["energy_kwh"] = out["valid_duration_energy_kwh"].where(out["hour_complete"])
    duration_h = out["usable_minutes"] / MPH
    out["observed_duration_mean_power_kw"] = out["valid_duration_energy_kwh"] / duration_h.replace(0, np.nan)
    # The main hourly target is defined only for a complete one-hour interval.
    out["mean_power_kw"] = out["energy_kwh"]

    out.index.name = "timestamp"
    return out


def build_daily(hourly: pd.DataFrame) -> pd.DataFrame:
    lab = hourly.index.floor("D")
    g = pd.DataFrame({
        "c": hourly["hour_complete"].astype("int64").to_numpy(),
        "u": hourly["usable_minutes"].to_numpy(),
        "e": hourly["valid_duration_energy_kwh"].to_numpy(),
    }, index=lab).groupby(level=0)

    daily = pd.DataFrame({
        "valid_hours": g["c"].sum(),
        "valid_minutes": g["u"].sum(),
        "valid_duration_energy_kwh": g["e"].sum(min_count=1),
    })
    full_days = pd.date_range(START.floor("D"), (END - pd.Timedelta(minutes=1)).floor("D"), freq="D")
    daily = daily.reindex(full_days)
    daily.index.name = "date"

    daily["expected_hours"] = HPD
    daily["day_complete"] = daily["valid_hours"] == HPD
    daily["coverage"] = daily["valid_minutes"] / (MPH * HPD)
    daily["energy_kwh"] = daily["valid_duration_energy_kwh"].where(daily["day_complete"])
    daily["mean_power_kw"] = daily["energy_kwh"] / HPD
    return daily


def build_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for month, part in daily.groupby(daily.index.tz_localize(None).to_period("M")):
        calendar_days = int(part.shape[0])
        # 文件边界是否覆盖整个自然月
        first, last = part.index.min(), part.index.max()
        boundary_complete = (first.day == 1) and (last + pd.Timedelta(days=1)).month != last.month
        complete_days = int(part["day_complete"].sum())
        month_complete = boundary_complete and complete_days == calendar_days and calendar_days == month.days_in_month
        rows.append({
            "year_month": str(month),
            "file_boundary_complete": bool(boundary_complete),
            "calendar_days": calendar_days,
            "complete_days": complete_days,
            "usable_minutes": int(part["valid_minutes"].sum()),
            "coverage": float(part["valid_minutes"].sum() / (calendar_days * MPH * HPD)),
            "complete_month_energy_kwh": float(part["energy_kwh"].sum()) if month_complete else np.nan,
            "complete_day_mean_energy_kwh": float(part.loc[part["day_complete"], "energy_kwh"].mean())
            if complete_days else np.nan,
        })
    return pd.DataFrame(rows)


def build_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """按自然周（周一至周日，W-SUN）汇总；周完整 = 7/7 个完整日，且窗口覆盖整 7 天。"""
    rows = []
    for _, part in daily.groupby(daily.index.tz_localize(None).to_period("W-SUN")):
        first, last = part.index.min(), part.index.max()
        calendar_days = int(part.shape[0])
        complete_days = int(part["day_complete"].sum())
        week_complete = calendar_days == 7 and complete_days == 7
        rows.append({
            "week_start": first.strftime("%Y-%m-%d"),
            "week_end": last.strftime("%Y-%m-%d"),
            "iso_week": f"{first.isocalendar()[0]}-W{first.isocalendar()[1]:02d}",
            "calendar_days": calendar_days,
            "complete_days": complete_days,
            "usable_minutes": int(part["valid_minutes"].sum()),
            "coverage": float(part["valid_minutes"].sum() / (calendar_days * MPH * HPD)),
            "week_complete": bool(week_complete),
            "week_energy_kwh": float(part["energy_kwh"].sum()) if week_complete else np.nan,
            "complete_day_mean_energy_kwh": float(part.loc[part["day_complete"], "energy_kwh"].mean())
            if complete_days else np.nan,
        })
    return pd.DataFrame(rows)


def build_typical(hourly: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    complete_days = daily.index[daily["day_complete"]]
    mask = hourly.index.floor("D").isin(complete_days)
    part = hourly.loc[mask & hourly["hour_complete"]].copy()
    part["hour"] = part.index.hour
    g = part.groupby("hour")["energy_kwh"]
    prof = pd.DataFrame({
        "n_days": g.size(),
        "mean_kwh": g.mean(),
        "median_kwh": g.median(),
        "p25_kwh": g.quantile(0.25),
        "p75_kwh": g.quantile(0.75),
        "min_kwh": g.min(),
        "max_kwh": g.max(),
    }).reindex(range(24))
    prof.index.name = "hour"
    return prof.reset_index()


def build_appliance_hourly():
    panel_def = json.loads((SOURCE_ROOT / "task01/reports/panel_definition.json").read_text(encoding="utf-8"))
    devices = next(p["devices"] for p in panel_def["panels"] if p["panel_id"] == PANEL_ID)

    frames = []
    full_hours = pd.date_range(START.floor("h"), (END - pd.Timedelta(minutes=1)).floor("h"), freq="h")
    for dev in devices:
        path = STD / "appliance_quality" / f"{dev}.csv.gz"
        if not path.is_file():
            raise FileNotFoundError(f"Missing required fixed-panel input: {path}")
        a = pd.read_csv(path, usecols=["timestamp", "is_usable", "usable_value"])
        a["timestamp"] = pd.to_datetime(a["timestamp"]).dt.tz_convert(TZ)
        a = a.set_index("timestamp").sort_index()
        a = a.loc[(a.index >= START) & (a.index < END)]
        usable = a["is_usable"].fillna(False).astype(bool)
        en = pd.to_numeric(a["usable_value"], errors="coerce").where(usable) / DIVISOR

        lab = a.index.floor("h")
        tmp = pd.DataFrame({"u": usable.to_numpy().astype("int64"), "e": en.to_numpy()},
                           index=lab).groupby(level=0)
        h = pd.DataFrame({
            "usable_minutes": tmp["u"].sum(),
            "valid_duration_energy_kwh": tmp["e"].sum(min_count=1),
        }).reindex(full_hours)
        h["usable_minutes"] = h["usable_minutes"].fillna(0).astype("int64")
        h["hour_complete"] = h["usable_minutes"] == MPH
        h["energy_kwh"] = h["valid_duration_energy_kwh"].where(h["hour_complete"])
        h["appliance_id"] = dev
        h["panel_id"] = PANEL_ID
        h.index.name = "timestamp"
        frames.append(h.reset_index())

    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)
    return out[["timestamp", "panel_id", "appliance_id", "usable_minutes", "hour_complete",
                "valid_duration_energy_kwh", "energy_kwh"]]


def season_labels(index):
    names = {3: "spring", 4: "spring", 5: "spring", 6: "summer", 7: "summer", 8: "summer",
             9: "autumn", 10: "autumn", 11: "autumn", 12: "winter", 1: "winter", 2: "winter"}
    return [f"{t.year - int(t.month in (1, 2))}_{names[t.month]}" for t in index]


def build_grouped_profiles(hourly, daily, grouping):
    """Each period uses the same complete-date cohort at all 24 hours."""
    good_days = daily.index[daily.day_complete]
    part = hourly.loc[hourly.index.normalize().isin(good_days)].copy()
    part["hour"] = part.index.hour
    part[grouping] = part.index.strftime("%Y-%m") if grouping == "year_month" else season_labels(part.index)
    day_labels = daily.index.strftime("%Y-%m") if grouping == "year_month" else season_labels(daily.index)
    calendar_counts = pd.Series(day_labels).value_counts()
    frames = []
    for label, period in part.groupby(grouping, sort=False):
        g = period.groupby("hour").energy_kwh
        f = pd.DataFrame(dict(n_days=g.size(), mean_kwh=g.mean(), median_kwh=g.median(),
            p25_kwh=g.quantile(.25), p75_kwh=g.quantile(.75), min_kwh=g.min(), max_kwh=g.max())).reindex(range(24))
        f.index.name = "hour"
        f = f.reset_index()
        f.insert(0, grouping, label)
        f["calendar_days_in_window"] = int(calendar_counts[label])
        f["sample_scope"] = "strict_complete_days_only"
        f["panel_id"] = PANEL_ID
        f["panel_version"] = C["panel_version"]
        f["data_version"] = VERSION
        frames.append(f)
    return pd.concat(frames, ignore_index=True)


def make_grouped_figure(profile, grouping, filename, columns):
    labels = profile[grouping].drop_duplicates().tolist()
    rows = int(np.ceil(len(labels) / columns))
    fig, axes = plt.subplots(rows, columns, figsize=(columns * 3.8, rows * 2.8), squeeze=False)
    for ax, label in zip(axes.flat, labels):
        f = profile.loc[profile[grouping].eq(label)]
        ax.fill_between(f.hour, f.p25_kwh, f.p75_kwh, color="#4C72B0", alpha=.16)
        ax.plot(f.hour, f.mean_kwh, color="#4C72B0", label="均值")
        ax.plot(f.hour, f.median_kwh, color="#55A868", linestyle="--", label="中位数")
        ax.set_title(f"{label}  n={int(f.n_days.iloc[0])} 天", fontsize=10)
        ax.set_xticks([0, 6, 12, 18, 23])
        ax.set_xlabel("小时")
        ax.set_ylabel("小时电量 (kWh)")
        ax.grid(alpha=.2)
    for ax in list(axes.flat)[len(labels):]:
        ax.set_visible(False)
    handles, legends = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, legends, loc="upper right", fontsize=9)
    fig.suptitle("各期典型曲线：固定完整日集合；阴影为 25–75 分位范围", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, .96))
    path = FIGS / filename
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def make_figures(hourly, daily, prof, monthly, monthly_prof, seasonal_prof):
    FIGS.mkdir(parents=True, exist_ok=True)
    made = []

    fig, ax = plt.subplots(figsize=(13, 4.2))
    ok = daily["day_complete"]
    ax.plot(daily.index, daily["energy_kwh"], lw=1.2, color="#4C72B0", label="完整日电量（缺测断线）")
    bad = daily.index[~ok]
    ax.scatter(bad, np.full(len(bad), daily.loc[ok, "energy_kwh"].min() * 0.9),
               marker="|", s=60, color="#C44E52", label=f"不完整日（{len(bad)} 天，不参与电量统计）")
    ax.axhline(daily.loc[ok, "energy_kwh"].mean(), ls="--", lw=1, color="#555555",
               label=f"完整日均值 {daily.loc[ok, 'energy_kwh'].mean():.2f} kWh")
    ax.set_title(f"{PANEL_ID} 逐日电量趋势（{ok.sum()} 个完整日）")
    ax.set_xlabel("日期")
    ax.set_ylabel("日电量 (kWh)")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    p = FIGS / "01_daily_energy_trend.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    made.append(p)

    mat = hourly["energy_kwh"].to_frame("energy_kwh")
    mat["date"] = mat.index.floor("D")
    mat["hour"] = mat.index.hour
    pivot = mat.pivot_table(index="date", columns="hour", values="energy_kwh", aggfunc="first")
    # pivot_table 会丢掉全为空的行，补回完整日历，保证缺测日以灰色占位而不是消失
    pivot = pivot.reindex(index=daily.index, columns=range(24))

    cmap = plt.get_cmap("YlOrRd").copy()
    cmap.set_bad("#B0B0B0")
    fig, ax = plt.subplots(figsize=(13, min(11, max(3.5, 0.03 * len(pivot)))))
    x = mdates.date2num(pivot.index.to_pydatetime())
    xe = np.concatenate([[x[0] - 0.5], x + 0.5])
    im = ax.pcolormesh(xe, np.arange(25), np.ma.masked_invalid(pivot.T.values),
                       cmap=cmap, shading="flat")
    ax.set_xlabel("日期")
    ax.set_ylabel("小时")
    ax.set_title(f"{PANEL_ID} 日期×小时电量热力图（灰=小时不完整，不按 0 处理）")
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    plt.setp(ax.get_xticklabels(), fontsize=8, rotation=0)
    ax.set_yticks([0, 6, 12, 18, 24])
    fig.colorbar(im, ax=ax, label="kWh")
    fig.tight_layout()
    p = FIGS / "02_date_hour_heatmap.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    made.append(p)

    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.fill_between(prof["hour"], prof["p25_kwh"], prof["p75_kwh"], color="#4C72B0", alpha=0.15,
                    label="25–75 分位")
    ax.plot(prof["hour"], prof["mean_kwh"], marker="o", color="#4C72B0", label="平均电量")
    ax.plot(prof["hour"], prof["median_kwh"], marker="s", ls="--", color="#55A868", label="中位电量")
    ax.set_xticks(range(24))
    ax.set_xlabel("小时")
    ax.set_ylabel("小时电量 (kWh)")
    ax.set_title(f"24 小时典型曲线（{int(prof['n_days'].max())} 个完整日）")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    p = FIGS / "03_typical_24h_curve.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    made.append(p)

    fig, ax = plt.subplots(figsize=(12, 3.8))
    x = np.arange(len(monthly))
    full = monthly["complete_month_energy_kwh"].notna()
    ax.bar(x[full], monthly.loc[full, "complete_month_energy_kwh"], color="#4C72B0", label="完整月电量（左轴）")
    ax.set_xticks(x)
    ax.set_xticklabels(monthly["year_month"], rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("月电量 (kWh)")
    ax.grid(alpha=0.25, axis="y")

    # 不完整月改在右轴画「完整日均值」，避免把日均值与月总量放在同一刻度上比较
    ax2 = ax.twinx()
    ax2.plot(x[~full], monthly.loc[~full, "complete_day_mean_energy_kwh"], marker="o", ls="none",
             color="#C44E52", label="不完整月的完整日均值（右轴，非全月电量）")
    ax2.set_ylabel("完整日均值 (kWh)")

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")
    ax.set_title(f"{PANEL_ID} 月度电量与样本支持")
    fig.tight_layout()
    p = FIGS / "04_monthly_support.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    made.append(p)
    made.append(make_grouped_figure(monthly_prof, "year_month", "05_monthly_typical_profiles.png", 4))
    made.append(make_grouped_figure(seasonal_prof, "season_period", "06_seasonal_typical_profiles.png", 3))
    return made


def verify(hourly, daily):
    checks = {}
    sh = pd.read_csv(SOURCE_ROOT / "task01/reports/strict_hourly_check.csv", float_precision="round_trip")
    sh = sh.loc[sh["panel_id"].eq(PANEL_ID)].copy()
    sh["timestamp"] = pd.to_datetime(sh["timestamp"]).dt.tz_convert(TZ)
    sh = sh.set_index("timestamp").sort_index()

    checks["hour_complete_mine"] = int(hourly["hour_complete"].sum())
    checks["hour_complete_task01"] = int(sh["hour_complete"].sum())
    checks["usable_minutes_match"] = bool(
        hourly["usable_minutes"].reindex(sh.index).fillna(0).astype("int64").equals(
            sh["usable_minutes"].astype("int64"))
    )

    sd = pd.read_csv(SOURCE_ROOT / "task01/reports/strict_daily_check.csv", float_precision="round_trip")
    sd = sd.loc[sd["panel_id"].eq(PANEL_ID)].copy()
    sd["date"] = pd.to_datetime(sd["date"]).dt.tz_convert(TZ)
    sd = sd.set_index("date").sort_index()
    checks["day_complete_mine"] = int(daily["day_complete"].sum())
    checks["day_complete_task01"] = int(sd["day_complete"].sum())

    j = hourly[["energy_kwh"]].join(sh[["energy_kwh"]], how="inner", rsuffix="_t01").dropna()
    diff = (j["energy_kwh"] - j["energy_kwh_t01"]).abs()
    checks["hour_energy_max_abs_diff"] = float(diff.max()) if len(diff) else None
    checks["hour_energy_compared"] = int(len(diff))
    checks["hour_index_matches"] = hourly.index.equals(sh.index)
    checks["day_index_matches"] = daily.index.equals(sd.index)
    checks["strict_mean_missing_on_incomplete_hours"] = bool(hourly.loc[~hourly.hour_complete, "mean_power_kw"].isna().all())
    checks["strict_mean_matches_task01"] = bool(np.allclose(hourly.mean_power_kw, sh.mean_power_kw,
        atol=1e-10, rtol=1e-10, equal_nan=True))
    checks["hour_energy_nan_mask_matches"] = bool(np.array_equal(hourly.energy_kwh.isna(), sh.energy_kwh.isna()))
    checks["day_energy_nan_mask_matches"] = bool(np.array_equal(daily.energy_kwh.isna(), sd.energy_kwh.isna()))

    checks["all_pass"] = bool(
        checks["hour_complete_mine"] == checks["hour_complete_task01"]
        and checks["day_complete_mine"] == checks["day_complete_task01"]
        and checks["usable_minutes_match"]
        and (checks["hour_energy_max_abs_diff"] or 0) < 1e-9
        and all(checks[k] for k in ["hour_index_matches", "day_index_matches",
            "strict_mean_missing_on_incomplete_hours", "strict_mean_matches_task01",
            "hour_energy_nan_mask_matches", "day_energy_nan_mask_matches"])
    )
    return checks


def write_report(hourly, daily, monthly, weekly, prof, checks, figs, path, monthly_prof, seasonal_prof):
    ok_h = int(hourly["hour_complete"].sum())
    ok_d = int(daily["day_complete"].sum())
    ok = daily["day_complete"]
    mean_d = daily.loc[ok, "energy_kwh"].mean()
    peak = prof.loc[prof["mean_kwh"].idxmax()]
    valley = prof.loc[prof["mean_kwh"].idxmin()]
    total = daily["energy_kwh"].sum()
    load_mean = daily.loc[ok, "mean_power_kw"].mean()
    load_max = daily.loc[ok, "mean_power_kw"].max()
    h8 = prof.loc[8, "mean_kwh"]
    h21 = prof.loc[21, "mean_kwh"]

    # 季节比较只用「完整月」，避免把 2021-05 的 1 天、2021-07 的 26 天与整月并列
    mfull = monthly.dropna(subset=["complete_month_energy_kwh"]).copy()
    mmean = monthly.dropna(subset=["complete_day_mean_energy_kwh"])
    hi_m = mfull.loc[mfull["complete_day_mean_energy_kwh"].idxmax()]
    lo_m = mfull.loc[mfull["complete_day_mean_energy_kwh"].idxmin()]
    part_jul = mmean[mmean["year_month"] == "2021-07"]

    hh = hourly.loc[hourly["hour_complete"]].copy()
    hh["month"] = hh.index.tz_localize(None).to_period("M").astype(str)
    hh["hour"] = hh.index.hour
    by_mh = hh.groupby(["month", "hour"])["energy_kwh"].mean()
    mpeak = {m: int(g.idxmax()[1]) for m, g in by_mh.groupby(level=0)}
    morning_m = [m for m in mfull["year_month"] if mpeak[m] == 8]
    evening_m = [m for m in mfull["year_month"] if mpeak[m] in (21, 22, 23)]
    wk_ok = weekly[weekly["week_complete"]]
    wk_bad = weekly[~weekly["week_complete"]]

    lines = [
        "# 任务二 结果报告",
        "",
        f"数据版本 `{VERSION}`；主面板 `{PANEL_ID}/{C['panel_version']}`；时区 `{TZ}`；功率 W。",
        f"分析区间 `[2021-05-31 00:00, 2022-06-01 00:00)`，366 个自然日、8784 个小时。",
        "",
        "## 口径",
        "",
        "- 计量含义：`panel_power_w` 为已由作者规则化的发布分钟功率，单位 **W**；"
        "采用左标签 60 s 矩形近似积分，该分钟电量 `= P_W / 60000` kWh。原发布序列含同分钟上报均值与作者前向保持，不等同于结算电表读数。",
        "- 有效分钟 = `panel_complete` 为真且 `panel_power_w` 非空；缺口不参与积分。",
        "- 小时完整 = 60/60 有效分钟；日完整 = 24/24 完整小时；周完整 = 7/7 完整日。缺口不积分、不延长、不按覆盖率放大。",
        "- `energy_kwh`（kWh）仅在完整时段给出；不完整时段只保留 `valid_duration_energy_kwh` 与覆盖度。",
        "- `mean_power_kw`（kW）仅对完整小时给出，数值等于该完整一小时的 energy_kwh；不完整小时为空。",
        "- `observed_duration_mean_power_kw` 仅表示有效分钟片段的均值，保留 4 个部分小时的诊断信息，不作为完整小时真实目标。日平均负荷为完整日电量 / 24h。",
        "",
        "## 结果",
        "",
        f"- 完整小时 **{ok_h}** 个（任务一核验表 {checks['hour_complete_task01']} 个）",
        f"- 完整日 **{ok_d}** 天（任务一核验表 {checks['day_complete_task01']} 天）",
        f"- 完整日合计电量 **{total:.2f} kWh**，日均 **{mean_d:.2f} kWh**，"
        f"中位 **{daily.loc[daily['day_complete'], 'energy_kwh'].median():.2f} kWh**",
        f"- 最高完整日 {daily.loc[daily['day_complete'], 'energy_kwh'].idxmax():%Y-%m-%d} "
        f"{daily['energy_kwh'].max():.2f} kWh；"
        f"最低完整日 {daily.loc[daily['day_complete'], 'energy_kwh'].idxmin():%Y-%m-%d} "
        f"{daily['energy_kwh'].min():.2f} kWh",
        f"- 24 小时典型曲线：最高小时 **{int(peak['hour'])} 时**（均值 {peak['mean_kwh']:.3f} kWh），"
        f"最低小时 **{int(valley['hour'])} 时**（均值 {valley['mean_kwh']:.3f} kWh）",
        f"- 日均负荷（`mean_power_kw`）：完整日均值 **{load_mean:.4f} kW**，最大 **{load_max:.4f} kW**；"
        f"{ok_d} 个完整日的电量合计为 {total:.2f} kWh；未包含 {len(daily) - ok_d} 个不完整日的完整电量，因此不报告全分析期间总电量。电量与负荷分别为能量和功率。",
        "",
        "## 各月样本支持",
        "",
        "| 月份 | 日历天 | 完整日 | 覆盖度 | 是否完整月 | 完整月电量 kWh | 完整日均值 kWh |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for _, r in monthly.iterrows():
        lines.append(
            f"| {r['year_month']} | {int(r['calendar_days'])} | {int(r['complete_days'])} | "
            f"{r['coverage']:.2%} | {'是' if pd.notna(r['complete_month_energy_kwh']) else '否'} | "
            f"{'' if pd.isna(r['complete_month_energy_kwh']) else format(r['complete_month_energy_kwh'], '.2f')} | "
            f"{'' if pd.isna(r['complete_day_mean_energy_kwh']) else format(r['complete_day_mean_energy_kwh'], '.2f')} |"
        )

    lines += [
        "",
        f"## 各周样本支持",
        "",
        f"- 完整周 **{len(wk_ok)}** 个（7/7 完整日），不完整周 **{len(wk_bad)}** 个；"
        f"完整周电量合计 **{wk_ok['week_energy_kwh'].sum():.1f} kWh**，"
        f"周均 {wk_ok['week_energy_kwh'].mean():.1f} kWh，"
        f"最高 {wk_ok['week_energy_kwh'].max():.1f} kWh、最低 {wk_ok['week_energy_kwh'].min():.1f} kWh",
        "",
        "| 周起始（周一） | 周结束 | ISO 周 | 完整日/日历天 | 周电量 kWh | 完整日均值 kWh | 是否完整周 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for _, r in weekly.iterrows():
        lines.append(
            f"| {r['week_start']} | {r['week_end']} | {r['iso_week']} | "
            f"{int(r['complete_days'])}/{int(r['calendar_days'])} | "
            f"{'' if pd.isna(r['week_energy_kwh']) else format(r['week_energy_kwh'], '.2f')} | "
            f"{'' if pd.isna(r['complete_day_mean_energy_kwh']) else format(r['complete_day_mean_energy_kwh'], '.2f')} | "
            f"{'是' if r['week_complete'] else '否'} |"
        )

    mm = mmean.set_index("year_month")["complete_day_mean_energy_kwh"]
    d1019 = prof.loc[10:19, "mean_kwh"]
    lines += [
        "",
        "## 形态与季节归纳",
        "",
        f"- **典型日内形态**：主峰在 **{int(peak['hour'])} 时**（{peak['mean_kwh']:.3f} kWh），"
        f"次峰在 **8 时**（{h8:.3f} kWh），白天 10–19 时基本平稳（{d1019.min():.2f}–{d1019.max():.2f} kWh），"
        f"谷值在 **{int(valley['hour'])} 时**（{valley['mean_kwh']:.3f} kWh）。"
        f"夜间 21–23 时明显抬升（{h21:.3f} / {peak['mean_kwh']:.3f} / {prof.loc[23, 'mean_kwh']:.3f} kWh），"
        "这些是监测面板的时段形态；具体设备贡献和住户起床时间需另用分项或行为证据验证。",
        f"- **季节变化**：只比较 10 个完整月。最高 **{hi_m['year_month']}**（{hi_m['complete_day_mean_energy_kwh']:.2f} kWh/天），"
        f"最低 **{lo_m['year_month']}**（{lo_m['complete_day_mean_energy_kwh']:.2f} kWh/天）。"
        f"8 月（{mm['2021-08']:.2f}）与 12 月（{mm['2021-12']:.2f}）构成夏、冬两个高平台，"
        f"3–5 月（{mm['2022-03']:.2f} / {mm['2022-04']:.2f} / {mm['2022-05']:.2f}）处于中间水平，"
        f"观测期完整日样本均值 {mean_d:.2f} kWh/天；各月负荷水平存在差异，具体设备和季节机制留待任务五分项验证。"
        + (f"（2021-07 只有 {int(part_jul['complete_days'].iloc[0])} 个完整日，"
           f"样本均值 {part_jul['complete_day_mean_energy_kwh'].iloc[0]:.2f} kWh/天，"
           "样本不足以代表整月，不与完整月并列比较。）" if len(part_jul) else ""),
        f"- **主峰时刻**：各完整月逐时均值最大值的落点为 "
        f"{'、'.join(f'{m[:4]} 年 {int(m[5:])} 月 {mpeak[m]} 时' for m in mfull['year_month'])}。"
        f"其中 {len(morning_m)} 个月（{'、'.join(str(int(m[5:])) for m in morning_m)} 月）最高点在早晨 8 时，"
        f"{len(evening_m)} 个月（{'、'.join(str(int(m[5:])) for m in evening_m)} 月）最高点在晚间 21–23 时，"
        f"耗电最低的 {lo_m['year_month'][:4]} 年 {int(lo_m['year_month'][5:])} 月曲线最平坦、最高点落在午后。"
        "典型曲线上早晨与晚间负荷的相对高度随月份变化；仅凭面板曲线不能判断住户作息是否整体位移。",
        "- **从图里读出、需要进一步比较的变化**：",
        "  1. 日电量在同一季节内部仍有明显高低起伏（热力图与趋势图上多段连续深色带），"
        "工作日与周末是否构成两套不同的用电方式，留给任务三检验；",
        "  2. 夏、冬两个高平台的形成原因需要分项证据，`data/derived/task02/hourly_appliance.csv` 已按 13 台设备逐小时备好；",
        "  3. 各月峰值高度差异明显（7 月中旬单周 147.8 kWh、2 月初单周 21.0 kWh），"
        "且最高点在早晨 8 时与晚间 21–23 时之间切换，说明「峰值变高」更像某一类负荷被放大而非作息整体后移，"
        "可在峰谷分析时用分项表确认是空调还是热水器驱动；",
        "  4. 2022-02 的低谷是否与假期外出有关，仅凭功率数据无法判定，需要外部作息信息。",
    ]

    lines += ["", "## 按月与季节的典型曲线", "",
        f"- monthly_typical_hourly_profile.csv 共 {len(monthly_prof)} 行，13 个年月份各 24 小时。",
        f"- seasonal_typical_hourly_profile.csv 共 {len(seasonal_prof)} 行，5 个季节时期各 24 小时。",
        "- 每期均值、中位数、25/75 分位数、最小/最大值和 n_days 使用同一批完整日。",
        "- 2021-05 只有 1 个完整日；2021 年夏季仅有 78 个完整日。两端春季分开；冬季以十二月所在年命名。分组曲线是样本描述，不补足缺测月份。", "",
        "| 时期 | 完整日样本数 |", "| --- | --- |"]
    for field, frame in [("year_month", monthly_prof), ("season_period", seasonal_prof)]:
        lines += [f"| {r[field]} | {int(r['n_days'])} |" for _, r in frame.drop_duplicates(field).iterrows()]

    bad_days = daily.index[~daily["day_complete"]]
    lines += [
        "",
        f"## 剔除与标记",
        "",
        f"- 不完整日 {len(bad_days)} 天：{', '.join(d.strftime('%Y-%m-%d') for d in bad_days[:20])}"
        f"{' …' if len(bad_days) > 20 else ''}",
        "- 这些日期保留在时间轴上，`day_complete=False`，电量留空，不当作低用电日，也不写 0。",
        "- 本次未启用短缺口估计版，新增插补 0。",
        "",
        "## 核验",
        "",
        f"```json\n{json.dumps(checks, ensure_ascii=False, indent=2)}\n```",
        "",
        "## 图",
        "",
    ] + [f"![{Path(p).stem}](figures/{Path(p).name})" for p in figs]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    global SOURCE_ROOT, STD
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-appliance", action="store_true", help="跳过逐设备小时表")
    ap.add_argument("--source-root", type=Path, default=ROOT,
                    help="包含 data/standardized 与 task01/reports 的项目根目录；输出仍在本成果包")
    args = ap.parse_args()
    SOURCE_ROOT = args.source_root.resolve()
    STD = SOURCE_ROOT / "data/standardized" / VERSION

    DERIVE.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    df, valid = load_panel()
    hourly = build_hourly(df, valid)
    daily = build_daily(hourly)
    monthly = build_monthly(daily)
    weekly = build_weekly(daily)
    prof = build_typical(hourly, daily)
    monthly_prof = build_grouped_profiles(hourly, daily, "year_month")
    seasonal_prof = build_grouped_profiles(hourly, daily, "season_period")

    h_out = pd.DataFrame({
        "timestamp": hourly.index.map(lambda t: t.isoformat()),
        "panel_id": PANEL_ID,
        "data_version": VERSION,
        "usable_minutes": hourly["usable_minutes"],
        "coverage": hourly["coverage"],
        "hour_complete": hourly["hour_complete"],
        "valid_duration_energy_kwh": hourly["valid_duration_energy_kwh"],
        "energy_kwh": hourly["energy_kwh"],
        "mean_power_kw": hourly["mean_power_kw"],
        "observed_duration_mean_power_kw": hourly["observed_duration_mean_power_kw"],
    })
    h_out.to_csv(DERIVE / "hourly_panel13.csv", index=False, encoding="utf-8")

    d_out = pd.DataFrame({
        "date": daily.index.map(lambda t: t.isoformat()),
        "panel_id": PANEL_ID,
        "valid_hours": daily["valid_hours"],
        "day_complete": daily["day_complete"],
        "coverage": daily["coverage"],
        "valid_duration_energy_kwh": daily["valid_duration_energy_kwh"],
        "energy_kwh": daily["energy_kwh"],
        "mean_power_kw": daily["mean_power_kw"],
    })
    d_out.to_csv(DERIVE / "daily_panel13.csv", index=False, encoding="utf-8")

    monthly.to_csv(DERIVE / "monthly_support.csv", index=False, encoding="utf-8")
    weekly.to_csv(DERIVE / "weekly_support.csv", index=False, encoding="utf-8")
    prof.to_csv(DERIVE / "typical_hourly_profile.csv", index=False, encoding="utf-8")
    monthly_prof.to_csv(DERIVE / "monthly_typical_hourly_profile.csv", index=False, encoding="utf-8")
    seasonal_prof.to_csv(DERIVE / "seasonal_typical_hourly_profile.csv", index=False, encoding="utf-8")

    appliance = None if args.skip_appliance else build_appliance_hourly()
    if appliance is not None:
        appliance["timestamp"] = appliance["timestamp"].map(lambda t: t.isoformat())
        appliance.to_csv(DERIVE / "hourly_appliance.csv", index=False, encoding="utf-8")

    figs = make_figures(hourly, daily, prof, monthly, monthly_prof, seasonal_prof)
    checks = verify(hourly, daily)
    if not checks["all_pass"]:
        raise AssertionError(f"Strict output checks failed: {checks}")
    write_report(hourly, daily, monthly, weekly, prof, checks, figs, REPORTS / "task02_report.md", monthly_prof, seasonal_prof)

    panel_definition = SOURCE_ROOT / "task01/reports/panel_definition.json"
    definitions = json.loads(panel_definition.read_text(encoding="utf-8"))
    devices = next(p["devices"] for p in definitions["panels"] if p["panel_id"] == PANEL_ID)
    inputs = [STD / "panel_minute.csv.gz", panel_definition,
              SOURCE_ROOT / "task01/reports/strict_hourly_check.csv",
              SOURCE_ROOT / "task01/reports/strict_daily_check.csv", CONFIG_PATH, Path(__file__)]
    if not args.skip_appliance:
        inputs += [STD / "appliance_quality" / f"{dev}.csv.gz" for dev in devices]
    manifest = {
        "task": "task02_hourly_daily_statistics",
        "derivation_version": C["derivation_version"],
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {"python": platform.python_version(), "pandas": pd.__version__,
                    "numpy": np.__version__, "matplotlib": matplotlib.__version__},
        "generated_rules": {
            "panel_id": PANEL_ID,
            "panel_version": C["panel_version"],
            "data_version": VERSION,
            "timezone": TZ,
            "analysis_start": C["analysis_start"],
            "analysis_end_exclusive": C["analysis_end_exclusive"],
            "minute_energy_rule": "usable minute contributes panel_power_w/60000 kWh (left-labelled 60 s rectangle)",
            "hour_rule": "hour_complete = 60/60 usable minutes",
            "day_rule": "day_complete = 24/24 complete hours",
            "mean_power_rule": "mean_power_kw is strict full-hour average; incomplete hours remain missing",
            "observed_duration_mean_rule": "diagnostic mean over usable minutes only; never a complete-hour target",
            "grouped_profile_rule": "same strict complete-date cohort at all 24 hours within each year_month/season_period",
            "season_rule": "Mar-May spring; Jun-Aug summer; Sep-Nov autumn; Dec-Feb winter named by December year; spring boundaries kept separate",
            "no_imputation": True,
            "no_gap_extension": True,
            "no_coverage_scaling": True,
            "excluded_terminal_row": "2022-06-01 00:00:00+08:00",
        },
        "inputs": [{"path": recorded_path(p), "sha256": sha256(p), "bytes": p.stat().st_size}
                   for p in inputs],
        "counts": {
            "minutes_in_window": int(len(df)),
            "usable_minutes": int(valid.sum()),
            "invalid_minutes": int((~valid).sum()),
            "hours": int(len(hourly)),
            "hour_complete": int(hourly["hour_complete"].sum()),
            "days": int(len(daily)),
            "day_complete": int(daily["day_complete"].sum()),
            "weeks": int(len(weekly)),
            "week_complete": int(weekly["week_complete"].sum()),
            "appliance_rows": int(0 if appliance is None else len(appliance)),
            "monthly_profile_rows": len(monthly_prof),
            "seasonal_profile_rows": len(seasonal_prof),
            "partial_hours_retained_as_diagnostic": int(((hourly.usable_minutes > 0) & ~hourly.hour_complete).sum()),
        },
        "verification": checks,
        "outputs": sorted(p.name for p in DERIVE.glob("*")),
        "output_files": [{"path": recorded_path(p), "sha256": sha256(p), "bytes": p.stat().st_size}
                         for p in sorted(list(DERIVE.glob("*.csv")) + [REPORTS / "task02_report.md"] + figs)],
    }
    (DERIVE / "derivation_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 60)
    print(f"panel      : {PANEL_ID} ({C['panel_version']})  data {VERSION}")
    print(f"分钟       : 窗口 {len(df)}  可用 {int(valid.sum())}  不可用 {int((~valid).sum())}")
    print(f"小时       : 总 {len(hourly)}  完整 {int(hourly['hour_complete'].sum())} "
          f"(task01 {checks['hour_complete_task01']})")
    print(f"日         : 总 {len(daily)}  完整 {int(daily['day_complete'].sum())} "
          f"(task01 {checks['day_complete_task01']})")
    print(f"周         : 总 {len(weekly)}  完整 {int(weekly['week_complete'].sum())}")
    print(f"核验       : all_pass={checks['all_pass']}  最大小时电量差={checks['hour_energy_max_abs_diff']}")
    print(f"输出       : {DERIVE}")
    for f in sorted(DERIVE.glob("*")):
        print(f"  {f.name}")
    for f in figs:
        print(f"  图 {f.name}")
    print("=" * 60)


if __name__ == "__main__":
    main()
