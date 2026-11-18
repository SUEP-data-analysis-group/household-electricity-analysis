from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/derived/task06"
REPORT = ROOT / "task06/reports"
VERSION = "task06_v1.0.0_20261118"
TZ = "Asia/Shanghai"
START = pd.Timestamp("2021-05-31", tz=TZ)
VAL = pd.Timestamp("2022-03-09", tz=TZ)
TEST = pd.Timestamp("2022-04-06", tz=TZ)
END = pd.Timestamp("2022-06-01", tz=TZ)
HOUR = pd.Timedelta(hours=1)
DAY = pd.Timedelta(days=1)
Q = 0.7326097666666669
MODELS = ["B1", "B2", "Linear-L1", "Full", "NoCalendar", "No168Stats"]
INPUTS = [
    "data/derived/task02/hourly_panel13.csv",
    "task01/reports/panel_definition.json",
    "task01/reports/split_manifest.json",
    "task01/reports/forecast_origin_quality.csv",
    "task01/reports/strict_hourly_check.csv",
    "data/derived/task03/holiday_calendar_2021_2022.csv",
    "task03/sources/holiday_rules.json",
    "data/derived/task04/thresholds.json",
]
DEVICES = ["electric_kettle_w", "fridge_w", "computer_w", "tv_w",
           "upstairs_water_heater_w", "downstairs_water_heater_w", "washing_machine_w",
           *[f"air_conditioner_{i}_w" for i in range(1, 7)]]
HOLIDAYS = ["", "元旦", "春节", "清明节", "劳动节", "端午节", "中秋节", "国庆节"]
CATEGORIES = {
    "horizon": list(range(24)), "weekday": list(range(7)), "month": list(range(1, 13)),
    "natural_weekend": [0, 1], "actual_workday": [0, 1],
    "is_holiday_break": [0, 1], "is_makeup_workday": [0, 1],
    "holiday_name": HOLIDAYS, "makeup_for_holiday": HOLIDAYS,
}
CAL_FEATURES = list(CATEGORIES)[1:]
NUMERIC = ["lag24", "lag168", "recent",
           *[f"{s}_{w}h" for w in (24, 168) for s in ("mean", "std", "min", "max")]]
LGB_FIXED = dict(objective="regression_l1", metric="l1", device_type="cpu",
                 learning_rate=0.05, max_depth=4, random_state=42,
                 n_jobs=min(4, os.cpu_count() or 1), deterministic=True,
                 force_col_wise=True, subsample=1.0, subsample_freq=0,
                 colsample_bytree=1.0, verbosity=-1)
LGB_CANDIDATES = [dict(n_estimators=t, num_leaves=l, min_child_samples=n)
                  for t in (200, 500) for l in (7, 15) for n in (80, 40)]
ALPHAS = [0.0001, 0.001, 0.01, 0.1]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False,
                               default=lambda v: v.item() if isinstance(v, np.generic) else str(v)) + "\n",
                    encoding="utf-8")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def csv(df, name):
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / name, index=False, encoding="utf-8-sig")


def read_csv(path, **kwargs):
    return pd.read_csv(path, float_precision="round_trip", **kwargs)


def timestamps(series):
    return pd.to_datetime(series, utc=True).dt.tz_convert(TZ)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def protected_paths():
    return [p for p in git("ls-files", "-z").split("\0")
            if p.split("/")[0] in [f"task{i:02d}" for i in range(1, 6)]
            or p.startswith(("data/raw/", "data/standardized/", "data/derived/task01/",
                             "data/derived/task02/", "data/derived/task03/",
                             "data/derived/task04/", "data/derived/task05/"))]


