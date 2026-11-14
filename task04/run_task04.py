"""Reproduce task04 using frozen repository inputs; no downloads or imputation."""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
REPO=HERE.parent
IN_REPOSITORY=(REPO/'task01/reports/panel_definition.json').is_file()
DEFAULT_SOURCE=REPO if IN_REPOSITORY else HERE/'inputs'
DEFAULT_OUTPUT=REPO if IN_REPOSITORY else HERE
CFG=json.loads((HERE/'config.json').read_text(encoding='utf-8'))
TZ=CFG['timezone']
START=pd.Timestamp(CFG['analysis_start'])
END=pd.Timestamp(CFG['analysis_end_exclusive'])
STD='data/standardized/'+CFG['data_version']

def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def read(path,time_column=None,**kwargs):
    frame=pd.read_csv(path,float_precision='round_trip',**kwargs)
    if time_column:frame[time_column]=pd.to_datetime(frame[time_column],utc=True).dt.tz_convert(TZ)
    return frame

def stamp(value):return pd.Timestamp(value).isoformat()
def stamps(values):return json.dumps([stamp(x) for x in values],ensure_ascii=False)

def build_daily(hourly,daily,dimension):
    """Only full days; exact float64 ties, no rounding."""
    good=daily.loc[daily.day_complete].set_index('date')
    labels=dimension.set_index('date')
    rows=[];extrema=[]
    for date,group in hourly.groupby(hourly.timestamp.dt.normalize(),sort=True):
        if date not in good.index:continue
        assert len(group)==24 and group.hour_complete.all() and group.mean_power_kw.notna().all()
        values=group.mean_power_kw.to_numpy(dtype=np.float64)
        peak=float(values.max());valley=float(values.min());mean=float(values.mean())
        row=dict(date=date,panel_id=CFG['panel_id'],panel_version=CFG['panel_version'],
            data_version=CFG['data_version'],natural_day_type=labels.loc[date,'natural_day_type'],
            actual_day_type=labels.loc[date,'actual_day_type'],year_month=date.strftime('%Y-%m'),
            energy_kwh=float(good.loc[date,'energy_kwh']),peak_kw=peak,valley_kw=valley,
            peak_valley_kw=peak-valley,mean_kw=mean,load_factor=mean/peak if peak!=0 else np.nan,
            peak_tied_count=int((values==peak).sum()),valley_tied_count=int((values==valley).sum()),
            hour_count=24,day_complete=True)
        rows.append(row)
        for kind,value in [('peak',peak),('valley',valley)]:
            times=group.loc[group.mean_power_kw.eq(value),'timestamp']
            for time in times:
                extrema.append(dict(date=date,kind=kind,hour_start=time,hour=time.hour,
                    value_kw=value,tied_count=len(times),weight=1/len(times)))
    result=pd.DataFrame(rows);long=pd.DataFrame(extrema)
    assert len(result)==len(good)
    freq=[]
    for kind in ['peak','valley']:
        subset=long.loc[long.kind.eq(kind)]
        for hour in range(24):
            group=subset.loc[subset.hour.eq(hour)]
            freq.append(dict(kind=kind,hour=hour,weighted_days=float(group.weight.sum()),
                proportion=float(group.weight.sum()/len(result)),n_days=len(result),
                days_with_extreme_at_hour=group.date.nunique(),tie_rule='equal_weight_all_exact_ties'))
    return result,long,pd.DataFrame(freq)

def build_changes(hourly):
    h=hourly.sort_values('timestamp').reset_index(drop=True)
    prev_time=h.timestamp.shift(1)
    prev_complete=h.hour_complete.shift(1,fill_value=False)
    elapsed=(h.timestamp-prev_time).dt.total_seconds()/3600
    has_previous=prev_time.notna()
    valid=has_previous & elapsed.eq(1) & h.hour_complete & prev_complete
    reason=np.select([~has_previous,~elapsed.eq(1),~h.hour_complete & ~prev_complete,
                      ~h.hour_complete,~prev_complete],
                     ['no_previous_hour','non_adjacent_timestamp','both_hours_incomplete',
                      'current_hour_incomplete','previous_hour_incomplete'],default='')
    cross=(h.timestamp.dt.normalize()!=prev_time.dt.normalize()) & has_previous
    delta=(h.mean_power_kw-h.mean_power_kw.shift(1)).where(valid)
    return pd.DataFrame(dict(timestamp=h.timestamp,previous_timestamp=prev_time,
        current_mean_power_kw=h.mean_power_kw,previous_mean_power_kw=h.mean_power_kw.shift(1),
        current_hour_complete=h.hour_complete,previous_hour_complete=prev_complete,
        elapsed_hours=elapsed,valid_change=valid,exclusion_reason=reason,
        is_cross_midnight=cross,is_intra_day=has_previous & ~cross,
        delta_kw=delta,abs_delta_kw=delta.abs()))

