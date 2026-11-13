"""任务三：固定 panel13 的自然/法定日类型比较。项目根目录运行 python task03/run_task03.py。"""
import argparse
import base64
import hashlib
import html
import json
import platform
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
C = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
OUT = ROOT / C["derive_dir"]
REPORT = HERE / "reports"
FIG = REPORT / "figures"
SCHEMES = {"natural": ("natural_day_type", "weekday", "weekend"),
           "actual": ("actual_day_type", "actual_workday", "actual_restday")}
LABELS = {"weekday": "自然工作日", "weekend": "自然周末",
          "actual_workday": "实际工作日", "actual_restday": "实际休息日"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def recorded_path(path):
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def read_csv(path):
    return pd.read_csv(path, float_precision="round_trip")


def local_dates(values):
    return pd.to_datetime(values, utc=True).dt.tz_convert(C["timezone"])


def write_csv(frame, name):
    frame.to_csv(OUT / name, index=False, encoding="utf-8-sig")


def make_calendar():
    rules = json.loads((HERE / "sources/holiday_rules.json").read_text(encoding="utf-8"))
    cal = pd.DataFrame({"date": pd.date_range("2021-01-01", "2022-12-31", tz=C["timezone"])})
    cal["year_month"] = cal.date.dt.strftime("%Y-%m")
    cal["weekday"] = cal.date.dt.dayofweek  # Monday=0
    cal["natural_day_type"] = np.where(cal.weekday < 5, "weekday", "weekend")
    cal["actual_day_type"] = np.where(cal.weekday < 5, "actual_workday", "actual_restday")
    cal["season"] = cal.date.dt.month.map({m: s for s, ms in
        {"spring": [3, 4, 5], "summer": [6, 7, 8], "autumn": [9, 10, 11], "winter": [12, 1, 2]}.items() for m in ms})
    # 冬季以十二月所在年份命名，区分数据两端的春季。
    season_year = cal.date.dt.year - cal.date.dt.month.isin([1, 2]).astype(int)
    cal["season_period"] = season_year.astype(str) + "_" + cal.season
    cal["holiday_name"] = ""
    cal["is_holiday_break"] = False
    cal["is_makeup_workday"] = False
    cal["makeup_for_holiday"] = ""
    cal["rule_version"] = C["calendar_rule_version"]
    cal["source_url"] = ""
    cal["notice_date"] = ""
    for year, r in rules.items():
        mask = cal.date.dt.year.eq(int(year))
        cal.loc[mask, "source_url"] = r["source_url"]
        cal.loc[mask, "notice_date"] = r["notice_date"]
        for name, first, last in r["holidays"]:
            mask = cal.date.between(pd.Timestamp(first, tz=C["timezone"]), pd.Timestamp(last, tz=C["timezone"]))
            cal.loc[mask, ["actual_day_type", "holiday_name", "is_holiday_break"]] = ["actual_restday", name, True]
        for date, name in r["makeup_workdays"].items():
            mask = cal.date.eq(pd.Timestamp(date, tz=C["timezone"]))
            assert not cal.loc[mask, "is_holiday_break"].any()
            cal.loc[mask, ["actual_day_type", "is_makeup_workday", "makeup_for_holiday"]] = ["actual_workday", True, name]
    return cal


def load_inputs(input_dir, calendar):
    peer_manifest = json.loads((input_dir / "derivation_manifest.json").read_text(encoding="utf-8"))
    peer_rules = peer_manifest["generated_rules"]
    assert all(peer_rules[key] == C[key] for key in ["panel_id", "panel_version", "data_version", "timezone"])
    standard_panel = ROOT / "data/standardized" / C["data_version"] / "panel_minute.csv.gz"
    if standard_panel.exists():
        assert digest(standard_panel) == peer_manifest["inputs"][0]["sha256"], "task02 的上游标准分钟版本须与本仓库相同"
    daily = read_csv(input_dir / "daily_panel13.csv")
    hourly = read_csv(input_dir / "hourly_panel13.csv")
    daily["date"] = local_dates(daily.date)
    hourly["timestamp"] = local_dates(hourly.timestamp)
    expected = pd.date_range(C["analysis_start"], C["analysis_end_exclusive"], inclusive="left", tz=C["timezone"])
    assert daily.date.is_unique and daily.date.sort_values().tolist() == list(expected), "日表须包含完整 366 日历轴"
    hours = pd.date_range(expected[0], pd.Timestamp(C["analysis_end_exclusive"], tz=C["timezone"]), freq="h", inclusive="left")
    assert hourly.timestamp.is_unique and hourly.timestamp.sort_values().tolist() == list(hours)
    assert daily.panel_id.eq(C["panel_id"]).all() and hourly.panel_id.eq(C["panel_id"]).all()
    assert hourly.data_version.eq(C["data_version"]).all()
    for frame, flag in [(daily, "day_complete"), (hourly, "hour_complete")]:
        assert frame[flag].isin([True, False]).all() and frame[flag].dtype == bool
        assert frame.loc[frame[flag], "energy_kwh"].notna().all()
        assert frame.loc[~frame[flag], "energy_kwh"].isna().all()
    hourly["date"] = hourly.timestamp.dt.normalize()
    counts = hourly.groupby("date").hour_complete.sum().reindex(expected)
    summed = hourly.groupby("date").energy_kwh.sum(min_count=24).reindex(expected)
    d = daily.set_index("date").reindex(expected)
    assert counts.eq(d.valid_hours).all() and d.day_complete.eq(counts.eq(24)).all()
    np.testing.assert_allclose(summed, d.energy_kwh, rtol=1e-12, atol=1e-12, equal_nan=True)
    assert d.day_complete.sum() == 352 and hourly.hour_complete.sum() == 8503
    # 直接与 task01 核验表对照；成果包离线运行时可以没有整个 task01。
    reference = ROOT / "task01/reports/strict_daily_check.csv"
    reference_status = "not_present_in_standalone_package"
    if reference.exists():
        ref = read_csv(reference)
        ref = ref.loc[ref.panel_id.eq(C["panel_id"])].copy()
        ref["date"] = local_dates(ref.date)
        ref = ref.set_index("date").reindex(expected)
        np.testing.assert_array_equal(d.day_complete, ref.day_complete)
        np.testing.assert_allclose(d.energy_kwh, ref.energy_kwh, rtol=1e-12, atol=1e-12, equal_nan=True)
        refh = read_csv(ROOT / "task01/reports/strict_hourly_check.csv")
        refh = refh.loc[refh.panel_id.eq(C["panel_id"])].copy()
        refh["timestamp"] = local_dates(refh.timestamp)
        refh = refh.set_index("timestamp").reindex(hours)
        hourly_ordered = hourly.set_index("timestamp").reindex(hours)
        np.testing.assert_array_equal(hourly_ordered.hour_complete, refh.hour_complete)
        np.testing.assert_allclose(hourly_ordered.energy_kwh, refh.energy_kwh, rtol=1e-12, atol=1e-12, equal_nan=True)
        reference_status = "pass"
    dates = calendar.loc[calendar.date.isin(expected)].merge(daily, on="date", how="left", validate="one_to_one")
    dates["exclusion_reason"] = np.where(dates.day_complete, "", "incomplete_day_" + dates.valid_hours.astype(str) + "_of_24_hours")
    dates["data_version"] = C["data_version"]
    dates["panel_version"] = C["panel_version"]
    return dates, hourly, reference_status


def group_tables(dates, hourly):
    support, summaries, profiles = [], [], []
    full = dates.loc[dates.day_complete]
    h = hourly.merge(full[["date", "natural_day_type", "actual_day_type"]], on="date", validate="many_to_one")
    h["hour"] = h.timestamp.dt.hour
    for scheme, (col, work, rest) in SCHEMES.items():
        for month, m in dates.groupby("year_month"):
            for kind in [work, rest]:
                g = m.loc[m[col].eq(kind)]
                n = int(g.day_complete.sum())
                support.append(dict(scheme=scheme, year_month=month, day_type=kind,
                    calendar_days=len(g), n_days=n, excluded_days=len(g)-n,
                    exclusion_rate=(len(g)-n)/len(g) if len(g) else np.nan,
                    file_boundary_complete=month != "2021-05"))
        for kind in [work, rest]:
            g = full.loc[full[col].eq(kind)]
            all_g = dates.loc[dates[col].eq(kind)]
            counts = g.year_month.value_counts().sort_index().to_dict()
            summaries.append(dict(scheme=scheme, day_type=kind, n_days=len(g),
                calendar_days=len(all_g), excluded_days=len(all_g)-len(g),
                exclusion_rate=1-len(g)/len(all_g), mean_energy_kwh=g.energy_kwh.mean(),
                median_energy_kwh=g.energy_kwh.median(), std_energy_kwh=g.energy_kwh.std(),
                q25_energy_kwh=g.energy_kwh.quantile(.25), q75_energy_kwh=g.energy_kwh.quantile(.75),
                month_composition=json.dumps(counts, ensure_ascii=False)))
            for hour, v in h.loc[h[col].eq(kind)].groupby("hour"):
                profiles.append(dict(scheme=scheme, day_type=kind, hour=hour, n_days=len(v),
                    mean_power_kw=v.mean_power_kw.mean(), median_power_kw=v.mean_power_kw.median(),
                    q25_power_kw=v.mean_power_kw.quantile(.25), q75_power_kw=v.mean_power_kw.quantile(.75)))
    return pd.DataFrame(support), pd.DataFrame(summaries), pd.DataFrame(profiles)


def matched_hourly_tables(dates, hourly):
    full = dates.loc[dates.day_complete]
    h = hourly.merge(full[["date", "year_month", "natural_day_type", "actual_day_type"]], on="date", validate="many_to_one")
    h["hour"] = h.timestamp.dt.hour
    monthly, adjusted = [], []
    for scheme, (col, work, rest) in SCHEMES.items():
        for (month, kind, hour), g in h.groupby(["year_month", col, "hour"]):
            monthly.append(dict(scheme=scheme, year_month=month, day_type=kind, hour=hour,
                n_days=len(g), mean_power_kw=g.mean_power_kw.mean(), median_power_kw=g.mean_power_kw.median()))
        eligible = [m for m, g in full.groupby("year_month") if {work, rest}.issubset(set(g[col]))]
        counts = full.loc[full.year_month.isin(eligible)].groupby("year_month").size()
        weights = counts / counts.sum()
        for hour in range(24):
            means = {}
            for kind in [work, rest]:
                means[kind] = sum(weights[m] * h.loc[h.year_month.eq(m) & h[col].eq(kind) & h.hour.eq(hour), "mean_power_kw"].mean() for m in eligible)
            adjusted.append(dict(scheme=scheme, hour=hour, n_work=int(full.loc[full.year_month.isin(eligible), col].eq(work).sum()),
                n_rest=int(full.loc[full.year_month.isin(eligible), col].eq(rest).sum()),
                work_mean_power_kw=means[work], rest_mean_power_kw=means[rest],
                difference_kw=means[rest]-means[work], month_weights=json.dumps(weights.to_dict(), sort_keys=True)))
    return pd.DataFrame(monthly), pd.DataFrame(adjusted)


def month_samples(dates, col, work, rest, block_days, rng):
    """年月份内非循环移动日历块；缺测日期随块保留且数值仍空。

    每月抽取 ceil(n/L) 个等长块后截到 n；不会跨月连接或先删缺测后拼接。
    返回每月每种日类型的重复抽样总量和日数，重算均值比值。
    """
    result = {}
    reps = C["bootstrap_repetitions"]
    for month, g in dates.groupby("year_month", sort=True):
        y = g.energy_kwh.to_numpy(float)
        n = len(g)
        length = min(block_days, n)
        starts = rng.integers(0, n-length+1, size=(reps, int(np.ceil(n/length))))
        idx = (starts[:, :, None] + np.arange(length)).reshape(reps, -1)[:, :n]
        result[month] = {}
        for kind in [work, rest]:
            valid = g[col].eq(kind).to_numpy() & np.isfinite(y)
            ys = np.where(valid, y, 0.)
            result[month][kind] = (ys[idx].sum(axis=1), valid[idx].sum(axis=1))
    return result


def safe_divide(a, b):
    a, b = np.broadcast_arrays(a, b)
    return np.divide(a, b, out=np.full(a.shape, np.nan, dtype=float), where=b != 0)


def ci(values):
    finite = np.asarray(values)[np.isfinite(values)]
    n = len(finite)
    if n < C["bootstrap_repetitions"] * C["minimum_valid_bootstrap_fraction"]:
        return np.nan, np.nan, n
    tail = (1-C["confidence_level"])/2
    lo, hi = np.quantile(finite, [tail, 1-tail])
    return float(lo), float(hi), n


def comparisons(dates):
    rows, sensitivity = [], []
    full = dates.loc[dates.day_complete]
    for si, (scheme, (col, work, rest)) in enumerate(SCHEMES.items()):
        eligible = [month for month, g in full.groupby("year_month") if {work, rest}.issubset(set(g[col]))]
        weights = full.loc[full.year_month.isin(eligible)].groupby("year_month").size()
        weights = weights / weights.sum()
        scopes = [("all_unadjusted", "all", list(dates.year_month.unique()), False),
                  ("month_standardized", "matched_months", eligible, True)]
        scopes += [("year_month", m, [m], False) for m in dates.year_month.unique()]
        scopes += [("season_period", s, list(g.year_month.unique()), False) for s, g in dates.groupby("season_period")]
        for block in C["sensitivity_block_days"]:
            rng = np.random.default_rng(np.random.SeedSequence([C["seed"], si, block]))
            samples = month_samples(dates, col, work, rest, block, rng)
            for scope, stratum, months, adjusted in scopes:
                if not months:
                    continue
                g = full.loc[full.year_month.isin(months)]
                ns = {k: int(g[col].eq(k).sum()) for k in [work, rest]}
                means, boots = {}, {}
                if adjusted:
                    valid_replicate = np.ones(C["bootstrap_repetitions"], dtype=bool)
                    for k in [work, rest]:
                        means[k] = sum(weights[m]*g.loc[g.year_month.eq(m) & g[col].eq(k), "energy_kwh"].mean() for m in months)
                        boots[k] = np.zeros(C["bootstrap_repetitions"])
                        for m in months:
                            sums, counts = samples[m][k]
                            valid_replicate &= counts > 0
                            boots[k] += weights[m] * safe_divide(sums, counts)
                    for k in [work, rest]:
                        boots[k][~valid_replicate] = np.nan
                else:
                    for k in [work, rest]:
                        means[k] = g.loc[g[col].eq(k), "energy_kwh"].mean()
                        sums = sum(samples[m][k][0] for m in months)
                        counts = sum(samples[m][k][1] for m in months)
                        boots[k] = safe_divide(sums, counts)
                diff = means[rest] - means[work]
                relative = 100*diff/means[work] if means[work] > C["relative_baseline_min_kwh"] else np.nan
                delta = boots[rest] - boots[work]
                relative_samples = 100*safe_divide(delta, np.where(boots[work] > C["relative_baseline_min_kwh"], boots[work], np.nan))
                lo, hi, valid_n = ci(delta)
                rlo, rhi, _ = ci(relative_samples)
                work_lo, work_hi, _ = ci(boots[work])
                rest_lo, rest_hi, _ = ci(boots[rest])
                status = "ok" if np.isfinite(lo) else "insufficient_bootstrap_group_support"
                if min(ns.values()) == 0:
                    status = "missing_day_type"
                row = dict(scheme=scheme, scope=scope, stratum=stratum, work_type=work, rest_type=rest,
                    n_work=ns[work], n_rest=ns[rest], n_days=len(g), excluded_days=int(dates.year_month.isin(months).sum())-len(g),
                    work_mean_kwh=means[work], rest_mean_kwh=means[rest], difference_kwh=diff,
                    relative_difference_pct=relative, ci_low_kwh=lo, ci_high_kwh=hi,
                    relative_ci_low_pct=rlo, relative_ci_high_pct=rhi,
                    work_mean_ci_low_kwh=work_lo, work_mean_ci_high_kwh=work_hi,
                    rest_mean_ci_low_kwh=rest_lo, rest_mean_ci_high_kwh=rest_hi,
                    block_days=block, bootstrap_repetitions=C["bootstrap_repetitions"], seed=C["seed"],
                    valid_bootstrap_repetitions=valid_n, status=status,
                    weight_rule="fixed_complete_day_counts_in_matched_year_months" if adjusted else "pooled_days",
                    month_weights=json.dumps(weights.to_dict(), sort_keys=True) if adjusted else "",
                    months=";".join(months), inference="exploratory_pointwise_95pct")
                if block == C["primary_block_days"]:
                    rows.append(row)
                if scope in ["all_unadjusted", "month_standardized"]:
                    sensitivity.append(row)
    return pd.DataFrame(rows), pd.DataFrame(sensitivity)


def autocorrelation(dates):
    series = dates.set_index("date").energy_kwh
    demeaned = series - series.groupby(series.index.strftime("%Y-%m")).transform("mean")
    rows = []
    for name, s in [("raw", series), ("within_year_month_demeaned", demeaned)]:
        for lag in [1, 2, 3, 7, 14]:
            pairs = pd.concat([s.rename("current"), s.shift(lag).rename("lagged")], axis=1).dropna()
            rows.append(dict(series=name, lag_calendar_days=lag, n_pairs=len(pairs), pearson_correlation=pairs.current.corr(pairs.lagged)))
    return pd.DataFrame(rows)


def make_figures(dates, summary, profiles, comp, sensitivity, support, adjusted_profiles):
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "axes.unicode_minus": False, "figure.dpi": 140,
                         "axes.spines.top": False, "axes.spines.right": False})
    colors = ["#176B87", "#E8933E"]
    full = dates.loc[dates.day_complete]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for ax, (scheme, (col, work, rest)) in zip(axes, SCHEMES.items()):
        groups = [full.loc[full[col].eq(k), "energy_kwh"] for k in [work, rest]]
        ax.boxplot(groups, labels=[f"{LABELS[k]}\nn={len(v)}" for k, v in zip([work, rest], groups)], showmeans=True)
        ax.set_title("自然星期口径" if scheme == "natural" else "法定日历口径")
        ax.grid(axis="y", alpha=.2)
    axes[0].set_ylabel("完整日电量（kWh）")
    fig.suptitle("固定 13 台监测设备｜日电量分布（保留高负荷日）")
    fig.tight_layout(); fig.savefig(FIG / "01_daily_distribution.png"); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.7), sharey=True)
    for ax, scheme in zip(axes, SCHEMES):
        g = comp.loc[comp.scheme.eq(scheme) & comp.scope.eq("year_month")]
        x = np.arange(len(g))
        ax.axhline(0, color="#555", lw=1)
        ax.scatter(x, g.difference_kwh, color=colors[0], zorder=3)
        good = g.ci_low_kwh.notna()
        ax.vlines(x[good], g.loc[good, "ci_low_kwh"], g.loc[good, "ci_high_kwh"], color=colors[0], lw=2)
        ax.set_xticks(x, g.stratum, rotation=60, ha="right")
        ax.set_title("自然周末 − 自然工作日" if scheme == "natural" else "实际休息日 − 实际工作日")
        ax.grid(axis="y", alpha=.2)
    axes[0].set_ylabel("同年月份内日电量差（kWh）")
    fig.suptitle("月内差异与 7 天块 bootstrap 95% 区间｜缺少点或区间表示支持不足")
    fig.tight_layout(); fig.savefig(FIG / "02_monthly_comparison.png"); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for ax, (scheme, (_, work, rest)) in zip(axes, SCHEMES.items()):
        for color, kind in zip(colors, [work, rest]):
            g = profiles.loc[profiles.scheme.eq(scheme) & profiles.day_type.eq(kind)]
            ax.plot(g.hour.to_numpy(), g.mean_power_kw.to_numpy(), color=color, lw=2, label=f"{LABELS[kind]} n={g.n_days.iloc[0]}")
            ax.fill_between(g.hour.to_numpy(), g.q25_power_kw.to_numpy(), g.q75_power_kw.to_numpy(), color=color, alpha=.13)
        ax.set_xticks(range(0, 24, 3)); ax.set_xlabel("北京时间（小时起点）"); ax.legend(fontsize=9)
        ax.grid(alpha=.2)
    axes[0].set_ylabel("小时平均负荷（kW）")
    fig.suptitle("24 小时典型曲线｜各小时固定同组完整日期，阴影为日间四分位范围")
    fig.tight_layout(); fig.savefig(FIG / "03_hourly_profiles.png"); plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    for ax, (scheme, (_, work, rest)) in zip(axes, SCHEMES.items()):
        months = sorted(support.year_month.unique()); x = np.arange(len(months))
        for i, kind in enumerate([work, rest]):
            g = support.loc[support.scheme.eq(scheme) & support.day_type.eq(kind)].set_index("year_month").reindex(months)
            ax.bar(x+(i-.5)*.36, g.n_days, .36, color=colors[i], label=LABELS[kind])
            ax.bar(x+(i-.5)*.36, g.excluded_days, .36, bottom=g.n_days, color="#d6d6d6", hatch="//")
        ax.set_ylabel("自然日数"); ax.legend(ncol=2); ax.grid(axis="y", alpha=.15)
    axes[-1].set_xticks(x, months, rotation=45, ha="right")
    fig.suptitle("各月样本支持｜灰色斜线为因缺测排除日期；2021-05 仅观测 1 天")
    fig.tight_layout(); fig.savefig(FIG / "04_monthly_support.png"); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharey=True)
    for ax, scheme in zip(axes, SCHEMES):
        g = sensitivity.loc[sensitivity.scheme.eq(scheme) & sensitivity.scope.eq("month_standardized")]
        ax.axhline(0, color="#555", lw=1)
        ax.scatter(g.block_days, g.difference_kwh, color=colors[0])
        ax.vlines(g.block_days, g.ci_low_kwh, g.ci_high_kwh, color=colors[0], lw=2)
        ax.set_xticks([1, 3, 7, 14]); ax.set_xlabel("块长（日）；1 日为独立日抽样")
        ax.set_title("自然星期口径" if scheme == "natural" else "法定日历口径"); ax.grid(alpha=.15)
    axes[0].set_ylabel("月度标准化的休息类 − 工作类（kWh/日）")
    fig.suptitle("置信区间对块长的敏感性｜2000 次抽样，种子 42")
    fig.tight_layout(); fig.savefig(FIG / "05_block_sensitivity.png"); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for ax, (scheme, (_, work, rest)) in zip(axes, SCHEMES.items()):
        g = adjusted_profiles.loc[adjusted_profiles.scheme.eq(scheme)]
        for color, kind, key in zip(colors, [work, rest], ["work_mean_power_kw", "rest_mean_power_kw"]):
            ax.plot(g.hour, g[key], color=color, lw=2, label=LABELS[kind])
        ax.set_title("自然星期口径" if scheme == "natural" else "法定日历口径")
        ax.set_xticks(range(0, 24, 3)); ax.set_xlabel("北京时间（小时起点）"); ax.legend(); ax.grid(alpha=.2)
    axes[0].set_ylabel("月度标准化小时平均负荷（kW）")
    fig.suptitle("控制月份组成的 24 小时曲线｜12 个同年月份，固定完整日权重")
    fig.tight_layout(); fig.savefig(FIG / "06_matched_hourly_profiles.png"); plt.close(fig)


