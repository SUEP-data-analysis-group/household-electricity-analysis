"""独立复核 Task05：以向量化证据事件重建状态，不调用生产状态机。"""
import itertools
import json
import subprocess
import sys
import numpy as np
import pandas as pd
from common import *


def reference_states(x, usable, t, scale=1):
    """用连续阈值证据长度和最近确认事件推导状态，独立于逐点状态机。"""
    x=np.asarray(x);good=np.asarray(usable)&np.isfinite(x)
    n=len(x);idx=np.arange(n);reason=np.zeros(n,np.uint8)
    if t.detection_status=='unidentifiable':
        reason[:]=2;reason[~good]=1
        return np.full(n,-1,np.int8),reason
    high=good&(x>=t.on_threshold_w*scale);low=good&(x<=t.off_threshold_w*scale)
    def length(flag): return idx-np.maximum.accumulate(np.where(~flag,idx,-1))
    confirmed_high=high&(length(high)>=int(t.min_on_minutes))
    confirmed_low=low&(length(low)>=int(t.min_off_minutes))
    event=~good|confirmed_high|confirmed_low
    event_label=np.full(n,-1,np.int8);event_label[confirmed_high]=1;event_label[confirmed_low]=0
    previous=np.maximum.accumulate(np.where(event,idx,-1))
    state=np.where(previous>=0,event_label[np.maximum(previous,0)],-1).astype(np.int8)
    pending_high=good&high&(state!=1);pending_low=good&low&(state!=0)
    reason[good&(state<0)&~high&~low]=3
    reason[pending_high]=4;reason[pending_low]=5;reason[~good]=1
    state[reason!=0]=-1
    return state,reason


