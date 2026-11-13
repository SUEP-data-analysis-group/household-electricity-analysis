# 任务三：比较工作日与休息日（已完成）

本任务承接同伴 `E:\task02` 的正式日表与小时表，完成自然星期、法定节假日与调休两套日类型比较。原任务要求保存在 [REQUIREMENTS.md](REQUIREMENTS.md)。**只分析固定 panel13 的 13 台监测设备，不等同于整户总表。**

## 先看结果

- [完整报告 HTML](reports/task03_report.html)：单文件含全部表格和 6 张图，浏览器直接打开，无需 Python。
- [完整报告 Markdown](reports/task03_report.md)：便于合并小组总报告。
- [核验日志](reports/verify_task03.txt)：独立核验程序的实际运行结果。
- [派生结果](../data/derived/task03/)：日期标签、样本支持、分层统计、曲线及来源清单。

主要结果（均为休息类减工作类，控制同年月份组成）：

| 口径 | 工作类均值 kWh/日 | 休息类均值 kWh/日 | 差值 kWh/日 | 相对差 | 7 天块 95% 区间 |
| --- | --- | --- | --- | --- | --- |
| 自然工作日 / 周末 | 7.648 | 8.168 | +0.520 | +6.80% | [-0.019, 1.069] |
| 实际工作日 / 休息日 | 7.688 | 8.121 | +0.434 | +5.64% | [-0.101, 1.052] |

两项主比较区间都包含 0，不能断言休息日稳定更耗电。1、3、7、14 天块长敏感性分析的主比较也均包含 0。小时平均曲线均在晚间 22 时附近达到高点；这些是本家庭观测期的关联，不是因果结论。

## 输入、日历与统计规则

- 标准版本 `cn_obee_v1_noimpute_v1.0.0`；`panel13/v1.0.0`；北京时间 `Asia/Shanghai`。
- 日期范围 `[2021-05-31, 2022-06-01)`，366 天、352 个严格完整日、14 个排除日。完整日要求 24/24 合格小时，缺测日保留，新增插补为 0。
- 同伴输入的 3 个文件按原字节复制到 `data/derived/task02/`，其余 task02 成果仍在同伴原成果包中。导入来源与哈希见 `sources/task02_import_manifest.json`。在完整仓库运行时另与 task01 小时、日核验表比较，并核验标准分钟文件 SHA-256；成果包复现仅需附带的 task02 输入。
- 国务院 2021、2022 年通知原文 HTML、URL、获取时间和哈希均在 `sources/`，离线可复核。全年日历先生成 730 日再截取；调休上班覆盖周末默认值。完整放假区间不等于每一天都是法定节日本日，也不代表住户本人实际休假。
- 同年月份是基本层；主比较将有两类日期的 12 个月按完整日数固定加权，两类使用相同权重。2021-05 只有 1 日，不参与月度标准化，主比较 351 日；原始全样本描述用 352 日。
- 气象季节为 3–5 春、6–8 夏、9–11 秋、12–2 冬；两个春季边界分开，冬季按 12 月所在年命名。2021-06/07 缺测集中，未声称这些月份完整。
- 种子 42，2000 次年月份内非循环日历块 bootstrap，主块长 7 天，并列检查 1、3、14 天。缺测保留在原日历位置；不将分钟当作独立样本。报告相关性、端点权重偏差、小样本及探索性区间限制。
- 原始、月内及月份标准化的 24 小时曲线均使用固定完整日期集合；原始曲线的阴影是四分位范围，不能当作置信带。

## 复现

在项目根目录运行，建议 Python 3.9 或以上：

```bash
python -m pip install -r task03/requirements.txt
python task03/run_task03.py
python task03/verify_task03.py
```

本机已使用 `E:\miniconda3\python.exe`（Python 3.8.16 / pandas 2.0.3 / NumPy 1.24.4 / Matplotlib 3.7.5）实际运行通过。若默认 `python` 指向缺少依赖的环境，可在 PowerShell 使用：

```powershell
& 'E:\miniconda3\python.exe' task03/run_task03.py
& 'E:\miniconda3\python.exe' task03/verify_task03.py
```

也可显式传入同伴结果目录：

```powershell
python task03/run_task03.py --task02-dir 'E:\task02\data\derived\task02'
```

核验程序默认校验附带的 `data/derived/task02/` 输入。通常直接用默认路径，便于和其他成员共享。主程序会重生成 task03 结果、报告和图，不修改同伴的原始成果。

## 正式派生表

均在 `data/derived/task03/`；UTF-8 BOM CSV，时间含 `+08:00`，空值留空，数值不主动四舍五入。

| 文件 | 内容 |
| --- | --- |
| `date_dimension.csv` | 366 日；完整性、排除原因、两套日类型、月份、季节、假期与调休、来源 |
| `holiday_calendar_2021_2022.csv` | 两个完整年份 730 日历史日历，独立于用电质量 |
| `day_type_support.csv` | 两套口径逐月应有日、完整日、排除数与排除率 |
| `day_type_summary.csv` | 组均值、中位数、日数、月份组成、原始组差、区间与抽样参数 |
| `hourly_day_type_profile.csv` | 352 个完整日的 24 小时原始均值、中位数、四分位曲线 |
| `monthly_hourly_day_type_profile.csv` | 同年月份内按日类型的小时曲线和日数 |
| `standardized_hourly_day_type_profile.csv` | 同月权重标准化曲线与逐小时差值，24h 积分与主日电量差一致 |
| `stratified_comparison.csv` | 全样本、同月标准化、逐月、独立季节时期差值、相对差及区间 |
| `bootstrap_sensitivity.csv` | 两套口径、两种总体比较、四个块长共 16 行 |
| `autocorrelation_diagnostics.csv` | 原始及月内去均值日电量的真实日历 lag 相关性 |
| `derivation_manifest.json` | 配置、输入及结果哈希、运行环境、数量、规则与上游核验结果 |

`difference_kwh` 一律为休息类减工作类；`relative_difference_pct` 以工作类为基准；`ci_low_kwh/ci_high_kwh` 是组差区间，`mean_ci_*` 是组均值区间。`weekday` 为 0=周一至 6=周日。`holiday_name` 指放假区间，调休对应假期在 `makeup_for_holiday`。`status=missing_day_type` 不计算差值；bootstrap 有效次数少于 95% 则不发布区间。月度权重、样本组成等 JSON 字段读取后可用 `json.loads()` 解析。

## 交给后续任务

task04 可接 `date_dimension.csv` 做实际日类型案例选择。task06 仅取事先已知的日期、星期、法定假期和调休日历字段，并核验通知发布日期；不能把当日电量、完整性、覆盖率等事后字段当作日前已知信息。完整历史日历文件可独立复用。

交付包含 task03 源码、配置、归档来源、报告、6 张图、全部派生表及必要 task02 输入；解压后即可在含依赖的 Python 环境中复现，不需要原始分钟大表。
