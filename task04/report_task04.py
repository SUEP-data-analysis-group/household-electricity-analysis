"""Offline Chinese figures, report and task04 handoff documentation."""
import base64
import html
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd

LABELS={'electric_kettle_w':'电水壶','fridge_w':'冰箱','computer_w':'电脑','tv_w':'电视',
        'upstairs_water_heater_w':'楼上热水器','downstairs_water_heater_w':'楼下热水器',
        'washing_machine_w':'洗衣机',**{f'air_conditioner_{i}_w':f'空调{i}' for i in range(1,7)}}
NAVY='#17324D';TEAL='#087F8C';ORANGE='#D97722';RED='#BB3E48';GRAY='#687C8C'

def table(frame):
    f=frame.copy()
    for c in f:
        f[c]=f[c].map(lambda x: f'{x:.4f}' if isinstance(x,(float,np.floating)) else str(x))
    return '| '+' | '.join(map(str,f.columns))+' |\n| '+' | '.join(['---']*len(f.columns))+' |\n'+'\n'.join('| '+' | '.join(str(x).replace('|','/') for x in row)+' |' for row in f.itertuples(index=False,name=None))

def setup():
    for name in ['Microsoft YaHei','Noto Sans CJK SC','SimHei']:
        if any(f.name==name for f in font_manager.fontManager.ttflist):
            plt.rcParams['font.sans-serif']=[name,'DejaVu Sans'];break
    plt.rcParams.update({'axes.unicode_minus':False,'font.size':10,'axes.titlesize':13,
        'axes.labelcolor':NAVY,'text.color':NAVY,'xtick.color':GRAY,'ytick.color':GRAY,
        'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#B7C5CE',
        'grid.color':'#DAE3E9','grid.alpha':.65,'figure.facecolor':'white','axes.facecolor':'white',
        'savefig.facecolor':'white','lines.linewidth':1.2})