def main():
    checks=[]
    def check(name,condition,**details):
        checks.append(dict(check=name,passed=bool(condition),**details))
        if not condition:
            write_json(OUT/'verification_task05.json',dict(all_pass=False,checks=checks))
            raise AssertionError(name)
    check('required_derivation_manifest_exists',(OUT/'derivation_manifest.json').is_file())
    p,valid,qc=load_power_quality();devs=list(p);mask=complete_day_mask(p.index)
    config=json.loads((HERE/'config.json').read_text(encoding='utf-8'))
    thresholds=read(OUT/'operation_thresholds.csv').set_index('appliance_id')
    frame=read(OUT/'minute_operation_state.csv.gz')
    timestamps=pd.DatetimeIndex(pd.to_datetime(frame.timestamp,utc=True).dt.tz_convert(TZ))
    check('continuous_unique_527040_minute_axis',timestamps.equals(p.index) and timestamps.is_unique and len(frame)==527040)
    check('fixed_panel13_no_rice',devs==devices()==config['fixed_energy_panel'] and len(devs)==13 and 'rice_cooker_w' not in devs)
    check('frozen_training_end',thresholds.fitted_end_exclusive.eq(TRAIN_END.isoformat()).all() and thresholds.fitted_start.eq(START.isoformat()).all())
    values=frame[devs].to_numpy()
    s=np.where(values=='on',1,np.where(values=='off',0,-1)).astype(np.int8)
    reasons=frame[[d+'__reason' for d in devs]].to_numpy(np.uint8)
    check('only_three_states',frame[devs].isin(['unknown','off','on']).all().all())
    for j,d in enumerate(devs):
        a,b=reference_states(p[d].to_numpy(),valid[d].to_numpy(),thresholds.loc[d])
        check('independent_full_state_and_reason_'+d,np.array_equal(s[:,j],a) and np.array_equal(reasons[:,j],b),compared_minutes=len(p))
    check('source_invalid_always_unknown',np.all(s[~valid.to_numpy()]==-1) and np.all(reasons[~valid.to_numpy()]==1))
    ac3=devs.index('air_conditioner_3_w')
    check('AC3_all_unknown_energy_retained',np.all(s[:,ac3]==-1) and p.iloc[:,ac3].notna().any())
    check('review_bits_not_deleted_and_no_filling',np.array_equal(frame.any_qc_review.to_numpy(),((qc.to_numpy()&48)!=0).any(axis=1)))
    # 生产状态机只用于独立于全状态重建的因果前缀测试。
    from operation_rules import classify
    for j,d in enumerate(devs):
        t=thresholds.loc[d];cuts=[1,59,60,1441,50000,406080,446400]
        for cut in cuts:
            a,b=classify(p[d].to_numpy()[:cut],valid[d].to_numpy()[:cut],t.on_threshold_w,t.off_threshold_w,int(t.min_on_minutes),int(t.min_off_minutes),t.detection_status!='unidentifiable')
            assert np.array_equal(a,s[:cut,j]) and np.array_equal(b,reasons[:cut,j]),(d,cut)
    check('causal_prefix_invariance_91_prefixes',True,prefixes=13*7)
    scopes={'panel13_complete_352d':mask,'all_calendar_527040':np.ones(len(p),bool)}
    support=read(OUT/'operation_support.csv')
    for row in support.itertuples():
        use=scopes[row.sample_scope];j=devs.index(row.appliance_id);x=s[use,j];r=reasons[use,j]
        assert row.observed_minutes==use.sum() and row.known_minutes==(x>=0).sum()
        assert row.on_minutes==(x==1).sum() and row.off_minutes==(x==0).sum() and row.unknown_minutes==(x<0).sum()
        assert row.on_minutes+row.off_minutes+row.unknown_minutes==row.observed_minutes
        for code,name in config['reason_codes'].items():
            if int(code): assert getattr(row,'unknown_'+name+'_minutes')==(r==int(code)).sum()
        bits=qc.iloc[:,j].to_numpy()[use]
        assert row.on_qc16_review_minutes==((x==1)&(bits&16!=0)).sum()
        assert row.on_qc32_review_minutes==((x==1)&(bits&32!=0)).sum()
    check('support_and_unknown_reason_counts_26_rows',len(support)==26)
    monthly=read(OUT/'monthly_operation_support.csv')
    totals=monthly.groupby('appliance_id')[['calendar_minutes','known_minutes','on_minutes','unknown_minutes']].sum()
    full=support[support.sample_scope.eq('all_calendar_527040')].set_index('appliance_id')
    check('monthly_support_sums',np.array_equal(totals.loc[devs,'calendar_minutes'],full.loc[devs,'observed_minutes']) and all(np.array_equal(totals.loc[devs,c],full.loc[devs,c]) for c in ['known_minutes','on_minutes','unknown_minutes']))
    events=read(OUT/'confirmed_on_segments.csv')
    grouped=events.groupby('appliance_id').confirmed_on_minutes.sum().reindex(devs,fill_value=0)
    check('confirmed_segment_minutes_equal_all_on',np.array_equal(grouped,full.loc[devs,'on_minutes']))
    starts=pd.DatetimeIndex(pd.to_datetime(events.start,utc=True).dt.tz_convert(TZ));ends=pd.DatetimeIndex(pd.to_datetime(events.end_exclusive,utc=True).dt.tz_convert(TZ))
    check('segment_time_lengths',np.array_equal((ends-starts).total_seconds()/60,events.confirmed_on_minutes))
    for row,a,b in zip(events.itertuples(),p.index.get_indexer(starts),p.index.get_indexer(ends-pd.Timedelta(minutes=1))+1):
        j=devs.index(row.appliance_id)
        assert np.all(s[a:b,j]==1) and (a==0 or s[a-1,j]!=1) and (b==len(p) or s[b,j]!=1)
        assert abs(p.iloc[a:b,j].sum()/60000-row.energy_kwh)<1e-9
    check('segments_maximal_on_ranges_and_energy',True,segments=len(events))
    subset=[devs.index(d) for d in config['comparable_operation_subset']]
    check('S12_excludes_only_AC3',len(subset)==12 and set(subset)==set(range(13))-{ac3})
    pairs=read(OUT/'overlap_summary.csv')
    def assert_ratio(actual,num,den):
        assert pd.isna(actual) if den==0 else np.isclose(actual,num/den,rtol=0,atol=1e-14)
    for row in pairs.itertuples():
        i=devs.index(row.appliance_i);j=devs.index(row.appliance_j);scope=scopes[row.sample_scope]
        k=scope&((s[:,subset]>=0).all(axis=1) if row.denominator_scope=='S12_common_known' else ((s[:,i]>=0)&(s[:,j]>=0)))
        a=s[:,i]==1;b=s[:,j]==1;both=int((a&b&k).sum());ia=int((a&k).sum());jb=int((b&k).sum());union=int(((a|b)&k).sum());nk=int(k.sum())
        assert row.known_minutes==nk and row.both_on_minutes==both and row.observed_minutes==scope.sum()
        assert row.i_on_known_minutes==ia and row.j_on_known_minutes==jb and row.union_on_minutes==union
        assert_ratio(row.overlap_rate,both,nk);assert_ratio(row.unknown_fraction,scope.sum()-nk,scope.sum())
        assert_ratio(row.p_j_on_given_i_on,both,ia);assert_ratio(row.p_i_on_given_j_on,both,jb);assert_ratio(row.jaccard,both,union)
        review=((qc.iloc[:,i].to_numpy()|qc.iloc[:,j].to_numpy())&48)!=0
        assert row.both_on_with_qc_review_minutes==(a&b&k&review).sum()
    check('independent_all_pair_counts_and_five_rates',len(pairs)==288,rows=len(pairs))
    check('AC3_24_pair_scope_rows_zero_known_and_missing_rate',len(pairs[pairs.known_minutes.eq(0)])==24 and pairs.loc[pairs.known_minutes.eq(0),'overlap_rate'].isna().all())
    group=read(OUT/'overlap_group_summary.csv');hist=read(OUT/'concurrent_device_count.csv')
    for row in group.itertuples():
        ids=subset if row.device_set=='S12_common_known' else list(range(13))
        use=scopes[row.sample_scope]&(s[:,ids]>=0).all(axis=1);counts=(s[use][:,ids]==1).sum(axis=1)
        assert row.known_minutes==use.sum() and row.at_least_two_on_minutes==(counts>=2).sum()
        assert_ratio(row.at_least_two_on_rate,(counts>=2).sum(),len(counts))
        sub=hist[hist.sample_scope.eq(row.sample_scope)&hist.device_set.eq(row.device_set)]
        for h in sub.itertuples(): assert h.n_minutes==(counts==h.n_on).sum()
    check('global_groups_and_concurrency_histograms',len(group)==4)
    case=read(OUT/'case_operation_state.csv.gz');manifest=read(OUT/'case_manifest.csv')
    check('four_original_case_files_unchanged',sha(OUT/'case_manifest.csv')==sha(INPUT/'task04/case_manifest.csv'))
    check('four_case_days_5760_minutes',len(case)==5760 and manifest.case_id.tolist()==['C01','C02','C03','C04'] and pd.to_datetime(manifest.date).dt.strftime('%Y-%m-%d').tolist()==['2021-08-10','2021-08-22','2021-08-04','2021-07-12'])
    loc=p.index.get_indexer(pd.to_datetime(case.timestamp,utc=True).dt.tz_convert(TZ))
    check('case_states_and_power_same_minute',np.array_equal(case[devs].to_numpy(),frame.iloc[loc][devs].to_numpy()) and np.array_equal(case[[d+'__power_w' for d in devs]].to_numpy(),p.iloc[loc].to_numpy()))
    sens=read(OUT/'threshold_sensitivity_support.csv');sp=read(OUT/'threshold_sensitivity_overlap.csv')
    for scale in [.8,1,1.2]:
        st=np.column_stack([reference_states(p[d].to_numpy(),valid[d].to_numpy(),thresholds.loc[d],scale)[0] for d in devs])
        k=mask&(st[:,subset]>=0).all(axis=1)
        for row in sens[sens.threshold_scale.eq(scale)].itertuples():
            x=st[mask,devs.index(row.appliance_id)];assert row.known_minutes==(x>=0).sum() and row.on_minutes==(x==1).sum()
        for row in sp[sp.threshold_scale.eq(scale)].itertuples():
            both=((st[:,devs.index(row.appliance_i)]==1)&(st[:,devs.index(row.appliance_j)]==1)&k).sum()
            assert row.known_minutes==k.sum() and row.both_on_minutes==both;assert_ratio(row.overlap_rate,both,k.sum())
    check('independent_sensitivity_all_scales',len(sens)==39 and len(sp)==198)
    for f in ['contribution_panel13.csv','contribution_panel14_supplement.csv','peak_contribution.csv','case_manifest.csv']:
        original=read(INPUT/'first_three/out/交付表'/f)
        current=read(OUT/f)
        metadata={'n_days','date_list_file','period_first_minute','period_last_minute'}
        columns=[c for c in original if c not in metadata]
        pd.testing.assert_frame_equal(original[columns],current[columns],check_exact=True)
        check('unchanged_first_three_values_'+f,True)
    check('case_manifest_bytes_unchanged',sha(OUT/'case_manifest.csv')==sha(INPUT/'task04/case_manifest.csv'))
    from verify_delivery import verify_delivery
    for name in verify_delivery(p,valid,mask):
        check(name,True)
    for name in ['contribution_panel13.csv','contribution_panel14_supplement.csv']:
        table=read(OUT/name)
        for key,rows in table.groupby(['sample_scope','panel_id']):
            # 原表含合计和同集合ref13电饭煲空占位；只对实际设备能量行求和。
            part=rows[rows.appliance_id.isin(devs+['rice_cooker_w'])&rows.energy_kwh.notna()]
            assert part.appliance_id.is_unique
            denominator=part.denominator_kwh.iloc[0]
            assert np.allclose(part.denominator_kwh,denominator,atol=1e-6,rtol=0)
            assert abs(part.energy_kwh.sum()-denominator)<1e-6
            assert abs(part.share.sum()-1)<2e-8
            assert np.allclose(part.share,part.energy_kwh/denominator,atol=1e-8,rtol=0)
        check('independent_contribution_totals_shares_'+name,True)
    h=read(OUT/'upstream_hour_reconciliation.csv');target=read(INPUT/'task02/hourly_panel13.csv')
    energy=p.loc[mask].sum().sum()/60000
    check('main_energy_and_8448_hour_targets',abs(energy-2739.597137333333)<1e-8 and h.main_complete_day.sum()==8448 and h.hour_complete.sum()==8503 and np.allclose(h.loc[h.hour_complete,'strict_target_kw'],target.loc[target.hour_complete,'mean_power_kw'],atol=1e-14,rtol=0))
    check('incomplete_hour_strict_target_missing',h.loc[~h.hour_complete,'strict_target_kw'].isna().all())
    peaks=read(OUT/'peak_contribution.csv');check('363_peak_hours_all13_retained',peaks[peaks.level.eq('hour_peak')].timestamp.nunique()==363 and len(peaks[peaks.level.eq('hour_peak')])==4719)
    for key,rows in peaks.groupby(['level','timestamp']):
        assert len(rows)==13 and rows.appliance_id.nunique()==13
        assert rows.panel_kw.nunique()==1 and abs(rows.value_kw.sum()-rows.panel_kw.iloc[0])<1e-8
        assert abs(rows.share.sum()-1)<1e-7
    check('same_time_peak_sum_and_share',True)
    peak_hours=peaks[peaks.level.eq('hour_peak')].drop_duplicates('timestamp')
    weights=peak_hours.groupby('date').weight.sum()
    check('tied_peak_weights_equal_one_per_352days',len(weights)==352 and np.allclose(weights,1,atol=1e-8,rtol=0))
    ab=json.loads((OUT/'AB_upstream_reaudit.json').read_text(encoding='utf-8'));c=json.loads((OUT/'C_state_rule_audit.json').read_text(encoding='utf-8'))
    check('upstream_and_rule_audits_pass',ab['all_pass'] and c['all_pass'])
    for f in c['frozen_files']: assert sha(ROOT/f['path'])==f['sha256']
    check('frozen_rules_not_changed_after_C_audit',True)
    result=subprocess.run([sys.executable,str(HERE/'tests/test_rules.py')],capture_output=True,text=True)
    check('13_boundary_tests_pass',result.returncode==0)
    result=subprocess.run([sys.executable,str(HERE/'tests/test_manifest_required.py')],capture_output=True,text=True)
    check('missing_manifest_rejected_regression',result.returncode==0)
    dm=json.loads((OUT/'derivation_manifest.json').read_text(encoding='utf-8'))
    required={'contribution_panel13.csv','contribution_panel14_supplement.csv','peak_contribution.csv',
              'operation_thresholds.csv','minute_operation_state.csv.gz','overlap_summary.csv','case_manifest.csv',
              'sample_minute_masks.csv.gz','sample_support_by_day.csv','first_three_reproduction.json',
              'repository_source_audit.json'}
    listed={entry['path'] for entry in dm['files']}
    check('all_required_deliveries_in_manifest',all('data/derived/task05/'+name in listed for name in required))
    for name in ['first_three_reproduction.json','repository_source_audit.json']:
        record=json.loads((OUT/name).read_text(encoding='utf-8'))
        check(name+'_passes',record['all_pass'])
    for entry in dm['files']: assert sha(ROOT/entry['path'])==entry['sha256'],entry['path']
    check('final_manifest_all_file_hashes',True,files=len(dm['files']))
    record=dict(generated_at=now(),version=VERSION,all_pass=True,check_count=len(checks),boundary_unit_tests=13,
        independent_method='vectorized threshold evidence lengths + most recent confirmation/reset event; no production classify import for full reconstruction',
        compared_state_cells=int(s.size),checks=checks,limitations=['Implementation correctness is not operation truth validation.','No actual task06 model audit performed.'])
    write_json(OUT/'verification_task05.json',record)
    lines=['# Task05 独立核验','',f'全部通过：{len(checks)}项汇总检查；13个状态边界单元测试。',f'独立逐点比较：{s.size:,}个状态及对应原因；全期13台×527,040分钟。','',
        '独立参考算法按连续阈值证据长度及最近确认/重置事件重建，不调用生产状态机。',
        '另对91个历史前缀检查结果不随后续数据变化。',
        '这是数据与实现核验，不是人工行为真值验证，也不表示Task06已训练或完成交叉审核。','', '| 检查 | 结果 |','|---|---|']
    lines += ['| '+x['check']+' | PASS |' for x in checks]
    (REPORT/'核验结果.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('PASS',len(checks),'aggregate checks; 13 unit tests;',s.size,'state cells and reasons independently matched')


if __name__=='__main__': main()
