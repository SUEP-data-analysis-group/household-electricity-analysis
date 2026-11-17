"""完成训练证据审查后冻结每设备阈值和共同可判定子集；不读取验证/测试功率。"""
import json
import numpy as np
import pandas as pd
from common import *

def main():
    evidence=read(OUT/'training_distribution.csv').set_index('appliance_id')
    runs=read(OUT/'training_candidate_run_lengths.csv')
    # 每一行均由训练期的待机平台、活跃平台和持续段证据制定；不是物理状态真值。
    specs=[
        ('electric_kettle_w',200,50,1,1,'高功率加热代理','待机主要小于1W；>=200W训练段1143个，其中70个为1分钟，保留短脉冲。'),
        ('fridge_w',50,20,2,2,'较高功率运行代理','训练p25约52W，低平台集中5至20W；50/20W区分功率层次，不能验证压缩机状态或排除除霜。'),
        ('computer_w',10,2,2,2,'较高电活跃代理','训练90%为0W，5.29W有长常值；>=10W为较高活动层，不把待机或电脑实际使用视作已验证。'),
        ('tv_w',50,5,2,2,'较高电活跃代理','待机主要0.5至1W，活跃主要100至205W；训练>=50W段无1分钟段。'),
        ('upstairs_water_heater_w',25,5,1,1,'非待机加热功率代理','训练有276560分钟为0W，其余最小正平台约25W；20W候选段793个仅1分钟，保留短脉冲。'),
        ('downstairs_water_heater_w',100,20,1,1,'高于待机的加热代理','待机1W占主导；>=100W段166个，其中6个1分钟；长常值只标复核，不删除。'),
        ('washing_machine_w',5,1,1,1,'分钟电活跃代理','待机约0.75W，>=5W训练2436分钟；只定义分钟活跃，不定义完整洗涤周期。'),
        ('air_conditioner_1_w',150,20,1,2,'高功率运行代理','训练大部分0至2.4W；>=150W段557个，其中230个1分钟，保留高功率短段。'),
        ('air_conditioner_2_w',150,20,1,2,'高功率运行代理','训练p99约22W，较低平台含风机候选；>=150W段644个，其中235个1分钟，保留。'),
        ('air_conditioner_3_w',np.nan,np.nan,1,1,'无法识别运行状态','训练最大0.71W，缺乏可辨识高功率平台；所有分钟运行状态unknown，功率仍计入panel13能量。'),
        ('air_conditioner_4_w',200,10,2,2,'高功率运行代理','训练约1至2W待机与500至848W高平台分离；>=200W段29个，仅2个1分钟，用2分钟确认。'),
        ('air_conditioner_5_w',300,20,2,2,'高功率运行代理','训练待机主要0至1.2W，50至200W另有低平台；>=300W段285个，其中4个1分钟，用2分钟确认。'),
        ('air_conditioner_6_w',200,10,2,2,'高功率运行代理','训练待机约1至2W，高平台主要500至1034W；>=200W段28个，无1分钟段，用2分钟确认。')]
    records=[]
    for dev,on,off,m_on,m_off,meaning,reason in specs:
        e=evidence.loc[dev]
        records.append(dict(appliance_id=dev,on_threshold_w=on,off_threshold_w=off,min_on_minutes=m_on,min_off_minutes=m_off,
            state_meaning=meaning,off_meaning='规则低功率状态，不代表拔电或无人',evidence=reason,
            evidence_file='training_distribution.csv;training_modes.csv;training_candidate_run_lengths.csv',
            fitted_period='[2021-05-31T00:00:00+08:00,2022-03-09T00:00:00+08:00)',
            fitted_start=START.isoformat(),fitted_end_exclusive=TRAIN_END.isoformat(),
            training_usable_minutes=int(e.n_usable),training_max_w=e['q1'],training_median_w=e['q0.5'],
            detection_status='unidentifiable' if dev=='air_conditioner_3_w' else 'rule_proxy_only',
            threshold_selection='manual_training_distribution_and_run_review',threshold_version=VERSION,
            confirmation='consecutive_threshold_minutes; candidate minutes unknown; no_backfill',
            future_minutes_required=False,maximum_confirmation_delay_minutes=max(m_on,m_off)-1))
    thresholds=pd.DataFrame(records)
    assert thresholds.appliance_id.tolist()==devices()
    save(thresholds,'operation_thresholds.csv')
    config=dict(task='task05_steps_4_5_6',version=VERSION,timezone=TZ,analysis_start=START.isoformat(),analysis_end_exclusive=END.isoformat(),
        threshold_fitted_start=START.isoformat(),threshold_fitted_end_exclusive=TRAIN_END.isoformat(),
        fixed_energy_panel=devices(),comparable_operation_subset=[d for d in devices() if d!='air_conditioner_3_w'],
        subset_exclusion={'air_conditioner_3_w':'No identifiable operation platform; remains in energy panel'},
        primary_overlap_scope='panel13_complete_352d',primary_comparison_denominator='S12_common_known',
        supplementary_overlap_scope='all_calendar_527040',
        state_encoding={'on':1,'off':0,'unknown':-1},reason_codes={str(k):v for k,v in __import__('operation_rules').REASONS.items()},
        initial_state='unknown; band remains unknown until confirmed threshold crossing',
        missing_rule='unknown and reset stable/candidate/count; restart after each gap',
        confirmation_rule='consecutive threshold evidence; candidate minutes unknown; no retroactive backfill',
        minimum_duration_interpretation='confirmation duration, not guaranteed output on/off run duration',
        prediction_use='Not used by task06 baseline; state only confirmed at current minute and aggregate later. Any use needs separate availability audit.',
        qc_review_bits=[16,32],qc_review_action='retain values; carry review counts, do not automatically delete',
        threshold_sensitivity_scales=[.8,1.0,1.2],absolute_energy_tolerance_kwh=1e-6,
        note='No manually labelled operation truth. High/low electrical proxy only; not occupancy or entire device cycle.')
    write_json(HERE/'config.json',config)
    print('PASS frozen 13 per-device rules and S12 subset before full-period state generation')

if __name__=='__main__': main()
