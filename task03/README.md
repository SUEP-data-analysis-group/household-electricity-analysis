# 任务三：工作日与休息日用电比较

状态：已完成。2026-11-13 根据验收意见补齐正式数据、复现输入和完整成果包，并承接 task02 修订版。派生版本 `task03_v1.1.0_20261113`；标准版本仍为 `cn_obee_v1_noimpute_v1.0.0`，固定 `panel13/v1.0.0`，北京时间。

## 版本怎么区分

| 版本阶段 | 状态与区别 |
| --- | --- |
| 2026-11-12 原始本地交付（未单独编号） | 23 个代码/来源/报告等文件，实际未附 data；此前未在 GitHub 发布，2026-11-13 才建立历史快照 |
| `task03_v1.1.0_20261113` | 当前推荐：10 CSV、清单、修订版 task02 输入、完整 ZIP；主要统计方法和结果保持一致 |

详细迭代与旧版快照见 [CHANGELOG.md](CHANGELOG.md)。主项目的数据统一放在根目录 `data/derived/`；ZIP 解压后则是自带 data 的独立包。本次上传同步更新了版本说明和 ZIP，未进一步改变正式 CSV。

`REQUIREMENTS.md` 是原任务要求，官方通知是来源原件，继续保留作参考；`reports/figure_contact_sheet.png` 是原交付的旧排版预览，当前图表以 `reports/figures/` 的 6 张图和新版报告为准。导入清单里的 `previous_import` 是旧输入记录，不是当前输入。

## 本次修订与结果入口

原提交只包含代码、来源和报告，本次已补齐 **10 个正式 CSV、派生清单及 3 个必要 task02 输入**。数据路径与运行布局已适配独立包和主项目，避免在桌面散落另一个 data 文件夹。

- [完整 HTML 报告](reports/task03_report.html)：单文件内嵌 6 张图和表格。
- [Markdown 报告](reports/task03_report.md)、[实际核验日志](reports/verify_task03.txt)。
- [正式结果目录](../data/derived/task03/)、[当前输入目录](../data/derived/task02/)、[来源与导入记录](sources/task02_import_manifest.json)。
- [完整 ZIP 交付说明](DELIVERY.md)。

输入来自 `task02_v1.1.0_20261113`，三个文件按字节复制并重新记录哈希；旧输入的记录在导入清单的 previous_import 中保留。小时主负荷使用严格 mean_power_kw，不完整小时留空，新增片段诊断量不参与本任务的完整日比较。

## 主要结论

| 控制同年月份的比较 | 工作类 kWh/日 | 休息类 kWh/日 | 休息类减工作类 | 相对差 | 7 天块 95% 区间 |
| --- | --- | --- | --- | --- | --- |
| 自然工作日 / 周末 | 7.648 | 8.168 | +0.520 | +6.80% | [-0.019, 1.069] |
| 实际工作日 / 休息日 | 7.688 | 8.121 | +0.434 | +5.64% | [-0.101, 1.052] |

两项区间均覆盖 0，不能断言休息日稳定更耗电。修订没有改变完整日样本、抽样方法或主要数值；仅解释这一个家庭监测设备在观测期内的关联。

## 任务一完成后的实际承接

### 本任务应交付

路径以项目/独立包根目录为起点，均在 `data/derived/task03/`。CSV 为 UTF-8 BOM，时间含 +08:00，空值留空。

| 文件 | 行数 | 用途 |
| --- | --- | --- |
| date_dimension.csv | 366 | 连续日期、质量、排除原因、两套日类型、月份、季节、假期与来源 |
| holiday_calendar_2021_2022.csv | 730 | 完整 2021/2022 历史日历，独立于电量质量 |
| day_type_support.csv | 52 | 两套口径按年月份、日类型的应有/完整/排除日数 |
| day_type_summary.csv | 4 | 两套分类的组统计、月份组成和区间 |
| hourly_day_type_profile.csv | 96 | 固定完整日组的原始小时曲线 |
| monthly_hourly_day_type_profile.csv | 1200 | 同年月份内的日类型小时曲线 |
| standardized_hourly_day_type_profile.csv | 48 | 两套口径的月份标准化小时曲线 |
| stratified_comparison.csv | 40 | 全样本、同月标准化、各月与各季节时期的比较 |
| bootstrap_sensitivity.csv | 16 | 两套口径、两种总体比较、4 种块长 |
| autocorrelation_diagnostics.csv | 10 | 原始及月内去均值的真实日历滞后相关性 |
| derivation_manifest.json | — | 规则、输入/输出哈希、运行环境、数量与 task01 对照状态 |

正式清单中的实际 rows 和 SHA-256 是核验依据。必要 task02 输入位于 `data/derived/task02/`，只附 daily_panel13.csv、hourly_panel13.csv、derivation_manifest.json；task02 清单列出的其他文件在完整 task02 包/主项目中，不要求为任务三重复附带。

## 日历、样本和统计规则

- 观测区间 `[2021-05-31,2022-06-01)`，366 天；352 个严格完整日、14 个不完整日保留在日历上，未新增插补，未剔除高负荷日。
- 国务院 2021/2022 年安排的 HTML、来源 URL、获取时间和哈希保存在 sources/。先建 730 日全年日历，再截取；调休上班覆盖自然周末。实际日类型指法定日历，不证明住户实际在家或休假。
- year_month 为基本层，两组用相同固定月份权重。2021-05 只有一个工作日，月度标准化排除该日后使用 351 日；全样本描述使用 352 日。
- 春夏秋冬按 3–5、6–8、9–11、12–2 月；冬季以十二月所在年命名，两端春季分开。
- 随机种子 42，2000 次月份内非循环日历块 bootstrap；主块长 7 日，并列检查 1、3、14 日。缺测位置保留；有效重复不足 95% 时不发布区间。
- 曲线每个小时使用同组完整日期。阴影是 25–75 分位范围，逐项 95% 区间不等于同时置信带。差值一律为休息类减工作类，相对差以工作类为基准。

## 复现、核验与完整打包

在本地主项目根目录运行下面命令。

```powershell
python -m pip install -r task03/requirements.txt
python task03/run_task03.py
python task03/verify_task03.py
python task03/package_task03.py
```

完整 ZIP 位于脚本旁的 `deliverables/`，另有 SHA-256 和解压复跑日志。ZIP 采用独立包布局，解压后代码、README、sources、reports、data 都在同一根目录，可运行 `python run_task03.py` 和 `python verify_task03.py`。

程序不联网下载。独立包没有标准分钟大表时，读取已归档的 task02 输入并检查内部一致性；合入完整主项目后，会额外核对标准面板哈希及 task01 小时/日核验表。当前运行模式与结果写入派生清单，不能把“未附带参考表”表述为“已经对照通过”。

合入主项目时将程序、配置、来源、报告放在 task03/，将本包 data/derived/task03/ 放在主项目同名位置；task02 的三个输入使用当前修订版。程序会自动识别这两种布局。

## 交给后续任务

- task04：使用 date_dimension.csv 的自然/实际日类型和排除信息挑选案例；仍以完整日分析峰谷。
- task06：只取事先已知的日期、星期、假期和调休字段，并按 notice_date 核验当时是否已公开；不要使用当日电量、覆盖率、完整性等事后字段作为日前已知特征。
- holiday_calendar_2021_2022.csv 独立于用电缺测，可单独复用。任务四和六统一引用本次数据与面板版本。
