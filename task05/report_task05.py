"""从正式结果生成中文实验撰写、可离线阅读的HTML和数据图。"""
import base64
import html
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap,BoundaryNorm
from common import *

LABELS=['电水壶','冰箱','电脑','电视','楼上热水器','楼下热水器','洗衣机','空调1','空调2','空调3','空调4','空调5','空调6']
NAMES=dict(zip(devices(),LABELS))
FIG=REPORT/'figures'
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','DejaVu Sans'],'axes.unicode_minus':False,
    'font.size':11,'axes.titlesize':15,'axes.labelsize':11,'savefig.dpi':160,'figure.facecolor':'white',
    'axes.spines.top':False,'axes.spines.right':False,'axes.titlepad':16})
ON='#167D9A';OFF='#DCE6EB';UNKNOWN='#777C84';ACCENT='#DD8743'


def finish(fig,name):
    fig.savefig(FIG/name,bbox_inches='tight',facecolor='white');plt.close(fig)


def plots(support,pairs,cases,frame,sensitivity):
    FIG.mkdir(parents=True,exist_ok=True)
    main=support[support.sample_scope.eq('panel13_complete_352d')].set_index('appliance_id').loc[devices()]
    fig,ax=plt.subplots(figsize=(11,6.3));y=np.arange(13);left=np.zeros(13)
    for field,label,color in [('on_minutes','on 规则活跃',ON),('off_minutes','off 规则低功率',OFF),('unknown_minutes','unknown',UNKNOWN)]:
        values=main[field].to_numpy()/506880*100;ax.barh(y,values,left=left,color=color,height=.65,label=label);left+=values
    ax.set_yticks(y,LABELS);ax.invert_yaxis();ax.set_xlim(0,100);ax.set_xlabel('占主样本全部分钟的比例（%）')
    ax.set_title('运行状态覆盖｜13台设备，352个完整日')
    ax.legend(ncol=3,loc='upper center',bbox_to_anchor=(.5,-.13),frameon=False)
    ax.text(0,-.23,'分母统一为506,880分钟；unknown含规则确认等待，不能视作off。',transform=ax.transAxes,color='#52616B',fontsize=10)
    finish(fig,'02_state_support.png')
    sub=[d for d in devices() if d!='air_conditioner_3_w'];data=np.full((12,12),np.nan)
    ranked=pairs[pairs.sample_scope.eq('panel13_complete_352d')&pairs.denominator_scope.eq('S12_common_known')]
    for r in ranked.itertuples():
        i=sub.index(r.appliance_i);j=sub.index(r.appliance_j);data[i,j]=data[j,i]=r.overlap_rate*100
    fig,ax=plt.subplots(figsize=(10.8,9));cmap=plt.get_cmap('YlGnBu').copy();cmap.set_bad('#F1F3F5')
    im=ax.imshow(data,cmap=cmap,vmin=0,vmax=25)
    ax.set_xticks(range(12),[NAMES[d] for d in sub],rotation=45,ha='right');ax.set_yticks(range(12),[NAMES[d] for d in sub])
    for i in range(12):
        for j in range(12):
            ax.text(j,i,'—' if i==j else f'{data[i,j]:.2f}',ha='center',va='center',fontsize=8,color='white' if i!=j and data[i,j]>13 else '#163240')
    ax.set_title('同分钟重叠率（%）｜固定S12，共同已知499,217分钟')
    cb=fig.colorbar(im,ax=ax,fraction=.045,pad=.04);cb.set_label('both on / S12共同已知分钟（%）')
    fig.subplots_adjust(bottom=.22)
    fig.text(.12,.015,'主范围：352完整日；S12仅排除状态不可识别的空调3；对角线不参与设备对统计。',fontsize=10,color='#52616B')
    finish(fig,'03_overlap_heatmap.png')
    cmap=ListedColormap([UNKNOWN,OFF,ON]);norm=BoundaryNorm([-1.5,-.5,.5,1.5],3)
    for case in cases.itertuples():
        x=frame[frame.case_id.eq(case.case_id)];state=np.where(x[devices()].to_numpy()=='on',1,np.where(x[devices()].to_numpy()=='off',0,-1)).astype(np.int8).T
        fig,(a,b)=plt.subplots(2,1,figsize=(12,7.7),gridspec_kw={'height_ratios':[1,2.4]},sharex=True)
        t=np.arange(1440)/60;a.plot(t,x.panel13_power_kw,color=ON,lw=1.2);a.set_ylabel('面板功率（kW）');a.set_ylim(bottom=0)
        a.grid(axis='y',alpha=.2);a.set_title(f'{case.case_id}｜{str(case.date)[:10]} {case.label}｜13台，1,440分钟')
        for peak in json.loads(case.peak_hour_starts):
            ts=pd.Timestamp(peak);hour=ts.hour+ts.minute/60;a.axvspan(hour,hour+1,color=ACCENT,alpha=.18)
        for peak in json.loads(case.minute_record_peak_times):
            ts=pd.Timestamp(peak);a.axvline(ts.hour+ts.minute/60,color=ACCENT,lw=.9,ls='--')
        b.imshow(state,aspect='auto',extent=[0,24,12.5,-.5],interpolation='nearest',cmap=cmap,norm=norm)
        b.set_yticks(range(13),LABELS);b.set_xticks(range(0,25,2));b.set_xlim(0,24);b.set_xlabel('北京时间（小时；橙色阴影为峰小时，虚线为分钟记录峰）')
        from matplotlib.patches import Patch
        b.legend(handles=[Patch(color=ON,label='on'),Patch(color=OFF,label='off'),Patch(color=UNKNOWN,label='unknown')],loc='upper right',bbox_to_anchor=(1,-.15),ncol=3,frameon=False)
        review=int(x.any_qc_review.sum());fig.text(.13,.025,f'原始有效功率保留；任一设备带QC复核标记：{review:,}/1,440分钟。复核标记不等于确认故障。',fontsize=10,color='#52616B')
        fig.tight_layout(rect=[0,.07,1,1]);finish(fig,f'04_{case.case_id}_operation.png')
    pivot=sensitivity.pivot(index='appliance_id',columns='threshold_scale',values='on_rate_given_known').loc[sub]*100
    fig,(a,b)=plt.subplots(1,2,figsize=(12,6.5),gridspec_kw={'width_ratios':[1.2,1]})
    for scale,col,mark in [(.8,'#94BDC6','o'),(1.,ON,'s'),(1.2,ACCENT,'D')]:
        a.plot(pivot[scale],np.arange(12),mark,ms=6,color=col,label=f'阈值 ×{scale:g}')
    a.set_yticks(range(12),[NAMES[d] for d in sub]);a.invert_yaxis();a.set_xlabel('on / 本设备已知分钟（%）');a.grid(axis='x',alpha=.2);a.set_title('设备规则活跃比例')
    sp=read(OUT/'threshold_sensitivity_overlap.csv')
    for i,j,label,color in [('fridge_w','upstairs_water_heater_w','冰箱—楼上热水器',ON),('fridge_w','tv_w','冰箱—电视',ACCENT),('tv_w','upstairs_water_heater_w','电视—楼上热水器','#6474A0')]:
        z=sp[sp.appliance_i.eq(i)&sp.appliance_j.eq(j)].sort_values('threshold_scale');b.plot(z.threshold_scale,z.overlap_rate*100,'o-',label=label,color=color)
    b.set_xticks([.8,1,1.2]);b.set_xlabel('on/off阈值同时缩放系数');b.set_ylabel('S12重叠率（%）');b.set_ylim(bottom=0);b.grid(axis='y',alpha=.2);b.set_title('主版本前三设备对的敏感性')
    a.legend(loc='lower right',frameon=False);b.legend(loc='lower left',frameon=False)
    fig.suptitle('阈值敏感性｜主样本352日，持续确认规则保持不变',y=1.02,fontsize=16)
    fig.text(.12,-.03,'各方案按自身已知状态计算分母（499,263 / 499,217 / 499,606分钟）；未按结果反向调整主阈值。',fontsize=10,color='#52616B')
    fig.tight_layout();finish(fig,'05_threshold_sensitivity.png')


