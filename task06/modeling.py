from __future__ import annotations

import time
import warnings
from dataclasses import dataclass

import joblib
import lightgbm as lgb
from scipy import sparse
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import QuantileRegressor
from threadpoolctl import threadpool_limits

from .common import *


@dataclass
class Encoder:
    variant: str
    scaled: bool
    mean_: object = None
    scale_: object = None

    @property
    def numeric(self):
        return [f for f in NUMERIC if not (self.variant == "No168Stats" and f.endswith("_168h"))]

    @property
    def categorical(self):
        return [f for f in CATEGORIES if self.variant != "NoCalendar" or f == "horizon"]

    @property
    def columns(self):
        return self.numeric + [f"{f}__{i}" for f in self.categorical for i in range(len(CATEGORIES[f]))]

    def fit(self, x):
        values = x[self.numeric].to_numpy(dtype="float64")
        assert np.isfinite(values).all()
        self.mean_ = values.mean(axis=0) if self.scaled else np.zeros(len(self.numeric))
        self.scale_ = values.std(axis=0, ddof=0) if self.scaled else np.ones(len(self.numeric))
        self.scale_[self.scale_ == 0] = 1
        return self

    def transform(self, x):
        arr = [(x[self.numeric].to_numpy(dtype="float64")-self.mean_)/self.scale_]
        for f in self.categorical:
            assert x[f].isin(CATEGORIES[f]).all(), f"Unknown category {f}"
            arr.extend([(x[f].to_numpy() == value).astype("float64")[:, None] for value in CATEGORIES[f]])
        return pd.DataFrame(np.concatenate(arr, axis=1), columns=self.columns, index=x.index)


def fit_model(x, y, variant, params):
    enc = Encoder(variant, variant == "Linear-L1").fit(x)
    xx = enc.transform(x)
    t = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=LGB_FIXED["n_jobs"]):
        warnings.simplefilter("always")
        if variant == "Linear-L1":
            model = QuantileRegressor(quantile=0.5, alpha=params["alpha"], solver="highs",
                                     solver_options={"threads": LGB_FIXED["n_jobs"]})
            model.fit(sparse.csc_matrix(xx.to_numpy()), y)
        else:
            model = lgb.LGBMRegressor(**LGB_FIXED, **params)
            model.fit(xx, y)
    warning_text = [f"{w.category.__name__}: {w.message}" for w in caught]
    assert not any(issubclass(w.category, ConvergenceWarning) for w in caught), warning_text
    details = dict(fit_seconds=time.perf_counter()-t, solver_status="success",
                   solver_iterations=int(getattr(model, "n_iter_", getattr(model, "n_estimators_", 0))),
                   warnings=warning_text, encoded_dimensions=len(enc.columns))
    return dict(encoder=enc, model=model), details


def predict(bundle, x):
    xx = bundle["encoder"].transform(x)
    if isinstance(bundle["model"], QuantileRegressor):
        xx = sparse.csc_matrix(xx.to_numpy())
    raw = bundle["model"].predict(xx)
    assert np.isfinite(raw).all(), "Non-finite prediction is a program error"
    return np.asarray(raw, dtype="float64")


def assert_prepared():
    state = read_json(OUT/"prepared_state.json")
    assert state["config_sha256"] == sha(OUT/"experiment_config.json")
    assert state["mask_sha256"] == sha(OUT/"common_score_mask.csv")
    for l in (0, 1):
        assert state["feature_hashes"][f"{l}h"] == sha(OUT/f"features_{l}h.pkl")
        assert state["sample_hashes"][f"{l}h"] == sha(OUT/f"samples_{l}h.pkl")


