"""Independent CSV-based acceptance path plus targeted metamorphic API checks.

Independent metric arithmetic below does not call production metric/bootstrap functions.
Production functions are only used where the subject under test is their online behavior.
"""
from __future__ import annotations

import math
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np
import pandas as pd

from task06.common import *


def independent_peak(y,p):
    y,p=list(y),list(p)
    a,b=max(y),max(p)
    t=[i for i,v in enumerate(y) if v==a]
    u=[i for i,v in enumerate(p) if v==b]
    flat=len(t)==24
    d=[abs(i-u[0]) for i in t]
    return dict(peak_abs_kw=abs(a-b),peak_under_kw=max(a-b,0),
        true_peak_gap_kw=statistics.mean([max(y[i]-p[i],0) for i in t]),
        peak_time_h=math.nan if flat else min(d),
        peak_time_circular_h=math.nan if flat else min(min(v,24-v) for v in d),
        predicted_ties_mean_distance_h=math.nan if flat else statistics.mean(min(abs(i-j) for j in t) for i in u),
        true_tie_count=len(t),predicted_tie_count=len(u),true_flat=flat,predicted_flat=len(u)==24,
        earliest_predicted_peak=u[0],true_peak_kw=a,predicted_peak_kw=b,
        true_peak_hours=t,predicted_peak_hours=u)


def independent_metrics(y,p):
    y,p=np.asarray(y),np.asarray(p)
    e=p-y
    h=y>Q
    gap=np.maximum(y[h]-p[h],0)
    under=gap[gap>0]
    out=dict(MAE_kw=float(np.mean(abs(e))),RMSE_kw=float(np.linalg.norm(e)/math.sqrt(len(e))),
             MAE_H_kw=float(np.mean(abs(e[h]))) if h.any() else math.nan,
             Bias_H_kw=float(np.mean(e[h])) if h.any() else math.nan,
             U_H_kw=float(np.mean(gap)) if h.any() else math.nan,
             under_rate_H=float(len(under)/len(gap)) if len(gap) else math.nan,
             conditional_gap_H_kw=float(np.mean(under)) if len(under) else math.nan,
             gap_q90_H_kw=float(np.percentile(gap,90)) if len(gap) else math.nan,
             FNR_H=float(np.mean(p[h]<=Q)) if h.any() else math.nan,
             over_mean_all_kw=float(np.mean(np.maximum(e,0))))
    return out


def close(a,b,tol=1e-12):
    if pd.isna(a) and pd.isna(b):
        return
    assert math.isfinite(float(a)) and math.isfinite(float(b)),(a,b)
    assert abs(float(a)-float(b))<=tol,(a,b,abs(float(a)-float(b)))