def fit_thresholds(hourly,changes,split):
    left,right=map(pd.Timestamp,split['train'])
    fit=changes.valid_change & changes.timestamp.ge(left) & changes.timestamp.lt(right) & changes.previous_timestamp.ge(left)
    target=hourly.loc[hourly.hour_complete & hourly.timestamp.ge(left) & hourly.timestamp.lt(right),'mean_power_kw']
    threshold=float(changes.loc[fit,'abs_delta_kw'].quantile(CFG['large_change_quantile'],interpolation='linear'))
    out=dict(unit='kW',training_interval=[stamp(left),stamp(right)],quantile_method='linear',
        train_abs_hour_change_q95_kw=threshold,train_change_pairs=int(fit.sum()),
        train_hourly_load_q90_kw=float(target.quantile(CFG['task06_high_load_quantile'],interpolation='linear')),
        train_strict_hours=len(target),large_change_rule='abs_delta_kw > train_abs_hour_change_q95_kw',
        changes_fit_rule='Both endpoints inside frozen training interval and strict-valid, exactly 1h apart',
        exploratory_full_period_abs_change_q95_kw=float(changes.loc[changes.valid_change,'abs_delta_kw'].quantile(.95)),
        exploratory_threshold_usage='Descriptive only; not fitted parameters for task06',
        task06_usage='Candidate evaluation thresholds only. Daily/case/QC outcomes are retrospective, never future-known features.')
    return out

def choose_cases(metrics,daily):
    eligible=[]
    for month,group in daily.groupby(daily.date.dt.strftime('%Y-%m'),sort=True):
        first=pd.Timestamp(month+'-01',tz=TZ)
        full=pd.date_range(first,first+pd.offsets.MonthBegin(1),freq='D',inclusive='left')
        available=metrics.loc[metrics.year_month.eq(month)]
        if (len(group)==len(full) and set(group.date)==set(full) and group.day_complete.all()
            and available.natural_day_type.eq('weekday').sum()>=5
            and available.natural_day_type.eq('weekend').sum()>=4):eligible.append(month)
    assert eligible,'No month meets the predeclared comparison support rule.'
    month=eligible[0];subset=metrics.loc[metrics.year_month.eq(month)]
    records=[]
    for case_id,kind,label in [('C01','typical_weekday','普通自然工作日'),('C02','typical_weekend','普通自然周末')]:
        daytype='weekday' if kind.endswith('weekday') else 'weekend'
        candidates=subset.loc[subset.natural_day_type.eq(daytype)].copy()
        target=float(candidates.energy_kwh.median())
        candidates['selection_distance']=(candidates.energy_kwh-target).abs()
        selected=candidates.sort_values(['selection_distance','date'],kind='stable').iloc[0]
        records.append(dict(case_id=case_id,case_type=kind,label=label,date=selected.date,
            selection_metric='energy_kwh',selection_target=target,
            selection_distance=float(selected.selection_distance),candidate_days=len(candidates),comparison_month=month))
    target=float(subset.energy_kwh.quantile(CFG['case_selection']['high_load_quantile'],interpolation='linear'))
    selected=subset.loc[subset.energy_kwh.ge(target)].sort_values(['energy_kwh','date'],kind='stable').iloc[0]
    records.append(dict(case_id='C03',case_type='high_load',label='同月高电量日',date=selected.date,
        selection_metric='energy_kwh',selection_target=target,selection_distance=float(selected.energy_kwh-target),
        candidate_days=len(subset),comparison_month=month))
    target=float(metrics.peak_kw.max())
    selected=metrics.loc[metrics.peak_kw.eq(target)].sort_values('date').iloc[0]
    records.append(dict(case_id='C04',case_type='global_peak',label='全期最大小时峰日',date=selected.date,
        selection_metric='peak_kw',selection_target=target,selection_distance=0.,candidate_days=len(metrics),comparison_month='all_complete_days'))
    return pd.DataFrame(records)