def preflight():
    from .evaluation import bootstrap_indices
    assert_prepared()
    x = pd.read_pickle(OUT/"features_0h.pkl")
    meta = pd.read_pickle(OUT/"samples_0h.pkl")
    mask = meta.fit_eligible_initial
    results = {}
    for variant, params in [("Full", LGB_CANDIDATES[0]), ("Linear-L1", {"alpha": 0.001})]:
        with timed("preflight_fit", variant=variant, n_rows=int(mask.sum())) as row:
            bundle, details = fit_model(x.loc[mask], meta.loc[mask, "y_true_kw"], variant, params)
            predict(bundle, x.loc[mask].iloc[:24])
            row.update(details)
        results[variant] = row
    # Synthetic training-residual-shaped sufficient statistics, no validation/test score access.
    t = time.perf_counter()
    idx = bootstrap_indices("paired_week7", 500, 42)
    synthetic = np.random.default_rng(7).random((6, 56, 20))
    weights = np.stack([np.bincount(i, minlength=56) for i in idx])
    np.einsum("bd,mdk->bmk", weights, synthetic)
    bs_seconds = time.perf_counter()-t
    mem = psutil.virtual_memory()
    estimate = 2 * (10 * results["Full"]["wall_seconds"] + 5 * results["Linear-L1"]["wall_seconds"]) + bs_seconds*20*8
    prepare_log = [json.loads(s) for s in (OUT/"training_log.jsonl").read_text(encoding="utf-8").splitlines()
                   if json.loads(s)["stage"] == "prepare_inputs_and_features"][-1]
    report = dict(created_at=now(), python=sys.executable, python_version=sys.version,
                  platform=platform.platform(), processor=platform.processor() or "unknown",
                  logical_cpus=os.cpu_count(), physical_cpus=psutil.cpu_count(logical=False),
                  threads=LGB_FIXED["n_jobs"], total_memory_bytes=mem.total, available_memory_bytes=mem.available,
                  feature_build_measured=prepare_log, raw_feature_dimension=len(x.columns),
                  encoded_feature_dimension=results["Full"]["encoded_dimensions"], measured_fits=results,
                  bootstrap_preflight=dict(B=500, seconds_measured=bs_seconds,
                      input="synthetic training-shaped daily sufficient statistics; no held-out scores",
                      estimated_per_10000_seconds=bs_seconds*20,
                      caveat="quantile metric and report I/O add unmeasured overhead"),
                  estimated_total_training_bootstrap_seconds=estimate,
                  estimate_kind="extrapolation; not a measured full-run time",
                  memory_requirement_estimated_bytes=max(r["process_peak_rss_bytes"] if isinstance(r["process_peak_rss_bytes"], int) else r["rss_after_bytes"] for r in results.values())*3,
                  local_feasible=True, cloud_cpu_needed=False, gpu_needed=False,
                  rationale="6072 rows and compact CPU models fit in available local memory; empirical fits completed",
                  migration=dict(minimum="4 CPU threads, 8 GB RAM; no GPU",
                                 command="python -m pip install -r task06/requirements.txt && python task06/run_task06.py all",
                                 checkpoints="prepare -> preflight -> train -> predict -> evaluate -> report -> verify"))
    write_json(OUT/"resource_preflight.json", report)


def select_candidate(rows, family):
    best = min(r["validation_mae_kw"] for r in rows)
    tied = [r for r in rows if r["validation_mae_kw"] <= best + 1e-12]
    if family == "Linear-L1":
        return max(tied, key=lambda r: r["params"]["alpha"])
    return min(tied, key=lambda r: (r["params"]["n_estimators"], r["params"]["num_leaves"], -r["params"]["min_child_samples"]))


