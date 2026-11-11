# 任务一 建立可信的用电数据

状态：已完成真实 CSV 审计、无新增插补标准化、面板选择、质量验收和预测日历冻结。完成日期：2026-11-10。原实施方案保留在 [PLAN.md](PLAN.md)。总体依据见[总 README](../README.md)。

标准版本 `cn_obee_v1_noimpute_v1.0.0`；主面板 `panel13/v1.0.0`；时区 `Asia/Shanghai`；功率 W。分析区间为 `[2021-05-31 00:00, 2022-06-01 00:00)`，共 366 个自然日。13 台联合有效率 96.8207%，严格完整小时 8,503 个、完整日 352 天。本次新增插补 0。

建议先阅读[实际质量报告](reports/quality_report.md)，再交给任务二；任务三、四、五依赖任务二的正式派生表，任务六依赖同一小时目标口径。

## 八步执行结果

| 步骤 | 已完成内容 | 可复核产物 |
| --- | --- | --- |
| 1 来源 | 核验归档与 8 个 CSV 哈希、CRC，补存官方 Code v1 的 Notebook.pdf | [来源清单](reports/source_manifest_audited.json)、[补充材料清单](../data/raw/support/support_manifest.json) |
| 2 字段 | 逐个真实表头映射全部源列，写明单位、时间语义、作者处理及未确认项 | [数据字典](reports/data_dictionary.csv)、[数据约定](DATA_CONTRACT.md) |
| 3 时间 | 8 个文件逐行时间核验，保留全部规则位置与源行号，保留末端单条记录 | [时间审计](reports/time_index_audit.csv)、[标准数据](../data/standardized/cn_obee_v1_noimpute_v1.0.0/) |
| 4 质量 | 原缺失保留，功率逐设备质量表，环境独立 QC；不平滑或删统计极端 | [QC 汇总](reports/qc_summary.csv)、[缺口](reports/gap_report.csv)、[异常候选](reports/anomaly_report.csv)、[变更日志](reports/value_change_log.csv) |
| 5 面板 | 13 台主面板准入通过；14 台单独作为共同有效时段补充 | [面板定义](reports/panel_definition.json)、[全期覆盖](reports/coverage_overall.csv)、[月度覆盖](reports/coverage_monthly.csv) |
| 6 核验 | 按发布分钟语义近似积分，严格小时与日交叉检查 | [小时核验表](reports/strict_hourly_check.csv)、[日核验表](reports/strict_daily_check.csv)、[验收](reports/acceptance_checks.csv) |
| 7 切分 | E=2022-06-01，训练/验证/测试按连续日历冻结，逐日起点检查历史 | [切分](reports/split_manifest.json)、[起点质量](reports/forecast_origin_quality.csv) |
| 8 交付 | 生成可复现程序、规则配置、版本清单和 task02–06 的实际承接步骤 | [处理日志](reports/processing_log.json)、[文件清单](reports/output_manifest.json) |

## 实际主口径

- 13 台联合覆盖 96.8207%，14 台联合覆盖 41.2953%。不得将二者拼接为可变设备总负荷。
- 文件边界支持 366 天，13 台严格完整日 352 天；其余 14 天保留缺口。2021-06、07 不支持完整月电量，2021-05 仅有 1 天。
- 电饭煲最后共同有效时刻为 2021-11-09 18:38；14 台严格完整日共 148 天，以质量掩码选取，不仅按起止日期截取。
- 不存在已发布的独立整户总表。统一称“固定监测面板总负荷”。
- 功率有效数值未改动，新增插补 0，所有发布值的上游填补身份为 unknown。天气 PPC 等未确认事项详见质量报告。

## 重新生成

在项目根目录用安装了 pandas、NumPy 的 Python 运行：

```powershell
python -m pip install -r task01/requirements.txt
python task01/run_task01.py
python task01/update_readmes.py --source-root .
python task01/verify_delivery.py
```

首次交付已实际运行，无需再次安装即可阅读产物。程序默认只读取 `data/raw/` 原件，覆盖生成版本目录与 `task01/reports/`，不修改下载原件。若要比较新规则，先修改数据版本和面板版本，保留旧版本再运行。执行环境及版本记录在 `processing_log.json`。`update_readmes.py` 是文档刷新程序，保留后续 README 的任务要求并刷新实际承接部分。

补充材料已在本地，重跑无需联网。仅在需要重新核验官方补充来源时运行 `python task01/fetch_support.py`；它只下载官方元数据和材料，不执行 Notebook 中的代码。

## 数据入口与下步

任务二从 `power_minute.csv.gz`、面板定义、缺口与质量开始发布正式小时/日/月统计。可以用任务一核验表对照，不能将不完整时段的有效累计值当完整电量。后续步骤已写入 [task02](../task02/README.md)、[task03](../task03/README.md)、[task04](../task04/README.md)、[task05](../task05/README.md)、[task06](../task06/README.md)。