def minute_comparison(panel,metrics):
    records=[]
    for date,row in metrics.set_index('date').iterrows():
        part=panel.loc[panel.timestamp.ge(date)&panel.timestamp.lt(date+pd.Timedelta(days=1))]
        assert len(part)==1440 and part.panel_complete.all() and part.panel_power_w.notna().all()
        value=float(part.panel_power_w.max())
        times=part.loc[part.panel_power_w.eq(value),'timestamp']
        records.append(dict(date=date,hour_peak_kw=row.peak_kw,minute_record_peak_w=value,
            minute_record_peak_kw=value/1000,minute_to_hour_peak_ratio=value/(row.peak_kw*1000) if row.peak_kw else np.nan,
            minute_peak_tied_count=len(times),minute_peak_times=stamps(times),complete_minutes=1440))
    return pd.DataFrame(records)

def extract_cases(source,panel,hourly,cases,metrics,extrema,minute,devices):
    dates=set(cases.date.dt.strftime('%Y-%m-%d'))
    power=read(source/STD/'power_minute.csv.gz',usecols=['timestamp','source_row_id','source_present']+devices)
    power=power.loc[power.timestamp.str[:10].isin(dates)].copy()
    power.timestamp=pd.to_datetime(power.timestamp,utc=True).dt.tz_convert(TZ)
    power=power.set_index('timestamp').sort_index()
    for device in devices:
        q=read(source/STD/'appliance_quality'/f'{device}.csv.gz',
               usecols=['timestamp','usable_value','is_usable','qc_bits','is_new_imputed'])
        q=q.loc[q.timestamp.str[:10].isin(dates)].copy()
        q.timestamp=pd.to_datetime(q.timestamp,utc=True).dt.tz_convert(TZ)
        q=q.set_index('timestamp').reindex(power.index)
        assert q.is_usable.all() and not q.is_new_imputed.any()
        assert np.array_equal(power[device].to_numpy(),q.usable_value.to_numpy(),equal_nan=True),device
        power[device+'_qc_bits']=q.qc_bits.astype('int64')
    p=panel.set_index('timestamp')
    power['panel_power_w']=p.panel_power_w.reindex(power.index)
    power['panel_complete']=p.panel_complete.reindex(power.index)
    assert np.allclose(power[devices].sum(axis=1),power.panel_power_w,rtol=1e-12,atol=1e-8)
    qcols=[d+'_qc_bits' for d in devices]
    combined=np.bitwise_or.reduce(power[qcols].to_numpy(dtype=np.int64),axis=1)
    power['combined_qc_bits']=combined
    power['any_review_flag']=(combined & (16|32))!=0
    power['new_imputed_devices']=0
    long=[];hours=[];quality=[];manifest=[]
    for case in cases.itertuples():
        date=case.date
        part=power.loc[(power.index>=date)&(power.index<date+pd.Timedelta(days=1))].copy()
        assert len(part)==1440 and part[devices].notna().all().all()
        part.insert(0,'case_id',case.case_id);part=part.reset_index();long.append(part)
        h=hourly.loc[hourly.timestamp.ge(date)&hourly.timestamp.lt(date+pd.Timedelta(days=1))].copy()
        h.insert(0,'case_id',case.case_id);hours.append(h)
        m=metrics.set_index('date').loc[date];mi=minute.set_index('date').loc[date]
        for device in devices:
            bits=part[device+'_qc_bits'].to_numpy(dtype=np.int64)
            quality.append(dict(case_id=case.case_id,date=date,appliance_id=device,n_minutes=len(part),
                usable_minutes=int(part[device].notna().sum()),unusable_minutes=int(part[device].isna().sum()),
                source_or_physical_invalid_minutes=int(((bits & 15)!=0).sum()),
                near_sensor_limit_review_minutes=int(((bits & 16)!=0).sum()),
                long_constant_review_minutes=int(((bits & 32)!=0).sum()),new_imputed_minutes=0,
                qc_unique_bits=json.dumps(sorted(np.unique(bits).tolist()))))
        record=case._asdict()
        record.update(dict(panel_id=CFG['panel_id'],panel_version=CFG['panel_version'],data_version=CFG['data_version'],
            device_ids=json.dumps(devices),n_devices=len(devices),day_complete=True,
            natural_day_type=m.natural_day_type,actual_day_type=m.actual_day_type,energy_kwh=m.energy_kwh,
            peak_kw=m.peak_kw,valley_kw=m.valley_kw,peak_valley_kw=m.peak_valley_kw,load_factor=m.load_factor,
            peak_hour_starts=stamps(extrema.loc[extrema.date.eq(date)&extrema.kind.eq('peak'),'hour_start']),
            valley_hour_starts=stamps(extrema.loc[extrema.date.eq(date)&extrema.kind.eq('valley'),'hour_start']),
            minute_record_peak_w=mi.minute_record_peak_w,minute_record_peak_times=mi.minute_peak_times,
            window_start=stamp(date),window_end_exclusive=stamp(date+pd.Timedelta(days=1)),complete_minutes=1440,
            review_flag_minutes=int(part.any_review_flag.sum()),new_imputed_minutes=0,
            qc_use='Retrospective review only; retained unchanged; not a future-known task06 feature'))
        manifest.append(record)
    return pd.DataFrame(manifest),pd.concat(hours,ignore_index=True),pd.concat(long,ignore_index=True),pd.DataFrame(quality)

