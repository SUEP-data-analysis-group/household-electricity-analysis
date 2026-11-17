"""Task05 后三步：审核上游、生成运行状态、统计同分钟重叠及可追溯支持。"""
import itertools
import json
import platform
import shutil
import numpy as np
import pandas as pd
from common import *
from operation_rules import classify,REASONS


def ratio(a,b): return float(a)/int(b) if int(b)>0 else np.nan


def preflight(p,valid,qc):
    checks=[]
    def check(name,condition,**extra):
        assert bool(condition),name
        checks.append(dict(check=name,passed=True,**extra))
    imported=json.loads((INPUT/'import_manifest.json').read_text(encoding='utf-8'))
    for entry in imported['files']:
        path=ROOT/entry['local_path']
        check('import_hash_'+entry['local_path'],sha(path)==entry['sha256'])
    peer=json.loads((INPUT/'first_three/out/derivation_manifest.json').read_text(encoding='utf-8'))
    for group in ['inputs','outputs','code']:
        for entry in peer[group]:
            rel=Path(entry['file'].replace(chr(92),'/'))
            path=INPUT/rel.relative_to('inputs') if rel.parts[0]=='inputs' else INPUT/'first_three'/rel
            check('peer_manifest_'+entry['file'],sha(path)==entry['sha256'])
    check('peer_audit_all_pass',peer['all_pass'])
    mask_complete=complete_day_mask(p.index)
    panel=read(INPUT/'standardized/panel_minute.csv.gz')
    panel['timestamp']=pd.to_datetime(panel.timestamp,utc=True).dt.tz_convert(TZ)
    panel=panel.loc[panel.timestamp.ge(START)&panel.timestamp.lt(END)]
    a=panel.loc[panel.panel_id.eq('panel13')].set_index('timestamp').reindex(p.index)
    known=valid.all(axis=1).to_numpy()
    check('panel13_510284_minutes',int(known.sum())==510284)
    check('panel13_complete_quality_exact',np.array_equal(known,a.panel_complete.to_numpy(bool)))
    check('main_352days_506880_minutes',int(mask_complete.sum())==506880 and known[mask_complete].all())
    summed=p.sum(axis=1,min_count=13).to_numpy()
    check('minute_panel_device_sum',np.allclose(summed[known],a.panel_power_w.to_numpy()[known],atol=1e-8,rtol=1e-12))
    energies={}
    for scope,mask in [('panel13_complete_352d',mask_complete),('panel13_all_common_valid',known)]:
        total=float(np.sum(summed[mask])/60000);energies[scope]=total
        table=read(INPUT/'first_three/out/交付表/contribution_panel13.csv')
        table=table.loc[table.sample_scope.eq(scope)].set_index('appliance_id')
        raw=p.loc[mask].sum()/60000
        raw.loc['__panel13__']=total
        check('contribution_'+scope,np.allclose(raw.reindex(table.index),table.energy_kwh,atol=1e-6,rtol=0)
            and np.allclose(table.denominator_kwh,total,atol=1e-6,rtol=0),energy_kwh=total)
    h=read(INPUT/'task02/hourly_panel13.csv')
    times=pd.to_datetime(h.timestamp,utc=True).dt.tz_convert(TZ)
    expected=pd.date_range(START,END,inclusive='left',freq='h')
    check('hour_keys_8784_exact',pd.DatetimeIndex(times).equals(expected))
    hm=mask_complete.reshape(-1,60).all(axis=1)
    kh=summed.reshape(-1,60).sum(axis=1)/60000
    strict=known.reshape(-1,60).all(axis=1)
    check('strict_hours8503_main_hours8448',int(strict.sum())==8503 and int(hm.sum())==8448 and np.array_equal(strict,h.hour_complete))
    maxdiff=float(np.max(np.abs(kh[hm]-h.loc[hm,'mean_power_kw'].to_numpy())))
    check('same8448hour_targets_reconcile',maxdiff<=1e-9,max_abs_diff_kw=maxdiff)
    check('all8503strict_targets_reconcile',np.allclose(kh[strict],h.loc[strict,'mean_power_kw'],atol=1e-9,rtol=0))
    partial_nonnull=int(h.loc[~strict,'mean_power_kw'].notna().sum())
    if (INPUT/'task02_reference/hourly_panel13.csv').exists():
        ref=read(INPUT/'task02_reference/hourly_panel13.csv')
        check('newer_hour_reference_strict_exact',np.allclose(h.loc[strict,'mean_power_kw'],ref.loc[strict,'mean_power_kw'],atol=0,rtol=0)
            and ref.loc[~strict,'mean_power_kw'].isna().all())
    save(pd.DataFrame(dict(timestamp=times,main_complete_day=hm,hour_complete=strict,minute_recomputed_kw=np.where(strict,kh,np.nan),
        inherited_mean_kw=h.mean_power_kw,strict_target_kw=h.mean_power_kw.where(strict),
        partial_mean_not_target=(~strict)&h.mean_power_kw.notna().to_numpy())),'upstream_hour_reconciliation.csv')
    # 独立核对 panel14 的共同集合，rice_cooker 不进入运行状态面板。
    rice=read(INPUT/'standardized/power_minute.csv.gz',usecols=['rice_cooker_w']).rice_cooker_w.to_numpy()[:len(p)]
    panel14=panel.loc[panel.panel_id.eq('panel14')].set_index('timestamp').reindex(p.index)
    m14=panel14.panel_complete.to_numpy(bool)
    check('panel14_217643_minutes',int(m14.sum())==217643 and np.isfinite(rice[m14]).all())
    v14=summed+rice
    check('panel14_sum_same_minute',np.allclose(v14[m14],panel14.panel_power_w.to_numpy()[m14],atol=1e-8,rtol=1e-12))
    pdays=m14.reshape(-1,1440).all(axis=1);mask148=np.repeat(pdays,1440)
    check('panel14_148_strict_days',int(pdays.sum())==148)
    t14=read(INPUT/'first_three/out/交付表/contribution_panel14_supplement.csv')
    for scope,mask in [('panel14_all_common_valid',m14),('panel14_complete_148d',mask148)]:
        for panel_id,values,devlist in [('panel14',np.column_stack([p.to_numpy(),rice]),list(p)+['rice_cooker_w']),('panel14_same_set_ref13',p.to_numpy(),list(p))]:
            sub=t14.loc[t14.sample_scope.eq(scope)&t14.panel_id.eq(panel_id)].set_index('appliance_id')
            calced=pd.Series(np.sum(values[mask],axis=0)/60000,index=devlist)
            if panel_id=='panel14': calced.loc['__panel14__']=float(calced.sum())
            check(panel_id+'_'+scope,np.allclose(calced.reindex(sub.index),sub.energy_kwh,atol=1e-6,rtol=0,equal_nan=True))
    peaks=read(INPUT/'task04/daily_extrema_times.csv');peaks=peaks.loc[peaks.kind.eq('peak')]
    check('363_peak_intervals',len(peaks)==363)
    inherited=read(INPUT/'first_three/out/交付表/peak_contribution.csv')
    ph=inherited.loc[inherited.level.eq('hour_peak')].copy()
    keys=pd.to_datetime(ph.timestamp).dt.tz_localize(TZ)
    positions=pd.DatetimeIndex(times).get_indexer(keys)
    check('peak_keys_in_valid_hours',(positions>=0).all() and strict[positions].all())
    device_idx={dev:i for i,dev in enumerate(p)}
    device_hours=p.to_numpy().reshape(-1,60,13).sum(axis=1)/60000
    calculated=np.array([device_hours[pos,device_idx[dev]] for pos,dev in zip(positions,ph.appliance_id)])
    check('peak_device_values_same_hour',np.allclose(calculated,ph.value_kw,atol=1e-9,rtol=0))
    check('peak_all_ties_and_devices',len(ph)==363*13 and ph.groupby('timestamp').appliance_id.nunique().eq(13).all())
    cases=read(INPUT/'task04/case_manifest.csv')
    dates=pd.to_datetime(cases.date,utc=True).dt.tz_convert(TZ)
    dm=read(INPUT/'task03/date_dimension.csv').set_index('date')
    dm.index=pd.to_datetime(dm.index,utc=True).tz_convert(TZ)
    check('fixed_case_ids',cases.case_id.tolist()==['C01','C02','C03','C04'])
    check('case_day_labels_match_task03',np.array_equal(cases.actual_day_type,dm.loc[dates,'actual_day_type']) and np.array_equal(cases.natural_day_type,dm.loc[dates,'natural_day_type']))
    for entry in cases.itertuples():
        for timestamp in json.loads(entry.minute_record_peak_times):
            ts=pd.Timestamp(timestamp);position=p.index.get_loc(ts)
            minute=inherited.loc[inherited.level.eq('minute_peak')&inherited.case_id.eq(entry.case_id)].set_index('appliance_id')
            check('minute_peak_'+entry.case_id,np.allclose(p.iloc[position].reindex(minute.index)/1000,minute.value_kw,atol=1e-9,rtol=0))
    # 上游文件原样承接，另外保留清单以免覆盖前三步出处。
    for name in ['contribution_panel13.csv','contribution_panel14_supplement.csv','peak_contribution.csv','case_manifest.csv']:
        shutil.copy2(INPUT/'first_three/out/交付表'/name,OUT/name)
    for name in ['A_sample_day_list_panel13.csv','A_sample_day_list_panel14.csv','C_peak_summary.csv','C_case_peak.csv']:
        shutil.copy2(INPUT/'first_three/out'/name,OUT/name)
    shutil.copy2(INPUT/'first_three/out/derivation_manifest.json',OUT/'upstream_first_three_manifest.json')
    from prepare_delivery import prepare
    prepare()
    write_json(OUT/'AB_upstream_reaudit.json',dict(generated_at=now(),scope='task05 self re-audit; no claim of task06 actual model verification',
        all_pass=True,checks=checks,energy_kwh=energies,partial_hour_mean_nonnull=partial_nonnull,
        resolution='Inherited raw column preserved. Never use mean_power_kw without hour_complete; strict_target_kw blanks incomplete hours.'))
    return mask_complete,known,cases,summed