def config():
    return dict(version=VERSION, timezone=TZ, data_version="cn_obee_v1_noimpute_v1.0.0",
                panel="panel13/v1.0.0", devices=DEVICES, inputs=INPUTS,
                target="mean_power_kw", unit="kW", dtype="float64", imputation=0,
                target_semantics="hourly time mean of SUM of fixed 13 monitored devices",
                splits={k: [str(a), str(b)] for k, a, b in
                        [("train", START, VAL), ("validation", VAL, TEST), ("test", TEST, END)]},
                release="D 00:00; horizons 0..23", latency_hours=[0, 1],
                availability="s + 1h + latency <= origin; source_timestamp < origin",
                windows={"0h": "[D-24h,D), [D-168h,D); recent D-1h",
                         "1h": "[D-25h,D-1h), [D-169h,D-1h); recent D-2h"},
                lag24_fallback="1h h=23 only: lag48 when nominal lag24 not yet published; no missing-value fallback",
                numeric_features=NUMERIC, categorical_features=CATEGORIES,
                encoding="fixed full one-hot categories for ALL learning models; no load-derived categories",
                scaling="Linear-L1 numeric only StandardScaler fitted on respective fit rows",
                release_eligibility="known complete 168h history, required lags and published calendar only",
                target_complete="all 24 strict labels finite; post-release scoring only",
                common_score_mask="release eligible AND target_complete, frozen before any scores; same for ablations",
                fit_eligibility="common mask and ALL day labels available at fit_cutoff",
                validation_selection="validation common mask AND all labels available at test_start",
                initial_fit_cutoff=str(VAL), refit_cutoff=str(TEST),
                training="one shared horizon model; initial train fit; select on validation MAE; refit once before test; fixed during test",
                linear=dict(quantile=0.5, solver="highs", alphas=ALPHAS,
                            solver_options={"threads": min(4, os.cpu_count() or 1)},
                            tie_break="MAE within 1e-12 -> larger alpha"),
                lightgbm=dict(fixed=LGB_FIXED, candidates=LGB_CANDIDATES,
                              early_stopping=False,
                              tie_break="within 1e-12 -> fewer trees, fewer leaves, larger min_child_samples"),
                ablations={"NoCalendar": "remove all calendar fields; retain horizon",
                           "No168Stats": "remove only 168h mean/std/min/max; retain lag168"},
                ablation_parameters="Full selected parameters, no independent search",
                prediction_postprocess="max(raw_pred,0); save raw and clipped counts",
                primary_metric="MAE", secondary_metrics=["RMSE", "high_load", "daily_peak"],
                high_load=dict(q=Q, rule="y_true > q on common mask", fit_hours=6487,
                               metrics=["MAE_H", "Bias_H", "U_H", "under_rate", "conditional_gap",
                                        "gap_q90", "FNR_H", "over_mean_all"]),
                peak=dict(ties="exact unrounded float64", predicted_tie="earliest",
                          main="min(abs(t_true - earliest_predicted_peak)); ordinary within-day hours",
                          secondary=["circular earliest-predicted distance", "mean nearest ordinary distance over all predicted ties"],
                          true_flat="timing NA; amplitude retained", pred_flat="retained; earliest=0"),
                bootstrap=dict(B=10000, seed=42, interval=[2.5, 97.5], valid_fraction=0.95,
                               primary="8 non-overlapping 7-day blocks anchored 2022-04-06; sample 8 with replacement",
                               sensitivity="non-circular moving day blocks L=3,7,14; uniform starts 0..56-L; concatenate ceil(56/L), truncate 56",
                               pairing="same sampled days for all models and metrics; recompute subset numerator/denominator",
                               uncertainty_target="frozen forecast evaluation metrics, NOT future-load prediction intervals"),
                stable_improvement="for EACH B1 and B2: Full-baseline MAE<0, primary 95% upper<0, >=6/8 weekly differences<0",
                practical_improvement_delta=None, tau_U=None, tau_P=None, tau_T=None,
                p_day=None, p_high=None, noninferiority_epsilon=None,
                case_rules=["first complete test day", "highest true test peak (post-hoc diagnostic)",
                            "worst Full daily test MAE (post-hoc diagnostic)"],
                limitations=["one household panel, fixed published data and assumed availability",
                             "test 2022-04-06..2022-05-31 only; no annual/cross-household claim",
                             "upstream per-point filling unknown; new imputation=0",
                             "upstream full-period descriptive work informed design; retrospective exploration",
                             "no online release logs or simulation of training/service latency",
                             "hours/days/weeks not proved independent; N_eff not estimated; only 8 blocks",
                             "10000 draws are not new observations; cross-week dependence and nonstationarity matter",
                             "horizon/ablation intervals are marginal, no simultaneous significance claim",
                             "CI crossing zero does not show equivalence/noninferiority"])


@contextmanager
def timed(stage, **extra):
    OUT.mkdir(parents=True, exist_ok=True)
    proc = psutil.Process()
    t = time.perf_counter()
    before = proc.memory_info().rss
    row = dict(stage=stage, started_at=now(), rss_before_bytes=before, **extra)
    try:
        yield row
        row["status"] = "ok"
    except Exception as exc:
        row.update(status="error", error=repr(exc))
        raise
    finally:
        row.update(wall_seconds=time.perf_counter() - t,
                   rss_after_bytes=proc.memory_info().rss,
                   process_peak_rss_bytes=getattr(proc.memory_info(), "peak_wset", "unknown"))
        with (OUT / "training_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        print(json.dumps(row, ensure_ascii=False, default=str), flush=True)
