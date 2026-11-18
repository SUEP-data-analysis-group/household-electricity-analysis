# task06：固定监测面板的条件性日前预测

本版实现 0h 主场景与 1h 发布延迟敏感性，比较昨日/上周基线、同特征 Linear-L1、LightGBM-L1 Full 和两组固定参数消融。实现、运行与独立核验状态以 [实验报告](reports/task06_report.md)、[完整 HTML 报告](reports/task06_report.html)和 [核验记录](reports/verification_task06.json)为准。

下面的框架综合了预测评价论文和 NeurIPS 官方清单，是针对你这个任务整理的检查方法，不是文献中的统一评分量表。预测评价论文明确讨论了基线、切分、指标、泄漏和统计比较；NeurIPS 清单则强调结论范围、实验细节、局限性与可复现性。

## 设计与数据

[DESIGN.md](DESIGN.md) 是统一规则说明，明确取代旧要求中冲突的发布资格、模型矩阵、峰时距离、1h 延迟、稳定改善与区间定义。机器配置位于 `data/derived/task06/experiment_config.json`；测试前选参冻结版为 `experiment_config_frozen.json` 及 `.sha256`。

输入固定 task02 连续严格小时负荷、task01 面板/切分/质量核验、task03 日历和 task04 阈值；详见 [输入清单](../data/derived/task06/input_manifest.json)。不重跑分钟处理，不使用 task05 状态，不修改 task01—05 发布原件。

标准版本 `cn_obee_v1_noimpute_v1.0.0`、`panel13/v1.0.0`，排除电饭煲。目标是固定 13 台监测设备**合计功率的小时内时间平均** `mean_power_kw`，单位 kW，不是设备间平均或独立整户总表。float64、round_trip；8784 小时连续网格、8503 严格有效小时；缺口留空，无目标填补或片段均值替代。

固定北京时间切分：训练 `[2021-05-31,2022-03-09)`，验证 `[2022-03-09,2022-04-06)`，测试 `[2022-04-06,2022-06-01)`。每天 D 00:00 发布 h=0…23。小时 s 的 `available_at=s+1h+latency`；只有已发布历史可用。发布不看未来完整性或事后 QC；评分才检查完整目标。全部起点和 origin×horizon 位置保留。

0h 评分支持为 253/28/56 天，初始拟合 253 天、最终重训 281 天。1h 评分同为 253/28/56 天，初始拟合 252 天、验证选参 27 天、重训 280 天；整日标签全部发布后才进入拟合或选参。1h h=23 的 B1 与学习模型 lag24 同步回退 lag48，B1 定义为 `lag24_else_lag48`，其他缺失不回填。支持均为实际计算，见 sample_support.csv。

日历白名单独立于负荷。保留 notice_date，新增 public_date/public_available_at；2021/2022 安排网页公开日为 2020-11-26/2021-10-25，未知时分保守假设次日北京时间 00:00。来源核对记录见 [web_verification.json](sources/web_verification.json)。目标日历日期可以在未来，审计规则公开时刻。

## 模型与评价

一个共享 horizon 模型，紧凑数值特征为周期滞后、最近可用小时、24/168h 的 mean/std/min/max（std ddof=0），类别全集预定义并统一 one-hot。线性中位数回归仅在相应拟合段缩放数值。完整候选、确定性并列规则、CPU 设置见配置；不用早停，两消融不独立调参。

先固定掩码与规则，再训练段拟合、验证选参、冻结，首次测试前重训一次，测试固定模型；验证预测保留初始模型，训练误差仅 fit_diagnostic。所有方法保存 raw_pred 并统一 max(raw,0)，异常预测报错而非删除评分行。

主 MAE；RMSE、高负荷与日峰值为预定次指标。高负荷 q=0.7326097666666669 kW，沿用最初训练段 6487 严格小时，不重算。报告偏差、低估量/率、条件缺口、缺口 q90、阈值漏报及全体高估量。峰时主规则是预测并列取最早小时，与全部真实并列峰取最小普通小时差；真实平坦日时差 NA，预测平坦不得排除；环形与全部预测峰平均最近距离另列。