def make_states(p,valid,thresholds,scale=1):
    states=np.empty(p.shape,dtype=np.int8);reasons=np.empty(p.shape,dtype=np.uint8)
    for j,dev in enumerate(p):
        t=thresholds.loc[dev]
        states[:,j],reasons[:,j]=classify(p[dev].to_numpy(),valid[dev].to_numpy(),t.on_threshold_w*scale,t.off_threshold_w*scale,
            int(t.min_on_minutes),int(t.min_off_minutes),t.detection_status!='unidentifiable')
    return states,reasons


def support_tables(p,states,reasons,qc,scopes):
    rows=[];monthly=[];events=[]
    for scope,mask in scopes.items():
        for j,dev in enumerate(p):
            s=states[mask,j];r=reasons[mask,j];bits=qc[dev].to_numpy()[mask]
            known=int((s>=0).sum());on=int((s==1).sum());unknown=int((s<0).sum())
            row=dict(sample_scope=scope,appliance_id=dev,observed_minutes=int(mask.sum()),known_minutes=known,
                unknown_minutes=unknown,unknown_fraction=ratio(unknown,mask.sum()),on_minutes=on,off_minutes=int((s==0).sum()),
                on_rate_given_known=ratio(on,known),on_qc16_review_minutes=int(((s==1)&(bits&16!=0)).sum()),
                on_qc32_review_minutes=int(((s==1)&(bits&32!=0)).sum()),threshold_version=VERSION)
            for code,name in REASONS.items():
                if code: row['unknown_'+name+'_minutes']=int((r==code).sum())
            rows.append(row)
    months=p.index.strftime('%Y-%m')
    for month in sorted(set(months)):
        mask=months==month
        for j,dev in enumerate(p):
            s=states[mask,j]
            monthly.append(dict(year_month=month,appliance_id=dev,calendar_minutes=int(mask.sum()),known_minutes=int((s>=0).sum()),
                on_minutes=int((s==1).sum()),unknown_minutes=int((s<0).sum()),on_rate_given_known=ratio((s==1).sum(),(s>=0).sum())))
    for j,dev in enumerate(p):
        is_on=states[:,j]==1
        changes=np.diff(np.r_[False,is_on,False].astype(np.int8))
        starts=np.flatnonzero(changes==1);ends=np.flatnonzero(changes==-1)
        for a,b in zip(starts,ends):
            events.append(dict(appliance_id=dev,start=p.index[a].isoformat(),end_exclusive=(p.index[b-1]+pd.Timedelta(minutes=1)).isoformat(),
                confirmed_on_minutes=int(b-a),energy_kwh=float(p[dev].iloc[a:b].sum()/60000),
                left_boundary='window_start' if a==0 else 'previous_unknown' if states[a-1,j]<0 else 'previous_off',
                right_boundary='window_end' if b==len(p) else 'next_unknown' if states[b,j]<0 else 'next_off',
                interpretation='confirmed on segment only; not a full appliance cycle'))
    return pd.DataFrame(rows),pd.DataFrame(monthly),pd.DataFrame(events)