def train():
    assert_prepared()
    assert (OUT/"resource_preflight.json").exists()
    assert not (OUT/"predictions.csv").exists(), "Refusing retraining after test predictions; create an explicit revised experiment version"
    model_dir = OUT/"models"
    model_dir.mkdir(exist_ok=True)
    selections, searches, index, val_predictions = {}, [], [], []
    for latency in (0, 1):
        scenario = f"{latency}h"
        x = pd.read_pickle(OUT/f"features_{scenario}.pkl")
        meta = pd.read_pickle(OUT/f"samples_{scenario}.pkl")
        fit = meta.fit_eligible_initial
        selection = meta.validation_selection_mask
        chosen_bundles, selected = {}, {}
        for family, candidates in [("Linear-L1", [dict(alpha=a) for a in ALPHAS]), ("Full", LGB_CANDIDATES)]:
            candidate_rows, bundles = [], []
            for i, params in enumerate(candidates):
                with timed("validation_candidate", scenario=scenario, model=family, candidate=i,
                           params=params, fit_cutoff=str(VAL), n_fit=int(fit.sum()),
                           n_selection=int(selection.sum())) as log:
                    bundle, details = fit_model(x.loc[fit], meta.loc[fit,"y_true_kw"], family, params)
                    raw = predict(bundle, x.loc[selection])
                    mae = float(np.mean(np.abs(np.maximum(raw,0)-meta.loc[selection,"y_true_kw"].to_numpy())))
                    log.update(details, validation_mae_kw=mae)
                result = dict(scenario=scenario, family=family, candidate=i, params=params,
                              validation_mae_kw=mae, n_fit=int(fit.sum()), n_selection=int(selection.sum()),
                              fit_cutoff=str(VAL), selection_cutoff=str(TEST), **details)
                candidate_rows.append(result)
                bundles.append(bundle)
            chosen = select_candidate(candidate_rows, family)
            chosen_bundles[family] = bundles[chosen["candidate"]]
            selected[family] = chosen["params"]
            searches.extend(dict(**r, selected=r["candidate"] == chosen["candidate"]) for r in candidate_rows)
        for variant in ("NoCalendar", "No168Stats"):
            with timed("initial_ablation", scenario=scenario, model=variant, fit_cutoff=str(VAL), n_fit=int(fit.sum())) as log:
                bundle, details = fit_model(x.loc[fit], meta.loc[fit,"y_true_kw"], variant, selected["Full"])
                log.update(details)
            chosen_bundles[variant] = bundle
        for variant, bundle in chosen_bundles.items():
            version = f"{VERSION}_{scenario}_{variant}_initial"
            path = model_dir/f"{scenario}_{variant}_initial.joblib"
            joblib.dump(bundle, path)
            index.append(stage_record(meta, fit, bundle, scenario, variant, version, "initial_train", VAL, path))
            v = meta.loc[meta.split.eq("validation")].copy()
            v["raw_pred_kw"] = predict(bundle, x.loc[v.index])
            v["y_pred_kw"] = np.maximum(v.raw_pred_kw,0)
            v["model"] = variant
            v["model_stage"] = "initial_train"
            v["model_version"] = version
            v["fit_cutoff"] = VAL
            val_predictions.append(v)
        selections[scenario] = selected
    search_df = pd.DataFrame(searches)
    search_df["params"] = search_df.params.map(lambda p: json.dumps(p, sort_keys=True))
    csv(search_df, "validation_search.csv")
    csv(pd.concat(val_predictions, ignore_index=True), "validation_predictions.csv")
    # Freeze both scenarios before ANY test prediction; initial fitted processors are hashed.
    frozen = dict(config=read_json(OUT/"experiment_config.json"), selected_parameters=selections,
                  created_at=now(), source_code_hashes={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/"task06").glob("*.py")},
                  experiment_config_sha256=sha(OUT/"experiment_config.json"),
                  prepared_state=read_json(OUT/"prepared_state.json"),
                  initial_model_hashes={p.name:sha(p) for p in model_dir.glob("*_initial.joblib")})
    write_json(OUT/"experiment_config_frozen.json", frozen)
    (OUT/"experiment_config_frozen.sha256").write_text(sha(OUT/"experiment_config_frozen.json")+"\n", encoding="ascii")
    for latency in (0, 1):
        scenario = f"{latency}h"
        x = pd.read_pickle(OUT/f"features_{scenario}.pkl")
        meta = pd.read_pickle(OUT/f"samples_{scenario}.pkl")
        fit = meta.fit_eligible_refit
        for variant in MODELS[2:]:
            params = selections[scenario]["Linear-L1" if variant == "Linear-L1" else "Full"]
            with timed("one_time_refit", scenario=scenario, model=variant, params=params,
                       fit_cutoff=str(TEST), n_fit=int(fit.sum())) as log:
                bundle, details = fit_model(x.loc[fit], meta.loc[fit,"y_true_kw"], variant, params)
                log.update(details)
            path = model_dir/f"{scenario}_{variant}_refit.joblib"
            joblib.dump(bundle, path)
            version = f"{VERSION}_{scenario}_{variant}_refit"
            index.append(stage_record(meta, fit, bundle, scenario, variant, version, "train_validation_refit", TEST, path))
    csv(pd.DataFrame(index), "model_stage_index.csv")


