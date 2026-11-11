# 任务二 按小时和日期统计用电量

状态：严格版统计已完成（2026-11-11），未启用任何插补。执行程序 [`run_task02.py`](run_task02.py)，参数 [`config.json`](config.json)，结果报告 [reports/task02_report.md](reports/task02_report.md)，派生表在 [`data/derived/task02/`](../data/derived/task02/)。输入为任务一锁定的标准分钟功率、质量表及固定面板定义。

## 任务一完成后的实际承接

标准版本 `cn_obee_v1_noimpute_v1.0.0`；主面板 `panel13/v1.0.0`；时区 `Asia/Shanghai`；功率 W。分析区间为 `[2021-05-31 00:00, 2022-06-01 00:00)`，共 366 个自然日。13 台联合有效率 96.8207%，严格完整小时 8,503 个、完整日 352 天。本次新增插补 0。

统一入口：标准表位于 `../data/standardized/cn_obee_v1_noimpute_v1.0.0/`；[面板定义](../task01/reports/panel_definition.json)、[数据字典](../task01/reports/data_dictionary.csv)、[字段和读取约定](../task01/DATA_CONTRACT.md)、[实际质量报告](../task01/reports/quality_report.md)。原件无需再次清洗。14 个不完整自然日仍保留在时间轴上，全部缺测不能写成 0。

### 按此顺序继续

1. 读取 `power_minute.csv.gz` 和 `panel_minute.csv.gz`，固定筛选 panel13；用 `panel_definition.json` 核对列清单。排除标准表末端 2022-06-01 00:00 的单条记录，仅在 [2021-05-31, 2022-06-01) 聚合。
2. 按左标签分钟近似积分，不跨缺口延长任何样本：有效分钟 `P_W/60000` kWh。小时要求 60/60 联合有效；日要求 24/24 严格小时。保存所有小时与日，完整指标为空的同时保留覆盖及排除原因。
3. 发布 `data/derived/task02/hourly_panel13.csv` 和 `daily_panel13.csv`，字段与任务一核验表对齐；逐设备小时表另存 `hourly_appliance.csv`，保证同区间分项可相加。
4. 与任务一的 [strict_hourly_check](../task01/reports/strict_hourly_check.csv) 和 [strict_daily_check](../task01/reports/strict_daily_check.csv) 对照，预期主面板 8503 个合格小时、352 个合格日。计数不一致先检查末端、面板或筛选规则，不修改标准数据凑数。
5. 典型 24 小时曲线主版统一使用 352 个完整日，再按月或季节分组，保存均值、分位数和 n_days。小时热图保留日历空缺并以独立颜色表示。
6. 月度表使用下方实际支持。2021-08 至 2022-05 可发布严格完整月电量；2021-05 是文件边界部分月，2021-06、07 有缺口，仅报告完整日样本均值/分布及有效时段累计，不命名为完整月电量。不要将 2021-05 与 2022-05 合并成一个“五月”月份样本而不披露。
7. 本次先执行严格版。若需短缺口估计，另起派生版本，先给出方法、比例和与严格版的电量/峰值差异，不覆盖标准表。

### 已知样本支持

| month | calendar_days | complete_days | joint_coverage | whole_month_in_file |
| --- | --- | --- | --- | --- |
| 2021-05 | 1 | 1 | 100.0000% | False |
| 2021-06 | 30 | 21 | 72.9769% | True |
| 2021-07 | 31 | 26 | 88.6156% | True |
| 2021-08 | 31 | 31 | 100.0000% | True |
| 2021-09 | 30 | 30 | 100.0000% | True |
| 2021-10 | 31 | 31 | 100.0000% | True |
| 2021-11 | 30 | 30 | 100.0000% | True |
| 2021-12 | 31 | 31 | 100.0000% | True |
| 2022-01 | 31 | 31 | 100.0000% | True |
| 2022-02 | 28 | 28 | 100.0000% | True |
| 2022-03 | 31 | 31 | 100.0000% | True |
| 2022-04 | 30 | 30 | 100.0000% | True |
| 2022-05 | 31 | 31 | 100.0000% | True |

### 本任务应交付

- `hourly_panel13.csv`：timestamp, panel_id, data_version, usable_minutes, coverage, hour_complete, valid_duration_energy_kwh, energy_kwh, mean_power_kw。
- `daily_panel13.csv`：date, panel_id, valid_hours, day_complete, coverage, valid_duration_energy_kwh, energy_kwh, mean_power_kw。
- `monthly_support.csv`：year_month, file_boundary_complete, calendar_days, complete_days, usable_minutes, coverage, complete_month_energy_kwh, complete_day_mean_energy_kwh；完整月指标对不合格月份为空。
- `typical_hourly_profile.csv`、覆盖热图和日/月解释报告；保存 `derivation_manifest.json`，记录输入哈希、版本、规则与排除数。

交给任务三的是带质量的日表和同组完整日小时曲线；任务四是严格小时表及分钟入口；任务五还需要逐设备明细；任务六使用连续小时表，保留无效标签。

