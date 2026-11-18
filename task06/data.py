"""Online information construction is intentionally separate from future-label masks."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .common import *


def load_inputs():
    hourly = read_csv(ROOT / INPUTS[0])
    hourly["timestamp"] = timestamps(hourly.timestamp)
    hourly = hourly.set_index("timestamp")
    expected = pd.date_range(START, END, inclusive="left", freq="h")
    assert hourly.index.is_unique and hourly.index.equals(expected)
    assert hourly.panel_id.eq("panel13").all()
    assert hourly.data_version.eq("cn_obee_v1_noimpute_v1.0.0").all()
    assert hourly.mean_power_kw.notna().equals(hourly.hour_complete)
    assert int(hourly.hour_complete.sum()) == 8503
    panel = read_json(ROOT / INPUTS[1])
    assert panel["main_panel"] == "panel13" and panel["panel_version"] == "v1.0.0"
    assert next(p["devices"] for p in panel["panels"] if p["panel_id"] == "panel13") == DEVICES
    threshold = read_json(ROOT / INPUTS[-1])
    assert threshold["train_hourly_load_q90_kw"] == Q and threshold["train_strict_hours"] == 6487
    split = read_json(ROOT / INPUTS[2])
    for name, a, b in [("train", START, VAL), ("validation", VAL, TEST), ("test", TEST, END)]:
        assert [pd.Timestamp(t) for t in split[name]] == [a, b]
    strict = read_csv(ROOT / INPUTS[4])
    strict = strict.loc[strict.panel_id.eq("panel13")].copy()
    strict["timestamp"] = timestamps(strict.timestamp)
    strict = strict.set_index("timestamp").reindex(expected)
    assert strict.mean_power_kw.isna().equals(hourly.mean_power_kw.isna())
    np.testing.assert_allclose(strict.mean_power_kw, hourly.mean_power_kw, atol=1e-12, rtol=0, equal_nan=True)
    calendar = read_csv(ROOT / INPUTS[5], keep_default_na=False)
    calendar["date"] = timestamps(calendar.date)
    assert calendar.date.is_unique and len(calendar) == 730
    calendar["public_date"] = calendar.date.dt.year.map({2021: "2020-11-26", 2022: "2021-10-25"})
    calendar["public_available_at"] = timestamps(calendar.public_date) + DAY
    calendar["public_time_assumption"] = "unknown time-of-day; next local midnight conservatively"
    # utc=True above parses date-only strings as UTC: localize public dates explicitly instead.
    calendar["public_available_at"] = pd.to_datetime(calendar.public_date).dt.tz_localize(TZ) + DAY
    return hourly, calendar.set_index("date")


def origin_features(y, calendar, origin, latency):
    """No target labels, target completeness or retrospective QC are accepted by this API."""
    cutoff = origin - latency * HOUR
    available = y.loc[(y.index + (1 + latency) * HOUR <= origin) & (y.index < origin)]
    window_index = pd.date_range(cutoff - 168 * HOUR, cutoff, inclusive="left", freq="h")
    hist = available.reindex(window_index).to_numpy(dtype="float64")
    history_complete = bool(np.isfinite(hist).all())
    row_cal = calendar.loc[origin.normalize()]
    calendar_known = row_cal.public_available_at <= origin
    feats, audit = [], []
    for w in (24, 168):
        vals = hist[-w:]
        for stat in ("mean", "std", "min", "max"):
            audit.append(dict(horizon="all", feature=f"{stat}_{w}h", kind="history",
                              nominal_source_start=cutoff-w*HOUR, source_start=cutoff-w*HOUR,
                              latest_source_time=cutoff-HOUR,
                              available_at=cutoff+latency*HOUR, fallback=False, fallback_reason=""))
    audit.append(dict(horizon="all", feature="recent", kind="history",
                      nominal_source_start=cutoff-HOUR, source_start=cutoff-HOUR,
                      latest_source_time=cutoff-HOUR, available_at=origin,
                      fallback=False, fallback_reason=""))
    for h in range(24):
        target = origin + h * HOUR
        f = dict(horizon=h, weekday=target.dayofweek, month=target.month,
                 natural_weekend=int(target.dayofweek >= 5),
                 actual_workday=int(row_cal.actual_day_type == "actual_workday"),
                 is_holiday_break=int(str(row_cal.is_holiday_break).lower() == "true"),
                 is_makeup_workday=int(str(row_cal.is_makeup_workday).lower() == "true"),
                 holiday_name=row_cal.holiday_name, makeup_for_holiday=row_cal.makeup_for_holiday)
        for lag in (24, 168):
            nominal = target-lag*HOUR
            fallback = lag == 24 and nominal+(1+latency)*HOUR > origin
            actual = target-48*HOUR if fallback else nominal
            f[f"lag{lag}"] = available.get(actual, np.nan)
            audit.append(dict(horizon=str(h), feature=f"lag{lag}", kind="history",
                              nominal_source_start=nominal, source_start=actual,
                              latest_source_time=actual, available_at=actual+(1+latency)*HOUR,
                              fallback=fallback,
                              fallback_reason="nominal_not_published" if fallback else ""))
        f["recent"] = hist[-1]
        for w in (24, 168):
            vals = hist[-w:]
            for stat, fn in [("mean", np.mean), ("std", np.std), ("min", np.min), ("max", np.max)]:
                f[f"{stat}_{w}h"] = float(fn(vals)) if np.isfinite(vals).all() else np.nan
        feats.append(f)
    for feature in CAL_FEATURES:
        audit.append(dict(horizon="all", feature=feature, kind="calendar",
                          nominal_source_start=origin, source_start=origin,
                          latest_source_time=origin, available_at=row_cal.public_available_at,
                          fallback=False, fallback_reason="", notice_date=row_cal.notice_date,
                          public_date=row_cal.public_date, source_url=row_cal.source_url))
    frame = pd.DataFrame(feats)
    known_inputs = bool(np.isfinite(frame[NUMERIC].to_numpy()).all())
    release = history_complete and known_inputs and calendar_known
    reasons = []
    if not history_complete:
        reasons.append("incomplete_available_168h_history")
    if not known_inputs:
        reasons.append("missing_required_history_feature")
    if not calendar_known:
        reasons.append("calendar_not_public")
    return frame, dict(history_complete=history_complete, release_eligible=release,
                       release_reason=";".join(reasons)), audit


def label_masks(y, origin, latency, release):
    target = y.reindex(pd.date_range(origin, periods=24, freq="h"))
    complete = bool(np.isfinite(target.to_numpy()).all())
    # A whole target day is available only after its final hour has been published.
    last_available = origin + DAY + latency * HOUR
    common = release and complete
    initial = common and origin < VAL and last_available <= VAL
    refit = common and origin < TEST and last_available <= TEST
    selection = common and VAL <= origin < TEST and last_available <= TEST
    reasons = []
    if not release:
        reasons.append("release_ineligible")
    if not complete:
        reasons.append("incomplete_strict_target_day")
    return dict(target_complete=complete, common_score_mask=common,
                fit_eligible_initial=initial, fit_eligible_refit=refit,
                fit_eligible=initial if origin < VAL else refit,
                validation_selection_mask=selection, last_label_available_at=last_available,
                exclusion_reason=";".join(reasons)), target.to_numpy(dtype="float64")


def build_scenario(hourly, calendar, latency):
    y = hourly.mean_power_kw
    features, rows, origins, audits = [], [], [], []
    for origin in pd.date_range(START, END, inclusive="left", freq="D"):
        split = "train" if origin < VAL else "validation" if origin < TEST else "test"
        f, online, audit = origin_features(y, calendar, origin, latency)
        quality, target = label_masks(y, origin, latency, online["release_eligible"])
        meta = dict(scenario=f"{latency}h", latency_hours=latency, origin=origin, split=split,
                    **online, **quality)
        origins.append(meta)
        for h in range(24):
            rows.append(dict(**meta, target_timestamp=origin+h*HOUR, horizon=h, y_true_kw=target[h]))
        features.append(f)
        audits.extend(dict(scenario=f"{latency}h", latency_hours=latency, origin=origin,
                           release_eligible=online["release_eligible"], **a) for a in audit)
    return pd.concat(features, ignore_index=True), pd.DataFrame(rows), pd.DataFrame(origins), pd.DataFrame(audits)


def feature_catalog():
    rows = []
    for f in [*CATEGORIES, *NUMERIC]:
        group = "horizon" if f == "horizon" else "calendar" if f in CAL_FEATURES else "168h_stats" if f.endswith("_168h") else "history"
        rows.append(dict(feature=f, group=group, dtype="category" if f in CATEGORIES else "float64",
                         categories=json.dumps(CATEGORIES.get(f), ensure_ascii=False),
                         definition=("population std ddof=0" if f.startswith("std_") else f),
                         source="published target calendar" if f in CATEGORIES else "strict mean_power_kw history",
                         source_rule="calendar public_available_at <= origin" if f in CATEGORIES else "source < origin; source+1h+latency <= origin",
                         retained_NoCalendar=group != "calendar", retained_No168Stats=group != "168h_stats"))
    return pd.DataFrame(rows)


def prepare():
    with timed("prepare_inputs_and_features") as timing:
        OUT.mkdir(parents=True, exist_ok=True)
        config_path = OUT / "experiment_config.json"
        expected = config()
        if config_path.exists():
            assert read_json(config_path) == expected, "Configuration changed: explicit new version required"
        else:
            write_json(config_path, expected)
        preserved = OUT / "upstream_preservation.json"
        if not preserved.exists():
            write_json(preserved, {p: sha(ROOT/p) for p in protected_paths()})
        hourly, calendar = load_inputs()
        write_json(OUT/"input_manifest.json", dict(start_commit=git("rev-parse", "HEAD"),
                   branch=git("branch", "--show-current"), created_at=now(),
                   upstream_versions={"task02": "task02_v1.1.0_20261113", "task03": "task03_v1.1.0_20261113", "task04": "task04_v1.0.1_20261114"},
                   inputs=[dict(path=p, actual_path=str(ROOT/p), sha256=sha(ROOT/p)) for p in INPUTS],
                   strict_label_max_abs_difference=float(np.nanmax(np.abs(hourly.mean_power_kw.to_numpy()-
                       read_csv(ROOT/INPUTS[4]).query("panel_id == 'panel13'").mean_power_kw.to_numpy())))))
        all_quality, all_masks, all_audits, support = [], [], [], []
        for latency in (0, 1):
            x, meta, quality, audit = build_scenario(hourly, calendar, latency)
            x.to_pickle(OUT/f"features_{latency}h.pkl")
            meta.to_pickle(OUT/f"samples_{latency}h.pkl")
            all_quality.append(quality)
            all_masks.append(meta.drop(columns="y_true_kw"))
            all_audits.append(audit)
            for split, g in quality.groupby("split", sort=False):
                support.append(dict(scenario=f"{latency}h", split=split, calendar_origins=len(g),
                    release_origins=int(g.release_eligible.sum()),
                    complete_target_origins=int(g.target_complete.sum()),
                    score_origins=int(g.common_score_mask.sum()), score_hours=int(g.common_score_mask.sum()*24),
                    initial_fit_origins=int(g.fit_eligible_initial.sum()), refit_origins=int(g.fit_eligible_refit.sum()),
                    validation_selection_origins=int(g.validation_selection_mask.sum())))
            if latency == 0:
                assert [int(quality.loc[quality.split.eq(s), "common_score_mask"].sum()) for s in ("train", "validation", "test")] == [253,28,56]
                assert quality.fit_eligible_refit.sum() == 281
                upstream = read_csv(ROOT/INPUTS[3])
                assert quality.common_score_mask.tolist() == upstream.conservative_eligible_origin.tolist()
            timing[f"{latency}h_shape"] = list(x.shape)
        csv(pd.concat(all_quality), "origin_quality.csv")
        csv(pd.concat(all_masks), "common_score_mask.csv")
        csv(pd.concat(all_audits), "feature_availability_audit.csv")
        csv(feature_catalog(), "feature_catalog.csv")
        csv(calendar.reset_index(), "calendar_availability.csv")
        csv(pd.DataFrame(support), "sample_support.csv")
        write_json(OUT/"split_manifest.json", dict(upstream=read_json(ROOT/INPUTS[2]),
                   upstream_sha256=sha(ROOT/INPUTS[2]), scenarios=support))
        write_json(OUT/"prepared_state.json", dict(created_at=now(), config_sha256=sha(config_path),
                   mask_sha256=sha(OUT/"common_score_mask.csv"),
                   feature_hashes={f"{l}h": sha(OUT/f"features_{l}h.pkl") for l in (0,1)},
                   sample_hashes={f"{l}h": sha(OUT/f"samples_{l}h.pkl") for l in (0,1)}))
    print(pd.DataFrame(support).to_string(index=False), flush=True)
