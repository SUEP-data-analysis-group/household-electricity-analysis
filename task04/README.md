# 任务四：峰值、低谷与日内变化

**已完成，2026-11-14。** 当前派生版 `task04_v1.0.1_20261114`。本目录为仓库 task04/，包含程序、来源、8 张图和离线报告；正式数据位于项目根目录 data/derived/task04/。

先打开 **[完整 HTML 报告](reports/task04_report.html)**；也可看 [Markdown 报告](reports/task04_report.md)、[核验日志](reports/verify_task04.txt)和 [字段说明](DATA_DICTIONARY.md)。

## 完成了什么

- 352 个完整日的日峰、谷、峰谷差、均值和负荷率；14 个不完整日只保留质量清单，不冒充已知全日极值。
- 全部并列小时保留，按 `1/tied_count` 分配权重；峰/谷各自的日期权重总和为 352。
- 连续保留 8784 小时、8503 个严格有效小时；有效相邻变化 8500 对，其中同日内 8147 对、跨午夜 353 对。缺口两侧不相减。
- 每个完整日另算分钟记录峰，与小时均值峰分开；全期最大小时峰 3.438890 kW，最大分钟记录峰 6130.41 W。
- 按预先写入配置的规则固定 4 个案例；每例附 13 台设备的全部 1440 分钟及 QC，不平滑、不削峰、不新增插补。

## 任务一完成后的实际承接

依据 [仓库](https://github.com/SUEP-data-analysis-group/household-electricity-analysis)提交 `3e0ffa3da8fbacf714bacff1d84094ed08a31f73` 的项目说明和任务四要求。28 份输入/要求原件已与 GitHub blob ID 核对，并记录 SHA-256，见 [输入清单](sources/input_manifest.json)。

- task01：`cn_obee_v1_noimpute_v1.0.0`、固定 `panel13/v1.0.0`、标准分钟功率和面板、13 台设备 QC、冻结切分及严格聚合核验表。
- task02：`task02_v1.1.0_20261113` 的严格小时/日表及派生清单；主字段 `mean_power_kw`，不完整小时为空。
- task03：`task03_v1.1.0_20261113` 的日期标签及派生清单。案例普通工作日/周末按自然星期选，实际法定日类型同时附带。

原任务说明留在 [sources/requirements/](sources/requirements/)；其中“尚未生成”是收到的历史任务要求，当前完成状态以本 README 和实际数据为准。原件和上游清单没有被改写。上游清单提到的其他结果不属于本任务必需输入，未重复打包。

## 目录与运行方式

程序、配置、字段说明、来源与报告位于 task04/；11 份 CSV、thresholds.json 和派生清单位于项目根目录 data/derived/task04/。24 份数据输入直接复用仓库已有 task01—task03 文件，不再复制 inputs/。

在完整仓库根目录运行：

```powershell
python -m pip install -r task04/requirements.txt
python task04/run_task04.py
python task04/verify_task04.py
python -m unittest discover -s task04/tests -v
```

程序根据 task01 元数据自动识别仓库根目录；仍支持 --source-root 和 --output-root 显式参数。清单中的 local_path 保留原独立包归档路径，数据定位使用 repository_path；原任务要求保存在 sources/requirements/。

本地审核版为 task04_v1.0.0_20261114，仓库路径适配版为 task04_v1.0.1_20261114。两版 11 份 CSV 的字节完全相同；变化限于路径识别、版本说明和报告入口。完整历史见 [版本记录](CHANGELOG.md)。

## 正式数据入口

### 本任务应交付

| 文件 | 行数 | 内容 |
| --- | --- | --- |
| [daily_peak_valley.csv](../data/derived/task04/daily_peak_valley.csv) | 352 | 完整日日峰、谷、差、均值、负荷率及并列数量 |
| [daily_extrema_times.csv](../data/derived/task04/daily_extrema_times.csv) | 715 | 全部并列峰谷小时及等权重 |
| [peak_hour_frequency.csv](../data/derived/task04/peak_hour_frequency.csv) | 48 | 24 小时 × 峰/谷；按完整日归一的加权频率 |
| [hourly_changes.csv](../data/derived/task04/hourly_changes.csv) | 8784 | 连续小时网格，含无效行原因、同日/跨午夜、严格相邻变化 |
| [case_manifest.csv](../data/derived/task04/case_manifest.csv) | 4 | 任务五共用的四个案例、设备范围、全部峰时、选择依据及质量 |
| [excluded_days.csv](../data/derived/task04/excluded_days.csv) | 14 | 14 个不完整日及无法确定全日峰谷的原因 |
| [daily_minute_hourly_comparison.csv](../data/derived/task04/daily_minute_hourly_comparison.csv) | 352 | 完整日分钟记录峰与小时均值峰对照，保留全部分钟并列峰 |
| [hourly_change_summary.csv](../data/derived/task04/hourly_change_summary.csv) | 3 | 全体/同日内/跨午夜的相邻变化支持与描述统计 |
| [case_hourly_curves.csv](../data/derived/task04/case_hourly_curves.csv) | 96 | 案例的全部严格小时输入 |
| [case_minute_curves.csv.gz](../data/derived/task04/case_minute_curves.csv.gz) | 5760 | 每例 1440 分钟的 13 台设备、面板值、源行号及逐设备 QC 位 |
| [case_quality_summary.csv](../data/derived/task04/case_quality_summary.csv) | 52 | 每例每台设备的有效/复核/插补数量 |

另附 [thresholds.json](../data/derived/task04/thresholds.json) 和 [derivation_manifest.json](../data/derived/task04/derivation_manifest.json)，记录版本、规则、输入/输出哈希、环境、实际数量和阈值。

## 口径、阈值和案例规则

时间为 Asia/Shanghai，分析 `[2021-05-31 00:00,2022-06-01 00:00)`，小时标签为左闭右开区间起点。功率 W/kW 分列，电量 kWh；float64 round-trip 读取，不先舍入再取极值。

负荷率是 `mean_kw/peak_kw`，零峰时为空；并列峰谷每小时分配 `1/tied_count`。分钟峰是上游规则化数据的“分钟记录峰值”，不声称真实瞬时峰值。14 个缺测日不在日极值主表中。

“大变化”用训练期有效相邻对 |变化| 的 q95：**0.644477241667 kW**，条件为严格大于；训练区间 `[2021-05-31,2022-03-09)`，两端都在训练段。另存训练期严格小时 q90 **0.732609766667 kW** 供任务六评估参考。全期分位数另标探索描述，不能拿来替换训练拟合参数。

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