def table_md(df):
    columns = list(df.columns)
    rows = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"]*len(columns)) + " |"]
    for row in df.itertuples(index=False, name=None):
        rows.append("| " + " | ".join("—" if pd.isna(v) else f"{v:.3f}" if isinstance(v, (float, np.floating)) else str(v) for v in row) + " |")
    return "\n".join(rows)


def make_report(dates, summary, profiles, comp, sensitivity, support, acf):
    headline = comp.loc[comp.scope.isin(["all_unadjusted", "month_standardized"]),
        ["scheme", "scope", "n_work", "n_rest", "work_mean_kwh", "rest_mean_kwh", "difference_kwh", "relative_difference_pct", "ci_low_kwh", "ci_high_kwh"]]
    monthly = support.pivot(index="year_month", columns=["scheme", "day_type"], values="n_days")
    monthly.columns = [f"{a}/{b}" for a, b in monthly.columns]
    summary_cols = ["scheme", "day_type", "n_days", "excluded_days", "mean_energy_kwh", "median_energy_kwh"]
    sensitivity_cols = ["scheme", "scope", "block_days", "ci_low_kwh", "ci_high_kwh", "valid_bootstrap_repetitions"]
    conclusion = []
    for scheme in SCHEMES:
        r = comp.loc[comp.scheme.eq(scheme) & comp.scope.eq("month_standardized")].iloc[0]
        conclusion.append(f"{'自然周末相对自然工作日' if scheme == 'natural' else '实际休息日相对实际工作日'}：同月标准化后差 {r.difference_kwh:.3f} kWh/日（{r.relative_difference_pct:+.2f}%），7 天块 95% 区间 [{r.ci_low_kwh:.3f}, {r.ci_high_kwh:.3f}]。" +
                          ("区间覆盖 0，差异方向存在不确定性。" if r.ci_low_kwh <= 0 <= r.ci_high_kwh else "区间未覆盖 0，但仍属单户观察性关联。"))
    changed = int((dates.natural_day_type.eq("weekday") != dates.actual_day_type.eq("actual_workday")).sum())
    lines = ["# 任务三：工作日与休息日用电比较", "", "## 主要结果", "", *conclusion, "",
        "固定 panel13 的 13 台监测设备，不等同于独立整户总表。完整日 352/366；因质量排除 14 日，保留在日历轴中。两套分类在观测区间内有 " + str(changed) + " 日不同。", "",
        table_md(headline), "", "差值均为休息类减工作类；相对差以工作类均值为分母。all_unadjusted 是全样本描述；month_standardized 是主要控制月份组成的比较。", "",
        "## 数据、历史日历与质量", "",
        "输入为同伴 task02 的正式日表、小时表和派生清单，逐字复制到 data/derived/task02；不重新清洗标准分钟表。分析区间 [2021-05-31, 2022-06-01)，北京时间。数据版本 cn_obee_v1_noimpute_v1.0.0，panel13/v1.0.0；零新增插补。", "",
        "严格日要求 24/24 合格小时，每小时要求 60/60 联合有效分钟。读取时核验逐小时汇总与日电量相等；与仓库 task01 日核验表复核。未剔除高负荷日，未将缺失当 0。", "",
        "日历先生成完整 2021、2022 年 730 日再截取。自然星期：周一至周五 weekday，周末 weekend；法定日历：国务院假期区间覆盖自然工作日、调休上班日覆盖自然周末。holiday_name 表示官方放假区间名称（并非区间每一天都是法定节日本日）；它不能证明该住户实际休假或在家。weekday 取 Monday=0。", "",
        "官方来源（原文 HTML、获取时间和 SHA-256 保存在 sources/）：", "",
        "- [2021 年安排](https://app.www.gov.cn/govdata/gov/202011/26/465359/article.html)，通知 2020-11-25。",
        "- [2022 年安排](https://app.www.gov.cn/govdata/gov/202110/25/477434/article.html)，通知 2021-10-25。", "",
        "## 两类日样本及电量", "", table_md(summary[summary_cols]), "", "### 每月完整日数", "",
        table_md(monthly.reset_index()), "",
        "2021-05 仅 1 个观测日且没有休息类，不能计算月内差异；2021-06/07 缺测集中。排除数、排除率及月份组成见 day_type_support.csv、day_type_summary.csv，逐日排除原因见 date_dimension.csv。缺测集中可能造成选择偏差，严格筛选不能消除该偏差。", "",
        "## 同月控制与季节", "",
        "基本层为 year_month，绝不把不同年份相同月份合并。只选同时有工作类、休息类完整日的月份；两类均值分别按该月完整日总数 / 所有可比月份完整日总数加权，再相减。固定权重写入 stratified_comparison.csv；2021-05 的 1 日不参与，主标准化比较为其余 351 日。此估计对象是观测支持月份的共同月份组成，不能解释为全年总体平均效果。", "",
        "气象季节：3–5 春、6–8 夏、9–11 秋、12–2 冬；季节描述使用 season_period，将 2021 年 5 月边界春季与 2022 年 3–5 月春季分开，2021-12 至 2022-02 合并为 2021_winter。季节结果仍可能有月份组成差异，以同年月份标准化为主。", "",
        table_md(comp.loc[comp.scope.eq("season_period"), ["scheme", "stratum", "n_work", "n_rest", "difference_kwh", "ci_low_kwh", "ci_high_kwh", "status"]]), "",
        "## 抽样、相关性与置信区间", "",
        "预设种子 42、2000 次；主块长 7 天对应完整周节律，并列审查 1、3、14 天。先在每个年月份的完整日历（包括缺测日期）抽取非循环移动块，块在原日历中连续、不跨月，拼接后截至原月日数。仅完整日数值参与均值；缺测日期不压缩、不插补。抽样单位最小为日，绝不把分钟视为独立样本。1 日抽样为月份内独立日 bootstrap。", "",
        "每次重新计算两类均值、差值和相对差，标准化权重固定。95% 百分位区间；两类都存在的抽样不足 95% 时不发布区间，保留有效次数和状态。边界月份块长取 min(L, n)，移动块有端点采样权重不均的问题；短月、少数类别、小样本或长记忆均限制区间校准，块长敏感性不能证明覆盖率。主块长预先锁定，不按是否显著选择。", "",
        "实际诊断中，原日电量 lag-1 相关约 0.635，按年月份去均值后仍约 0.295，lag-7 约 0.087；支持采用日块并检查不同块长。两套月度标准化估计在 1、3、7、14 天下的区间均覆盖 0；全样本自然星期差的区间会随块长改变是否跨 0，不能把某个区间当作稳定显著结论。", "",
        "日期轴上的相关性诊断（shift 不会跨缺口压缩）：", "", table_md(acf), "",
        table_md(sensitivity.loc[sensitivity.scope.eq("month_standardized"), sensitivity_cols]), "",
        "月、季节与小时比较均为探索性，未做大量显著性检验，不发布逐小时显著结论；表中 95% 区间为逐项区间，不是同时置信带。只有一户约一年数据，天气、季节、行为、缺测、节假日出行等均可能混杂，不能解释为休息日的因果作用或推广到其他家庭。", "",
        "## 24 小时形态", "",
        "两套口径的每条曲线都使用该组同一批完整日，24 个小时样本数固定。原始曲线为未控制月份的描述，阴影是日电量对应小时负荷的 25%–75% 分位范围，不是均值置信区间。另交付 monthly_hourly_day_type_profile.csv 的月内曲线与 standardized_hourly_day_type_profile.csv 的共同月份权重曲线；后者沿用日电量比较的同一组日期与固定月份权重，24 小时差值积分等于标准化日电量差。小时曲线均为探索性，未进行平滑、削峰或逐小时显著检验。", ""]
    for scheme, (_, work, rest) in SCHEMES.items():
        for kind in [work, rest]:
            g = profiles.loc[profiles.scheme.eq(scheme) & profiles.day_type.eq(kind)]
            peak = g.loc[g.mean_power_kw.idxmax()]; valley = g.loc[g.mean_power_kw.idxmin()]
            lines.append(f"- {LABELS[kind]}：平均曲线峰小时 {int(peak.hour):02d}:00（{peak.mean_power_kw:.3f} kW），谷小时 {int(valley.hour):02d}:00（{valley.mean_power_kw:.3f} kW）。")
    lines += ["", "## 图表", ""]
    names = ["日电量分布", "同月差异", "24 小时曲线", "月度样本支持", "块长敏感性", "控制月份后的曲线"]
    for name, path in zip(names, sorted(FIG.glob("*.png"))):
        lines += [f"![{name}](figures/{path.name})", ""]
    lines += ["## 复现与下游交接", "", "在项目根目录运行 `python -m pip install -r task03/requirements.txt`，随后 `python task03/run_task03.py`、`python task03/verify_task03.py`。无需联网，节假日来源已归档。", "",
        "date_dimension.csv 可供 task04 选择日类型案例；task06 只使用 date、星期、已发布法定假期及调休等事先已知日历字段。不得把 day_complete、energy_kwh、coverage 或当日质量/实测结果作为日前已知特征。通知发布时间写入 notice_date，预测时仍须按发布时间核验。", ""]
    (REPORT / "task03_report.md").write_text("\n".join(lines), encoding="utf-8")
    # 单文件 HTML 便于同伴直接打开；表格和图片均包含在文件中。
    blocks = []
    in_table = False
    for line in lines:
        if in_table and not line.startswith("|"):
            blocks.append("</tbody></table></div>")
            in_table = False
        if line.startswith("!["):
            file = REPORT / line.split("](", 1)[1].rstrip(")")
            blocks.append('<img alt="分析图" src="data:image/png;base64,' + base64.b64encode(file.read_bytes()).decode() + '">')
        elif line.startswith("### "):
            blocks.append("<h3>" + html.escape(line[4:]) + "</h3>")
        elif line.startswith("## "):
            blocks.append("<h2>" + html.escape(line[3:]) + "</h2>")
        elif line.startswith("# "):
            blocks.append("<h1>" + html.escape(line[2:]) + "</h1>")
        elif line.startswith("|"):
            if set(line.replace("|", "").strip()) <= {"-", " "}:
                continue
            cells = [html.escape(cell.strip()) for cell in line.strip("|").split("|")]
            if not in_table:
                blocks.append('<div class="tablewrap"><table><thead><tr>' + ''.join('<th>'+v+'</th>' for v in cells) + '</tr></thead><tbody>')
                in_table = True
            else:
                blocks.append('<tr>' + ''.join('<td>'+v+'</td>' for v in cells) + '</tr>')
        elif line:
            blocks.append("<p>" + html.escape(line) + "</p>")
    page = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Task03 工作日与休息日用电比较</title><style>body{max-width:1180px;margin:40px auto;padding:0 28px;font:16px/1.8 "Microsoft YaHei",sans-serif;color:#18303c;background:#faf9f6}h1{font-size:32px}h2{margin-top:42px;color:#176b87}img{max-width:100%;background:white;margin:16px 0}.tablewrap{overflow-x:auto}table{border-collapse:collapse;font-size:13px;background:white;width:100%}th,td{padding:8px 12px;border-bottom:1px solid #ddd;white-space:nowrap;text-align:left}th{background:#e8f0f3}p{overflow-wrap:anywhere}</style><body>' + "\n".join(blocks) + '</body></html>'
    (REPORT / "task03_report.html").write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task02-dir", type=Path, default=ROOT / "data/derived/task02")
    args = parser.parse_args()
    for p in [OUT, REPORT, FIG]:
        p.mkdir(parents=True, exist_ok=True)
    calendar = make_calendar()
    dates, hourly, reference_status = load_inputs(args.task02_dir, calendar)
    support, summary, profiles = group_tables(dates, hourly)
    monthly_profiles, adjusted_profiles = matched_hourly_tables(dates, hourly)
    comp, sensitivity = comparisons(dates)
    # summary 同时带上对应全样本组均值区间、组差值与抽样参数。
    for scheme in SCHEMES:
        r = comp.loc[comp.scheme.eq(scheme) & comp.scope.eq("all_unadjusted")].iloc[0]
        for kind in [r.work_type, r.rest_type]:
            mask = summary.scheme.eq(scheme) & summary.day_type.eq(kind)
            prefix = "work" if kind == r.work_type else "rest"
            for key in ["block_days", "bootstrap_repetitions", "seed", "difference_kwh", "relative_difference_pct", "ci_low_kwh", "ci_high_kwh", "relative_ci_low_pct", "relative_ci_high_pct"]:
                summary.loc[mask, key] = r[key]
            summary.loc[mask, "mean_ci_low_kwh"] = r[prefix + "_mean_ci_low_kwh"]
            summary.loc[mask, "mean_ci_high_kwh"] = r[prefix + "_mean_ci_high_kwh"]
            summary.loc[mask, "difference_direction"] = "rest_minus_work"
    acf = autocorrelation(dates)
    frames = {"holiday_calendar_2021_2022.csv": calendar, "date_dimension.csv": dates,
              "day_type_support.csv": support, "day_type_summary.csv": summary,
              "hourly_day_type_profile.csv": profiles, "stratified_comparison.csv": comp,
              "monthly_hourly_day_type_profile.csv": monthly_profiles,
              "standardized_hourly_day_type_profile.csv": adjusted_profiles,
              "bootstrap_sensitivity.csv": sensitivity, "autocorrelation_diagnostics.csv": acf}
    for name, frame in frames.items():
        write_csv(frame, name)
    make_figures(dates, summary, profiles, comp, sensitivity, support, adjusted_profiles)
    make_report(dates, summary, profiles, comp, sensitivity, support, acf)
    input_files = [args.task02_dir / n for n in ["daily_panel13.csv", "hourly_panel13.csv", "derivation_manifest.json"]]
    input_files += list((HERE / "sources").glob("*")) + [HERE / "config.json", HERE / "run_task03.py"]
    manifest = dict(task="task03_day_type_comparison", generated_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        rules=C, runtime=dict(python=platform.python_version(), pandas=pd.__version__, numpy=np.__version__, matplotlib=matplotlib.__version__),
        counts=dict(calendar_days=len(dates), complete_days=int(dates.day_complete.sum()), excluded_days=int((~dates.day_complete).sum()), holiday_calendar_days=len(calendar)),
        task01_daily_and_hourly_reference_check=reference_status,
        bootstrap=dict(unit="calendar_day", method="noncircular_moving_calendar_blocks_within_year_month", missing="retained_in_calendar_not_used_in_means", interval="pointwise_percentile", primary_block_days=7, repetitions=2000, seed=42),
        comparison_direction="rest_minus_work", no_imputation=True,
        inputs=[dict(path=recorded_path(p), sha256=digest(p), bytes=p.stat().st_size) for p in input_files],
        outputs=[dict(path=(OUT/n).relative_to(ROOT).as_posix(), rows=len(f), sha256=digest(OUT/n)) for n, f in frames.items()])
    (OUT / "derivation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS: 366 calendar days; 352 complete days; 730 full-year holiday labels")
    print(comp.loc[comp.scope.isin(["all_unadjusted", "month_standardized"]), ["scheme", "scope", "difference_kwh", "ci_low_kwh", "ci_high_kwh"]].to_string(index=False))


if __name__ == "__main__":
    main()