def render(here,output,tables,thresholds,devices,inputs):
    setup();reports=here/'reports';figures=reports/'figures';figures.mkdir(parents=True,exist_ok=True)
    metrics=tables['daily_peak_valley.csv'];extrema=tables['daily_extrema_times.csv'];freq=tables['peak_hour_frequency.csv']
    changes=tables['hourly_changes.csv'];cases=tables['case_manifest.csv'];minute=tables['daily_minute_hourly_comparison.csv']
    excluded=tables['excluded_days.csv'];case_minutes=tables['case_minute_curves.csv.gz'];case_hours=tables['case_hourly_curves.csv']
    images=[]
    def save(fig,name,caption):
        fig.savefig(figures/name,dpi=160,bbox_inches='tight');plt.close(fig)
        images.append((name,caption))

    calendar=pd.date_range('2021-05-31','2022-05-31',tz='Asia/Shanghai')
    daily=metrics.set_index('date').reindex(calendar)
    fig,axes=plt.subplots(3,1,figsize=(12,8),sharex=True,layout='constrained')
    axes[0].plot(calendar,daily.peak_kw,color=ORANGE,label='小时峰值')
    axes[0].plot(calendar,daily.valley_kw,color=TEAL,label='小时谷值');axes[0].set_ylabel('kW');axes[0].legend(ncol=2,frameon=False)
    axes[1].plot(calendar,daily.peak_valley_kw,color=NAVY);axes[1].set_ylabel('峰谷差 / kW')
    axes[2].plot(calendar,daily.load_factor,color=TEAL);axes[2].set_ylabel('负荷率');axes[2].set_ylim(0,1)
    for ax in axes:
        ax.grid(axis='y');
        for date in excluded.date:ax.axvspan(date,date+pd.Timedelta(days=1),color=RED,alpha=.1,lw=0)
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=2));axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    fig.suptitle('352 个完整日的小时峰谷与负荷率\n14 个不完整日保留缺口，红色阴影标示排除日期',fontsize=16)
    save(fig,'01_daily_peak_valley.png','小时均值尺度的日指标；曲线不跨缺测日期连线，负荷率无单位。')

    fig,axes=plt.subplots(2,1,figsize=(12,6),sharex=True,layout='constrained')
    for ax,kind,color,title in [(axes[0],'peak',ORANGE,'峰时'),(axes[1],'valley',TEAL,'谷时')]:
        f=freq.loc[freq.kind.eq(kind)]
        ax.bar(f.hour,f.proportion*100,color=color,width=.75)
        ax.set_ylabel('完整日权重 / %');ax.set_title(title+'频率：每日期总权重为 1');ax.grid(axis='y')
    axes[-1].set_xticks(range(24));axes[-1].set_xlabel('北京时间小时区间起点')
    fig.suptitle('并列极值分配等权，保留全部时刻',fontsize=16)
    save(fig,'02_extrema_hour_frequency.png','峰/谷分别覆盖 352 日；并列 k 个小时每个分配 1/k，比例分母是完整日数。')

    valid=changes.loc[changes.valid_change]
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),layout='constrained')
    axes[0].hist(valid.delta_kw,bins=65,color=TEAL,alpha=.85,log=True)
    t=thresholds['train_abs_hour_change_q95_kw']
    for sign in [-1,1]:axes[0].axvline(sign*t,color=ORANGE,ls='--',lw=1.4)
    axes[0].set_xlabel('本小时均值 − 前一小时均值 / kW');axes[0].set_ylabel('相邻小时对数（对数轴）')
    axes[0].set_title(f'训练期 |变化| q95 = {t:.4f} kW')
    for mask,label,color in [(~valid.is_cross_midnight,'同日内',TEAL),(valid.is_cross_midnight,'跨午夜',ORANGE)]:
        g=valid.loc[mask].groupby(valid.loc[mask,'timestamp'].dt.hour).abs_delta_kw.mean().reindex(range(24))
        axes[1].plot(range(24),g,marker='o',ms=3,color=color,label=label)
    axes[1].set_xlabel('后一小时的北京时间起点');axes[1].set_ylabel('平均绝对变化 / kW')
    axes[1].set_xticks(range(0,24,2));axes[1].legend(frameon=False);axes[1].set_title('跨午夜单独标示，不当作同日内变化')
    for ax in axes:ax.grid(axis='y')
    save(fig,'03_hourly_changes.png','变化只使用严格有效且相隔 1h 的两个小时；阈值只以冻结训练段拟合，不是设备启动阈值。')

    fig,ax=plt.subplots(figsize=(7.8,6),layout='constrained')
    points=ax.scatter(minute.hour_peak_kw,minute.minute_record_peak_kw,c=pd.to_datetime(minute.date).dt.month,
                      cmap='viridis',s=24,alpha=.7,edgecolors='none')
    limit=float(max(minute.hour_peak_kw.max(),minute.minute_record_peak_kw.max()))*1.04
    ax.plot([0,limit],[0,limit],color=GRAY,ls='--',label='两个尺度数值相同')
    ax.set(xlim=(0,limit),ylim=(0,limit),xlabel='日最大小时平均负荷 / kW',ylabel='日最大分钟记录值 / kW',
           title='分钟记录峰值与小时均值峰值分别报告')
    ax.legend(frameon=False);ax.grid();fig.colorbar(points,ax=ax,label='月份')
    save(fig,'04_minute_hour_peak_comparison.png','同一日、同一 panel13；分钟记录值来自上游已规则化数据，不称为真实瞬时峰值。')

    colors=plt.colormaps['tab20'](np.linspace(0,.95,len(devices)))
    for case in cases.itertuples():
        cm=case_minutes.loc[case_minutes.case_id.eq(case.case_id)]
        ch=case_hours.loc[case_hours.case_id.eq(case.case_id)]
        date=case.date;end=date+pd.Timedelta(days=1)
        fig,axes=plt.subplots(2,1,figsize=(12,7.5),sharex=True,gridspec_kw={'height_ratios':[1,1.35]})
        axes[0].plot(cm.timestamp,cm.panel_power_w/1000,color=TEAL,lw=.8,label='分钟记录负荷')
        axes[0].stairs(ch.mean_power_kw,np.append(ch.timestamp.to_numpy(),end),color=ORANGE,lw=1.7,label='严格小时平均负荷')
        peak=cm.panel_power_w.eq(case.minute_record_peak_w)
        axes[0].scatter(cm.loc[peak,'timestamp'],cm.loc[peak,'panel_power_w']/1000,s=14,color=RED,zorder=4,label='全部并列分钟峰')
        for start in json.loads(case.peak_hour_starts):
            start=pd.Timestamp(start);axes[0].axvspan(start,start+pd.Timedelta(hours=1),color=ORANGE,alpha=.12)
        axes[0].set_ylabel('panel13 / kW');axes[0].legend(ncol=3,frameon=False,fontsize=9)
        axes[1].stackplot(cm.timestamp,*[cm[d].to_numpy()/1000 for d in devices],colors=colors,labels=[LABELS[d] for d in devices],linewidth=0)
        axes[1].set_ylabel('13 台同时刻记录 / kW');axes[1].legend(loc='upper center',bbox_to_anchor=(.5,-.14),ncol=7,frameon=False,fontsize=8.5)
        ticks=[date+pd.Timedelta(hours=i) for i in range(0,25,4)]
        axes[1].set_xticks(ticks,labels=['00:00','04:00','08:00','12:00','16:00','20:00','24:00'])
        axes[1].set_xlim(date,end);axes[1].set_xlabel('北京时间；阴影表示全部并列小时峰区间')
        for ax in axes:ax.grid(axis='y')
        fig.suptitle(f'{case.case_id}  {case.label}｜{date:%Y-%m-%d}\n小时峰 {case.peak_kw:.3f} kW；分钟记录峰 {case.minute_record_peak_w/1000:.3f} kW；日电量 {case.energy_kwh:.3f} kWh',fontsize=14,y=.98)
        fig.text(.08,.02,f'固定 13 台，不含电饭煲；QC 复核标记涉及 {case.review_flag_minutes}/1440 分钟，原值和标记均保留；未平滑、削峰或新增插补。',fontsize=9,color=GRAY)
        fig.subplots_adjust(top=.86,bottom=.20,hspace=.22)
        save(fig,f'05_{case.case_id}_minute_case.png',f'{case.case_id} {case.label}，{date:%Y-%m-%d}；上图区分分钟记录与小时均值，下图是同一时刻 13 台设备曲线，不是设备独立峰值之和。')

    peakrow=metrics.loc[metrics.peak_kw.idxmax()];minuterow=minute.loc[minute.minute_record_peak_w.idxmax()]
    modal={kind:freq.loc[freq.kind.eq(kind)&freq.weighted_days.eq(freq.loc[freq.kind.eq(kind),'weighted_days'].max()),'hour'].astype(int).tolist() for kind in ['peak','valley']}
    stats=dict(complete_days=len(metrics),excluded_days=len(excluded),strict_hours=int(changes.current_hour_complete.sum()),
        valid_change_pairs=int(changes.valid_change.sum()),intra_day_pairs=int((changes.valid_change&changes.is_intra_day).sum()),
        cross_midnight_pairs=int((changes.valid_change&changes.is_cross_midnight).sum()),
        large_change_pairs=int(changes.is_large_change.sum()),peak_tied_days=int(metrics.peak_tied_count.gt(1).sum()),
        valley_tied_days=int(metrics.valley_tied_count.gt(1).sum()),modal_peak_hours=modal['peak'],modal_valley_hours=modal['valley'],
        max_hourly_peak_kw=float(peakrow.peak_kw),max_hourly_peak_date=peakrow.date.strftime('%Y-%m-%d'),
        max_minute_record_peak_w=float(minuterow.minute_record_peak_w),max_minute_record_peak_date=minuterow.date.strftime('%Y-%m-%d'),
        median_daily_peak_kw=float(metrics.peak_kw.median()),median_load_factor=float(metrics.load_factor.median()),
        median_minute_to_hour_peak_ratio=float(minute.minute_to_hour_peak_ratio.median()),case_count=len(cases),figures=len(images))
    caseview=cases[['case_id','label','date','energy_kwh','peak_kw','minute_record_peak_w','load_factor','review_flag_minutes']].copy()
    caseview['date']=caseview.date.dt.strftime('%Y-%m-%d')
    caseview.columns=['案例','类型','日期','日电量 kWh','小时峰 kW','分钟记录峰 W','负荷率','QC标记分钟']
    overview=pd.DataFrame([
        ['完整日 / 排除日',f'{len(metrics)} / {len(excluded)}'],['严格小时',str(stats['strict_hours'])],
        ['有效相邻变化对',str(stats['valid_change_pairs'])],['同日内 / 跨午夜',f'{stats["intra_day_pairs"]} / {stats["cross_midnight_pairs"]}'],
        ['峰值 / 谷值并列日期',f'{stats["peak_tied_days"]} / {stats["valley_tied_days"]}'],
        ['最大小时均值峰',f'{stats["max_hourly_peak_kw"]:.6f} kW，{stats["max_hourly_peak_date"]}'],
        ['最大分钟记录峰',f'{stats["max_minute_record_peak_w"]:.2f} W，{stats["max_minute_record_peak_date"]}'],
        ['完整日日峰中位数',f'{stats["median_daily_peak_kw"]:.6f} kW'],['完整日负荷率中位数',f'{stats["median_load_factor"]:.6f}'],
        ['分钟峰 / 小时峰中位比',f'{stats["median_minute_to_hour_peak_ratio"]:.4f}'],
        ['峰时 / 谷时最高频小时',f'{modal["peak"]} / {modal["valley"]}']],columns=['指标','结果'])
    extremes=pd.concat([valid.nlargest(5,'delta_kw'),valid.nsmallest(5,'delta_kw')])[['previous_timestamp','timestamp','delta_kw','is_cross_midnight']].copy()
    extremes.columns=['前一小时起点','当前小时起点','变化 kW','跨午夜']
    exclusion=excluded[['date','valid_hours','exclusion_reason']].copy();exclusion.date=exclusion.date.dt.strftime('%Y-%m-%d')
    code=inputs['repository_commit']
    opening=f'''# 任务四：峰谷与日内变化分析报告

派生版本 `task04_v1.0.0_20261114`，完成日期 2026-11-14。来源为仓库提交 `{code}`；输入与 GitHub 文件逐字节核对，固定 `panel13/v1.0.0`、标准版本 `cn_obee_v1_noimpute_v1.0.0`、北京时间。

## 结论与范围

主日分析使用 352 个完整日，14 个不完整日只保留质量记录。小时峰指 60 个联合有效分钟的平均负荷，分钟峰指规则化发布数据的最大分钟记录；这两者不能混作同一个量。监测范围为固定 13 台电器，不能称作独立整户总表。

{table(overview)}

小时均值会弱化短时峰值，需同时查看分钟记录。上述峰谷时刻是样本内频率描述，不能直接解释住户作息、设备启动或证明某设备造成高峰；具体贡献和运行重叠由任务五在相同时间集合继续核实。

这里的“最高频峰/谷时刻”统计逐日极值出现的位置，与任务二“先求全样本平均曲线、再找曲线峰谷”属于不同指标。{stats['cross_midnight_pairs']} 对跨午夜变化以两个小时均有效为准，可涉及不完整日中的有效小时，分母不是完整日数减一。

## 计算口径

- 区间 `[2021-05-31 00:00,2022-06-01 00:00)`；末端单条不进入分析。日均值、峰、谷、峰谷差和负荷率仅在 24/24 严格小时的日期计算。
- 负荷率 = 日均负荷 / 日峰负荷；峰为 0 时不可定义，留空。CSV 保留 float64 精度；报告表格只为显示而舍入。
- 并列以 round-trip 读回的 float64 完全相等判定，每日每种极值的全部时刻各分配 `1/tied_count`。频率分母是完整日数。
- 变化在连续小时索引上计算，只有两个小时均严格有效且确实相隔 1h 才相减。可包含不完整日中本身有效的小时；跨午夜单列，缺口两侧不比较。
- “大变化”定义为 `abs_delta_kw > {thresholds['train_abs_hour_change_q95_kw']:.12g} kW`；阈值是训练期 `[{thresholds['training_interval'][0]}, {thresholds['training_interval'][1]})` 内 {thresholds['train_change_pairs']} 个有效变化对的 q95（linear）。主模型用途不能改用全期 q95。
- 另存训练期 {thresholds['train_strict_hours']} 个严格小时的负荷 q90 = {thresholds['train_hourly_load_q90_kw']:.12g} kW，供任务六评估高负荷小时候选规则使用；不代表已完成预测或评分。
- 不插补、不平滑、不缩尾。源设备 QC 位原样附带，近量程与长常值复核标记不作为自动删值依据；常值标记使用回顾信息，不能当作预测时已知特征。

## 先声明的案例规则与选中结果

配置在计算前写入。比较月份取最早的完整自然月，要求月内每一天完整且至少 5 个自然工作日、4 个自然周末；本次为 {cases.iloc[0].comparison_month}。普通工作日与周末分别取最接近组内日电量中位数者，距离并列选最早日期。同月高电量日取达到该月 q95 的最小日电量，电量并列选最早日；另加全期最大小时峰日期，并列同样选最早日。

这是回顾性案例规则，不是预测抽样规则；实际工作/休息标签从任务三附带，但普通案例按自然星期选取。所有案例固定 13 台、1440 联合有效分钟，与任务五共享完全相同的 `case_manifest.csv`、全部峰小时区间及分钟峰时间集合。

前三例同月用于曲线展示，C04 是另行挑选的全期极值例；这些案例间差异不能替代任务三的月份分层总体比较或置信区间。

{table(caseview)}

每例保留设备功率与 `*_qc_bits`，并另存每设备复核数量。出现标记不等于已经证实仪表故障；本任务展示并保留，未替换为普通曲线。空调3的记录量级与其他空调不同，不据此推断是否损坏或有人使用。

## 相邻小时的大幅升降

以下为有效相邻对中数值最大的 5 次上升和 5 次下降；仍只是 1h 均值变化，不等于分钟内启动速率。

{table(extremes)}

## 排除的 14 个日期

不完整日无法确定全日峰谷。这里不报告其“忽略缺测后的日最大/最小”作为主指标。

{table(exclusion)}

## 图表

'''
    markdown=opening+'\n\n'.join(f'### 图{i}：{caption}\n\n![图{i}](figures/{name})' for i,(name,caption) in enumerate(images,1))
    markdown+='''

## 后续使用与限制

任务五应直接使用案例清单、设备分钟曲线和 QC，按同一峰小时/同一分钟计算贡献；不要把每台设备各自最大值相加，也不要重选案例。14 台补充面板属于另一个样本集合，不能并入本表。

任务六可参考 thresholds.json 中的训练期阈值；本任务日指标、案例选择、事后质量和 QC 均非未来已知变量。使用历史日指标作特征时仍需严格滞后、遵守任务一的发布时间和冻结切分。尚未构造特征、训练模型或得出预测成绩。

这是单户、固定监测设备和不完整年度支持上的描述分析；缺测集中在 2021-06/07，完整日统计不代表已经补齐全期。不能仅凭曲线或同日相关性下因果结论。
'''
    (reports/'task04_report.md').write_text(markdown,encoding='utf-8')
    # The HTML is self-contained; all figures and the compact result tables are embedded.
    body=[]
    for line in opening.split('\n'):
        if line.startswith('### '):body.append('<h3>'+html.escape(line[4:])+'</h3>')
        elif line.startswith('## '):body.append('<h2>'+html.escape(line[3:])+'</h2>')
        elif line.startswith('# '):body.append('<h1>'+html.escape(line[2:])+'</h1>')
        elif line.startswith('|'):continue
        elif line:body.append('<p>'+html.escape(line)+'</p>')
    # Put each real table at its associated section, not at the end of the page.
    text='\n'.join(body)
    for heading,frame in [('结论与范围',overview),('先声明的案例规则与选中结果',caseview),('相邻小时的大幅升降',extremes),('排除的 14 个日期',exclusion)]:
        text=text.replace('<h2>'+heading+'</h2>','<h2>'+heading+'</h2>'+frame.to_html(index=False,border=0,float_format=lambda x:f'{x:.4f}'))
    for i,(name,caption) in enumerate(images,1):
        b64=base64.b64encode((figures/name).read_bytes()).decode('ascii')
        text+=f'<figure><h3>图{i}：{html.escape(caption)}</h3><img alt="{html.escape(caption)}" src="data:image/png;base64,{b64}"></figure>'
    text+='<h2>交接与限制</h2><p>任务五共用 case_manifest.csv 的全部峰小时及分钟峰；任务六仅参考训练期阈值并遵守起点可获知性。无新增插补、设备因果判断或预测成绩。完整字段、复现命令和限制见同目录 README 及 Markdown 报告。</p>'
    css='body{font-family:"Microsoft YaHei",sans-serif;color:#17324d;max-width:1140px;margin:38px auto;padding:0 24px;line-height:1.8}h1{font-size:30px;border-bottom:4px solid #087f8c}h2{margin-top:36px}p{overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;font-size:13px;margin:20px 0}th{background:#17324d;color:white}td,th{padding:9px;border-bottom:1px solid #dce6ec;text-align:left}tr:nth-child(even){background:#f2f7f9}figure{margin:38px 0}img{max-width:100%;height:auto}h3{font-size:17px}'
    (reports/'task04_report.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>任务四峰谷分析</title><style>'+css+'</style><body>'+text+'</body></html>',encoding='utf-8')
    write_readme(here,tables,stats,thresholds,inputs,images)
    return stats