配对 bootstrap 主算法为 8 个不重叠连续 7 日块有放回抽 8 块；敏感性是不环绕移动日块 L=3/7/14。每算法每场景 10000 次，seed=42，方法间共享索引；重算总体及子集分子分母，有效重复不足 95% 不发布区间。

Full 对每条基线须同时满足测试 ΔMAE<0、主区间上界<0、至少 6/8 固定周块 ΔMAE<0，才称“在本测试时段内有稳定改进”。6/8 是项目预设规则。实用改善阈值、可靠性阈值与非劣界限均未定义；不自定 5% 资格线，不将跨零区间解释为等效，不把评价差值区间叫未来负荷预测区间。

## 运行入口

在仓库根目录，Python 3.12 的任务专用环境中运行：

```powershell
python -m pip install -r task06/requirements.txt
python task06/run_task06.py all
```

仓库已附正式结果时，保留原结果，在新目录完整复跑：

```powershell
python task06/run_task06.py all --output-root work/task06_reproduction/data --report-root work/task06_reproduction/reports
python task06/compare_reproduction.py
```

独立阶段：

```powershell
python task06/run_task06.py prepare
python task06/run_task06.py preflight
python -m pytest task06/tests -q
python task06/run_task06.py train
python task06/run_task06.py predict
python task06/run_task06.py evaluate
python task06/run_task06.py report
python task06/run_task06.py verify
python task06/run_task06.py manifest
```

一键入口会在核验后刷新最终报告。分阶段运行时，核验后再运行 report、manifest 可刷新核验状态与哈希。预测文件已存在时 train 会拒绝重新调参；若只需复核，运行 verify。恢复时从已完成检查点的下一阶段开始，不能根据测试结果重选参数；影响预测的修复须记录原因与新版本。

生产模块：data（输入、在线特征、独立标签掩码）、modeling（固定编码、模型、选择、重训）、evaluation（指标与配对 bootstrap）、reporting（图文报告）、verify_task06（独立 CSV 重算与变形核验）。源代码、设计、测试与报告在 task06/，正式数据、模型、审计和清单在 [data/derived/task06/](../data/derived/task06/)。

## 交付与核验

主要表包括 input/split/derivation manifest、配置与冻结哈希、特征目录/来源审计、起点质量/共同掩码、全位置预测与基线、验证搜索、模型索引、总体/日/时距/周/高负荷/峰值/消融/跨场景指标、所有区间和稳定性结论。另保存模型与处理器、训练日志、资源预检与实测报告、bootstrap 索引和核验用重复指标、独立核验 JSON。

核验覆盖实际输入/设备/标签、独立重建掩码、拟合与选参截止、1h 回退、同集预测键、人工峰时/空集反例、子集 bootstrap 分母和区间门槛、从保存预测的独立指标重算、合法模型未来记录删除/扰动不变性、目标质量/QC 不影响发布、模型加载复现与上游原字节。独立指代码计算路径，不暗示已由外部人员审阅。

## 范围限制

本项目新增插补 0，不等于上游从未填补；逐点上游填补身份 unknown。这是固定发布数据、固定面板和声明可用性假设下的条件性日前回测。真实部署可用性仍需在线日志验证。测试仅覆盖 2022-04-06 至 05-31，不能声称全年或跨家庭有效。设计参考过上游全期描述性成果，应披露回顾性探索背景。离线数据截止不等于已经模拟真实训练耗时和服务发布延迟。

小时、日和周块未证明独立，10000 次重抽样不是新数据，未估计 N_eff；只有 8 周，跨周依赖及非平稳性限制区间解释，多 horizon/消融结果不自动构成同时成立的显著性结论。整体 MAE 改善也不保证高负荷或峰值场景可靠。

## 参考资料

- [预测评价论文](https://link.springer.com/article/10.1007/s10618-022-00894-5)
- [NeurIPS 官方清单](https://neurips.cc/public/guides/PaperChecklist)
- [LightGBM 调参](https://lightgbm.readthedocs.io/en/stable/Parameters-Tuning.html)
- [LightGBM GPU 性能](https://lightgbm.readthedocs.io/en/stable/GPU-Performance.html)
- [QuantileRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.QuantileRegressor.html)
- [CN-OBEE 数据论文](https://www.nature.com/articles/s41597-023-02891-9)