def overlap_tables(states,qc,devs,subset,scopes):
    rows=[];groups=[];hist=[]
    subset_idx=[devs.index(dev) for dev in subset]
    for scope,mask in scopes.items():
        n=int(mask.sum());all13=(states>=0).all(axis=1)&mask
        common=(states[:,subset_idx]>=0).all(axis=1)&mask
        for name,idx,known in [('panel13_all_known',list(range(13)),all13),('S12_common_known',subset_idx,common)]:
            counts=(states[known][:,idx]==1).sum(axis=1)
            groups.append(dict(sample_scope=scope,device_set=name,device_ids=json.dumps([devs[i] for i in idx]),
                observed_minutes=n,known_minutes=int(known.sum()),unknown_fraction=ratio(n-known.sum(),n),
                at_least_two_on_minutes=int((counts>=2).sum()),at_least_two_on_rate=ratio((counts>=2).sum(),len(counts)),
                mean_on_device_count=float(counts.mean()) if len(counts) else np.nan))
            for count in range(len(idx)+1): hist.append(dict(sample_scope=scope,device_set=name,n_on=count,n_minutes=int((counts==count).sum()),rate_given_common_known=ratio((counts==count).sum(),len(counts))))
        for i,j in itertools.combinations(range(13),2):
            pair=(states[:,i]>=0)&(states[:,j]>=0)&mask
            denominators=[('pairwise_known',pair)]
            if i in subset_idx and j in subset_idx: denominators.append(('S12_common_known',common))
            for name,known in denominators:
                a=states[:,i]==1;b=states[:,j]==1
                nk=int(known.sum());both=int((a&b&known).sum());ia=int((a&known).sum());jb=int((b&known).sum());union=int(((a|b)&known).sum())
                review=((qc.iloc[:,i].to_numpy()&48)!=0)|((qc.iloc[:,j].to_numpy()&48)!=0)
                rows.append(dict(sample_scope=scope,denominator_scope=name,appliance_i=devs[i],appliance_j=devs[j],
                    observed_minutes=n,known_minutes=nk,unknown_fraction=ratio(n-nk,n),both_on_minutes=both,
                    overlap_rate=ratio(both,nk),i_on_known_minutes=ia,j_on_known_minutes=jb,
                    p_j_on_given_i_on=ratio(both,ia),p_i_on_given_j_on=ratio(both,jb),union_on_minutes=union,jaccard=ratio(both,union),
                    both_on_with_qc_review_minutes=int((a&b&known&review).sum()),threshold_version=VERSION,
                    metric_definition='both_on / simultaneous_known; unknown excluded, never off'))
    return pd.DataFrame(rows),pd.DataFrame(groups),pd.DataFrame(hist)