class Document:
    def __init__(self): self.md=[];self.ht=[]
    def heading(self,title,level=2):
        self.md+=['#'*level+' '+title,''];self.ht.append(f'<h{level}>{html.escape(title)}</h{level}>')
    def p(self,text): self.md += [text,''];self.ht.append('<p>'+html.escape(text)+'</p>')
    def table(self,headers,rows):
        def clean(x): return str(x).replace('|','／').replace('\n',' ')
        self.md += ['| '+' | '.join(map(clean,headers))+' |','| '+' | '.join(['---']*len(headers))+' |']
        self.md += ['| '+' | '.join(clean(v) for v in r)+' |' for r in rows];self.md+=['']
        self.ht.append('<div class="table-wrap"><table><thead><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in r)+'</tr>' for r in rows)+'</tbody></table></div>')
    def pic(self,file,caption):
        self.md += [f'![{caption}](figures/{file})','',caption,'']
        encoded=base64.b64encode((FIG/file).read_bytes()).decode('ascii')
        self.ht.append(f'<figure><img src="data:image/png;base64,{encoded}" alt="{html.escape(caption)}"><figcaption>{html.escape(caption)}</figcaption></figure>')
    def code(self,code): self.md += ['```text',code,'```',''];self.ht.append('<pre>'+html.escape(code)+'</pre>')
    def save(self):
        (REPORT/'task05_后三步实验报告.md').write_text('\n'.join(self.md),encoding='utf-8')
        style='body{margin:0;background:#f1f4f6;color:#1c303a;font:16px/1.85 "Microsoft YaHei",sans-serif}main{max-width:1120px;margin:30px auto;background:white;padding:52px 64px}h1{font-size:32px;line-height:1.4;border-bottom:3px solid #167d9a;padding-bottom:22px}h2{margin-top:52px;font-size:24px;color:#13677f}h3{margin-top:30px;font-size:19px}p{margin:16px 0}table{border-collapse:collapse;font-size:14px;line-height:1.65;width:100%}th{background:#edf4f7;text-align:left;white-space:nowrap}td,th{padding:10px 12px;border-bottom:1px solid #dce6eb;vertical-align:top}.table-wrap{overflow-x:auto;margin:24px 0}figure{margin:32px 0}img{max-width:100%;height:auto}figcaption{color:#536671;font-size:13px}pre{padding:20px;background:#f0f4f6;overflow:auto;font-size:14px;white-space:pre-wrap}@media(max-width:800px){main{padding:24px;margin:0}h1{font-size:25px}}@media print{body{background:white}main{padding:0;margin:0}figure,table{break-inside:avoid}h2,h3{break-after:avoid}}'
        (REPORT/'task05_后三步实验报告.html').write_text('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Task05 后三步实验报告</title><style>'+style+'</style></head><body><main>'+''.join(self.ht)+'</main></body></html>',encoding='utf-8')


def pct(x): return '不可定义' if pd.isna(x) else f'{x*100:.2f}%'
def num(x): return f'{int(x):,}'


def main():
    REPORT.mkdir(parents=True,exist_ok=True)
    support=read(OUT/'operation_support.csv');pairs=read(OUT/'overlap_summary.csv');cases=read(OUT/'case_manifest.csv')
    caseframe=read(OUT/'case_operation_state.csv.gz');sens=read(OUT/'threshold_sensitivity_support.csv')
    thresholds=read(OUT/'operation_thresholds.csv');groups=read(OUT/'overlap_group_summary.csv')
    main_support=support[support.sample_scope.eq('panel13_complete_352d')]
    top=pairs[pairs.sample_scope.eq('panel13_complete_352d')&pairs.denominator_scope.eq('S12_common_known')].sort_values('overlap_rate',ascending=False)
    ab=json.loads((OUT/'AB_upstream_reaudit.json').read_text(encoding='utf-8'))
    plots(support,pairs,cases,caseframe,sens)
    d=Document();d.heading('Task05 第4—6步：电器运行判据、分钟状态与运行重叠',1)
    d.p('实验版本：task05_v1.0.1_20261117。分析对象：固定监测面板panel13（排除电饭煲），不等同于独立家庭总表。时间区间为北京时间[2021-05-31 00:00, 2022-06-01 00:00)。')
    d.p('2026-11-17仓库修订：全部共同有效分钟涉及日期分别为panel13的356日、panel14的153日；352/148为其中完整日数。正式表增加逐日支持与精确分钟掩码，原能量及峰值数值不变。')
    d.heading('一、实验目标与分工衔接')
    d.p('本实验承接同伴task05前三步的输入锁定、同集合能量贡献、全部并列峰小时和四个固定案例，完成逐设备运行阈值、连续分钟状态及重叠统计。前三步来源快照与案例清单按字节保留，正式贡献表保留数值并修正日期元数据；本次新增审核、状态和重叠不改写原结果，也不重新挑选案例。')
    d.p('主结论：352个完整日中，固定可判定子集S12的共同已知分母为499,217分钟。其中187,147分钟至少两台设备处于规则on状态，占37.49%。主版本重叠率最高的设备对为冰箱与楼上热水器：121,359 / 499,217 = 24.31%。这些是特定电功率判据下的描述结果，不能当作有人工真值验证的压缩机状态、完整使用周期或住户行为记录。')
    d.p('重要限制：冰箱主阈值附近存在较多功率记录。将on/off阈值同时提高20%后，其规则on比例从88.88%降至51.04%，冰箱—楼上热水器重叠率从24.31%降至15.18%。因此，涉及冰箱的绝对运行时长和重叠强度应结合敏感性结果阅读，不宜作精确物理解释。')
    d.heading('二、数据、样本与上游复核')
    d.table(['用途','设备与范围','分钟/小时支持','说明'],[
        ['主贡献与主重叠','panel13，352完整日','506,880分钟；8,448小时','固定日期与task02 day_complete逐项一致'],
        ['贡献补充','panel13全期共同有效','510,284分钟','独立贡献分母；约2,758.881648 kWh'],
        ['重叠补充','panel13，完整日历轴','527,040分钟；8,784小时','保留缺口；各设备状态unknown另报'],
        ['14台独立贡献补充','panel14含电饭煲','217,643共同有效分钟；148完整日','原样继承，不进入本次运行子集'],
        ['阈值制定','训练日历段[2021-05-31,2022-03-09)','406,080日历分钟','仅以训练段分布与持续段证据手工制定规则']])
    d.p('源数据为cn_obee_v1_noimpute_v1.0.0；功率单位W，分钟积分为ΣP/60000 kWh。本次不新增功率插补，不把缺测补0，不把发布记录等同于未处理的原始传感器事件。13份逐设备质量表的usable_value与宽表数值、缺测位置逐点一致；bit16/32仅保留复核，不自动删值。')
    d.p(f'独立对账确认：352日同集合分项电量与面板电量一致，约{ab["energy_kwh"]["panel13_complete_352d"]:.9f} kWh；8,448个主小时与8,503个全部严格有效小时均按相同时间键核对。继承的hourly_panel13.csv有{ab["partial_hour_mean_nonnull"]}个不完整小时仍填有mean_power_kw，较新参考表将其留空。原文件保持不变，正式对账字段strict_target_kw强制按hour_complete置空，部分小时诊断均值不充当完整小时目标。')
    d.p('全部363个并列峰小时区间、原四案例和分钟记录峰继续保留。A/B记录为本次对上游的实现自查；未获取Task06模型实际运行产物，因此不声称完成了Task06负责人之间的交叉审核。')
    d.heading('三、步骤四：逐设备运行判据')
    d.p('先检查训练期有效功率分位数、常见平台、长常值标记和不同候选阈值下的连续高功率段，再冻结规则。阈值是可审查的电功率层次划分，没有人工开关标签，未估计准确率或宣称最优。on阈值高于off阈值，两者之间保留最近已确认状态；不同设备采用不同确认长度。')
    rows=[]
    for t in thresholds.itertuples():
        rows.append([NAMES[t.appliance_id],'—' if pd.isna(t.on_threshold_w) else f'{t.on_threshold_w:g}',
            '—' if pd.isna(t.off_threshold_w) else f'{t.off_threshold_w:g}',f'{t.min_on_minutes} / {t.min_off_minutes}',t.state_meaning])
    d.table(['设备','on阈值W（≥）','off阈值W（≤）','on/off连续确认分钟','on的含义'],rows)
    d.p('电水壶和加热设备保留1分钟可观测高功率脉冲；空调1/2的训练段也有较多1分钟高功率段，on采用1分钟确认。冰箱、电视、电脑和空调4/5/6采用2分钟确认。min_on/min_off在本实现中表示连续阈值证据长度，不保证输出状态段至少持续同样长度。')
    d.table(['设备','训练期制定依据'],[[NAMES[t.appliance_id],t.evidence] for t in thresholds.itertuples()])
    d.pic('01_training_distributions.png','图1 训练期13台设备功率分布。横轴采用对数化功率刻度；阈值证据另见训练分位数、平台与持续段CSV。')
    d.heading('四、步骤五：分钟状态与unknown')
    d.p('状态表保留连续527,040行，每台设备每分钟为on、off或unknown，并保留对应原因。起始状态为unknown；源缺测或无效值立即输出unknown并清空状态与确认计数。恢复观测后重新初始化，落在迟滞区间内仍为unknown，直至出现足够阈值证据。源功率完整不保证运行状态已知，因为规则还可能等待确认或本身不可识别。')
    d.code('若源记录无效：unknown，重置稳定状态和候选计数\n若设备不可识别：unknown\n未初始化：连续达到on阈值确认on，连续低于off阈值确认off；区间内unknown\n已确认off：达到on阈值开始on确认；其余有效记录保留off\n已确认on：低于off阈值开始off确认；其余有效记录保留on\n确认等待分钟：unknown；确认完成只赋当前分钟；历史分钟从不回填')
    d.p('状态判定仅使用截至当前分钟的证据；2分钟规则在首次阈值证据后需额外等待1分钟。候选中途取消时，过去等待分钟仍为unknown。该因果定义避免回填，但不代表数据已满足在线预测发布延迟要求；本次未将状态送入Task06，未来作为特征还须独立审核available_at。')
    d.table(['原因码','含义'],[['0','状态已知'],['1','源缺测或无效'],['2','运行状态不可识别'],['3','重置/起始后位于迟滞带，未能初始化'],['4','等待on连续证据确认'],['5','等待off连续证据确认']])
    d.table(['设备','已知分钟','on分钟','unknown分钟','unknown/全部','on/已知','on中QC16/32分钟'],[
        [NAMES[r.appliance_id],num(r.known_minutes),num(r.on_minutes),num(r.unknown_minutes),pct(r.unknown_fraction),pct(r.on_rate_given_known),f'{r.on_qc16_review_minutes:,} / {r.on_qc32_review_minutes:,}'] for r in main_support.itertuples()])
    d.p('上表全部行的观测分母均为506,880分钟。空调3全部unknown，不能将其0个on分钟解释为未使用；其有效电量继续留在panel13。电脑和楼下热水器的on段各含1,440个长常值复核分钟，按要求保留；这会限制对活跃持续时长和个别案例的物理解释。')
    d.pic('02_state_support.png','图2 主样本状态覆盖。off为规则低功率状态，不表示拔电、停用或无人。')
    d.p('另外保存全日历范围与逐月支持表，以及18,484个最大连续已确认on段。段边界可能由unknown打断；它们不是完整洗衣周期、一次入住或一次设备使用事件，不能直接将段数当作真实开机次数。')
    d.heading('五、步骤六：运行重叠与统一分母')
    d.code('设备对已知分母 N_known = 同一分钟i与j均非unknown的分钟数\n共同on分钟 N_both = 已知集合内i与j都on的分钟数\n重叠率 overlap_rate = N_both / N_known\n条件比例 P(j on | i on) = N_both / N_i_on_known\nJaccard = N_both / N_union_on\n任一指标自己的分母为0时留空；unknown不按off处理')
    d.p('overlap_summary.csv同时保留逐设备对分母pairwise_known，以及固定S12共同已知分母S12_common_known。前者方便查看每一对的可用支持，后者用于同范围横向排名。S12预先固定为panel13排除空调3后的12台，不能按结果高低再选择设备。')
    d.table(['统计范围','比较集合','观测分钟','共同已知分钟','unknown比例','至少2台on分钟','至少2台on比例'],[
        ['352完整日' if r.sample_scope=='panel13_complete_352d' else '全日历366日',r.device_set,num(r.observed_minutes),num(r.known_minutes),pct(r.unknown_fraction),num(r.at_least_two_on_minutes),pct(r.at_least_two_on_rate)] for r in groups.itertuples()])
    d.p('全13台共同已知分钟数为0，因此全13台的重叠比例不可定义，不能填0或声称没有共同运行。主S12范围的共同未知比例为1.51%，这部分来自判据确认等待等状态不确定性，已经从分母中排除。全日历补充S12分母为502,578分钟，其不同于能量补充的510,284个共同有效功率分钟。')
    d.table(['主排名','设备对','共同已知分钟','共同on分钟','重叠率','P(j on | i on)','Jaccard'],[
        [i+1,NAMES[r.appliance_i]+'—'+NAMES[r.appliance_j],num(r.known_minutes),num(r.both_on_minutes),pct(r.overlap_rate),pct(r.p_j_on_given_i_on),pct(r.jaccard)] for i,r in enumerate(top.head(10).itertuples())])
    d.p('排名以both_on/共同已知为准；表中条件比例与Jaccard只作不同含义的补充。冰箱有较高基础on比例，因此与其他设备重叠较多并不自动表示协同行为或因果关系。图3所有设备对使用相同499,217分钟，未把不同分母的设备对直接混排。')
    d.pic('03_overlap_heatmap.png','图3 S12同分钟重叠率热图；固定共同已知分母，单位%。完整66个设备对与逐对支持见正式CSV。')
    d.heading('六、固定案例的状态与峰值解释')
    d.p('C01、C02、C03是原任务四同月案例，C04为全期最大小时峰日。各案例仅展示原日期的1,440分钟，不替代全期统计。自然周末与法定休息日沿用任务三不同字段，未合并为一个“工作日”标签。橙色峰小时与分钟峰位置来自原案例清单，不由状态重新选择。')
    peaks=read(OUT/'peak_contribution.csv')
    for c in cases.itertuples():
        x=caseframe[caseframe.case_id.eq(c.case_id)];st=x[devices()].to_numpy();known=(st[:,[j for j,dv in enumerate(devices()) if dv!='air_conditioner_3_w']]!='unknown').all(axis=1)
        n_on=(st=='on').sum(axis=1);mp=peaks[peaks.level.eq('minute_peak')&peaks.case_id.eq(c.case_id)].sort_values('share',ascending=False).iloc[0]
        d.heading(f'{c.case_id}｜{str(c.date)[:10]} {c.label}',3)
        d.p(f'原日能量{c.energy_kwh:.3f} kWh；最大小时均值{c.peak_kw:.3f} kW；分钟记录峰{c.minute_record_peak_w/1000:.3f} kW。分钟峰同一分钟的最大功率贡献来自{NAMES[mp.appliance_id]}（{pct(mp.share)}）。S12共同已知{known.sum():,}分钟，其中至少两台规则on为{((n_on>=2)&known).sum():,}分钟（{pct(((n_on>=2)&known).sum()/known.sum())}）。')
        d.pic(f'04_{c.case_id}_operation.png',f'图4-{c.case_id} 原始面板曲线与13台分钟状态；峰时与复核标记保留。')
    d.p('小时峰与分钟峰常处于不同时间，能量贡献与规则on也不是同一量。2分钟确认设备在高功率首次出现时可暂为unknown，不能为使峰图“对齐”而回填。C04的23:00峰小时代表[23:00,次日00:00)，没有把起点标签错作区间结束。')
    d.heading('七、阈值敏感性与解释边界')
    d.p('规则冻结时预先规定on/off阈值同时乘0.8、1.0、1.2，持续确认长度不变。仅作描述性敏感性检查，没有根据全年结果挑选阈值。各方案仍在同一352日范围内，但确认等待会让S12共同已知分钟数分别为499,263、499,217、499,606；下表按各自已知分母计算，不把它们称为逐分钟完全相同的集合。')
    wide=sens.pivot(index='appliance_id',columns='threshold_scale',values='on_rate_given_known')
    d.table(['设备','阈值×0.8：on/已知','主阈值：on/已知','阈值×1.2：on/已知'],[[NAMES[dev]]+[pct(wide.loc[dev,k]) for k in [.8,1,1.2]] for dev in devices()])
    sp=read(OUT/'threshold_sensitivity_overlap.csv');rows=[]
    for r in top.head(3).itertuples():
        z=sp[sp.appliance_i.eq(r.appliance_i)&sp.appliance_j.eq(r.appliance_j)].set_index('threshold_scale')
        rows.append([NAMES[r.appliance_i]+'—'+NAMES[r.appliance_j]]+[pct(z.loc[k,'overlap_rate']) for k in [.8,1,1.2]])
    d.table(['主版本前三设备对','阈值×0.8重叠率','主阈值重叠率','阈值×1.2重叠率'],rows)
    d.pic('05_threshold_sensitivity.png','图5 阈值敏感性。冰箱变化明显；其余设备对是否稳定应查询全量敏感性CSV，不从前三名推广到全部设备。')
    d.p('三种方案的前三设备对顺序相同，但冰箱—楼上热水器重叠率提高阈值后下降约9.13个百分点，不能以排名未变声称绝对重叠强度稳健。阈值敏感性不等同于准确率验证；仍需要独立的设备运行标签来验证物理状态。')
    d.heading('八、验收、复现与交付')
    d.p('生产状态机之外，独立核验程序采用连续阈值证据长度与最近确认/重置事件重建全期状态，逐点比较6,851,520个状态及其原因；另检查91个历史前缀的一致性和13个边界单元测试。核验还覆盖所有288行重叠、零分母留空、QC保留、案例同时性、连续on段、敏感性以及前三步正式文件哈希。最终通过项数和详情以verification_task05.json及核验结果.md为准。')
    d.p('C节点先于全期状态生成，冻结阈值、四类合成短样例和边界测试。A/B及C均为自动实现自查，未冒充外部人工审核。无功率新增插补、无缺口压缩、无跨缺口延续；正式贡献表原数值与原案例文件保持一致。')
    d.code('在仓库根目录运行（环境见requirements.txt）：\npython task05/verify_task05.py\n\n完整复算六步：\npython task05/run_all.py\n\n后三步分步重算：\npython task05/inspect_training.py\npython task05/freeze_rules.py\npython task05/audit_rules.py\npython task05/run_task05.py\npython task05/report_task05.py\npython task05/make_manifest.py\npython task05/verify_task05.py')
    d.p('完整包内置所需冻结输入；首次复跑不需要访问原E盘来源目录或联网。CSV为UTF-8（普通CSV带BOM，gzip CSV为UTF-8）；比率储存为0—1数值，零分母为空。请将reports内实验报告用于正文撰写，按DATA_DICTIONARY.md解释字段；inputs/first_three保留原贡献程序、说明与证据，来源归属清楚。')
    d.p('本次整合并核对Task05六步，修正样本元数据；详见验收修订说明。未实施Task06训练或把状态加入预测，也不将本次2021年案例替换Task06的2022年固定测试期。')
    d.save();print('PASS Chinese report, offline HTML and 8 figures')


if __name__=='__main__': main()