def stage_record(meta, fit, bundle, scenario, variant, version, stage, cutoff, path):
    return dict(scenario=scenario, model=variant, model_stage=stage, model_version=version,
                fit_cutoff=str(cutoff), n_fit_rows=int(fit.sum()), n_fit_origins=int(meta.loc[fit,"origin"].nunique()),
                first_fit_target=str(meta.loc[fit,"target_timestamp"].min()),
                last_fit_target=str(meta.loc[fit,"target_timestamp"].max()),
                last_fit_label_available_at=str(meta.loc[fit,"last_label_available_at"].max()),
                model_path=str(path.relative_to(ROOT)), model_sha256=sha(path),
                numeric_features=json.dumps(bundle["encoder"].numeric),
                categorical_features=json.dumps(bundle["encoder"].categorical),
                encoded_columns=json.dumps(bundle["encoder"].columns),
                scaler_mean=json.dumps(bundle["encoder"].mean_.tolist()),
                scaler_scale=json.dumps(bundle["encoder"].scale_.tolist()))


def frozen_check():
    frozen_path = OUT/"experiment_config_frozen.json"
    expected = (OUT/"experiment_config_frozen.sha256").read_text().strip()
    assert sha(frozen_path) == expected
    frozen = read_json(frozen_path)
    assert frozen["experiment_config_sha256"] == sha(OUT/"experiment_config.json")
    assert_prepared()
    for name, value in frozen["initial_model_hashes"].items():
        assert sha(OUT/"models"/name) == value
    return frozen


def make_predictions():
    frozen_check()
    frames = []
    with timed("frozen_predictions"):
        for latency in (0, 1):
            scenario = f"{latency}h"
            x = pd.read_pickle(OUT/f"features_{scenario}.pkl")
            meta = pd.read_pickle(OUT/f"samples_{scenario}.pkl")
            for variant in MODELS:
                result = meta.copy()
                raw = np.full(len(meta), np.nan, dtype="float64")
                release = meta.release_eligible
                result["model"] = variant
                result["model_stage"] = "baseline"
                result["model_version"] = f"{VERSION}_{scenario}_{variant}"
                result["fit_cutoff"] = "not_fitted"
                if variant in ("B1", "B2"):
                    raw[release] = x.loc[release, "lag24" if variant == "B1" else "lag168"]
                else:
                    for is_test, suffix, stage, cutoff in [(False,"initial","initial_train",VAL),
                                                          (True,"refit","train_validation_refit",TEST)]:
                        choose = release & (meta.split.eq("test") if is_test else ~meta.split.eq("test"))
                        bundle = joblib.load(OUT/"models"/f"{scenario}_{variant}_{suffix}.joblib")
                        raw[choose] = predict(bundle, x.loc[choose])
                        stage_rows = meta.split.eq("test") if is_test else ~meta.split.eq("test")
                        result.loc[stage_rows,"model_stage"] = stage
                        result.loc[stage_rows,"model_version"] = f"{VERSION}_{scenario}_{variant}_{suffix}"
                        result.loc[stage_rows,"fit_cutoff"] = str(cutoff)
                assert np.isfinite(raw[meta.common_score_mask]).all()
                result["raw_pred_kw"] = raw
                result["y_pred_kw"] = np.maximum(raw,0)
                result["negative_clipped"] = raw < 0
                result["score_mask"] = meta.common_score_mask
                result["evaluation_role"] = np.where(meta.split.eq("train"), "fit_diagnostic", "out_of_sample")
                result["baseline_definition"] = ("lag24_else_lag48" if latency == 1 else "lag24") if variant == "B1" else "lag168" if variant == "B2" else ""
                result.loc[~release,"exclusion_reason"] = result.loc[~release,"exclusion_reason"] + ";" + meta.loc[~release,"release_reason"]
                frames.append(result)
        prediction = pd.concat(frames, ignore_index=True)
        csv(prediction, "predictions.csv")
        csv(prediction.loc[prediction.model.isin(["B1","B2"])], "baseline_predictions.csv")
        csv(prediction.groupby(["scenario","split","model"], as_index=False).agg(
            clipped_count=("negative_clipped","sum"), release_rows=("release_eligible","sum"),
            score_rows=("score_mask","sum")), "clipping_summary.csv")
        write_json(OUT/"prediction_state.json", dict(created_at=now(),
            frozen_sha256=sha(OUT/"experiment_config_frozen.json"), predictions_sha256=sha(OUT/"predictions.csv"),
            rows=len(prediction), test_forecasts_generated_after_frozen_config=True))
