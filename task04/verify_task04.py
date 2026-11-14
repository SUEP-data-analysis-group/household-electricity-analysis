"""Independent checks from frozen minute/hour inputs; does not import calculation code."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
REPO=HERE.parent
IN_REPOSITORY=(REPO/'task01/reports/panel_definition.json').is_file()
DEFAULT_SOURCE=REPO if IN_REPOSITORY else HERE/'inputs'
DEFAULT_OUTPUT=REPO if IN_REPOSITORY else HERE
TZ='Asia/Shanghai'
LOG=[]

def check(ok,label):
    if not bool(ok):raise AssertionError(label)
    LOG.append('PASS '+label)

def read(path,column=None,**kwargs):
    x=pd.read_csv(path,float_precision='round_trip',**kwargs)
    if column:x[column]=pd.to_datetime(x[column],utc=True).dt.tz_convert(TZ)
    return x

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def close(a,b):return np.allclose(a,b,rtol=1e-11,atol=1e-10,equal_nan=True)

def main(source,root):
    out=root/'data/derived/task04'
    manifest=json.loads((out/'derivation_manifest.json').read_text(encoding='utf-8'))
    check(manifest['derivation_version']==json.loads((HERE/'config.json').read_text(encoding='utf-8'))['derivation_version'],'Declared derivation version')
    for record in manifest['inputs']:
        path=source/record['repository_path'] if record['local_path'].startswith('inputs/') else HERE/record['local_path']
        check(sha(path)==record['sha256'],'Input SHA-256 '+record['repository_path'])
        blob=hashlib.sha1(f'blob {path.stat().st_size}\0'.encode())
        with path.open('rb') as f:
            for chunk in iter(lambda:f.read(1<<20),b''):blob.update(chunk)
        assert blob.hexdigest()==record['git_blob_sha1']
    check(True,'All frozen input Git blob IDs match the recorded current repository commit')
    for record in manifest['code_files']:
        check(sha(HERE/record['path'])==record['sha256'],'Calculation/config SHA-256 '+record['path'])
    for record in manifest['outputs']:
        path=(root if record['scope']=='output_root' else HERE)/record['path']
        check(sha(path)==record['sha256'],'Output SHA-256 '+record['path'])
    h=read(source/'data/derived/task02/hourly_panel13.csv','timestamp')
    d=read(source/'data/derived/task02/daily_panel13.csv','date')
    dim=read(source/'data/derived/task03/date_dimension.csv','date')
    dates=pd.date_range('2021-05-31','2022-05-31',tz=TZ)
    times=pd.date_range(dates[0],dates[-1]+pd.Timedelta(days=1),freq='h',inclusive='left')
    check(h.timestamp.tolist()==list(times) and len(h)==8784,'8784 unique continuous hourly positions')
    check(d.date.tolist()==list(dates) and dim.date.tolist()==list(dates),'366 continuous dates and identical task03 date range')
    hc=h.hour_complete.to_numpy(dtype=bool);y=h.mean_power_kw.to_numpy(dtype=float)
    complete=hc.reshape(366,24).all(axis=1)
    check(int(hc.sum())==8503 and int(complete.sum())==352,'8503 strict hours and 352 full days')
    check(np.array_equal(complete,d.day_complete) and np.array_equal(complete,dim.day_complete),'Daily strict masks from all 24 hours agree with task02/task03')
    check(close(y,h.energy_kwh) and np.isnan(y[~hc]).all(),'Strict target uses only full hours, no partial-hour mean targets')
    std=source/'data/standardized/cn_obee_v1_noimpute_v1.0.0'
    panel=read(std/'panel_minute.csv.gz','timestamp')
    panel=panel.loc[panel.panel_id.eq('panel13')&panel.timestamp.ge(dates[0])&panel.timestamp.lt(dates[-1]+pd.Timedelta(days=1))]
    minute_times=pd.date_range(dates[0],dates[-1]+pd.Timedelta(days=1),freq='min',inclusive='left')
    check(panel.timestamp.tolist()==list(minute_times),'527040 continuous source panel13 minute positions')
    p=panel.panel_power_w.to_numpy(dtype=float).reshape(366,24,60)
    pm=panel.panel_complete.to_numpy(dtype=bool).reshape(366,24,60)
    minute_hc=pm.all(axis=2).reshape(-1)
    minute_hour=(p.sum(axis=2)/60000).reshape(-1)
    check(np.array_equal(minute_hc,hc) and close(minute_hour,y),'Independent minute matrix integration recovers strict task02 hours including NaNs')
    check(close(minute_hour.reshape(366,24).sum(axis=1),d.energy_kwh),'Independent minute-to-day integration and excluded-day NaNs')
    th=read(source/'task01/reports/strict_hourly_check.csv','timestamp')
    th=th.loc[th.panel_id.eq('panel13')]
    td=read(source/'task01/reports/strict_daily_check.csv','date')
    td=td.loc[td.panel_id.eq('panel13')]
    check(close(th.mean_power_kw,y) and close(td.energy_kwh,d.energy_kwh),'Original task01 hourly/daily references agree')

    daily=read(out/'daily_peak_valley.csv','date')
    ext=read(out/'daily_extrema_times.csv','date');ext.hour_start=pd.to_datetime(ext.hour_start,utc=True).dt.tz_convert(TZ)
    frequency=read(out/'peak_hour_frequency.csv')
    excluded=read(out/'excluded_days.csv','date')
    values=y.reshape(366,24)[complete];good_dates=dates[complete]
    check(daily.date.tolist()==list(good_dates) and len(daily)==352,'Main daily table contains exactly the 352 complete dates')
    check(excluded.date.tolist()==list(dates[~complete]) and not excluded.daily_extrema_determined.any()
          and excluded.exclusion_reason.notna().all(),'All 14 incomplete days retained separately with reasons and undetermined extrema')
    pk=np.max(values,axis=1);vl=np.min(values,axis=1);mean=np.mean(values,axis=1)
    check(close(daily.peak_kw,pk) and close(daily.valley_kw,vl) and close(daily.peak_valley_kw,pk-vl),'All daily peak, valley and range independently recalculated')
    check(close(daily.mean_kw,mean) and close(daily.load_factor,np.divide(mean,pk,out=np.full(len(pk),np.nan),where=pk!=0)),'All daily means and zero-safe load factors independently recalculated')
    check(daily.load_factor.dropna().between(0,1).all() and close(daily.energy_kwh,values.sum(axis=1)),'Load factor range and daily energy consistency')
    check(daily.panel_id.eq('panel13').all() and daily.panel_version.eq('v1.0.0').all(),'Fixed panel13 scope and version')
    labels=dim.set_index('date').loc[good_dates]
    check(np.array_equal(daily.natural_day_type,labels.natural_day_type) and np.array_equal(daily.actual_day_type,labels.actual_day_type),'Date labels inherited exactly from task03')
    expected_freq={kind:np.zeros(24) for kind in ['peak','valley']}
    for i,date in enumerate(good_dates):
        for kind,value in [('peak',pk[i]),('valley',vl[i])]:
            pos=np.flatnonzero(values[i]==value)
            actual=ext.loc[ext.date.eq(date)&ext.kind.eq(kind)].sort_values('hour_start')
            assert actual.hour.tolist()==pos.tolist() and len(actual)==len(pos)
            assert actual.hour_start.tolist()==[date+pd.Timedelta(hours=int(k)) for k in pos]
            assert actual.value_kw.eq(value).all() and actual.tied_count.eq(len(pos)).all()
            assert close(actual.weight,1/len(pos)) and close(actual.weight.sum(),1)
            expected_freq[kind][pos]+=1/len(pos)
    check(len(ext)==sum((values==pk[:,None]).sum(axis=1))+sum((values==vl[:,None]).sum(axis=1)),'Every exact float64 tie retained, no extra extrema rows')
    check(True,'Every date/kind has correct tied count, timestamp/value, equal weights summing to one')
    for kind in ['peak','valley']:
        f=frequency.loc[frequency.kind.eq(kind)].sort_values('hour')
        assert f.hour.tolist()==list(range(24)) and close(f.weighted_days,expected_freq[kind])
        assert close(f.proportion,expected_freq[kind]/352) and close(f.weighted_days.sum(),352) and close(f.proportion.sum(),1)
    check(len(frequency)==48,'Peak/valley frequency complete grids, weighting and denominators')

    changes=read(out/'hourly_changes.csv','timestamp')
    changes.previous_timestamp=pd.to_datetime(changes.previous_timestamp,utc=True).dt.tz_convert(TZ)
    valid=np.zeros(len(y),dtype=bool);valid[1:]=hc[1:] & hc[:-1]
    delta=np.full(len(y),np.nan);delta[1:]=y[1:]-y[:-1];delta[~valid]=np.nan
    cross=np.array([i>0 and t.hour==0 for i,t in enumerate(times)])
    intra=np.arange(len(y))>0;intra &= ~cross
    check(changes.timestamp.tolist()==list(times) and np.array_equal(changes.valid_change,valid),'Changes retain every calendar hour and exact validity mask')
    check(close(changes.delta_kw,delta) and close(changes.abs_delta_kw,np.abs(delta)),'Signed and absolute adjacent changes independently recomputed')
    check(changes.loc[~changes.valid_change,['delta_kw','abs_delta_kw','is_large_change']].isna().all().all(),'No differences or large-change labels across gaps/invalid hours')
    check(changes.loc[changes.valid_change,'elapsed_hours'].eq(1).all() and changes.loc[~changes.valid_change,'exclusion_reason'].notna().all(),'All valid changes are exactly 1h; invalid rows carry reasons')
    check(np.array_equal(changes.is_cross_midnight,cross) and np.array_equal(changes.is_intra_day,intra),'Cross-midnight separately labelled and first row excluded')
    split=json.loads((source/'task01/reports/split_manifest.json').read_text(encoding='utf-8'))
    left,right=map(pd.Timestamp,split['train'])
    train=(times>=left)&(times<right)
    fit=valid & train & np.r_[False,train[:-1]]
    threshold=json.loads((out/'thresholds.json').read_text(encoding='utf-8'))
    q95=float(np.quantile(np.abs(delta[fit]),.95,method='linear'))
    q90=float(np.quantile(y[train & hc],.9,method='linear'))
    check(close(threshold['train_abs_hour_change_q95_kw'],q95) and threshold['train_change_pairs']==int(fit.sum()),'Change q95 fits only pairs with both endpoints in frozen training')
    check(close(threshold['train_hourly_load_q90_kw'],q90) and threshold['train_strict_hours']==int((train & hc).sum()),'High-load q90 fits only strict frozen-training targets')
    check(np.array_equal(changes.loc[valid,'is_large_change'].astype(bool),np.abs(delta[valid])>q95),'Large-change comparison uses strict greater-than and fixed training threshold')

    comparison=read(out/'daily_minute_hourly_comparison.csv','date')
    pday=p.reshape(366,1440)[complete]
    minute_max=pday.max(axis=1)
    check(comparison.date.tolist()==list(good_dates) and close(comparison.minute_record_peak_w,minute_max),'Every complete-day minute record peak independently recomputed')
    check(close(comparison.hour_peak_kw,pk) and close(comparison.minute_record_peak_kw,minute_max/1000)
          and close(comparison.minute_to_hour_peak_ratio,minute_max/(pk*1000)),'Minute/hour scales and ratio converted to the same units')
    check((minute_max+1e-8>=pk*1000).all() and comparison.complete_minutes.eq(1440).all(),'All minute maxima dominate hour means with complete minute support')
    for i,row in enumerate(comparison.itertuples()):
        pos=np.flatnonzero(pday[i]==minute_max[i])
        assert row.minute_peak_tied_count==len(pos)
        assert [pd.Timestamp(x) for x in json.loads(row.minute_peak_times)]==[good_dates[i]+pd.Timedelta(minutes=int(k)) for k in pos]
    check(True,'All exact minute peak ties and timestamps retained')

    cases=read(out/'case_manifest.csv','date')
    allmonths=sorted(set(dates.strftime('%Y-%m')))
    month=None
    for candidate in allmonths:
        first=pd.Timestamp(candidate+'-01',tz=TZ)
        full=pd.date_range(first,first+pd.offsets.MonthBegin(1),inclusive='left')
        if set(full).issubset(set(good_dates)) and (full.weekday<5).sum()>=5 and (full.weekday>=5).sum()>=4:
            month=candidate;break
    subset=daily.loc[daily.date.dt.strftime('%Y-%m').eq(month)]
    expected=[]
    for weekday in [True,False]:
        group=subset.loc[(subset.date.dt.weekday<5).eq(weekday)]
        target=float(np.median(group.energy_kwh.to_numpy()))
        chosen=min(group.itertuples(),key=lambda row:(abs(row.energy_kwh-target),row.date))
        expected.append(chosen.date)
    cutoff=float(np.quantile(subset.energy_kwh,.95,method='linear'))
    expected.append(min(subset.loc[subset.energy_kwh.ge(cutoff)].itertuples(),key=lambda r:(r.energy_kwh,r.date)).date)
    expected.append(min(daily.itertuples(),key=lambda r:(-r.peak_kw,r.date)).date)
    check(cases.case_id.tolist()==['C01','C02','C03','C04'] and cases.date.tolist()==expected,'All four cases independently selected by predeclared month/median/quantile/global-peak rules')
    check(cases.iloc[:3].comparison_month.eq(month).all() and cases.complete_minutes.eq(1440).all(),'Ordinary and high-energy cases use one fully supported calendar month')
    definition=json.loads((source/'task01/reports/panel_definition.json').read_text(encoding='utf-8'))
    devices=next(x['devices'] for x in definition['panels'] if x['panel_id']=='panel13')
    check(all(json.loads(x)==devices for x in cases.device_ids) and cases.n_devices.eq(13).all(),'Shared task05 case manifest fixes exactly the same ordered 13-device scope')
    cm=read(out/'case_minute_curves.csv.gz','timestamp')
    ch=read(out/'case_hourly_curves.csv','timestamp')
    cq=read(out/'case_quality_summary.csv','date')
    check(len(cm)==4*1440 and not cm.duplicated(['case_id','timestamp']).any() and len(ch)==4*24 and len(cq)==4*13,'Complete case minute/hour grids and one quality row per case/device')
    raw=read(std/'power_minute.csv.gz',usecols=['timestamp','source_row_id','source_present']+devices)
    raw=raw.loc[raw.timestamp.str[:10].isin(set(cases.date.dt.strftime('%Y-%m-%d')))].copy()
    raw.timestamp=pd.to_datetime(raw.timestamp,utc=True).dt.tz_convert(TZ);raw=raw.set_index('timestamp')
    panel_index=panel.set_index('timestamp')
    for case in cases.itertuples():
        part=cm.loc[cm.case_id.eq(case.case_id)].sort_values('timestamp')
        expected_minutes=pd.date_range(case.date,case.date+pd.Timedelta(days=1),freq='min',inclusive='left')
        assert part.timestamp.tolist()==list(expected_minutes)
        source_part=raw.reindex(expected_minutes)
        assert close(part[devices].to_numpy(),source_part[devices].to_numpy())
        assert np.array_equal(part.source_row_id,source_part.source_row_id) and np.array_equal(part.source_present,source_part.source_present)
        assert close(part.panel_power_w,panel_index.reindex(expected_minutes).panel_power_w)
        assert close(part[devices].sum(axis=1),part.panel_power_w) and part.panel_complete.all()
        hh=ch.loc[ch.case_id.eq(case.case_id)].sort_values('timestamp')
        assert close(part.panel_power_w.to_numpy().reshape(24,60).sum(axis=1)/60000,hh.mean_power_kw)
        dayext=ext.loc[ext.date.eq(case.date)]
        assert [pd.Timestamp(x) for x in json.loads(case.peak_hour_starts)]==dayext.loc[dayext.kind.eq('peak'),'hour_start'].tolist()
        assert [pd.Timestamp(x) for x in json.loads(case.valley_hour_starts)]==dayext.loc[dayext.kind.eq('valley'),'hour_start'].tolist()
        pp=part.panel_power_w.to_numpy();pos=np.flatnonzero(pp==pp.max())
        assert [pd.Timestamp(x) for x in json.loads(case.minute_record_peak_times)]==list(expected_minutes[pos])
    check(True,'Every case minute value/source row, simultaneous panel sum, hour integral and all peak intervals match source')
    for device in devices:
        q=read(std/'appliance_quality'/f'{device}.csv.gz',usecols=['timestamp','qc_bits','is_usable','is_new_imputed'])
        q=q.loc[q.timestamp.str[:10].isin(set(cases.date.dt.strftime('%Y-%m-%d')))].copy()
        q.timestamp=pd.to_datetime(q.timestamp,utc=True).dt.tz_convert(TZ);q=q.set_index('timestamp')
        for case in cases.itertuples():
            part=cm.loc[cm.case_id.eq(case.case_id)]
            src=q.reindex(part.timestamp);bits=src.qc_bits.to_numpy(dtype='int64')
            assert np.array_equal(part[device+'_qc_bits'],bits) and src.is_usable.all() and not src.is_new_imputed.any()
            row=cq.loc[cq.case_id.eq(case.case_id)&cq.appliance_id.eq(device)].iloc[0]
            assert row.near_sensor_limit_review_minutes==int(((bits&16)!=0).sum())
            assert row.long_constant_review_minutes==int(((bits&32)!=0).sum())
            assert row.usable_minutes==1440 and row.new_imputed_minutes==0 and row.unusable_minutes==0
        check(True,'Original minute QC and quality summaries preserved for '+device)
    combined=np.bitwise_or.reduce(cm[[x+'_qc_bits' for x in devices]].to_numpy(dtype='int64'),axis=1)
    check(np.array_equal(cm.combined_qc_bits,combined) and np.array_equal(cm.any_review_flag,(combined&48)!=0)
          and cm.new_imputed_devices.eq(0).all(),'Minute review masks retained without imputation or suppression')
    text=(HERE/'reports/task04_report.html').read_text(encoding='utf-8')
    check(text.count('data:image/png;base64,')==8 and len(list((HERE/'reports/figures').glob('*.png')))==8,'Eight readable figures, all embedded in standalone HTML')
    check('<table' in text and '352' in text and '跨午夜' in text,'Report contains real tables, sample support and midnight distinction')
    check(manifest['no_new_imputation'] and manifest['retrospective_qc_not_a_predictor'],'No new imputation; retrospective QC explicitly not a predictor')
    return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,default=DEFAULT_SOURCE)
    parser.add_argument('--output-root',type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args();passed=False
    try:
        main(args.source_root.resolve(),args.output_root.resolve());passed=True
    except Exception as exc:
        LOG.append('FAIL '+repr(exc));raise
    finally:
        folder=HERE/'reports';folder.mkdir(exist_ok=True)
        tail=f'ALL PASS ({len(LOG)} checks)' if passed else 'VERIFICATION FAILED'
        (folder/'verify_task04.txt').write_text('\n'.join(LOG)+'\n'+tail+'\n',encoding='utf-8')
        (folder/'verification.json').write_text(json.dumps(dict(passed=passed,checks=len(LOG),details=LOG),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(tail,flush=True)