def write_csv(frame,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.suffix=='.gz':
        frame.to_csv(path,index=False,encoding='utf-8-sig',compression={'method':'gzip','mtime':0},lineterminator='\n')
    else:frame.to_csv(path,index=False,encoding='utf-8-sig',lineterminator='\n')

def run(source,output):
    source=source.resolve();output=output.resolve()
    inputs=json.loads((HERE/'sources/input_manifest.json').read_text(encoding='utf-8'))
    for record in inputs['inputs']:
        path=(source/record['repository_path'] if record['local_path'].startswith('inputs/') else HERE/record['local_path'])
        assert digest(path)==record['sha256'],'Input SHA mismatch: '+str(path)
    print('PASS: all 28 frozen repository input hashes',flush=True)
    h=read(source/'data/derived/task02/hourly_panel13.csv','timestamp')
    d=read(source/'data/derived/task02/daily_panel13.csv','date')
    dim=read(source/'data/derived/task03/date_dimension.csv','date')
    assert len(h)==8784 and h.timestamp.is_unique and h.timestamp.tolist()==list(pd.date_range(START,END,freq='h',inclusive='left'))
    assert len(d)==366 and int(d.day_complete.sum())==352 and int(h.hour_complete.sum())==8503
    assert h.panel_id.eq(CFG['panel_id']).all() and h.data_version.eq(CFG['data_version']).all()
    assert np.allclose(h.mean_power_kw,h.energy_kwh,equal_nan=True) and h.loc[~h.hour_complete,'mean_power_kw'].isna().all()
    assert np.array_equal(d.day_complete,dim.day_complete) and np.allclose(d.energy_kwh,dim.energy_kwh,equal_nan=True)
    split=json.loads((source/'task01/reports/split_manifest.json').read_text(encoding='utf-8'))
    definition=json.loads((source/'task01/reports/panel_definition.json').read_text(encoding='utf-8'))
    devices=next(p['devices'] for p in definition['panels'] if p['panel_id']==CFG['panel_id'])
    metrics,extrema,freq=build_daily(h,d,dim)
    changes=build_changes(h);thresholds=fit_thresholds(h,changes,split)
    changes['is_large_change']=pd.array(np.where(changes.valid_change,changes.abs_delta_kw.gt(thresholds['train_abs_hour_change_q95_kw']),None),dtype='boolean')
    cases=choose_cases(metrics,d)
    print('PASS: strict daily metrics, exact extrema, adjacent changes and predeclared case selection',flush=True)
    panel=read(source/STD/'panel_minute.csv.gz','timestamp')
    panel=panel.loc[panel.panel_id.eq(CFG['panel_id'])&panel.timestamp.ge(START)&panel.timestamp.lt(END)].copy()
    assert len(panel)==527040 and panel.timestamp.is_unique
    minute=minute_comparison(panel,metrics)
    cases,case_hours,case_minutes,quality=extract_cases(source,panel,h,cases,metrics,extrema,minute,devices)
    summary=[]
    for name,mask in [('all_adjacent_valid',changes.valid_change),('intra_day',changes.valid_change&changes.is_intra_day),
                      ('cross_midnight',changes.valid_change&changes.is_cross_midnight)]:
        group=changes.loc[mask]
        summary.append(dict(scope=name,n_pairs=len(group),mean_delta_kw=float(group.delta_kw.mean()),
            median_abs_delta_kw=float(group.abs_delta_kw.median()),p95_abs_delta_kw=float(group.abs_delta_kw.quantile(.95)),
            max_rise_kw=float(group.delta_kw.max()),max_fall_kw=float(group.delta_kw.min()),
            n_large_changes=int(group.is_large_change.sum()),large_change_threshold_kw=thresholds['train_abs_hour_change_q95_kw']))
    excluded=dim.loc[~dim.day_complete,['date','valid_hours','coverage','exclusion_reason','natural_day_type','actual_day_type']].copy()
    excluded['daily_extrema_determined']=False
    tables={'daily_peak_valley.csv':metrics,'daily_extrema_times.csv':extrema,'peak_hour_frequency.csv':freq,
        'hourly_changes.csv':changes,'case_manifest.csv':cases,'excluded_days.csv':excluded,
        'daily_minute_hourly_comparison.csv':minute,'hourly_change_summary.csv':pd.DataFrame(summary),
        'case_hourly_curves.csv':case_hours,'case_minute_curves.csv.gz':case_minutes,'case_quality_summary.csv':quality}
    out=output/'data/derived/task04';out.mkdir(parents=True,exist_ok=True)
    for name,frame in tables.items():write_csv(frame,out/name)
    (out/'thresholds.json').write_text(json.dumps(thresholds,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PASS: exported all formal tables and unchanged case minute/QC values',flush=True)
    from report_task04 import render
    stats=render(HERE,output,tables,thresholds,devices,inputs)
    import matplotlib
    outputs=[]
    for path in sorted(out.iterdir()):
        if path.name=='derivation_manifest.json' or not path.is_file():continue
        record=dict(path=path.relative_to(output).as_posix(),scope='output_root',sha256=digest(path),bytes=path.stat().st_size)
        if path.name in tables:record['rows']=len(tables[path.name])
        outputs.append(record)
    for path in sorted((HERE/'reports').rglob('*')):
        if path.is_file() and path.name not in {'verify_task04.txt','verification.json','figure_contact_sheet.png','test_rules.txt'}:
            outputs.append(dict(path=path.relative_to(HERE).as_posix(),scope='task_directory',sha256=digest(path),bytes=path.stat().st_size))
    for name in ['README.md','DATA_DICTIONARY.md']:
        outputs.append(dict(path=name,scope='task_directory',sha256=digest(HERE/name),bytes=(HERE/name).stat().st_size))
    manifest=dict(task='task04_peak_valley_and_changes',derivation_version=CFG['derivation_version'],
        generated_at=datetime.now().astimezone().isoformat(),repository_commit=inputs['repository_commit'],
        rules=CFG,thresholds=thresholds,counts={name:len(frame) for name,frame in tables.items()},summary=stats,
        source_root_layout='Repository root is selected automatically when task01 metadata exists; standalone package uses inputs/; archived local_path fields retain original package locations',
        inputs=inputs['inputs'],code_files=[dict(path=name,sha256=digest(HERE/name)) for name in ['run_task04.py','report_task04.py','verify_task04.py','config.json','sources/input_manifest.json','requirements.txt','tests/test_rules.py']],
        outputs=outputs,runtime=dict(python=platform.python_version(),pandas=pd.__version__,numpy=np.__version__,matplotlib=matplotlib.__version__),
        no_new_imputation=True,retrospective_qc_not_a_predictor=True)
    (out/'derivation_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(version=CFG['derivation_version'],counts=manifest['counts'],cases=cases[['case_id','date']].astype(str).to_dict('records')),ensure_ascii=True),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=DEFAULT_SOURCE)
    parser.add_argument('--output-root',type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args();run(args.source_root,args.output_root)