def verify():
    checks=[]
    details={}
    failures=[]
    def run(name,fn):
        try:
            value=fn()
            checks.append(dict(name=name,status="passed",details=value))
            print(f"PASS {name}",flush=True)
        except Exception as exc:
            checks.append(dict(name=name,status="failed",error=repr(exc)))
            failures.append(name)
            print(f"FAIL {name}: {exc!r}",flush=True)

    hourly=read_csv(ROOT/INPUTS[0]); hourly["timestamp"]=timestamps(hourly.timestamp)
    hourly=hourly.set_index("timestamp")
    pred=read_csv(OUT/"predictions.csv")
    for col in ["origin","target_timestamp"]:
        pred[col]=timestamps(pred[col])
    masks=read_csv(OUT/"common_score_mask.csv")
    masks["origin"]=timestamps(masks.origin)
    origin_quality=read_csv(OUT/"origin_quality.csv")
    origin_quality["origin"]=timestamps(origin_quality.origin)
    stages=read_csv(OUT/"model_stage_index.csv")
    metrics=read_csv(OUT/"metrics.csv")
    high=read_csv(OUT/"high_load_metrics.csv")
    peaks=read_csv(OUT/"daily_peak_metrics.csv")
    peaks["origin"]=timestamps(peaks.origin)
    scored=pred.loc[pred.score_mask]

    def input_invariants():
        ix=pd.date_range(START,END,inclusive="left",freq="h")
        assert hourly.index.equals(ix) and hourly.index.is_unique and len(ix)==8784
        assert str(hourly.index.tz)==TZ
        assert len(ix.normalize().unique())==366 and hourly.hour_complete.sum()==8503
        assert hourly.mean_power_kw.notna().equals(hourly.hour_complete)
        panel=read_json(ROOT/INPUTS[1])
        devices=next(p["devices"] for p in panel["panels"] if p["panel_id"]=="panel13")
        assert devices==DEVICES and "rice_cooker_w" not in devices
        split=read_json(ROOT/INPUTS[2])
        for name,a,b in [("train",START,VAL),("validation",VAL,TEST),("test",TEST,END)]:
            assert list(map(pd.Timestamp,split[name]))==[a,b]
        reference=read_csv(ROOT/INPUTS[4]).query("panel_id=='panel13'")
        reference["timestamp"]=timestamps(reference.timestamp)
        reference=reference.set_index("timestamp").reindex(ix)
        assert np.array_equal(reference.mean_power_kw.isna(),hourly.mean_power_kw.isna())
        difference=np.nanmax(abs(reference.mean_power_kw-hourly.mean_power_kw))
        assert difference<1e-12
        for row in read_json(OUT/"input_manifest.json")["inputs"]:
            assert sha(ROOT/row["path"])==row["sha256"]
        return dict(strict_hours=8503,missing_hours=281,max_label_difference_kw=difference,devices=devices)
    run("input_timezone_grid_devices_splits_strict_labels",input_invariants)

    def independent_masks():
        support=[]
        y=hourly.mean_power_kw
        for latency in (0,1):
            q=origin_quality.loc[origin_quality.scenario.eq(f"{latency}h")].set_index("origin")
            assert len(q)==366
            for origin,row in q.iterrows():
                right=origin-latency*HOUR
                history=y.reindex(pd.date_range(right-168*HOUR,right,inclusive="left",freq="h"))
                target=y.reindex(pd.date_range(origin,periods=24,freq="h"))
                history_ok=history.notna().all()
                target_ok=target.notna().all()
                assert bool(row.history_complete)==bool(history_ok)
                assert bool(row.target_complete)==bool(target_ok)
                assert bool(row.release_eligible)==bool(history_ok) # all applicable calendars already public
                assert bool(row.common_score_mask)==bool(history_ok and target_ok)
                expected_initial=history_ok and target_ok and origin<VAL and origin+DAY+latency*HOUR<=VAL
                expected_refit=history_ok and target_ok and origin<TEST and origin+DAY+latency*HOUR<=TEST
                expected_selection=history_ok and target_ok and VAL<=origin<TEST and origin+DAY+latency*HOUR<=TEST
                assert row.fit_eligible_initial==expected_initial
                assert row.fit_eligible_refit==expected_refit
                assert row.validation_selection_mask==expected_selection
            s={split:int(q.loc[q.split.eq(split),"common_score_mask"].sum()) for split in ("train","validation","test")}
            assert s==dict(train=253,validation=28,test=56)
            assert q.fit_eligible_initial.sum()==(253 if latency==0 else 252)
            assert q.fit_eligible_refit.sum()==(281 if latency==0 else 280)
            assert q.validation_selection_mask.sum()==(28 if latency==0 else 27)
            support.append(dict(scenario=f"{latency}h",score_days=s,
                initial_fit_days=int(q.fit_eligible_initial.sum()),refit_days=int(q.fit_eligible_refit.sum()),
                selection_days=int(q.validation_selection_mask.sum())))
        return support
    run("independently_reconstructed_masks_and_delayed_label_cutoffs",independent_masks)

    def availability_audit():
        audit=read_csv(OUT/"feature_availability_audit.csv")
        for col in ["origin","latest_source_time","available_at","source_start","nominal_source_start"]:
            audit[col]=timestamps(audit[col])
        history=audit.loc[audit.kind.eq("history")]
        assert (history.latest_source_time<history.origin).all()
        assert (history.available_at<=history.origin).all()
        assert (history.available_at==history.latest_source_time+(1+history.latency_hours)*HOUR).all()
        calendar=audit.loc[audit.kind.eq("calendar")]
        assert (calendar.available_at<=calendar.origin).all()
        fallback=history.loc[history.fallback]
        assert len(fallback)==366
        assert fallback.latency_hours.eq(1).all() and fallback.feature.eq("lag24").all()
        assert fallback.horizon.astype(str).eq("23").all()
        assert (fallback.source_start==fallback.origin-25*HOUR).all()
        assert (fallback.nominal_source_start==fallback.origin-HOUR).all()
        calendar_source=read_csv(OUT/"calendar_availability.csv")
        pub=timestamps(calendar_source.public_available_at)
        dates=timestamps(calendar_source.date)
        assert pub.loc[dates.dt.year.eq(2021)].eq(pd.Timestamp("2020-11-27",tz=TZ)).all()
        assert pub.loc[dates.dt.year.eq(2022)].eq(pd.Timestamp("2021-10-26",tz=TZ)).all()
        return dict(rows=len(audit),fallback_rows=len(fallback),calendar_date_may_be_future=True)
    run("source_times_publication_times_and_calendar_public_dates",availability_audit)

    def prediction_keys_common_masks():
        keys=["scenario","origin","horizon"]
        assert len(pred)==2*366*24*6
        assert not pred.duplicated(keys+["model"]).any()
        assert len(masks)==2*8784 and not masks.duplicated(keys).any()
        merged=pred.merge(masks[keys+["common_score_mask"]],on=keys,suffixes=("","_independent"),validate="many_to_one")
        assert np.array_equal(merged.score_mask,merged.common_score_mask_independent)
        assert np.isfinite(scored[["raw_pred_kw","y_pred_kw","y_true_kw"]]).all().all()
        np.testing.assert_array_equal(scored.y_pred_kw,np.maximum(scored.raw_pred_kw,0))
        source_y=hourly.mean_power_kw.reindex(pred.target_timestamp).to_numpy()
        np.testing.assert_array_equal(source_y,pred.y_true_kw.to_numpy())
        assert pred.groupby(keys).model.nunique().eq(6).all()
        return dict(rows=len(pred),common_score_keys=int(len(scored)/6))
    run("six_method_keys_masks_and_no_dynamic_deletion",prediction_keys_common_masks)

    def stage_cutoffs_encodings_scalers():
        for row in stages.itertuples():
            cutoff=pd.Timestamp(row.fit_cutoff)
            assert pd.Timestamp(row.last_fit_label_available_at)<=cutoff
            assert sha(ROOT/row.model_path)==row.model_sha256
            bundle=joblib.load(ROOT/row.model_path)
            x=pd.read_pickle(OUT/f"features_{row.scenario}.pkl")
            m=pd.read_pickle(OUT/f"samples_{row.scenario}.pkl")
            fit=m.fit_eligible_initial if row.model_stage=="initial_train" else m.fit_eligible_refit
            assert fit.sum()==row.n_fit_rows and m.loc[fit,"origin"].nunique()==row.n_fit_origins
            assert m.loc[fit,"target_timestamp"].max()<cutoff
            enc=bundle["encoder"]
            for f in enc.categorical:
                assert f in CATEGORIES
            assert enc.columns==json.loads(row.encoded_columns)
            if row.model=="Linear-L1":
                raw=x.loc[fit,enc.numeric].to_numpy()
                np.testing.assert_allclose(enc.mean_,raw.mean(0),atol=1e-14,rtol=0)
                sd=raw.std(0,ddof=0); sd[sd==0]=1
                np.testing.assert_allclose(enc.scale_,sd,atol=1e-14,rtol=0)
                assert bundle["model"].quantile==.5 and bundle["model"].solver=="highs"
            else:
                assert not enc.scaled and np.array_equal(enc.mean_,np.zeros(len(enc.numeric)))
                params=bundle["model"].get_params()
                assert params["objective"]=="regression_l1" and params["deterministic"]
            if row.model=="NoCalendar":
                assert enc.categorical==["horizon"]
            if row.model=="No168Stats":
                assert "lag168" in enc.numeric and not any(f.endswith("_168h") for f in enc.numeric)
        search=read_csv(OUT/"validation_search.csv")
        for (scenario,family),g in search.groupby(["scenario","family"]):
            assert len(g)==(4 if family=="Linear-L1" else 8) and g.selected.sum()==1
            assert g.fit_cutoff.map(pd.Timestamp).eq(VAL).all()
            assert g.selection_cutoff.map(pd.Timestamp).eq(TEST).all()
            best=g.validation_mae_kw.min(); tied=g.loc[g.validation_mae_kw<=best+1e-12]
            def order(row):
                p=json.loads(row.params)
                return (-p["alpha"],) if family=="Linear-L1" else (p["n_estimators"],p["num_leaves"],-p["min_child_samples"])
            expected=min(tied.itertuples(),key=order).candidate
            assert g.loc[g.selected,"candidate"].iloc[0]==expected
        return dict(saved_model_stages=len(stages),validation_candidates=len(search))
    run("fitting_selection_scaling_and_ablation_cutoffs",stage_cutoffs_encodings_scalers)

    def metamorphic_checks():
        from task06.data import load_inputs,origin_features,label_masks
        from task06.modeling import predict
        _,calendar=load_inputs()
        records=[]
        for latency in (0,1):
            origin=TEST
            y=hourly.mean_power_kw.copy()
            original,release,_=origin_features(y,calendar,origin,latency)
            future=y.index+(1+latency)*HOUR>origin
            altered=y.copy(); altered.loc[future]=np.random.default_rng(42).normal(99,5,future.sum())
            removed=y.loc[~future]
            for variant in MODELS[2:]:
                bundle=joblib.load(OUT/"models"/f"{latency}h_{variant}_refit.joblib")
                expected=predict(bundle,original)
                for label,changed in [("perturbed",altered),("deleted",removed)]:
                    xx,rr,_=origin_features(changed,calendar,origin,latency)
                    pd.testing.assert_frame_equal(xx,original)
                    assert rr==release
                    difference=float(np.max(abs(predict(bundle,xx)-expected)))
                    assert difference==0
                    records.append(dict(scenario=f"{latency}h",model=variant,operation=label,
                                        origin=str(origin),max_prediction_difference_kw=difference))
            original_quality,_=label_masks(y,origin,latency,release["release_eligible"])
            changed=y.copy(); changed.loc[origin]=np.nan
            xx,rr,_=origin_features(changed,calendar,origin,latency)
            changed_quality,_=label_masks(changed,origin,latency,rr["release_eligible"])
            pd.testing.assert_frame_equal(xx,original)
            assert rr==release and original_quality["common_score_mask"] and not changed_quality["common_score_mask"]
            # Post-hoc QC and target_complete are not accepted by the release API.
            qc=hourly.copy(); qc["qc_bits"]=255; qc["target_complete"]=False
            xx,rr,_=origin_features(qc.mean_power_kw,calendar,origin,latency)
            pd.testing.assert_frame_equal(xx,original); assert rr==release
            records.append(dict(scenario=f"{latency}h",operation="target_missing_and_QC_changed",
                                release_unchanged=True,score_mask_changed=True))
        csv(pd.DataFrame(records),"metamorphic_checks.csv")
        return records
    run("future_record_perturbation_deletion_and_posthoc_quality_invariance",metamorphic_checks)

    def lag_fallback_all_models():
        y=hourly.mean_power_kw
        x=pd.read_pickle(OUT/"features_1h.pkl")
        m=pd.read_pickle(OUT/"samples_1h.pkl")
        for i,row in m.loc[m.release_eligible].iterrows():
            actual=row.target_timestamp-(48 if row.horizon==23 else 24)*HOUR
            close(x.loc[i,"lag24"],y.loc[actual],0)
        b=pred.loc[pred.scenario.eq("1h")&pred.model.eq("B1")&pred.release_eligible]
        for row in b.itertuples():
            actual=row.target_timestamp-(48 if row.horizon==23 else 24)*HOUR
            close(row.raw_pred_kw,y.loc[actual],0)
        for row in stages.loc[stages.scenario.eq("1h")].itertuples():
            assert "lag24" in joblib.load(ROOT/row.model_path)["encoder"].numeric
        last=origin_quality.loc[origin_quality.scenario.eq("1h")&origin_quality.origin.eq(TEST-DAY)].iloc[0]
        assert last.target_complete and not last.validation_selection_mask and not last.fit_eligible_refit
        return dict(fallback_horizon=23,all_learning_variants_share_feature=True,
                    last_validation_day="2022-04-05",excluded_from_selection_and_refit=True)
    run("one_hour_fallback_and_last_validation_day",lag_fallback_all_models)

    def independent_point_scores():
        checked=0
        score_groups={key:g for key,g in scored.groupby(["scenario","split","model"],sort=False)}
        for row in metrics.itertuples():
            g=score_groups[(row.scenario,row.split,row.model)]
            actual=independent_metrics(g.y_true_kw,g.y_pred_kw)
            close(actual["MAE_kw"],row.MAE_kw); close(actual["RMSE_kw"],row.RMSE_kw)
            assert len(g)==row.n_hours
            high_row=high.loc[(high.scenario==row.scenario)&(high.split==row.split)&(high.model==row.model)].iloc[0]
            for field,value in actual.items():
                if field not in ["MAE_kw","RMSE_kw"]:
                    close(value,high_row[field])
            checked+=len(actual)
        for name,key in [("daily_metrics.csv","origin"),("horizon_metrics.csv","horizon"),("weekly_metrics.csv","week_block")]:
            frame=read_csv(OUT/name)
            if key=="origin": frame["origin"]=timestamps(frame.origin)
            working=scored.copy()
            if key=="week_block":
                anchors=working.split.map({"train":START,"validation":VAL,"test":TEST})
                working["week_block"]=(working.origin-anchors).dt.days//7
            groups={kk:gg for kk,gg in working.groupby(["scenario","split","model",key],sort=False)}
            for row in frame.itertuples():
                g=groups[(row.scenario,row.split,row.model,getattr(row,key))]
                result=independent_metrics(g.y_true_kw,g.y_pred_kw)
                close(result["MAE_kw"],row.MAE_kw); close(result["RMSE_kw"],row.RMSE_kw)
                checked+=2
        peak_groups={key:g.sort_values("horizon") for key,g in scored.groupby(["scenario","model","origin"],sort=False)}
        for row in peaks.itertuples():
            g=peak_groups[(row.scenario,row.model,row.origin)]
            result=independent_peak(g.y_true_kw,g.y_pred_kw)
            for field,value in result.items():
                if field in ["true_peak_hours","predicted_peak_hours"]:
                    assert value==json.loads(getattr(row,field))
                else:
                    close(value,getattr(row,field))
                checked+=1
        return dict(independent_numeric_checks=checked,tolerance_kw_or_h=1e-12)
    run("independent_csv_point_high_peak_daily_horizon_weekly_metrics",independent_point_scores)

    def model_reload_prediction_reproduction():
        from task06.modeling import predict
        max_difference=0
        for row in stages.itertuples():
            bundle=joblib.load(ROOT/row.model_path)
            x=pd.read_pickle(OUT/f"features_{row.scenario}.pkl")
            m=pd.read_pickle(OUT/f"samples_{row.scenario}.pkl")
            wanted=m.release_eligible & (m.split.eq("test") if row.model_stage=="train_validation_refit" else ~m.split.eq("test"))
            actual=predict(bundle,x.loc[wanted])
            saved=pred.loc[pred.scenario.eq(row.scenario)&pred.model.eq(row.model)&pred.release_eligible&pred.model_stage.eq(row.model_stage)]
            saved=saved.sort_values(["origin","horizon"])
            difference=float(np.max(abs(actual-saved.raw_pred_kw.to_numpy())))
            assert difference<=1e-12
            max_difference=max(max_difference,difference)
        v=read_csv(OUT/"validation_predictions.csv")
        v["origin"]=timestamps(v.origin)
        merged=v.merge(pred.loc[pred.split.eq("validation")],on=["scenario","origin","horizon","model"],suffixes=("_initial","_final"),validate="one_to_one")
        np.testing.assert_array_equal(merged.raw_pred_kw_initial,merged.raw_pred_kw_final)
        assert merged.model_stage_final.eq("initial_train").all()
        return dict(stages=len(stages),maximum_difference_kw=max_difference,tolerance_kw=1e-12)
    run("reloaded_models_and_original_validation_predictions",model_reload_prediction_reproduction)

    def bootstrap_independent_recalculation():
        evidence=read_csv(OUT/"bootstrap_replicate_checks.csv")
        evidence_groups={key:g.set_index("metric") for key,g in evidence.groupby(["scenario","algorithm","replicate","model"],sort=False)}
        uncertainty=read_csv(OUT/"uncertainty_summary.csv")
        checked=0
        for scenario in ("0h","1h"):
            test=pred.loc[pred.scenario.eq(scenario)&pred.split.eq("test")]
            arrays={m:g.sort_values(["origin","horizon"])[["y_true_kw","y_pred_kw","score_mask"]].to_numpy().reshape(56,24,3)
                    for m,g in test.groupby("model")}
            for algorithm in ("paired_week7","moving_day_3","moving_day_7","moving_day_14"):
                indices=np.load(OUT/f"bootstrap_indices_{scenario}_{algorithm}.npz")["days"]
                assert indices.shape==(10000,56) and indices.min()>=0 and indices.max()<56
                if algorithm=="paired_week7":
                    blocks=indices.reshape(10000,8,7)
                    assert (blocks[:,:,0]%7==0).all() and (np.diff(blocks,axis=2)==1).all()
                else:
                    L=int(algorithm.rsplit("_",1)[1])
                    for begin in range(0,56,L):
                        assert (np.diff(indices[:,begin:min(begin+L,56)],axis=1)==1).all()
                    assert all((indices[:,begin]<=56-L).all() for begin in range(0,56,L))
                for r in range(20):
                    days=indices[r]
                    for model,a in arrays.items():
                        sample=a[days].reshape(-1,3)
                        valid=sample[:,2].astype(bool)
                        result=independent_metrics(sample[valid,0].astype(float),sample[valid,1].astype(float))
                        peak_results=[independent_peak(a[d,:,0].astype(float),a[d,:,1].astype(float)) for d in days if a[d,:,2].all()]
                        for field in ["peak_abs_kw","peak_under_kw","true_peak_gap_kw","peak_time_h","peak_time_circular_h","predicted_ties_mean_distance_h"]:
                            vals=[p[field] for p in peak_results if not pd.isna(p[field])]
                            result[field]=statistics.mean(vals) if vals else math.nan
                        saved=evidence_groups[(scenario,algorithm,r,model)]
                        for field,value in result.items():
                            close(value,saved.loc[field,"value"]); checked+=1
                # Recompute all 10000 primary/moving MAE intervals directly from saved daily errors.
                daily_error={m:np.mean(np.abs(a[:,:,1].astype(float)-a[:,:,0].astype(float)),axis=1) for m,a in arrays.items()}
                for left,right in [("Full","B1"),("Full","B2"),("Full","Linear-L1"),("NoCalendar","Full"),("No168Stats","Full")]:
                    replicates=(daily_error[left][indices]-daily_error[right][indices]).mean(axis=1)
                    lo,hi=np.percentile(replicates,[2.5,97.5])
                    saved=uncertainty.loc[(uncertainty.scenario==scenario)&(uncertainty.algorithm==algorithm)&
                        (uncertainty.metric=="MAE_kw")&(uncertainty.comparison==f"{left}-{right}")].iloc[0]
                    close(lo,saved.ci_low); close(hi,saved.ci_high)
                    assert saved.valid_repetitions==10000
        return dict(direct_replicate_metric_checks=checked,independently_recomputed_MAE_intervals=40,
                    pairing="single day-index array applied to every method",tolerance=1e-12)
    run("bootstrap_pairing_subsets_quantiles_intervals_and_indices",bootstrap_independent_recalculation)

    def frozen_and_preserved():
        assert sha(OUT/"experiment_config_frozen.json")==(OUT/"experiment_config_frozen.sha256").read_text().strip()
        frozen=read_json(OUT/"experiment_config_frozen.json")
        core_hashes={p:h for p,h in frozen["source_code_hashes"].items()
                     if Path(p).name in ["common.py","data.py","modeling.py","evaluation.py"]}
        for p,h in core_hashes.items():
            assert sha(ROOT/p)==h,f"Prediction/metric core changed after freeze: {p}"
        ps=read_json(OUT/"prediction_state.json")
        assert pd.Timestamp(frozen["created_at"])<pd.Timestamp(ps["created_at"])
        assert ps["frozen_sha256"]==sha(OUT/"experiment_config_frozen.json")
        preserved=read_json(OUT/"upstream_preservation.json")
        for p,h in preserved.items():
            assert sha(ROOT/p)==h,p
        cfg=read_json(OUT/"experiment_config.json")
        for field in ["practical_improvement_delta","tau_U","tau_P","tau_T","p_day","p_high","noninferiority_epsilon"]:
            assert cfg[field] is None
        return dict(upstream_files_byte_identical=len(preserved),test_predicted_after_freeze=True,
                    frozen_core_source_files_unchanged=len(core_hashes))
    run("configuration_freeze_and_upstream_original_bytes",frozen_and_preserved)

    def edge_tests():
        proc=subprocess.run([sys.executable,"-m","pytest","task06/tests","-q"],cwd=ROOT,
                            text=True,encoding="utf-8",stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (REPORT/"unit_tests.txt").write_text(proc.stdout,encoding="utf-8")
        assert proc.returncode==0,proc.stdout
        return proc.stdout.strip()
    REPORT.mkdir(parents=True,exist_ok=True)
    run("explicit_peak_highload_interval_and_selection_counterexamples",edge_tests)
    result=dict(version=VERSION,created_at=now(),status="passed" if not failures else "failed",
                checks=checks,passed=sum(c["status"]=="passed" for c in checks),failed=len(failures),
                independent_path="saved CSV arithmetic, explicit artificial examples, frozen-model metamorphic experiments; not a production-function rerun",
                limitations="independent code path in same process/environment; no external human reviewer implied")
    write_json(OUT/"verification_task06.json",result)
    write_json(REPORT/"verification_task06.json",result)
    assert not failures,failures
    return result


if __name__=="__main__":
    verify()
