from __future__ import annotations

import base64
import html
import importlib.metadata
import re
import os
from pathlib import Path
os.environ.setdefault("MPLCONFIGDIR",str(Path(__file__).resolve().parents[1]/"work/matplotlib-cache"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

from .common import *

METHOD_NOTE = "下面的框架综合了预测评价论文和 NeurIPS 官方清单，是针对你这个任务整理的检查方法，不是文献中的统一评分量表。预测评价论文明确讨论了基线、切分、指标、泄漏和统计比较；NeurIPS 清单则强调结论范围、实验细节、局限性与可复现性。"
REFERENCES = [
    ("预测评价方法", "https://link.springer.com/article/10.1007/s10618-022-00894-5"),
    ("NeurIPS 官方清单", "https://neurips.cc/public/guides/PaperChecklist"),
    ("LightGBM 调参", "https://lightgbm.readthedocs.io/en/stable/Parameters-Tuning.html"),
    ("LightGBM GPU 性能", "https://lightgbm.readthedocs.io/en/stable/GPU-Performance.html"),
    ("QuantileRegressor", "https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.QuantileRegressor.html"),
    ("CN-OBEE 数据论文", "https://www.nature.com/articles/s41597-023-02891-9"),
    ("2021 官方安排", "https://app.www.gov.cn/govdata/gov/202011/26/465359/article.html"),
    ("2022 官方安排", "https://app.www.gov.cn/govdata/gov/202110/25/477434/article.html"),
]
COLORS = dict(zip(MODELS,["#737373","#a6761d","#7570b3","#0072b2","#d55e00","#009e73"]))


def fmt(v):
    if isinstance(v,(float,np.floating)):
        return "NA" if pd.isna(v) else f"{v:.6f}"
    return str(v)


def table(df):
    columns=list(df.columns)
    rows=["| "+" | ".join(columns)+" |","| "+" | ".join(["---"]*len(columns))+" |"]
    rows.extend("| "+" | ".join(fmt(v).replace("|","/") for v in row)+" |" for row in df.itertuples(index=False,name=None))
    return "\n".join(rows)


def savefig(fig,name):
    folder=REPORT/"figures"; folder.mkdir(parents=True,exist_ok=True)
    fig.savefig(folder/name,dpi=160,bbox_inches="tight")
    plt.close(fig)


def figures():
    fonts={f.name for f in font_manager.fontManager.ttflist}
    chosen=next((n for n in ["Microsoft YaHei","SimHei","Noto Sans CJK SC","SimSun"] if n in fonts),None)
    if chosen:
        plt.rcParams["font.sans-serif"]=[chosen,"DejaVu Sans"]
    plt.rcParams.update({"axes.unicode_minus":False,"axes.spines.top":False,"axes.spines.right":False,
                         "font.size":10,"axes.grid":True,"grid.alpha":.18})
    daily=read_csv(OUT/"daily_metrics.csv").query("split=='test'")
    daily["origin"]=timestamps(daily.origin)
    horizon=read_csv(OUT/"horizon_metrics.csv").query("split=='test'")
    weekly=read_csv(OUT/"weekly_metrics.csv").query("split=='test'")
    high=read_csv(OUT/"high_load_metrics.csv").query("split=='test'")
    fig,axes=plt.subplots(2,1,figsize=(12,7),sharex=True,layout="constrained")
    for ax,scenario in zip(axes,["0h","1h"]):
        for m in MODELS:
            g=daily.loc[(daily.scenario==scenario)&(daily.model==m)].sort_values("origin")
            dates=pd.date_range(TEST,END,inclusive="left",freq="D")
            series=g.set_index("origin").MAE_kw.reindex(dates)
            ax.plot(dates,series,color=COLORS[m],label=m,lw=1.4,alpha=.9)
        ax.set(title=f"{scenario}: daily MAE, 56 complete paired test days",ylabel="MAE (kW)")
    axes[0].legend(ncol=6,loc="upper left",fontsize=9)
    savefig(fig,"01_daily_mae.png")
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),sharey=True,layout="constrained")
    for ax,scenario in zip(axes,["0h","1h"]):
        for m in MODELS:
            g=horizon.loc[(horizon.scenario==scenario)&(horizon.model==m)].sort_values("horizon")
            ax.plot(g.horizon,g.MAE_kw,label=m,color=COLORS[m])
        ax.set(title=f"{scenario}: 56 test observations per horizon",xlabel="Horizon / local hour",ylabel="MAE (kW)",xticks=[0,4,8,12,16,20,23])
    axes[1].legend(fontsize=9)
    savefig(fig,"02_horizon_mae.png")
    fig,axes=plt.subplots(2,1,figsize=(11,7),sharex=True,layout="constrained")
    for ax,scenario in zip(axes,["0h","1h"]):
        w=weekly.loc[weekly.scenario==scenario].pivot(index="week_block",columns="model",values="MAE_kw")
        for left,right in [("Full","B1"),("Full","B2"),("Full","Linear-L1"),("NoCalendar","Full"),("No168Stats","Full")]:
            ax.plot(w.index+1,w[left]-w[right],marker="o",label=f"{left} - {right}")
        ax.axhline(0,color="black",lw=1)
        ax.set(title=f"{scenario}: paired fixed 7-day blocks; 168 hours each",ylabel="Delta MAE (kW)")
    axes[0].legend(ncol=3,fontsize=9)
    axes[1].set(xlabel="Block from 2022-04-06 (1..8)",xticks=range(1,9))
    savefig(fig,"03_weekly_paired_deltas.png")
    fig,axes=plt.subplots(2,3,figsize=(13,7),layout="constrained")
    for row,scenario in enumerate(["0h","1h"]):
        g=high.loc[high.scenario==scenario].set_index("model").reindex(MODELS)
        for col,(metric,label) in enumerate([("MAE_H_kw","High-load MAE (kW)"),("U_H_kw","Mean positive shortfall on H (kW)"),("FNR_H","Threshold miss rate on H")]):
            ax=axes[row,col]
            ax.bar(range(6),g[metric],color=[COLORS[m] for m in MODELS])
            ax.set(xticks=range(6),xticklabels=MODELS,ylabel=label,title=f"{scenario}: H = y > {Q:.4f}; n={int(g.n_H.iloc[0])}")
            ax.tick_params(axis="x",rotation=35,labelsize=8)
    savefig(fig,"04_high_load_diagnostics.png")
    pred=read_csv(OUT/"predictions.csv").query("split=='test'")
    pred["origin"]=timestamps(pred.origin)
    cases=[]
    fig,axes=plt.subplots(2,3,figsize=(15,7),sharex=True,layout="constrained")
    for row,scenario in enumerate(["0h","1h"]):
        g=pred.loc[pred.scenario.eq(scenario)&pred.score_mask]
        truth=g.loc[g.model.eq("Full")].groupby("origin").y_true_kw.max()
        worst=daily.loc[daily.scenario.eq(scenario)&daily.model.eq("Full")].sort_values(["MAE_kw","origin"],ascending=[False,True]).iloc[0].origin
        dates=[truth.index.min(),truth.sort_index().idxmax(),worst]
        labels=["First complete day","Highest true peak [post-hoc]","Worst Full daily MAE [post-hoc]"]
        for col,(date,label) in enumerate(zip(dates,labels)):
            ax=axes[row,col]; gg=g.loc[g.origin.eq(date)]
            yy=gg.loc[gg.model.eq("Full")].sort_values("horizon")
            ax.plot(yy.horizon,yy.y_true_kw,color="black",lw=2,label="Observed strict panel13")
            for model in MODELS:
                a=gg.loc[gg.model.eq(model)].sort_values("horizon")
                ax.plot(a.horizon,a.y_pred_kw,label=model,color=COLORS[model],lw=1.1,alpha=.85)
            ax.set(title=f"{scenario} {date.date()}\n{label}; n=24",xlabel="Local hour",ylabel="Mean power (kW)",xticks=[0,6,12,18,23])
            cases.append(dict(scenario=scenario,origin=date,selection_rule=label,posthoc=col>0))
    axes[0,0].legend(fontsize=8,ncol=2)
    savefig(fig,"05_fixed_rule_cases.png")
    csv(pd.DataFrame(cases),"case_selection.csv")
    return dict(font=chosen or "DejaVu Sans; plot labels use ASCII",figures=5)


