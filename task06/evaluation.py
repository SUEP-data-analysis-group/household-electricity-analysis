"""Point metrics and paired calendar-block uncertainty from frozen predictions only."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

from .common import *

COMPARISONS = [("Full", "B1"), ("Full", "B2"), ("Full", "Linear-L1"),
               ("NoCalendar", "Full"), ("No168Stats", "Full")]
PEAK_FIELDS = ["peak_abs_kw", "peak_under_kw", "true_peak_gap_kw", "peak_time_h",
               "peak_time_circular_h", "predicted_ties_mean_distance_h"]
HIGH_FIELDS = ["MAE_H_kw", "Bias_H_kw", "U_H_kw", "under_rate_H", "conditional_gap_H_kw",
               "gap_q90_H_kw", "FNR_H", "over_mean_all_kw"]


def ratio(num, den):
    return float(num/den) if den else np.nan


def peak_metrics(y, p):
    y, p = np.asarray(y, dtype="float64"), np.asarray(p, dtype="float64")
    assert len(y) == len(p) == 24 and np.isfinite(y).all() and np.isfinite(p).all()
    true_set = np.flatnonzero(y == y.max())
    pred_set = np.flatnonzero(p == p.max())
    true_flat, pred_flat = len(true_set) == 24, len(pred_set) == 24
    ordinary = np.abs(true_set-pred_set[0])
    return dict(peak_abs_kw=float(abs(y.max()-p.max())),
                peak_under_kw=float(max(y.max()-p.max(),0)),
                true_peak_gap_kw=float(np.maximum(y[true_set]-p[true_set],0).mean()),
                peak_time_h=np.nan if true_flat else float(ordinary.min()),
                peak_time_circular_h=np.nan if true_flat else float(np.minimum(ordinary,24-ordinary).min()),
                predicted_ties_mean_distance_h=np.nan if true_flat else float(np.abs(pred_set[:,None]-true_set[None,:]).min(axis=1).mean()),
                true_peak_hours=json.dumps(true_set.tolist()), predicted_peak_hours=json.dumps(pred_set.tolist()),
                true_tie_count=len(true_set), predicted_tie_count=len(pred_set),
                true_flat=true_flat, predicted_flat=pred_flat, earliest_predicted_peak=int(pred_set[0]),
                true_peak_kw=float(y.max()), predicted_peak_kw=float(p.max()),
                timing_exclusion_reason="true_day_flat" if true_flat else "")


def high_metrics(y, p):
    y, p = np.asarray(y,dtype="float64"), np.asarray(p,dtype="float64")
    h = y > Q
    n = int(h.sum())
    gap = np.maximum(y[h]-p[h],0)
    under = gap > 0
    return dict(n_H=n, MAE_H_kw=ratio(np.abs(p[h]-y[h]).sum(),n),
                Bias_H_kw=ratio((p[h]-y[h]).sum(),n), U_H_kw=ratio(gap.sum(),n),
                under_rate_H=ratio(under.sum(),n), conditional_gap_H_kw=ratio(gap.sum(),under.sum()),
                gap_q90_H_kw=float(np.quantile(gap,.9,method="linear")) if n else np.nan,
                FNR_H=ratio((p[h] <= Q).sum(),n), over_mean_all_kw=ratio(np.maximum(p-y,0).sum(),len(y)),
                high_subset_reason="" if n else "empty_high_load_subset",
                conditional_gap_reason="" if under.any() else "no_underestimation" if n else "empty_high_load_subset")


def simple_metrics(g):
    error = g.y_pred_kw.to_numpy()-g.y_true_kw.to_numpy()
    return dict(n_hours=len(g), MAE_kw=float(np.abs(error).mean()), RMSE_kw=float(np.sqrt((error**2).mean())))


def bootstrap_indices(algorithm, B=10000, seed=42):
    rng = np.random.default_rng(seed)
    if algorithm == "paired_week7":
        week = rng.integers(0,8,size=(B,8))
        return (week[:,:,None]*7 + np.arange(7)[None,None,:]).reshape(B,56)
    length = int(algorithm.rsplit("_",1)[1])
    assert length in (3,7,14)
    starts = rng.integers(0,56-length+1,size=(B,math.ceil(56/length)))
    return (starts[:,:,None]+np.arange(length)[None,None,:]).reshape(B,-1)[:,:56]


def publish_interval(values, B=10000):
    valid = values[np.isfinite(values)]
    n = len(valid)
    if n < .95*B:
        return dict(ci_low=np.nan, ci_high=np.nan, valid_repetitions=n,
                    interval_reason="fewer_than_95_percent_valid_repetitions")
    lo, hi = np.percentile(valid,[2.5,97.5],method="linear")
    return dict(ci_low=float(lo), ci_high=float(hi), valid_repetitions=n, interval_reason="")


def daily_statistics(test):
    """Sufficient statistics preserve denominators; RMSE is rooted after aggregation."""
    values = {}
    gaps = []
    peaks = []
    for model in MODELS:
        m = test.loc[test.model.eq(model)].sort_values(["origin","horizon"])
        assert len(m) == 56*24
        y = m.y_true_kw.to_numpy().reshape(56,24)
        p = m.y_pred_kw.to_numpy().reshape(56,24)
        valid = m.score_mask.to_numpy().reshape(56,24)
        assert np.isfinite(p[valid]).all() and np.isfinite(y[valid]).all()
        e = np.where(valid,p-y,0)
        h = valid & (y>Q)
        gap = np.where(h,np.maximum(y-p,0),0)
        u = h & (p<y)
        n, nh, nu = valid.sum(1), h.sum(1), u.sum(1)
        stats = {
            "MAE_kw": (np.abs(e).sum(1),n), "RMSE_kw": ((e**2).sum(1),n),
            "MAE_H_kw": (np.where(h,np.abs(e),0).sum(1),nh),
            "Bias_H_kw": (np.where(h,e,0).sum(1),nh), "U_H_kw": (gap.sum(1),nh),
            "under_rate_H": (nu,nh), "conditional_gap_H_kw": (gap.sum(1),nu),
            "FNR_H": ((h & (p<=Q)).sum(1),nh),
            "over_mean_all_kw": (np.maximum(e,0).sum(1),n),
        }
        peak_rows = [peak_metrics(y[d],p[d]) if valid[d].all() else {f:np.nan for f in PEAK_FIELDS} for d in range(56)]
        peaks.append(peak_rows)
        for f in PEAK_FIELDS:
            a = np.array([r[f] for r in peak_rows],dtype=float)
            stats[f] = (np.nan_to_num(a),np.isfinite(a).astype(int))
        values[model] = stats
        gaps.append((gap[h], np.repeat(np.arange(56),24).reshape(56,24)[h]))
    return values, gaps


def repeated_q90(gap, day, weights):
    """Exact linear quantile of an integer-multiplicity sample, without expanding hours."""
    if not len(gap):
        return np.full(len(weights),np.nan)
    order = np.argsort(gap,kind="stable")
    gap, day = gap[order],day[order]
    counts = weights[:,day]
    cumulative = counts.cumsum(axis=1)
    n = cumulative[:,-1]
    position = (n-1)*.9
    low_rank = np.floor(position).astype(int)
    high_rank = np.ceil(position).astype(int)
    low = (cumulative <= low_rank[:,None]).sum(axis=1).clip(0,len(gap)-1)
    high = (cumulative <= high_rank[:,None]).sum(axis=1).clip(0,len(gap)-1)
    result = gap[low]+(gap[high]-gap[low])*(position-low_rank)
    result[n==0] = np.nan
    return result


def uncertainty(test, B=10000):
    rows = []
    replicate_checks = []
    for scenario, g in test.groupby("scenario",sort=False):
        stats, gaps = daily_statistics(g)
        names = list(stats[MODELS[0]])
        num = np.stack([[stats[m][f][0] for f in names] for m in MODELS])
        den = np.stack([[stats[m][f][1] for f in names] for m in MODELS])
        point = {}
        for j,f in enumerate(names):
            point[f] = np.divide(num[:,j,:].sum(1),den[:,j,:].sum(1),out=np.full(6,np.nan),where=den[:,j,:].sum(1)>0)
            if f == "RMSE_kw":
                point[f] = np.sqrt(point[f])
        point["gap_q90_H_kw"] = np.array([np.quantile(a,.9,method="linear") if len(a) else np.nan for a,d in gaps])
        for algorithm in ("paired_week7","moving_day_3","moving_day_7","moving_day_14"):
            with timed("bootstrap", scenario=scenario, algorithm=algorithm, B=B):
                indices = bootstrap_indices(algorithm,B,42)
                np.savez_compressed(OUT/f"bootstrap_indices_{scenario}_{algorithm}.npz",days=indices)
                samples = {f:np.empty((B,6)) for f in [*names,"gap_q90_H_kw"]}
                for begin in range(0,B,256):
                    ix = indices[begin:begin+256]
                    weights = np.stack([np.bincount(i,minlength=56) for i in ix])
                    ns = np.einsum("bd,mkd->bmk",weights,num,optimize=True)
                    ds = np.einsum("bd,mkd->bmk",weights,den,optimize=True)
                    z = np.divide(ns,ds,out=np.full_like(ns,np.nan),where=ds>0)
                    for j,f in enumerate(names):
                        samples[f][begin:begin+len(ix)] = np.sqrt(z[:,:,j]) if f == "RMSE_kw" else z[:,:,j]
                    for j,(gap,day) in enumerate(gaps):
                        samples["gap_q90_H_kw"][begin:begin+len(ix),j] = repeated_q90(gap,day,weights)
                for metric,values in samples.items():
                    for r in range(min(20,B)):
                        for j,m in enumerate(MODELS):
                            replicate_checks.append(dict(scenario=scenario,algorithm=algorithm,
                                replicate=r,model=m,metric=metric,value=values[r,j]))
                    for j,m in enumerate(MODELS):
                        rows.append(dict(scenario=scenario,algorithm=algorithm,metric=metric,
                            comparison=m, left_model=m, right_model="", point_estimate=point[metric][j],
                            B=B,seed=42,**publish_interval(values[:,j],B)))
                    for left,right in COMPARISONS:
                        a,b = MODELS.index(left),MODELS.index(right)
                        rows.append(dict(scenario=scenario,algorithm=algorithm,metric=metric,
                            comparison=f"{left}-{right}",left_model=left,right_model=right,
                            point_estimate=point[metric][a]-point[metric][b],B=B,seed=42,
                            **publish_interval(values[:,a]-values[:,b],B)))
    csv(pd.DataFrame(replicate_checks),"bootstrap_replicate_checks.csv")
    return pd.DataFrame(rows)


def evaluate():
    from .modeling import frozen_check
    frozen_check()
    prediction_state = read_json(OUT/"prediction_state.json")
    assert prediction_state["predictions_sha256"] == sha(OUT/"predictions.csv")
    with timed("point_evaluation"):
        pred = read_csv(OUT/"predictions.csv",keep_default_na=True)
        pred["origin"] = timestamps(pred.origin)
        pred["target_timestamp"] = timestamps(pred.target_timestamp)
        scored = pred.loc[pred.score_mask].copy()
        assert np.isfinite(scored[["y_true_kw","raw_pred_kw","y_pred_kw"]].to_numpy()).all()
        anchor = scored["split"].map({"train": START, "validation": VAL, "test": TEST})
        scored["week_block"] = ((scored.origin-anchor)/DAY).astype(int)//7
        overall, highs, daily, horizons, weeks, peaks = [],[],[],[],[],[]
        for keys,g in scored.groupby(["scenario","split","model"],sort=False):
            meta = dict(zip(["scenario","split","model"],keys))
            overall.append(dict(**meta,**simple_metrics(g), n_days=g.origin.nunique(),
                                evaluation_role="fit_diagnostic" if meta["split"] == "train" else "out_of_sample"))
            high = high_metrics(g.y_true_kw,g.y_pred_kw)
            high.update(n_H_days=g.loc[g.y_true_kw>Q,"origin"].nunique(),
                        n_H_week_blocks=g.loc[g.y_true_kw>Q,"week_block"].nunique(),
                        per_week_high_counts=json.dumps(g.loc[g.y_true_kw>Q].groupby("week_block").size().to_dict()))
            highs.append(dict(**meta,**high))
        for key,collection in [("origin",daily),("horizon",horizons),("week_block",weeks)]:
            for keys,g in scored.groupby(["scenario","split","model",key],sort=False):
                meta = dict(zip(["scenario","split","model",key],keys))
                collection.append(dict(**meta,**simple_metrics(g),n_H=int((g.y_true_kw>Q).sum())))
                if key == "origin" and len(g) == 24:
                    g = g.sort_values("horizon")
                    peaks.append(dict(**meta,**peak_metrics(g.y_true_kw,g.y_pred_kw)))
        overall, highs, daily, horizons, weeks, peaks = map(pd.DataFrame,[overall,highs,daily,horizons,weeks,peaks])
        for frame,name in [(overall,"metrics.csv"),(highs,"high_load_metrics.csv"),
                           (daily,"daily_metrics.csv"),(horizons,"horizon_metrics.csv"),
                           (weeks,"weekly_metrics.csv"),(peaks,"daily_peak_metrics.csv")]:
            csv(frame,name)
        comparisons=[]
        for (scenario,split),g in overall.groupby(["scenario","split"],sort=False):
            g=g.set_index("model")
            for left,right in COMPARISONS:
                for metric in ["MAE_kw","RMSE_kw"]:
                    a,b=g.loc[left,metric],g.loc[right,metric]
                    comparisons.append(dict(scenario=scenario,split=split,left_model=left,right_model=right,
                        metric=metric,difference=a-b,relative_improvement=ratio(b-a,b),
                        relative_reason="" if b else "zero_baseline_metric"))
        comparison=pd.DataFrame(comparisons)
        csv(comparison,"model_comparison.csv")
        csv(comparison.loc[comparison.left_model.isin(["NoCalendar","No168Stats"])],"ablation_metrics.csv")
        common_keys = ["origin","horizon","model","split"]
        cross = pred.loc[pred.scenario.eq("0h") & pred.score_mask,common_keys+["y_true_kw","y_pred_kw"]].merge(
            pred.loc[pred.scenario.eq("1h") & pred.score_mask,common_keys+["y_pred_kw"]],on=common_keys,
            suffixes=("_0h","_1h"),validate="one_to_one")
        sensitivity=[]
        for (split,model),g in cross.groupby(["split","model"],sort=False):
            for scenario in ("0h","1h"):
                e=g[f"y_pred_kw_{scenario}"]-g.y_true_kw
                sensitivity.append(dict(scope="cross_scenario_intersection",split=split,model=model,scenario=scenario,
                    n_hours=len(g),n_days=g.origin.nunique(),MAE_kw=float(abs(e).mean()),RMSE_kw=float(np.sqrt((e**2).mean()))))
        csv(pd.DataFrame(sensitivity),"information_sensitivity.csv")
    intervals=uncertainty(pred.loc[pred.split.eq("test")])
    csv(intervals,"uncertainty_summary.csv")
    conclusions=[]
    for scenario in ("0h","1h"):
        d=daily.loc[daily.scenario.eq(scenario)&daily.split.eq("test")].pivot(index="origin",columns="model",values="MAE_kw")
        w=weeks.loc[weeks.scenario.eq(scenario)&weeks.split.eq("test")].pivot(index="week_block",columns="model",values="MAE_kw")
        for baseline in ("B1","B2"):
            delta=d.Full-d[baseline]
            week_delta=w.Full-w[baseline]
            ci=intervals.loc[(intervals.scenario==scenario)&(intervals.algorithm=="paired_week7")&
                            (intervals.metric=="MAE_kw")&(intervals.comparison==f"Full-{baseline}")].iloc[0]
            positive_weeks=int((week_delta<0).sum())
            stable=bool(ci.point_estimate<0 and ci.ci_high<0 and positive_weeks>=6)
            conclusions.append(dict(scenario=scenario,baseline=baseline,
                delta_MAE_kw=ci.point_estimate,ci_low=ci.ci_low,ci_high=ci.ci_high,
                winning_weeks=positive_weeks,total_weeks=len(w),daily_win_rate=float((delta<0).mean()),
                tied_days=int((delta==0).sum()),daily_delta_median_kw=float(delta.median()),
                worst_week=int(week_delta.idxmax()),worst_week_delta_kw=float(week_delta.max()),
                stable_improvement=stable, practical_qualification="not_defined"))
    csv(pd.DataFrame(conclusions),"stability_conclusions.csv")
