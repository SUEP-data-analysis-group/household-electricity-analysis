"""生成六步成果无循环的输入/代码/规则/输出清单，最后运行独立核验。"""
import platform
import numpy as np
import pandas as pd
import matplotlib
from common import *


def main():
    files=[]
    for base in [HERE,OUT]:
        for p in sorted(base.rglob('*')):
            if not p.is_file() or '__pycache__' in p.parts or p.suffix=='.pyc': continue
            # 原输入的同名manifest属于来源，必须纳入；仅排除本次顶层自指项。
            if p==OUT/'derivation_manifest.json' or p==OUT/'verification_task05.json' or p==REPORT/'核验结果.md': continue
            rel=p.relative_to(ROOT).as_posix()
            role='input' if INPUT in p.parents else 'code' if p.suffix=='.py' else 'report' if REPORT in p.parents else 'rules' if p.name in ['config.json','operation_thresholds.csv'] else 'documentation' if p.suffix=='.md' else 'output'
            files.append(dict(path=rel,role=role,bytes=p.stat().st_size,sha256=sha(p)))
    support=read(OUT/'operation_support.csv');group=read(OUT/'overlap_group_summary.csv')
    main=group[group.sample_scope.eq('panel13_complete_352d')&group.device_set.eq('S12_common_known')].iloc[0]
    upstream=json.loads((OUT/'AB_upstream_reaudit.json').read_text(encoding='utf-8'))
    original=json.loads((INPUT/'import_manifest.json').read_text(encoding='utf-8'))
    result=dict(task='task05_steps_1_2_3_4_5_6',version=VERSION,generated_at=now(),
        source_version='cn_obee_v1_noimpute_v1.0.0',panel_version='panel13/v1.0.0',
        completed_steps=['1 input/sample audit','2 same-sample contributions','3 same-time peak contributions',
                         '4 per-device operation rules','5 continuous minute states','6 overlap/report/verification'],
        inherited_steps='1-3 numeric values retained; sample metadata corrected; original bytes in inputs/first_three',
        timezone=TZ,interval=dict(start=START.isoformat(),end_exclusive=END.isoformat()),
        samples=dict(calendar_minutes=527040,calendar_hours=8784,calendar_days=366,main_complete_days=352,
            panel13_common_valid_dates=356,panel13_partial_dates=4,panel14_common_valid_dates=153,panel14_partial_dates=5,
            main_minutes=506880,panel13_common_valid_power_minutes=510284,panel14_common_valid_power_minutes=217643,
            panel14_complete_days=148,main_S12_known_minutes=int(main.known_minutes),main_at_least_two_on_minutes=int(main.at_least_two_on_minutes),
            main_energy_kwh=upstream['energy_kwh']['panel13_complete_352d'],all13_common_known_minutes=0,
            fixed_peak_hours=363,fixed_case_ids=['C01','C02','C03','C04']),
        operation_subset=json.loads((HERE/'config.json').read_text(encoding='utf-8'))['comparable_operation_subset'],
        rules=dict(threshold_period_start=START.isoformat(),threshold_period_end_exclusive=TRAIN_END.isoformat(),
            causal_current_minute=True,backfill=False,new_power_imputation=False,invalid_state='unknown',gap_reset=True,
            review_bits_retained=[16,32],zero_denominator='missing',state_truth='no manually labelled device operation truth'),
        incomplete_hour_note=dict(inherited_nonnull_partial_means=upstream['partial_hour_mean_nonnull'],target_requires_hour_complete=True),
        environment=dict(python=platform.python_version(),numpy=np.__version__,pandas=pd.__version__,matplotlib=matplotlib.__version__),
        source_import_manifest='task05/inputs/import_manifest.json',source_file_records=len(original['files']),
        validation=dict(independent_script='task05/verify_task05.py',result='data/derived/task05/verification_task05.json',
            self_hash_excluded=True,final_verification_files_excluded_to_prevent_cycle=True,no_task06_actual_model_audit_claim=True),
        files=files)
    write_json(OUT/'derivation_manifest.json',result)
    print('PASS manifest',len(files),'files; regenerate verification next')


if __name__=='__main__': main()