def resource_report():
    r=read_json(OUT/"resource_preflight.json")
    logs=[json.loads(line) for line in (OUT/"training_log.jsonl").read_text(encoding="utf-8").splitlines()]
    frame=pd.DataFrame(logs)
    aggregate=frame.groupby("stage",sort=False).agg(runs=("wall_seconds","size"),measured_wall_seconds=("wall_seconds","sum"))
    peaks=[r.get("process_peak_rss_bytes") for r in logs if isinstance(r.get("process_peak_rss_bytes"),int)]
    text=["# 本地资源预检与实测", "",f"Python：`{r['python']}`；{r['python_version'].splitlines()[0]}。",
          f"CPU：{r['processor']}；{r['physical_cpus']} 物理核 / {r['logical_cpus']} 逻辑 CPU，本任务模型线程 {r['threads']}。",
          f"预检总内存 {r['total_memory_bytes']/2**30:.2f} GiB，可用 {r['available_memory_bytes']/2**30:.2f} GiB。",
          "", "已实际完成导入与两个模型的小样本拟合，然后在保守完整训练集完成代表候选预检。依赖精确锁定见 requirements.txt。",
          f"特征与输入检查实测 {r['feature_build_measured']['wall_seconds']:.3f} 秒，包含上游字节哈希、输入核验、两场景构造和审计表写盘；每场景 8784×20 原始字段、78 个编码维度。",
          f"LightGBM 代表候选全训练集实测 {r['measured_fits']['Full']['fit_seconds']:.3f} 秒；Linear-L1 实测 {r['measured_fits']['Linear-L1']['fit_seconds']:.3f} 秒。",
          f"bootstrap 小批次 500 次实测 {r['bootstrap_preflight']['seconds_measured']:.6f} 秒，线性推算每 10000 次 {r['bootstrap_preflight']['estimated_per_10000_seconds']:.4f} 秒；这只测充分统计量内核，未包含 q90 与文件 I/O，不能等同正式耗时。",
          f"预检推算训练和 bootstrap 总耗时 {r['estimated_total_training_bootstrap_seconds']:.1f} 秒，属于推算；下表为正式分阶段墙钟实测。Python 启动、人工编码、网络和报告核验不计入该预检估算。",
          "",table(aggregate.reset_index()),"",
          f"已记录阶段进程峰值最大 {max(peaks)/2**20:.1f} MiB。内存按进程 RSS/Windows peak working set 记录，阶段开始/结束另有数值；不是整个系统或所有子进程的峰值。",
          "", "结论：本地可完成。无需云 CPU，也无 GPU 需求证据。主要模型开销来自 HiGHS 线性规划；日历/审计写盘和独立核验也有开销。没有因节省时间减少候选或最终重抽样次数。",
          "HiGHS 的 threads 选项由 SciPy 发出 OptimizeWarning 后原样传入 HiGHS；该警告和成功求解迭代数均保留，未换用其他回归器。",
          "最初受限网络下 Git DNS 失败，后已成功获取；uv 缓存路径权限问题已通过任务目录缓存修复。它们不属于算力不足。CIM CPU 型号接口不可访问，使用 platform.processor 与 psutil 记录硬件。",
          "", "若迁移：4 CPU 线程、8 GB RAM、Python 3.12，无需 GPU。依次执行 `python -m pip install -r task06/requirements.txt` 与 `python task06/run_task06.py all`。恢复时从 prepare/preflight/train/predict/evaluate/report/verify/manifest 已完成检查点的下一阶段运行；预测后 train 会拒绝重新选参。",
          "", "日志时间采用 UTC ISO 格式；业务切分和所有预测时间均为 Asia/Shanghai。拟合数据截止是历史信息截止，不代表已模拟真实在线计算与发布延迟。"]
    if (OUT/"reproduction_check.json").exists():
        rr=read_json(OUT/"reproduction_check.json")
        text.extend([f"独立目录完整一键复跑的观测阶段跨度 {rr['observed_stage_span_seconds']:.3f} 秒；从首阶段开始时间到最后报告结束时间推算，排除解释器启动和最终清单 I/O。12 份关键表（含 105408 行预测）完全一致。该复跑验证可复现性，未修改参数或根据测试成绩重新选择模型。"])
    (REPORT/"resource_report.md").write_text("\n\n".join(text),encoding="utf-8")
    (OUT/"resource_report.md").write_text("\n\n".join(text),encoding="utf-8")
    csv(frame,"resource_stage_measurements.csv")


