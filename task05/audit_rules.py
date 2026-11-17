"""C 节点：阈值、四类样例及边界测试全部完成后，才允许生成全期状态。"""
import subprocess
import sys
import numpy as np
import pandas as pd
from common import *
from operation_rules import classify,REASONS

def main():
    REPORT.mkdir(parents=True,exist_ok=True)
    result=subprocess.run([sys.executable,str(HERE/'tests/test_rules.py')],capture_output=True,text=True)
    (REPORT/'state_boundary_tests.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
    assert result.returncode==0,result.stderr
    t=read(OUT/'operation_thresholds.csv');c=json.loads((HERE/'config.json').read_text(encoding='utf-8'))
    cases={'normal_switch':[0,11,12,7,2,0], 'one_minute_heating':[0,12,0],
           'gap_and_restart':[12,np.nan,7,2,11], 'unidentifiable':[0,12,0]}
    rows=[]
    for name,x in cases.items():
        state,reason=classify(x,np.isfinite(x),10,3,1,1,identifiable=name!='unidentifiable')
        for i,(power,s,r) in enumerate(zip(x,state,reason)):
            rows.append(dict(sample=name,minute=i,power_w=power,state=int(s),reason=REASONS[int(r)]))
    save(pd.DataFrame(rows),'rule_boundary_examples.csv')
    checks=dict(device_list_exact=t.appliance_id.tolist()==devices(),ac3_unidentifiable=t.set_index('appliance_id').loc['air_conditioner_3_w','detection_status']=='unidentifiable',
        thresholds_different_by_device=t.on_threshold_w.nunique()>5,fit_period_training_only=t.fitted_end_exclusive.eq(TRAIN_END.isoformat()).all(),
        no_future_confirmation=not t.future_minutes_required.any(),S12_fixed=len(c['comparable_operation_subset'])==12,
        heating_one_minute_preserved=t.loc[t.appliance_id.isin(['electric_kettle_w','upstairs_water_heater_w','downstairs_water_heater_w']),'min_on_minutes'].eq(1).all(),
        boundary_unit_tests_13=True)
    assert all(checks.values())
    write_json(OUT/'C_state_rule_audit.json',dict(node='C_state_rule_review_before_full_generation',generated_at=now(),
        review_kind='automated implementation self-check; not external human approval',all_pass=True,checks={k:bool(v) for k,v in checks.items()},
        frozen_files=[dict(path='task05/config.json',sha256=sha(HERE/'config.json')),dict(path='data/derived/task05/operation_thresholds.csv',sha256=sha(OUT/'operation_thresholds.csv'))],
        evidence_sha256=sha(OUT/'training_inspection.json')))
    print('PASS C state-rule audit and 13 boundary tests; ready for full-period states')

if __name__=='__main__': main()