def write_readme(here,tables,stats,thresholds,inputs,images):
    descriptions={
        'daily_peak_valley.csv':'完整日日峰、谷、差、均值、负荷率及并列数量',
        'daily_extrema_times.csv':'全部并列峰谷小时及等权重',
        'peak_hour_frequency.csv':'24 小时 × 峰/谷；按完整日归一的加权频率',
        'hourly_changes.csv':'连续小时网格，含无效行原因、同日/跨午夜、严格相邻变化',
        'case_manifest.csv':'任务五共用的四个案例、设备范围、全部峰时、选择依据及质量',
        'excluded_days.csv':'14 个不完整日及无法确定全日峰谷的原因',
        'daily_minute_hourly_comparison.csv':'完整日分钟记录峰与小时均值峰对照，保留全部分钟并列峰',
        'hourly_change_summary.csv':'全体/同日内/跨午夜的相邻变化支持与描述统计',
        'case_hourly_curves.csv':'案例的全部严格小时输入',
        'case_minute_curves.csv.gz':'每例 1440 分钟的 13 台设备、面板值、源行号及逐设备 QC 位',
        'case_quality_summary.csv':'每例每台设备的有效/复核/插补数量'
    }
    files='\n'.join(f'| [{name}](data/derived/task04/{name}) | {len(frame)} | {descriptions[name]} |' for name,frame in tables.items())
    readme=f'''# 任务四：峰值、低谷与日内变化

**已完成，2026-11-14。** 当前派生版 `task04_v1.0.0_20261114`。本目录是独立本地交付，含所需输入、程序、正式数据、8 张图和可离线阅读的报告。

先打开 **[完整 HTML 报告](reports/task04_report.html)**；也可看 [Markdown 报告](reports/task04_report.md)、[核验日志](reports/verify_task04.txt)和 [字段说明](DATA_DICTIONARY.md)。

## 完成了什么

- 352 个完整日的日峰、谷、峰谷差、均值和负荷率；14 个不完整日只保留质量清单，不冒充已知全日极值。
- 全部并列小时保留，按 `1/tied_count` 分配权重；峰/谷各自的日期权重总和为 352。
- 连续保留 8784 小时、8503 个严格有效小时；有效相邻变化 {stats['valid_change_pairs']} 对，其中同日内 {stats['intra_day_pairs']} 对、跨午夜 {stats['cross_midnight_pairs']} 对。缺口两侧不相减。
- 每个完整日另算分钟记录峰，与小时均值峰分开；全期最大小时峰 {stats['max_hourly_peak_kw']:.6f} kW，最大分钟记录峰 {stats['max_minute_record_peak_w']:.2f} W。
- 按预先写入配置的规则固定 4 个案例；每例附 13 台设备的全部 1440 分钟及 QC，不平滑、不削峰、不新增插补。

## 任务一完成后的实际承接

依据 [仓库](https://github.com/SUEP-data-analysis-group/household-electricity-analysis)提交 `{inputs['repository_commit']}` 的项目说明和任务四要求。28 份输入/要求原件已与 GitHub blob ID 核对，并记录 SHA-256，见 [输入清单](sources/input_manifest.json)。

- task01：`cn_obee_v1_noimpute_v1.0.0`、固定 `panel13/v1.0.0`、标准分钟功率和面板、13 台设备 QC、冻结切分及严格聚合核验表。
- task02：`task02_v1.1.0_20261113` 的严格小时/日表及派生清单；主字段 `mean_power_kw`，不完整小时为空。
- task03：`task03_v1.1.0_20261113` 的日期标签及派生清单。案例普通工作日/周末按自然星期选，实际法定日类型同时附带。

原任务说明留在 [sources/requirements/](sources/requirements/)；其中“尚未生成”是收到的历史任务要求，当前完成状态以本 README 和实际数据为准。原件和上游清单没有被改写。上游清单提到的其他结果不属于本任务必需输入，未重复打包。

## 目录为什么有这些文件

```text
README.md、DATA_DICTIONARY.md、config.json、requirements.txt
run_task04.py / report_task04.py / verify_task04.py  生成、报告、独立核验
inputs/                  从仓库逐字节复制的 24 个必需数据/规则文件
sources/                 原要求、数据约定与来源哈希
data/derived/task04/      当前正式结果，后续任务从这里读取
reports/                 报告、8 张图、实际核验记录
tests/                   并列、零峰、缺口及训练阈值的边界检查
```

输入约 90 MB，主要是全年标准分钟数据与 13 台 QC；保留它们是为了本目录能独立复跑。没有另放一套旧版结果或额外重复 ZIP。

## 复现与核验

推荐使用本次实际环境：Python 3.13.5，依赖版本见 requirements.txt。在本目录运行：

```powershell
cd 'D:\\Desktop\\task04'
python -m pip install -r requirements.txt
python run_task04.py
python verify_task04.py
python -m unittest discover -s tests -v
```

本机已有相同依赖的 Python 为 `D:\\anaconda\\python.exe`，可将上述 `python` 换为 `& 'D:\\anaconda\\python.exe'`。生成程序只写本目录结果/报告，不联网，也不修改 inputs。核验程序只写核验日志。

若并入仓库，代码/配置/说明/报告放入 `task04/`，正式结果放入根目录 `data/derived/task04/`，然后在仓库根目录运行：

```powershell
python task04/run_task04.py --source-root . --output-root .
python task04/verify_task04.py --source-root . --output-root .
```

同时保留本任务 `sources/` 中的原要求和哈希。`--source-root` 指向同字节的标准输入，`--output-root` 控制正式数据位置；报告仍在脚本旁 reports/。清单使用相对路径，移动文件夹无需恢复某个旧盘符。

## 正式数据入口

### 本任务应交付

| 文件 | 行数 | 内容 |
| --- | --- | --- |
{files}

另附 [thresholds.json](data/derived/task04/thresholds.json) 和 [derivation_manifest.json](data/derived/task04/derivation_manifest.json)，记录版本、规则、输入/输出哈希、环境、实际数量和阈值。

## 口径、阈值和案例规则

时间为 Asia/Shanghai，分析 `[2021-05-31 00:00,2022-06-01 00:00)`，小时标签为左闭右开区间起点。功率 W/kW 分列，电量 kWh；float64 round-trip 读取，不先舍入再取极值。

负荷率是 `mean_kw/peak_kw`，零峰时为空；并列峰谷每小时分配 `1/tied_count`。分钟峰是上游规则化数据的“分钟记录峰值”，不声称真实瞬时峰值。14 个缺测日不在日极值主表中。

“大变化”用训练期有效相邻对 |变化| 的 q95：**{thresholds['train_abs_hour_change_q95_kw']:.12g} kW**，条件为严格大于；训练区间 `[2021-05-31,2022-03-09)`，两端都在训练段。另存训练期严格小时 q90 **{thresholds['train_hourly_load_q90_kw']:.12g} kW** 供任务六评估参考。全期分位数另标探索描述，不能拿来替换训练拟合参数。

案例规则先写在 config.json：最早完整自然月内，普通工作日/周末各取接近组内日电量中位数的日期；高电量日取同月达到 q95 的最小电量日期；另保留全期最大小时峰日期。所有并列候选取最早日期。案例选择是回顾性描述，不作为预测参数。

## 任务五、六如何接着做

| 下游 | 读取 | 接着做 |
| --- | --- | --- |
| task05 | case_manifest.csv、case_minute_curves.csv.gz、case_hourly_curves.csv、case_quality_summary.csv | 原样共用案例、13 台设备、完整时间窗和全部峰时；在同一小时/同一分钟计算贡献，继续制定逐设备运行阈值和重叠统计 |
| task06 | thresholds.json；task02 连续严格小时表及 task01 冻结切分 | 训练阈值可作为预先声明的评估规则；仍需特征可获知性检查、训练/验证/测试及共同掩码，不能使用当日峰谷、事后 QC 或案例选择作为已知未来特征 |

task05 不要相加各设备各自最大值；如有并列小时峰，保留所有区间或事先声明等权汇总。电饭煲/14 台补充须使用独立共同有效样本，不能塞进此 13 台主表。任务六还没有由本任务完成预测或得到成绩。

## 版本与限制

仓库原 task04 仅有任务要求，本版是 2026-11-14 首次实现，不沿用 task02/03 的旧版本号。源数据、上游派生版本与本任务派生版本分别记录。

本任务只描述这一户固定监测设备的观测结果，不等于独立整户总表；缺测集中在 2021-06/07，不能解释为已补齐全年。长常值和近量程 QC 只复核、不删值；空调3的小量级记录不能直接证明故障或未使用。曲线与电量关联不能单独支持设备或住户行为的因果判断。
'''
    (here/'README.md').write_text(readme,encoding='utf-8')
    dictionary='''# task04 字段与读取约定

数值 CSV 为 UTF-8 BOM，空值为空单元格；gzip 可由 pandas 直接读取。读取数值使用 float_precision='round_trip'，时间显式转 Asia/Shanghai。布尔为 True/False。除报告显示外不主动舍入；不完整/不可定义值不能填 0。

## 日指标和极值

- `date`：北京时间自然日零点；`panel_id/panel_version/data_version`：固定范围与标准版本；`natural_day_type/actual_day_type/year_month`：任务三标签。
- `energy_kwh`：task02 严格完整日电量；`peak_kw/valley_kw`：该日 24 个严格小时均值最大/最小；`peak_valley_kw`：二者之差；`mean_kw`：24 小时均值；`load_factor`：mean_kw/peak_kw，零峰为空。
- `peak_tied_count/valley_tied_count`：相同 float64 读数的并列小时数；`hour_count=24/day_complete=True`：主日样本支持。
- 极值长表 `kind`=peak/valley；`hour_start`：完整小时时间戳；`hour`：本地小时；`value_kw`：极值；`tied_count`：该日该类并列数；`weight=1/tied_count`。
- 时刻频率 `weighted_days`：该小时的日期权重之和；`proportion=weighted_days/n_days`；`days_with_extreme_at_hour` 是未分权的涉及日数，不能与权重合计混用。

## 连续小时变化

- `timestamp/previous_timestamp`：当前/上一行小时起点；`current_mean_power_kw/previous_mean_power_kw` 为对应严格负荷；`current_hour_complete/previous_hour_complete` 为质量。
- `elapsed_hours`：两时间点实际相差小时数；首行为空。`valid_change` 要求有前一行、相差恰为 1h、双方完整。
- `exclusion_reason`：no_previous_hour、non_adjacent_timestamp、both_hours_incomplete、current_hour_incomplete 或 previous_hour_incomplete；有效行为空。
- `is_cross_midnight/is_intra_day` 仅描述日界关系，不替代 valid_change；首行均 False。`delta_kw`=当前减前一小时，`abs_delta_kw` 为绝对值，二者在无效行都为空。
- `is_large_change`：只在有效行定义，绝对变化严格大于训练 q95；无效行为空。单位是 kW 的 1h 均值差，不是分钟变化率。
- 变化汇总 `n_pairs` 是该 scope 的有效分母；p95_abs_delta_kw 属全期该 scope 的描述分位数，不是训练参数。

## 分钟与案例

- `minute_record_peak_w/kw`：完整日标准面板的分钟记录最大值，W 与 kW 分列；`hour_peak_kw` 是同日日最大小时均值；`minute_to_hour_peak_ratio` 分母转为同单位，零小时峰为空。
- `minute_peak_times/minute_record_peak_times/peak_hour_starts/valley_hour_starts`：JSON 字符串，保留全部并列时间，均含 +08:00；`minute_peak_tied_count` 为分钟并列数。
- `case_id`：稳定案例编号 C01–C04；`case_type/label`：自然工作日、自然周末、同月高电量、全期最大小时峰；`selection_metric/selection_target/selection_distance/candidate_days/comparison_month`：可复现选择依据。
- `device_ids`：JSON 固定 13 台列表；`window_start/window_end_exclusive`：同一 24h 左闭右开；`complete_minutes=1440/n_devices=13`；`review_flag_minutes` 为任一设备有 bit16/32 标记的分钟数，不是丢弃数。
- 分钟曲线的 `*_w` 是同一分钟设备功率 W；`panel_power_w` 是固定 13 台同时求和；`source_row_id/source_present` 保留 power_minute 的来源行信息；逐设备 `*_w_qc_bits` 原样来自 task01 QC。
- QC 位 1=源缺失、2=时间缺行、4=非数值/非有限、8=物理错误、16=近量程复核、32=长常值复核；可叠加。`combined_qc_bits` 是 13 台按位或；`any_review_flag` 仅表示出现 16/32；`new_imputed_devices=0`。完整案例仍可有复核标记，不据此删值。
- `case_quality_summary` 每例每设备一行。`usable_minutes/unusable_minutes` 是功率可用支持；`source_or_physical_invalid_minutes` 数 bit1/2/4/8；两个 review 字段数 bit16/32；`new_imputed_minutes` 数新增插补；`qc_unique_bits` 保留出现的位值。

## 清单和阈值

thresholds.json 的训练区间沿用 task01；变化阈值两端都在训练段，分位数算法 linear。全期探索阈值明确单列，不供预测参数拟合。derivation_manifest.json 的输入有 GitHub 提交及 SHA-256；输出 `scope=output_root` 相对 --output-root，`scope=task_directory` 相对脚本目录。原输入文件中的历史绝对路径只作历史来源，不用于本任务定位文件。
'''
    (here/'DATA_DICTIONARY.md').write_text(dictionary,encoding='utf-8')
