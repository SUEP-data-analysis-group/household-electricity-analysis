"""独立核验已发布 task03 结果；不导入主程序，不重新调用统计实现。"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = (HERE.parent if (HERE.parent / "task01/reports/panel_definition.json").is_file()
        else HERE if (HERE / "data/derived/task02").is_dir() else HERE.parent)
OUT = ROOT / "data/derived/task03"
INPUT = ROOT / "data/derived/task02"
LOG = []


def check(condition, message):
    if not bool(condition):
        LOG.append("FAIL " + message)
        raise AssertionError(message)
    LOG.append("PASS " + message)


def read(name, folder=OUT):
    return pd.read_csv(folder / name, float_precision="round_trip")


def close(a, b):
    return np.allclose(a, b, rtol=1e-11, atol=1e-11, equal_nan=True)


def main():
    d = read("date_dimension.csv")
    h = read("hourly_panel13.csv", INPUT)
    upstream = read("daily_panel13.csv", INPUT)
    cal = read("holiday_calendar_2021_2022.csv")
    summary = read("day_type_summary.csv")
    support = read("day_type_support.csv")
    profiles = read("hourly_day_type_profile.csv")
    monthly_profiles = read("monthly_hourly_day_type_profile.csv")
    standardized_profiles = read("standardized_hourly_day_type_profile.csv")
    comp = read("stratified_comparison.csv")
    sensitivity = read("bootstrap_sensitivity.csv")
    for f, col in [(d, "date"), (cal, "date"), (upstream, "date"), (h, "timestamp")]:
        f[col] = pd.to_datetime(f[col], utc=True).dt.tz_convert("Asia/Shanghai")
    expected = pd.date_range("2021-05-31", "2022-05-31", tz="Asia/Shanghai")
    check(len(d) == 366 and d.date.is_unique and d.date.tolist() == list(expected), "366 unique contiguous local dates")
    check(d.day_complete.sum() == 352 and (~d.day_complete).sum() == 14, "352 complete and 14 excluded days")
    check(d.loc[~d.day_complete, "energy_kwh"].isna().all() and d.loc[~d.day_complete, "exclusion_reason"].notna().all(), "excluded dates retain missing energy and reasons")
    check(close(d.energy_kwh, upstream.energy_kwh) and d.day_complete.equals(upstream.day_complete), "no alteration of peer daily values or quality")
    check(h.hour_complete.sum() == 8503 and len(h) == 8784, "input hourly grid and strict-hour support")
    check(close(h.mean_power_kw, h.energy_kwh) and h.loc[~h.hour_complete, "mean_power_kw"].isna().all(),
          "strict hourly mean target and incomplete-hour missingness inherited from revised task02")
    h["date"] = h.timestamp.dt.normalize()
    h["hour"] = h.timestamp.dt.hour
    full = d.loc[d.day_complete]
    selected = h.merge(full[["date", "natural_day_type", "actual_day_type"]], on="date", validate="many_to_one")
    selected["year_month"] = selected.date.dt.strftime("%Y-%m")
    check(len(selected) == 352*24 and selected.hour_complete.all(), "curves use only 24 valid hours on each complete date")
    daily_recomputed = selected.groupby("date").energy_kwh.sum().reindex(full.date)
    check(close(daily_recomputed, full.energy_kwh), "hourly integrals equal complete-day energy")
    check(len(cal) == 730 and cal.date.is_unique and cal.date.min().strftime("%Y-%m-%d") == "2021-01-01" and cal.date.max().strftime("%Y-%m-%d") == "2022-12-31", "calendar covers full 2021 and 2022 before slicing")
    check(np.array_equal(cal.weekday, cal.date.dt.weekday) and np.array_equal(cal.natural_day_type, np.where(cal.date.dt.weekday < 5, "weekday", "weekend")), "natural weekday labels independently recomputed")
    # 独立按 JSON 日期集合展开，逐日核对官方放假和上班覆盖。
    rules = json.loads((HERE / "sources/holiday_rules.json").read_text(encoding="utf-8"))
    expected_labels = []
    expected_holidays = []
    expected_makeup = []
    for row in cal.itertuples():
        rule = rules[str(row.date.year)]
        day = row.date.strftime("%Y-%m-%d")
        holiday = next((name for name, first, last in rule["holidays"] if first <= day <= last), "")
        makeup = day in rule["makeup_workdays"]
        check_no_conflict = not (holiday and makeup)
        assert check_no_conflict
        is_rest = bool(holiday) or (row.date.weekday() >= 5 and not makeup)
        expected_labels.append("actual_restday" if is_rest else "actual_workday")
        expected_holidays.append(bool(holiday)); expected_makeup.append(makeup)
    check(np.array_equal(cal.actual_day_type, expected_labels) and np.array_equal(cal.is_holiday_break, expected_holidays) and np.array_equal(cal.is_makeup_workday, expected_makeup), "every holiday and makeup label matches independent rule expansion")
    check(cal.groupby(cal.date.dt.year).is_holiday_break.sum().eq(31).all() and cal.groupby(cal.date.dt.year).is_makeup_workday.sum().eq(7).all(), "31 holiday-break dates and 7 makeup dates in each full year")
    lookup = cal.set_index(cal.date.dt.strftime("%Y-%m-%d"))
    cases = {"2021-09-18": "actual_workday", "2021-09-20": "actual_restday",
             "2021-10-09": "actual_workday", "2022-01-03": "actual_restday",
             "2022-01-29": "actual_workday", "2022-01-30": "actual_workday",
             "2022-02-01": "actual_restday", "2022-04-02": "actual_workday",
             "2022-05-02": "actual_restday", "2022-05-07": "actual_workday",
             "2022-10-08": "actual_workday"}
    check(all(lookup.loc[day, "actual_day_type"] == kind for day, kind in cases.items()), "holiday/weekend overrides and year-boundary January cases")
    joined = d.merge(cal[["date", "actual_day_type", "natural_day_type"]], on="date", suffixes=("", "_cal"))
    check(joined.actual_day_type.equals(joined.actual_day_type_cal) and joined.natural_day_type.equals(joined.natural_day_type_cal), "analysis date labels exactly inherited from full-year calendar")
    seasons = {3: "spring", 4: "spring", 5: "spring", 6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn", 12: "winter", 1: "winter", 2: "winter"}
    check(d.season.equals(d.date.dt.month.map(seasons)) and len(d.loc[d.season.eq("spring"), "season_period"].unique()) == 2 and d.loc[d.date.dt.month.isin([12, 1, 2]), "season_period"].nunique() == 1, "meteorological seasons preserve separate spring boundary periods")
    for scheme, col, work, rest in [("natural", "natural_day_type", "weekday", "weekend"), ("actual", "actual_day_type", "actual_workday", "actual_restday")]:
        ss = support.loc[support.scheme.eq(scheme)]
        check(ss.calendar_days.sum() == 366 and ss.n_days.sum() == 352 and ss.excluded_days.sum() == 14, scheme + " monthly support preserves denominators")
        for row in ss.itertuples():
            original = d.loc[d.year_month.eq(row.year_month) & d[col].eq(row.day_type)]
            assert row.calendar_days == len(original) and row.n_days == original.day_complete.sum()
        for row in summary.loc[summary.scheme.eq(scheme)].itertuples():
            g = full.loc[full[col].eq(row.day_type)]
            assert row.n_days == len(g) and close(row.mean_energy_kwh, g.energy_kwh.mean())
            assert close(row.median_energy_kwh, g.energy_kwh.median())
            assert json.loads(row.month_composition) == g.year_month.value_counts().sort_index().to_dict()
        check(True, scheme + " group mean/median/day counts and month composition independently recomputed")
        for row in profiles.loc[profiles.scheme.eq(scheme)].itertuples():
            g = selected.loc[selected[col].eq(row.day_type) & selected.hour.eq(row.hour)]
            assert row.n_days == len(g) and close(row.mean_power_kw, g.mean_power_kw.mean())
        ps = profiles.loc[profiles.scheme.eq(scheme)]
        check(len(ps) == 48 and ps.groupby("day_type").n_days.nunique().eq(1).all(), scheme + " 24 hours use identical date cohorts and correct means")
        for row in comp.loc[comp.scheme.eq(scheme)].itertuples():
            g = full.loc[full.year_month.isin(row.months.split(";"))]
            assert row.n_work == g[col].eq(work).sum() and row.n_rest == g[col].eq(rest).sum()
            if row.scope == "month_standardized":
                weights = json.loads(row.month_weights)
                assert close(sum(weights.values()), 1) and "2021-05" not in weights
                wm = sum(w*g.loc[g.year_month.eq(m) & g[col].eq(work), "energy_kwh"].mean() for m, w in weights.items())
                rm = sum(w*g.loc[g.year_month.eq(m) & g[col].eq(rest), "energy_kwh"].mean() for m, w in weights.items())
                assert row.n_days == 351 and all(close(w, len(g.loc[g.year_month.eq(m)])/len(g)) for m, w in weights.items())
            else:
                wm = g.loc[g[col].eq(work), "energy_kwh"].mean()
                rm = g.loc[g[col].eq(rest), "energy_kwh"].mean()
            assert close(row.work_mean_kwh, wm) and close(row.rest_mean_kwh, rm)
            assert close(row.difference_kwh, rm-wm) and close(row.relative_difference_pct, (rm-wm)/wm*100)
        check(True, scheme + " monthly/seasonal/raw and matched-weight differences independently recomputed")
        r = comp.loc[comp.scheme.eq(scheme) & comp.scope.eq("month_standardized")].iloc[0]
        hp = standardized_profiles.loc[standardized_profiles.scheme.eq(scheme)]
        check(len(hp) == 24 and close(hp.difference_kw.sum(), r.difference_kwh) and close(hp.work_mean_power_kw.sum(), r.work_mean_kwh) and close(hp.rest_mean_power_kw.sum(), r.rest_mean_kwh), scheme + " matched hourly profiles integrate to standardized daily means/difference")
    for row in monthly_profiles.itertuples():
        col = "natural_day_type" if row.scheme == "natural" else "actual_day_type"
        g = selected.loc[selected.year_month.eq(row.year_month) & selected[col].eq(row.day_type) & selected.hour.eq(row.hour)]
        assert len(g) == row.n_days and close(g.mean_power_kw.mean(), row.mean_power_kw)
    check(True, "every within-month hourly mean independently recomputed")
    for frame in [comp, sensitivity]:
        check(frame.bootstrap_repetitions.eq(2000).all() and frame.seed.eq(42).all(), "bootstrap settings frozen to 2000 repetitions and seed 42")
        adequate = frame.valid_bootstrap_repetitions >= 1900
        check(frame.loc[adequate, "ci_low_kwh"].notna().all() and frame.loc[~adequate, "ci_low_kwh"].isna().all(), "intervals withheld if fewer than 95 percent of bootstrap draws support both groups")
        available = frame.ci_low_kwh.notna()
        assert (frame.loc[available, "ci_low_kwh"] <= frame.loc[available, "ci_high_kwh"]).all()
    check(set(sensitivity.block_days) == {1, 3, 7, 14} and len(sensitivity) == 16, "all four block-length sensitivities reported for both estimands and schemes")
    acf = read("autocorrelation_diagnostics.csv")
    series = d.set_index("date").energy_kwh
    for row in acf.itertuples():
        s = series if row.series == "raw" else series-series.groupby(series.index.strftime("%Y-%m")).transform("mean")
        pairs = pd.concat([s, s.shift(row.lag_calendar_days)], axis=1).dropna()
        assert row.n_pairs == len(pairs) and close(row.pearson_correlation, pairs.iloc[:, 0].corr(pairs.iloc[:, 1]))
    check(True, "autocorrelations use actual calendar lags and preserve gaps")
    source_manifest = json.loads((HERE / "sources/source_manifest.json").read_text(encoding="utf-8"))
    for entry in source_manifest:
        source = HERE / "sources" / entry["local_file"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == entry["sha256"]
        assert str(entry["year"]) in source.read_text(encoding="utf-8")
        assert entry["source_url"].startswith("https://app.www.gov.cn/") and entry["retrieved_at"]
    check(True, "two official notice snapshots have source URLs, retrieval timestamps and matching hashes")
    manifest = json.loads((OUT / "derivation_manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["inputs"] + manifest["outputs"]:
        path = ROOT / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], str(path)
    check(True, "all recorded input/source/code and output hashes match")
    check(len(list((HERE / "reports/figures").glob("*.png"))) == 6 and (HERE / "reports/task03_report.html").exists() and (HERE / "reports/task03_report.md").exists(), "six figures and both readable report formats delivered")
    text = (HERE / "reports/task03_report.html").read_text(encoding="utf-8")
    check(text.count("data:image/png;base64,") == 6 and "<table>" in text, "single-file HTML embeds all figures and actual tables")
    print("\n".join(LOG))
    print(f"\nALL PASS ({len(LOG)} checks)")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        LOG.append("ERROR " + repr(exc))
        (HERE / "reports/verify_task03.txt").write_text("\n".join(LOG), encoding="utf-8")
        raise
    (HERE / "reports/verify_task03.txt").write_text("\n".join(LOG) + f"\nALL PASS ({len(LOG)} checks)\n", encoding="utf-8")