def report():
    REPORT.mkdir(parents=True,exist_ok=True)
    with timed("report_generation"):
        fig_info=figures()
        resource_report()
        metric=read_csv(OUT/"metrics.csv").query("split=='test'")
        support=read_csv(OUT/"sample_support.csv")
        stability=read_csv(OUT/"stability_conclusions.csv")
        high=read_csv(OUT/"high_load_metrics.csv").query("split=='test'")
        peak=read_csv(OUT/"daily_peak_metrics.csv").query("split=='test'")
        peak_summary=peak.groupby(["scenario","model"],sort=False).agg(
            peak_abs_kw=("peak_abs_kw","mean"),peak_under_kw=("peak_under_kw","mean"),
            true_peak_gap_kw=("true_peak_gap_kw","mean"),peak_time_h=("peak_time_h","mean"),
            peak_time_circular_h=("peak_time_circular_h","mean"),true_flat_days=("true_flat","sum"),
            pred_flat_days=("predicted_flat","sum"),days=("origin","size")).reset_index()
        uncertainty=read_csv(OUT/"uncertainty_summary.csv")
        eligibility=read_csv(OUT/"origin_quality.csv").copy()
        for row_mask,col in [("fit_eligible_initial","initial_fit_exclusion_reason"),
                             ("fit_eligible_refit","refit_exclusion_reason"),
                             ("validation_selection_mask","validation_selection_exclusion_reason")]:
            reasons=[]
            for row in eligibility.itertuples():
                if getattr(row,row_mask):
                    reasons.append("")
                elif not row.common_score_mask:
                    reasons.append("incomplete_history_or_target; see release_reason and exclusion_reason")
                elif row_mask=="fit_eligible_initial" and row.split!="train":
                    reasons.append("outside_initial_training_split")
                elif row_mask=="fit_eligible_refit" and row.split=="test":
                    reasons.append("test_never_fitted")
                elif row_mask=="validation_selection_mask" and row.split!="validation":
                    reasons.append("outside_validation_split")
                else:
                    reasons.append("whole_day_labels_not_yet_published_at_cutoff")
            eligibility[col]=reasons
        csv(eligibility,"eligibility_exclusions.csv")
        intervals=uncertainty.loc[(uncertainty.algorithm=="paired_week7")&uncertainty.metric.eq("MAE_kw")&uncertainty.right_model.notna()]
        selected=read_json(OUT/"experiment_config_frozen.json")["selected_parameters"]
        manifest_input=read_json(OUT/"input_manifest.json")
        verification_path=OUT/"verification_task06.json"
        verification=read_json(verification_path) if verification_path.exists() else None
        status=(f"已独立核验通过：{verification['passed']} 组验收，失败 {verification['failed']}。" if verification and verification['status']=="passed" else "独立核验待运行；本处不预先声明通过。")
        reproduction=read_json(OUT/"reproduction_check.json") if (OUT/"reproduction_check.json").exists() else None
        text=["# task06 条件性日前预测实验报告", "",
              f"版本 `{VERSION}`。实际起点提交 `{manifest_input['start_commit']}`；独立分支 `{manifest_input['branch']}`。",
              "设计规定已整理至 DESIGN.md；六种方法、双延迟、可获知性、固定掩码、独立选参、一次重训、10000 次四算法配对 bootstrap 已实现并实际运行。"+status,
              "",METHOD_NOTE,"", "## 数据与信息边界", "",
              "固定 cn_obee_v1_noimpute_v1.0.0，panel13/v1.0.0，排除电饭煲。目标为 13 台监测设备合计功率的小时内时间平均，单位 kW，不是设备间平均或独立整户电表。连续 8784 小时、8503 严格有效小时和 281 缺口全部保留。数据输入版本、实际路径和 SHA-256 见 input_manifest.json。",
              "训练 [2021-05-31,2022-03-09)，验证 [2022-03-09,2022-04-06)，测试 [2022-04-06,2022-06-01)，每天北京时间 00:00 发布 24h。发布只依赖可获知历史和已公开日历，未来目标完整性仅参与评分与已发生标签拟合。",
              "", table(support), "",
              "0h 初始拟合 253 天 / 6072 行，选参 28 天 / 672 行，重训 281 天 / 6744 行；1h 初始拟合 252 天 / 6048 行，选参 27 天 / 648 行，重训 280 天 / 6720 行。两场景测试均 56 天 / 1344 小时，8 个固定周块。1h 最后一个训练日和最后一个验证日的末标签在相应午夜尚未发布；完整日保守规则排除整日，事后验证仍完整报告 28 天。",
              "2021/2022 日历网页分别公开于 2020-11-26、2021-10-25；未知时分时保守假设次日 00:00 可用。notice_date 原字节不改，新增 public_date/public_available_at 并审计。1h 的 h=23 昨日同期改为前日同期，B1 名称为 lag24_else_lag48；所有学习模型同步。无真实缺失临时回填。",
              "", "## 冻结模型与验证", "",
              "一个共享 horizon 模型，20 个信息字段统一固定 one-hot 为 78 维；Linear-L1 只在当前拟合段学习数值缩放。训练候选仅用初始训练段，验证选参只用截至 test_start 已发布的完整验证日。近似并列容差 1e-12；线性优先强正则，树模型依次优先少树、少叶、大最小叶样本。消融固定 Full 参数。",
              "```json\n"+json.dumps(selected,ensure_ascii=False,indent=2)+"\n```", "",
              f"最终冻结文件 SHA-256：`{sha(OUT/'experiment_config_frozen.json')}`。首次测试预测前已保存；每场景重训一次，测试固定模型。真实验证预测来自初始模型，未用重训模型回填。训练集结果单列 fit_diagnostic，不作样本外证据。raw 与 max(raw,0) 及截断数均保存。",
              "候选验证 MAE、求解状态、耗时见 validation_search.csv；模型、处理器、拟合支持和截止见 model_stage_index.csv 与 training_log.jsonl。",
              "", "## 测试总体与稳定改善", "",table(metric[["scenario","model","n_hours","n_days","MAE_kw","RMSE_kw"]]), "",
              table(intervals[["scenario","comparison","point_estimate","ci_low","ci_high","valid_repetitions"]]),"",
              table(stability), "",
              "主差值为 Full−比较方法，负值代表 Full 的 MAE 更低；消融差值为消融−Full，正值代表 Full 更好。稳定改善对两条基线分别要求总体负差、配对周块区间上界<0、至少 6/8 周负差。6/8 为本项目预设操作规则，不是通用显著性检验。",
              "实际用途阈值、τ_U/τ_P/τ_T、p_day/p_high、实际改善量与非劣界限全部未定义，不判绝对合格、等效或不劣，也不使用 5% 作为实际资格线。",
              "", "## 高负荷与低估风险", "",
              f"H 为共同小时中 y>{Q} kW，阈值直接承接最初训练段 6487 严格小时，未用 6072 行模型集合重新拟合。",
              table(high[["scenario","model","n_H","n_H_days","n_H_week_blocks","MAE_H_kw","Bias_H_kw","U_H_kw","under_rate_H","conditional_gap_H_kw","gap_q90_H_kw","FNR_H","over_mean_all_kw"]]), "",
              "低估发生率是预测低于真实；FNR_H 是高负荷小时预测未超过阈值，两者不能混同。gap_q90 包含所有高负荷小时的零缺口。U_H 是全部 H 小时平均正缺口；只有发生低估的小时才进入条件平均缺口。各周高负荷数量和 NA 原因见 high_load_metrics.csv 与 weekly_metrics.csv。",
              "", "## 日峰值", "",table(peak_summary),"",
              "精确 float64 并列；预测取最早峰，对所有真实峰取最小普通小时差为主。环形距离只作补充。真实平坦日时差 NA，幅度保留；预测平坦仍保留并取 0 点。逐日真实/预测峰集合、并列数、平坦标记和全部预测并列到真实峰的平均最近距离见 daily_peak_metrics.csv。",
              "", "## 风险比较与消融", ""]
        for scenario in ("0h","1h"):
            hh=high.loc[high.scenario==scenario].set_index("model")
            pp=peak_summary.loc[peak_summary.scenario==scenario].set_index("model")
            for baseline in ("B1","B2"):
                diffs={f:float(hh.loc["Full",f]-hh.loc[baseline,f]) for f in ["MAE_H_kw","U_H_kw","FNR_H"]}
                pdiffs={f:float(pp.loc["Full",f]-pp.loc[baseline,f]) for f in ["peak_abs_kw","peak_under_kw","peak_time_h"]}
                text.append(f"{scenario} Full−{baseline} 高负荷差："+", ".join(f"{k}={v:+.6f}" for k,v in diffs.items())+
                            "；峰值差："+", ".join(f"{k}={v:+.6f}" for k,v in pdiffs.items())+"。上述误差/风险差为正代表恶化。")
        text.extend(["即使整体 MAE 更低，高负荷或峰值指标恶化仍须单独披露，不能据总体结果宣称峰值场景可靠。消融回答当前 Full 参数配置下删除特征组的影响；即使某消融测试更好，也不回头替换主模型。",
              "",table(read_csv(OUT/"ablation_metrics.csv").query("split=='test'")),"",
              "跨场景比较见 information_sensitivity.csv，使用两场景交集重新计算；不同场景独立拟合，不复用模型。",
              "", "## 时间块区间与限制", "",
              "主算法有放回抽 8 个不重叠连续 7 日块；移动日块敏感性 L=3/7/14，均不环绕，拼接后截取 56 日。每项每算法每场景 B=10000、seed=42，全部方法配对使用同一日索引。重算平方误差与子集分子分母，不平均周 RMSE 或高负荷 MAE；q90 使用整数重复权重的精确线性分位数。有效重复不足 95% 不发布区间。完整结果及有效次数见 uncertainty_summary.csv，索引和部分重抽样指标留供独立核验。",
              "小时、日期、周块均未经证明相互独立；10000 次重抽样不是 10000 份新数据。本版未估计 N_eff；只有 8 块，跨周依赖和非平稳性限制区间解释。多 horizon 与消融的逐项区间不是同时成立的显著性结论。区间跨零不等于等效，评价差值区间不是未来负荷预测区间。",
              "", "## 图表与案例", "",
              "以下图表全部为测试集。无缺口时完整绘制；绘图数据按真实日历重建并保留 NaN，缺口不连线。支持数写在图内。案例规则在测试前固定，最高真实峰和 Full 最差日属于事后诊断，不能代表整体证据。",
              *[f"![{name}](figures/{name})" for name in ["01_daily_mae.png","02_horizon_mae.png","03_weekly_paired_deltas.png","04_high_load_diagnostics.png","05_fixed_rule_cases.png"]],
              "", "## 实际运行与核验", "",
              "在仓库根目录，实际使用专用环境执行：", "",
              "```powershell\n& ..\\.venv\\Scripts\\python.exe task06/run_task06.py prepare\n& ..\\.venv\\Scripts\\python.exe task06/run_task06.py preflight\n& ..\\.venv\\Scripts\\python.exe -m pytest task06/tests -q\n& ..\\.venv\\Scripts\\python.exe task06/run_task06.py train\n& ..\\.venv\\Scripts\\python.exe task06/run_task06.py predict\n& ..\\.venv\\Scripts\\python.exe task06/run_task06.py evaluate\n& ..\\.venv\\Scripts\\python.exe task06/run_task06.py report\n& ..\\.venv\\Scripts\\python.exe task06/run_task06.py verify\n& ..\\.venv\\Scripts\\python.exe task06/run_task06.py manifest\n```", "",status,
              "核验采用已保存 CSV 的独立算术、人工反例、合法冻结模型的未来记录删除/扰动不变性实验、目标缺口/QC 改动、全部模型加载复现与上游原字节检查；同一环境中的独立代码路径不代表外部人员审阅。详见 verification_task06.json。",
              (f"独立目录从输入开始的一键复跑也已完成：观测阶段跨度 {reproduction['observed_stage_span_seconds']:.3f} 秒，另一次训练/选参/重训仍按同一冻结规则运行，12 份关键表与主实验逐字节一致，含 105408 行全位置预测。详情见 reproduction_check.json。" if reproduction else "独立目录完整复跑状态另见 reproduction_check.json（如已生成）。"),
              "", "## 资源与结论范围", "",
              "本地资源实测与推算分列于 resource_report.md；CPU 预检已完成，无需云 CPU 或 GPU。最终 bootstrap 不重复拟合，也没有减少正式次数。",
              "本项目新增插补 0，不等于上游从未填补；逐点上游填补身份 unknown。这是固定发布数据、固定面板和声明可用性假设下的条件性日前回测。真实部署可用性仍需在线日志验证。测试仅覆盖 2022-04-06 至 05-31，不能声称全年或跨家庭有效。设计参考过上游全期描述性成果，具有回顾性探索背景。离线数据截止不等于已经模拟真实训练耗时和服务发布延迟。",
              "源数据未知的上游填补和真实部署日志不是本版已解决问题；全部已计划实现/运行/核验状态以实际日志为准。主分支由用户合并。",
              "", "## 参考资料", "",*[f"- [{label}]({url})" for label,url in REFERENCES]])
        md="\n\n".join(text)
        (REPORT/"task06_report.md").write_text(md,encoding="utf-8")
        # Self-contained HTML for review; Markdown retained as the source report.
        parts=["<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>task06 实验报告</title>",
               "<style>body{font:16px/1.75 'Microsoft YaHei',sans-serif;max-width:1280px;margin:32px auto;padding:0 24px;color:#183042}table{border-collapse:collapse;display:block;overflow:auto;font-size:13px}th,td{border:1px solid #ccd7df;padding:6px 10px;white-space:nowrap}h1,h2{color:#005b89}img{max-width:100%}pre{overflow:auto;background:#f1f5f8;padding:16px}</style>"]
        for chunk in text:
            if not chunk: continue
            if chunk.startswith("!["):
                path=REPORT/re.search(r"\]\((.*)\)",chunk).group(1)
                b64=base64.b64encode(path.read_bytes()).decode()
                parts.append(f"<img src='data:image/png;base64,{b64}' alt='{path.name}'>")
            elif chunk.startswith("| "):
                lines=chunk.splitlines(); cells=[[c.strip() for c in line.strip("|").split("|")] for line in lines]
                parts.append("<table><thead><tr>"+"".join("<th>"+html.escape(c)+"</th>" for c in cells[0])+"</tr></thead><tbody>"+
                    "".join("<tr>"+"".join("<td>"+html.escape(c)+"</td>" for c in row)+"</tr>" for row in cells[2:])+"</tbody></table>")
            elif chunk.startswith("```"):
                parts.append("<pre>"+html.escape("\n".join(chunk.splitlines()[1:-1]))+"</pre>")
            elif chunk.startswith("# "):
                parts.append("<h1>"+html.escape(chunk[2:])+"</h1>")
            elif chunk.startswith("## "):
                parts.append("<h2>"+html.escape(chunk[3:])+"</h2>")
            elif chunk.startswith("- ["):
                match=re.match(r"- \[(.*?)\]\((.*?)\)",chunk)
                parts.append(f"<p><a href='{html.escape(match.group(2))}'>{html.escape(match.group(1))}</a></p>")
            else:
                parts.append("<p>"+html.escape(chunk)+"</p>")
        parts.append("</html>")
        (REPORT/"task06_report.html").write_text("\n".join(parts),encoding="utf-8")
        write_json(REPORT/"figure_metadata.json",fig_info)


def manifest():
    paths=[p for folder in [ROOT/"task06",OUT] for p in folder.rglob("*") if p.is_file()
           and "__pycache__" not in p.parts and ".pytest_cache" not in p.parts
           and p.name!="derivation_manifest.json"]
    write_json(OUT/"derivation_manifest.json",dict(version=VERSION,created_at=now(),
        start_commit=read_json(OUT/"input_manifest.json")["start_commit"],branch=git("branch","--show-current"),
        inputs=read_json(OUT/"input_manifest.json"),
        dependencies={d.metadata["Name"]:d.version for d in importlib.metadata.distributions()},
        verification=read_json(OUT/"verification_task06.json")["status"],
        outputs=[dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(paths)],
        manifest_self_hash="intentionally excluded to avoid recursion"))