def main():
    OUT.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    config=json.loads((HERE/'config.json').read_text(encoding='utf-8'))
    audit=json.loads((OUT/'C_state_rule_audit.json').read_text(encoding='utf-8'))
    assert audit['all_pass']
    for entry in audit['frozen_files']: assert sha(ROOT/entry['path'])==entry['sha256'],'Frozen rules changed; rerun C audit'
    p,valid,qc=load_power_quality()
    main_mask,common_valid,cases,summed=preflight(p,valid,qc)
    thresholds=read(OUT/'operation_thresholds.csv').set_index('appliance_id')
    states,reasons=make_states(p,valid,thresholds)
    assert (states[:,list(p).index('air_conditioner_3_w')]==-1).all()
    assert (states[~valid.to_numpy()]==-1).all()
    frame=pd.DataFrame({'timestamp':p.index})
    names=np.array(['unknown','off','on'])
    for j,dev in enumerate(p): frame[dev]=names[states[:,j]+1]
    for j,dev in enumerate(p): frame[dev+'__reason']=reasons[:,j]
    frame['any_qc_review']=(qc.to_numpy()&48!=0).any(axis=1)
    save(frame,'minute_operation_state.csv.gz')
    scopes={'panel13_complete_352d':main_mask,'all_calendar_527040':np.ones(len(p),bool)}
    support,monthly,events=support_tables(p,states,reasons,qc,scopes)
    save(support,'operation_support.csv');save(monthly,'monthly_operation_support.csv');save(events,'confirmed_on_segments.csv')
    overlap,group,hist=overlap_tables(states,qc,list(p),config['comparable_operation_subset'],scopes)
    save(overlap,'overlap_summary.csv');save(group,'overlap_group_summary.csv');save(hist,'concurrent_device_count.csv')
    case_rows=[]
    for case in cases.itertuples():
        date=pd.Timestamp(case.date);mask=p.index.normalize()==date
        x=frame.loc[mask].copy();x.insert(0,'case_id',case.case_id)
        x['panel13_power_kw']=summed[mask]/1000
        for dev in p: x[dev+'__power_w']=p.loc[mask,dev].to_numpy()
        case_rows.append(x)
    save(pd.concat(case_rows,ignore_index=True),'case_operation_state.csv.gz')
    # 只改变预先声明阈值比例作描述敏感性，不用结果反向选阈值。
    sens_support=[];sens_pairs=[]
    for scale in config['threshold_sensitivity_scales']:
        if scale==1: st=states
        else: st,_=make_states(p,valid,thresholds,scale)
        ids=[list(p).index(d) for d in config['comparable_operation_subset']]
        known=(st[:,ids]>=0).all(axis=1)&main_mask
        for j,dev in enumerate(p):
            s=st[main_mask,j];sens_support.append(dict(threshold_scale=scale,appliance_id=dev,known_minutes=int((s>=0).sum()),
                on_minutes=int((s==1).sum()),unknown_fraction=ratio((s<0).sum(),len(s)),on_rate_given_known=ratio((s==1).sum(),(s>=0).sum())))
        for i,j in itertools.combinations(ids,2):
            both=int(((st[:,i]==1)&(st[:,j]==1)&known).sum())
            sens_pairs.append(dict(threshold_scale=scale,appliance_i=list(p)[i],appliance_j=list(p)[j],known_minutes=int(known.sum()),
                both_on_minutes=both,overlap_rate=ratio(both,known.sum())))
    save(pd.DataFrame(sens_support),'threshold_sensitivity_support.csv');save(pd.DataFrame(sens_pairs),'threshold_sensitivity_overlap.csv')
    write_json(OUT/'state_generation_record.json',dict(generated_at=now(),minutes=len(p),devices=list(p),
        state_file_sha256=sha(OUT/'minute_operation_state.csv.gz'),threshold_sha256=sha(OUT/'operation_thresholds.csv'),
        config_sha256=sha(HERE/'config.json'),training_rule_audit_sha256=sha(OUT/'C_state_rule_audit.json'),
        no_backfill=True,no_future_minutes=True,no_new_power_imputation=True,all13_common_known_minutes=0,
        runtime=dict(python=platform.python_version(),pandas=pd.__version__,numpy=np.__version__)))
    print('PASS states 527040 x 13; overlap rows',len(overlap),'confirmed segments',len(events))
    print(group.to_string(index=False,columns=['sample_scope','device_set','known_minutes','at_least_two_on_rate']))
    print(overlap.loc[overlap.sample_scope.eq('panel13_complete_352d')&overlap.denominator_scope.eq('S12_common_known')].nlargest(5,'overlap_rate')[['appliance_i','appliance_j','known_minutes','both_on_minutes','overlap_rate']].to_string(index=False))

if __name__=='__main__': main()
