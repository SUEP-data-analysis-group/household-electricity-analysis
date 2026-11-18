# 家庭用电规律与负荷变化分析

基于 **CN-OBEE v1**，分析北京一户家庭监测电器的用电规律、日类型差异、峰谷变化、电器贡献与日前负荷预测。

**当前进度（2026-11-18）：task01—task06 均已交付，代码、数据、报告与核验记录已入库。** 主分析固定为不含电饭煲的 13 台监测设备；设备合计负荷不代表独立整户电表读数。

[任务与报告](#任务与报告) · [数据口径](#数据口径) · [快速使用](#快速使用) · [版本与来源](#版本与来源)

## 从哪里开始

- **看研究结果：**从下表进入各任务报告；HTML 报告下载后可离线打开，Markdown 报告可直接在 GitHub 阅读。
- **使用现成数据：**优先读取 [严格小时负荷](data/derived/task02/hourly_panel13.csv)、[日历标签](data/derived/task03/holiday_calendar_2021_2022.csv)和各任务的正式派生数据，无需重跑分钟处理。
- **复核或继续开发：**先读 [数据契约](task01/DATA_CONTRACT.md)，再按各任务 README 查看依赖、运行命令、版本与适用范围。

## 任务与报告

任务目录存放程序、说明与报告；正式派生数据集中在 `data/derived/`。

| 任务 | 完成内容 | 结果入口 | 数据入口 |
| --- | --- | --- | --- |
| [task01 数据基础](task01/README.md) | 来源核验、标准化、质量审计、固定面板与预测切分 | [质量报告](task01/reports/quality_report.md) | [标准数据](data/standardized/cn_obee_v1_noimpute_v1.0.0/) · [字典与核验表](task01/reports/) |
| [task02 时间统计](task02/README.md) | 严格小时/日统计、周月支持、月度与季节典型曲线 | [分析报告](task02/reports/task02_report.md) | [正式数据](data/derived/task02/) |
| [task03 日类型比较](task03/README.md) | 自然周末与法定休息日、日历、同月比较及块抽样区间 | [分析报告](task03/reports/task03_report.md) · [HTML](task03/reports/task03_report.html) | [正式数据](data/derived/task03/) |
| [task04 峰谷与变化](task04/README.md) | 日峰谷、并列时刻、相邻小时变化、分钟峰与固定案例 | [分析报告](task04/reports/task04_report.md) · [HTML](task04/reports/task04_report.html) | [正式数据](data/derived/task04/) |
| [task05 电器贡献与重叠](task05/README.md) | 同集合贡献、峰时贡献、运行规则、分钟状态与重叠 | [验收说明](task05/reports/验收修订说明.md) · [实验报告](task05/reports/task05_后三步实验报告.md) | [正式数据](data/derived/task05/) |
| [task06 日前预测](task06/README.md) | 双延迟、六种方法、可获知性审计、配对评价与独立核验 | [实验报告](task06/reports/task06_report.md) · [HTML](task06/reports/task06_report.html) | [预测、指标与模型](data/derived/task06/) |

## 主要结果

- **样本支持：**366 个日历日中有 352 个严格完整日，完整日合计约 **2739.60 kWh**；其余 14 日完整电量未知，不能将这个合计称作全区间总电量。
- **日类型比较：**控制同年月份后，自然周末与法定休息日的日均电量差分别约为 **+0.520、+0.434 kWh**，两项主区间均覆盖 0，不能断言休息日稳定更耗电。
- **电器重叠：**固定可判定 S12 子集内，至少两台电器规则判定为 on 的时间占共同已知分钟的 **37.49%**。运行状态是功率规则代理，不能据此推断住户活动或因果关系。

### task06：日前预测

每天北京时间 00:00 一次预测未来 24 小时；固定测试期为 **2022-04-06 至 2022-05-31**，两个场景均为 56 日、1344 小时。0h 为小时结束即最终可用的假设，1h 为额外延迟一小时的敏感性场景。

| 方法 | 0h 测试 MAE（kW） | 1h 测试 MAE（kW） |
| --- | ---: | ---: |
| 昨日同期 B1（1h 末小时回退至前日同期） | 0.128200 | 0.127276 |
| 上周同期 B2 | 0.132949 | 0.132949 |
| 同特征线性中位数回归 Linear-L1 | 0.094460 | 0.096057 |
| LightGBM-L1 Full | 0.095704 | 0.095287 |

Full 在两个场景均满足本项目预设的稳定改进规则：相对两条基线的总体 MAE 更低、主配对周块差值区间上界小于 0，且 **8/8 个固定周块**获胜。0h 下 Linear-L1 的 MAE 略优于 Full。

**整体改善不代表峰值可靠。** 测试仅有 17 个高负荷小时，Full 的高负荷误差、平均低估量及日峰幅度误差存在恶化，17 个高负荷小时全部漏报阈值。消融、逐日/时距/周结果、区间和结论范围见 [完整报告](task06/reports/task06_report.md)与 [统一设计](task06/DESIGN.md)。

## 数据口径

| 项目 | 固定约定 |
| --- | --- |
| 标准版本 | `cn_obee_v1_noimpute_v1.0.0` |
| 主面板 | `panel13/v1.0.0`，固定 13 台设备，排除电饭煲；[具体名单](task01/reports/panel_definition.json) |
| 时区与区间 | `Asia/Shanghai`；`[2021-05-31 00:00, 2022-06-01 00:00)`，左闭右开 |
| 连续网格 | 527040 分钟、8784 小时、366 日；缺口保留，不压缩时间轴 |
| 严格有效支持 | 8503 个完整小时、352 个完整日；面板分钟联合有效率 96.8207% |
| 单位与完整性 | 分钟功率 W、小时平均负荷 kW、电量 kWh；完整小时要求 60/60 有效分钟，完整日要求 24/24 合格小时 |
| 缺测与填补 | 本项目新增插补 0；上游逐点填补身份为 `unknown`，不能称全部数值为原始实测 |

小时主目标为严格 `mean_power_kw`，不完整小时保持为空；`observed_duration_mean_power_kw` 与部分设备求和仅供诊断。14 台设备的补充分析使用独立共同有效集合，不能与 panel13 拼接。2021 年 6—7 月缺测集中，结论不能脱离样本范围。

预测切分固定为训练 `[2021-05-31,2022-03-09)`、验证 `[2022-03-09,2022-04-06)`、测试 `[2022-04-06,2022-06-01)`。历史值必须在预测起点已发布，未来目标完整性只参与事后评分；规则见 [task06 设计](task06/DESIGN.md)，切分原件见 [split_manifest.json](task01/reports/split_manifest.json)。

## 快速使用

```bash
git clone https://github.com/SUEP-data-analysis-group/household-electricity-analysis.git
cd household-electricity-analysis
```

安装 [task02 的依赖](task02/requirements.txt)后，可直接读取现成小时表：

```python
import pandas as pd

hourly = pd.read_csv(
    "data/derived/task02/hourly_panel13.csv",
    float_precision="round_trip",
)
hourly["timestamp"] = pd.to_datetime(hourly["timestamp"]).dt.tz_convert("Asia/Shanghai")
# mean_power_kw 保留缺失；不要补 0 或用片段均值替代。
```

完整复跑与独立核验请按各任务 README 执行，并分别建立兼容环境；环境版本、耗时和通过记录以相应发布报告为准。[task06 资源报告](task06/reports/resource_report.md)记录了 CPU 预检与实测，本地无需 GPU。

> 核验快照说明：task06 的原始实验提交为 [f1ad8ea](https://github.com/SUEP-data-analysis-group/household-electricity-analysis/tree/f1ad8ea075755ea1c4b9a69f22064c7212cc3c1b)。main 已移除三个 task03 历史交付档案，原始严格保全核验仍引用它们；复核该快照或处理合并后的档案缺失时，请看 [PR #1 的说明](https://github.com/SUEP-data-analysis-group/household-electricity-analysis/pull/1)。

## 目录

```text
data/raw/            发布原件、来源清单与官方元数据
data/standardized/   标准分钟数据、固定面板与质量标记
data/derived/        task02—task06 正式派生数据与清单
task01/              数据基础程序、契约、字典与质量报告
task02/—task06/      各任务程序、配置、依赖、报告与核验
docs/history/        历史交付与归档说明
```

## 版本与来源

当前成果使用 `main`；详细迭代见 [CHANGELOG.md](CHANGELOG.md)，其中较早的“待执行”表述属于历史记录，当前完成状态以上方任务导航及各任务最新报告为准。

<details>
<summary>展开查看当前版本与历史入口</summary>

| 任务 | 当前版本 | 版本说明 |
| --- | --- | --- |
| task01 | `cn_obee_v1_noimpute_v1.0.0` | [数据基础](task01/README.md) |
| task02 | `task02_v1.1.0_20261113` | [修订记录](task02/CHANGELOG.md) |
| task03 | `task03_v1.1.0_20261113` | [修订记录](task03/CHANGELOG.md) |
| task04 | `task04_v1.0.1_20261114` | [修订记录](task04/CHANGELOG.md) |
| task05 | `task05_v1.0.1_20261117` | [验收修订](task05/reports/验收修订说明.md) |
| task06 | `task06_v1.0.0_20261118` | [执行记录](task06/EXECUTION_NOTES.md) · [独立核验](task06/reports/verification_task06.json) |

原始交付和审核版通过 Git 历史与标签检索；旧结果不与当前派生表混用。

</details>

- **数据论文：**Wang 等（2024），[Occupant behavior, thermal environment, and appliance electricity use of a single-family apartment in China](https://doi.org/10.1038/s41597-023-02891-9)，*Scientific Data*, 11, 65；[公开全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC10784530/)。
- **数据集：**[CN-OBEE 集合 v1](https://doi.org/10.6084/m9.figshare.c.6742536.v1)，文件条目 DOI `10.6084/m9.figshare.23686476.v1`；本地保留 [下载清单](data/raw/source_manifest.json)与 [官方元数据](data/raw/figshare_metadata.json)。原数据许可证为 CC0，详见元数据。
- **预测研究参考：**Saleptsis、Mussetta 与 Leva（2025），[Gradient Boosting Algorithms for Day-ahead Residential Load Forecasting of Individual Household](https://re.public.polimi.it/handle/11311/1304587)。仅借鉴公开摘要中的研究思路，不声称复现其全文实验设置；本项目预测评价规则与参考文献见 [task06 报告](task06/reports/task06_report.md)。