## 仍需完成的预处理

1. 核实功率记录所代表的时间区间。用 `Σ(P_W × Δt_seconds) / 3,600,000` 计算 kWh；规则一分钟序列可用 `ΣP_W / 60,000`。源记录不是区间平均时，明确这是近似积分，不赋予超出数据粒度的精度。
2. 自然小时采用左闭右开区间，标签为起点。缺口不能通过与下一条有效记录的长时间间隔直接积分。分别保存每设备及主面板的有效时段电量、完整小时电量、有效分钟数和质量等级。
3. 主版小时电量要求面板联合覆盖 100%；日期要求 24 个合格小时。部分小时或日期保留，完整总电量为空。不能把缺失量忽略后称为小时或日总量，不能按覆盖率自动放大。
4. 明确 `energy_kwh` 与 `mean_power_kw`。完整一小时内二者数值可能相同，但物理量和单位不同；日均负荷应以完整日电量除以 24 小时。
5. 汇总时先确定比较口径。24 小时典型曲线主版使用同一组完整日期，各小时报告样本数；如另用“各小时所有有效记录”，标明样本集合不同。
6. 月度完整电量只有在整月时间范围和数据均完整时才发布。否则提供有效日统计、有效日数量和覆盖率；不能把有效日累计值称为全月电量。缺测集中在哪些时段或季节也要说明。
7. 如严格规则使样本过少，另建可选短缺口估计版。必须先声明适用设备、最长缺口、端点条件、方法、总填补比例；与严格版并列核对电量和高峰变化，不覆盖标准数据。开关型电器不默认线性插补。

## 输出与核验

输出小时表、日表、月度样本支持表及典型曲线数据。热力图中的缺测使用单独颜色，不画成 0。合格日期验证分钟积分、小时累加和日电量一致。

## 本次实际执行（2026-11-11）

| 项 | 结果 |
| --- | --- |
| 输入版本 | `cn_obee_v1_noimpute_v1.0.0`，主面板 `panel13/v1.0.0`，功率 W |
| 区间 | `[2021-05-31 00:00, 2022-06-01 00:00)`，366 天 / 8784 小时 / 527040 分钟 |
| 积分假设 | 左标签 60 s 矩形近似，有效分钟 `P_W/60000` kWh；缺口不积分、不延长、不按覆盖率放大 |
| 有效分钟 | 510284 可用，16756 不可用（13 台未全部可用），占比 3.18% |
| 完整小时 | **8503**，与任务一核验表逐行一致 |
| 完整日 | **352** 天；14 个不完整日保留在时间轴并标记，不当作低用电日 |
| 完整周 | **48** 个（周一起始 7/7 完整日），不完整周 5 个；完整周电量合计 2624.3 kWh，周均 54.7 kWh |
| 完整日合计 | 2739.60 kWh，日均 7.78 kWh，中位 6.77 kWh |
| 日均负荷 | `mean_power_kw` 完整日均值 0.3243 kW，最大 1.9907 kW（kW 是功率，与 kWh 电量不同量） |
| 典型曲线 | 最高在 22 时（0.500 kWh），最低在 4 时（0.213 kWh） |
| 月度支持 | 2021-08 至 2022-05 共 10 个完整月可发布完整月电量；2021-05（文件边界 1 天）、2021-06（21/30）、2021-07（26/31）只报告完整日样本，不命名为完整月电量 |
| 插补 | 未启用短缺口估计版，新增插补 0 |
| 分项可加性 | 8503 个完整小时中，13 台分项之和与面板电量最大绝对差 1.3e-15 kWh |

核验：完整小时数、完整日数、逐小时 `usable_minutes` 与电量均与 `task01/reports/strict_hourly_check.csv`、`strict_daily_check.csv` 对齐（电量最大差 6.7e-16）。月度完整天数与覆盖度与任务一已公布月度表一致（2021-06 为 21 天 / 72.9769%，2021-07 为 26 天 / 88.6156%）。

说明：作业要求第 4 条要求「整理日、周、月统计」，而本 README 原先的交付清单只列到小时/日/月，因此本次补充 `weekly_support.csv`（周一起始，周完整 = 7/7 完整日）。

产出：`hourly_panel13.csv`、`daily_panel13.csv`、`weekly_support.csv`、`monthly_support.csv`、`typical_hourly_profile.csv`、`hourly_appliance.csv`、`derivation_manifest.json`，图见 `reports/figures/`。

复现：

```powershell
python task02/run_task02.py
```

独立核验（另用 resample 路径从原始分钟表重算，与主程序算法不同，只读不写派生表）：

```powershell
python task02/verify_task02.py
```

核验输出见 `reports/verify_task02.txt`，覆盖分钟行数、逐小时完整标记与电量、逐日完整标记与电量、典型曲线、分项可加性抽查、月度完整天数，并与 `task01/reports/` 两张表逐行比对，退出码 0 表示全部通过。
