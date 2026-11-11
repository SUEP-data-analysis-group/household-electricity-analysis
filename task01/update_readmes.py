"""Publish the audited facts and actionable task handoffs into the project READMEs."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / 'task01/reports'
S = ROOT / 'data/standardized/cn_obee_v1_noimpute_v1.0.0'

def load(name):
    return pd.read_csv(R / name)

def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + '\n', encoding='utf-8')

def table(frame):
    def fmt(x):
        if pd.isna(x): return ''
        return str(x).replace('|', '/')
    cols = list(frame.columns)
    return '| ' + ' | '.join(cols) + ' |\n| ' + ' | '.join(['---']*len(cols)) + ' |\n' + '\n'.join('| ' + ' | '.join(fmt(x) for x in row) + ' |' for row in frame.itertuples(index=False, name=None))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    source = args.source_root
    summary = json.loads((R / 'audit_summary.json').read_text(encoding='utf-8'))
    overall = load('coverage_overall.csv').set_index('entity')
    month = load('coverage_monthly.csv')
    daily = load('strict_daily_check.csv')
    p13 = daily[daily.panel_id == 'panel13'].copy()
    p14 = daily[daily.panel_id == 'panel14'].copy()
    split = load('forecast_split_quality.csv')
    qc = load('qc_summary.csv')
    gaps = load('gap_report.csv')
    power_gaps = gaps[gaps.source_file == 'Power.csv']
    main_gaps = power_gaps[power_gaps.entity == 'panel13']
    main_month = month[month.entity == 'panel13'].copy()
    p13['month'] = p13.date.str[:7]
    supports = p13.groupby('month').agg(calendar_days=('date','size'), complete_days=('day_complete','sum')).reset_index()
    supports['joint_coverage'] = main_month.usable_rate.map(lambda x: f'{x:.4%}').to_numpy()
    supports['whole_month_in_file'] = main_month.file_boundary_complete.to_numpy()
    s = summary['split']
    good14 = p14[p14.day_complete]
    panel_body = ', '.join(json.loads((R/'panel_definition.json').read_text(encoding='utf-8'))['panels'][0]['devices'])
    pass_count = int(load('acceptance_checks.csv').passed.sum())
    headline = f"标准版本 `cn_obee_v1_noimpute_v1.0.0`；主面板 `panel13/v1.0.0`；时区 `Asia/Shanghai`；功率 W。分析区间为 `[2021-05-31 00:00, 2022-06-01 00:00)`，共 {summary['calendar_days']} 个自然日。13 台联合有效率 {summary['panel_coverage']['panel13']:.4%}，严格完整小时 {summary['complete_hour_counts']['panel13']:,} 个、完整日 {summary['complete_day_counts']['panel13']} 天。本次新增插补 0。"
    quality_report = f'''# 任务一实际质量报告

审计日期：2026-11-10。统计来自本项目 CSV 逐行审计，不引用论文中的覆盖率作为运行结果。

{headline}

## 来源、边界与计量

- 原发布版本：CN-OBEE Figshare 条目 v1，DOI `10.6084/m9.figshare.23686476.v1`；集合 v1：`10.6084/m9.figshare.c.6742536.v1`。
- 下载归档 SHA-256：`04df16a1ccb67714d0ad4b310188427509cd7aee8d30a348abccf86fbe5884b0`。压缩包及 8 个 CSV 的 SHA-256 核验通过，压缩包 CRC 通过。下载时间及各文件哈希见[审计来源清单](source_manifest_audited.json)，原清单保留不覆盖。
- 7 个分钟文件均为 527,041 行，天气为 8,785 行。首条 2021-05-31 00:00，末条 2022-06-01 00:00，首尾均在源文件中。分钟数据有 527,040 个分析位置，文件覆盖 366 个完整自然日，区别于论文概述的 365 日。
- 末端的 2022-06-01 00:00 单条记录保留在所有标准表中；不纳入完整小时、日、月和预测窗口。各文件未发现时间解析失败、重复时间、冲突、乱序、缺行或偏离粒度的时间。值缺测仍大量存在，不能把“无缺行”解释为“无缺测”。
- 未发布独立整户总表。主目标名称为“固定监测面板总负荷”，不包括未监测设备。13 台固定列表：`{panel_body}`。电饭煲仅用于 14 台共同有效补充分析。

## 设备覆盖

分母为 527,040 个分析分钟；最后单条末端记录不进入此表。发布值非空率与可用率在本次功率审计中相同；不是原始实测率。作者上游填补无法逐点识别，统一写 `unknown`。

{table(overall.reset_index()[['entity','expected_minutes','usable_minutes','published_nonempty_rate','usable_rate','longest_gap_minutes','zero_minutes']])}

## 月度支持

{table(supports)}

2021 年 6、7 月联合覆盖分别只有 72.98% 和 88.62%，低于 95%。主面板满足全分析跨度的 95% 准入参考，并不代表这两个月适合发布整月电量。2021-05 仅有 5 月 31 日，属于月边界不完整；2021-08 至 2022-05 的整月均有完整数据。完整日主分析为 352 天，14 天不完整或全缺失；不能插补后声称全年完整。跨年、月份和季节比较须同时报告实际支持。

## 缺口、异常与来源不确定性

- 主面板有 {len(main_gaps)} 段缺口，共 {int(overall.loc['panel13','expected_minutes'] - overall.loc['panel13','usable_minutes']):,} 分钟，最长 {int(overall.loc['panel13','longest_gap_minutes']):,} 分钟。[缺口报告](gap_report.csv)保留所有变量和两个面板的起止、长度及短长分组。源变量缺口覆盖全部发布位置（含末端单条），面板缺口限定在分析区间；与 coverage_* 对照时须先截取同一区间。
- 电饭煲最后共同有效分钟为 2021-11-09 18:38，14 台严格完整日共 {summary['complete_day_counts']['panel14']} 天。14 台有效分钟为非连续集合，不把最早和最晚日期之间全部标为完整。
- 功率未发现负值、非数值、非有限值或超出论文 Table 2 对应量程的值。本次未修改任何已发布功率数值或补入功率数值。全部保存后的 7,378,574 个设备位置均与源数值逐一比对，NaN 位置一致。
- `long_constant_review` 连续常值阈值为 1,440 分钟，仅作回顾性检查。发布数据已经过事件上报后的前向保持，常值和零值不能直接判为卡死。近量程阈值为对应传感器量程的 90%，只标记不删除，不使用全期统计分位数作为预测清洗阈值。
- 空调 3 的最大值只有 0.71 W，应在任务五注明“该设备在发布值中未呈现明显运行功率”；无法据此证明设备坏了或住户从未使用。各设备常值标记数、范围、零值和缺失数量见[QC 汇总](qc_summary.csv)。
- 天气风向包含 `PPC`，次数及处理见[未解决类别](unresolved_categories.csv)。`wind_direction_raw` 原样保留；`wind_direction_deg` 对无法解析的记号留空，没有猜成 0°。这是数值投影不可用，不是把源记号删除。
- 窗状态可能含 0 与 1 之间的分钟平均值，保留并标记；不能把它当作全天开窗比例或按未知阈值还原事件。运动 0 仅表示发布分钟未检测到运动。
- 主卧环境缺测及其他辅助缺测独立保留，不删除同一时刻的功率。[辅助变量月度覆盖](auxiliary_coverage_monthly.csv)用于决定是否可做特定关联分析。

## 积分与数值核验

[论文 Methods 与 Table 2](https://doi.org/10.1038/s41597-023-02891-9)说明：功率为 W，分钟记录由同分钟上报均值和作者的前向保持构成。采用左端标签 `[t,t+1min)`，在有效分钟上按 `sum(P_W)/60000` 近似得到 kWh。该近似不等同于结算电表；天气小时值的准确平均区间尚未确认，不参与本次能量积分。

小时必须 60 个分钟均为面板联合有效，日必须 24 个小时合格。`valid_duration_energy_kwh` 仅累加有效分钟，`energy_kwh` 只对完整时段有值；全缺失时两者均为空，不自动按覆盖率放大。严格核验表仅为任务一的交叉核验产物，任务二仍需正式发布自己的派生表与统计图。

预设绝对容差 1e-8 kWh、相对容差 1e-10，检查使用较严格的绝对容差。{pass_count} 项实际验收检查通过，详见[验收结果](acceptance_checks.csv)。包括来源哈希、时间网格、面板缺失规则、分设备与面板小时积分、分钟到小时到日累计、保存后功率和时区往返核对。

## 冻结的预测日历

| 分段 | 左闭起点 | 右开终点 |
| --- | --- | --- |
| 训练 | 2021-05-31 00:00 | 2022-03-09 00:00 |
| 验证 28 天 | 2022-03-09 00:00 | 2022-04-06 00:00 |
| 测试 56 天 | 2022-04-06 00:00 | 2022-06-01 00:00 |

E = 2022-06-01 00:00+08:00。以每日 00:00 为起点，检查起点之前 168 个严格小时及未来 24 个严格目标小时。首个仅按文件历史可行的起点为 2021-06-07，缺测会进一步排除日期。

{table(split)}

该表 `eligible_origins` 对应保守完整历史规则的候选样本数，尚未构建最终模型特征，因此不能叫模型最终评分数。验证与测试的完整历史及目标支持已经核验；若任务六增添其他特征，须再次报告排除并冻结共同评分掩码。逐日起点和原因见[预测起点质量](forecast_origin_quality.csv)，边界见[切分清单](split_manifest.json)。

## 后续任务支持与限制

任务二至五可以在严格完整样本上继续。任务六有连续 4 周验证、8 周测试及至少 7 天过去上下文，满足日历跨度要求。主测试只覆盖 2022 年春季至初夏，不能代表全年跨季节泛化。没有带发布时间的历史天气预报，也没有实测发布延迟记录；00:00 能拿到前一小时数据属于任务六必须披露的可用性假设。

所有任务引用同一数据版本、面板、时区与单位。不同的任务过滤或估计仅在 `data/derived/taskXX/` 新建版本；不要覆盖标准数据或原发布数据。
'''
    write(R/'quality_report.md', quality_report)

    readme1 = f'''# 任务一 建立可信的用电数据

状态：已完成真实 CSV 审计、无新增插补标准化、面板选择、质量验收和预测日历冻结。完成日期：2026-11-10。原实施方案保留在 [PLAN.md](PLAN.md)。总体依据见[总 README](../README.md)。

{headline}

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

- 13 台联合覆盖 {summary['panel_coverage']['panel13']:.4%}，14 台联合覆盖 {summary['panel_coverage']['panel14']:.4%}。不得将二者拼接为可变设备总负荷。
- 文件边界支持 366 天，13 台严格完整日 {summary['complete_day_counts']['panel13']} 天；其余 14 天保留缺口。2021-06、07 不支持完整月电量，2021-05 仅有 1 天。
- 电饭煲最后共同有效时刻为 2021-11-09 18:38；14 台严格完整日共 {summary['complete_day_counts']['panel14']} 天，以质量掩码选取，不仅按起止日期截取。
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
'''
    write(ROOT/'task01/README.md', readme1)

    contract = '''# 标准数据与质量字段约定

版本 `cn_obee_v1_noimpute_v1.0.0`，面板 `v1.0.0`。标准表在 `data/standardized/cn_obee_v1_noimpute_v1.0.0/`，辅助质量表在其 `auxiliary_quality/`，电器质量表在其 `appliance_quality/`。

## 文件与字段

| 文件 | 一行表示 | 主要字段 |
| --- | --- | --- |
| power_minute.csv.gz | 一分钟，含末端单条 | timestamp, source_file, source_row_id, source_time, source_present，以及 14 个 *_w 设备列 |
| panel_minute.csv.gz | 一个面板的一分钟，两个面板纵向排列 | timestamp, panel_id, panel_version, n_expected, n_usable, panel_complete, panel_power_w, available_sum_w |
| appliance_quality/设备名.csv.gz | 一设备一分钟 | timestamp, appliance_id, source_file, source_row_id, source_time, source_token, source_value, usable_value, source_present, is_usable, qc_bits, qc_flags, upstream_fill_status, is_new_imputed |
| 各房间.csv.gz | 房间一分钟，独立时间轴 | 来源字段、温湿度、气压、窗状态和 motion_detected，具体见数据字典 |
| outdoor_weather.csv.gz | 室外一小时 | 来源字段、天气变量，wind_direction_raw 原记号、wind_direction_deg 数值投影 |
| auxiliary_quality/同名文件 | 同源时间点的逐变量标记 | source_row_id, 各变量_qc_bits, upstream_fill_status, is_new_imputed |
| task01/reports/coverage_* | 设备或面板在指定区间的覆盖 | expected_minutes_in_span, full_calendar_expected_minutes, file_boundary_complete, usable_minutes, published_nonempty_rate, usable_rate, longest_gap_minutes, strict_period_complete, exclusion_reason |
| strict_hourly_check.csv | 面板的一小时核验 | timestamp, panel_id, usable_minutes, expected_minutes, coverage, hour_complete, valid_duration_energy_kwh, energy_kwh, mean_power_kw |
| strict_daily_check.csv | 面板的一日核验 | date, panel_id, valid_hours, expected_hours, day_complete, valid_minutes, coverage, valid_duration_energy_kwh, energy_kwh, mean_power_kw |

source_row_id 是包含表头在内的物理 CSV 行号（首条数据=2），不是 Python 从 0 开始的索引。source_token 逐字保留源单元格字符串，source_value 是数值解析结果，usable_value 是 QC 后数值。source_present 表示源时间行存在，即使该设备值为空也为 True；is_usable 指设备数值可用。源原件保留全部字节，可据 source_file/source_row_id 找回任何房间原值。

## 编码、精度与时间

CSV 为严格 UTF-8，逗号分隔，一行表头；大表用 gzip 压缩，pandas 自动识别。数值空值编码为空单元格，绝不以 0 代替；source_token 与 wind_direction_raw 是字符串，读取时用 keep_default_na=False 才能逐字保留 `nan` 和空串。数值为 float64，写出不主动舍入；需要严格比对时用 float_precision='round_trip'。布尔列为 True/False。

timestamp/date 写出包含 +08:00 偏移。读回后显式 tz_convert('Asia/Shanghai')。源 source_time 为无偏移本地字符串，仅用 tz_localize，不先当 UTC。所有小时标签为区间起点、左闭右开。

功率 W；功率除以 1000 才是 kW。对 60 个有效分钟积分 sum(P_W)/60000 得到近似 kWh。完整小时 E_kWh 与均值 kW 的数值可能相同，但单位与物理量不同。室内气压 Pa 与室外 hPa 分列保留，若后续比较，另建有换算记录的变量。

## QC 位掩码

| bit | 含义 | 数值处理 |
| --- | --- | --- |
| 1 | source_missing | 源缺失保持为空 |
| 2 | grid_missing | 本版没有缺行，预留码，禁止假称已填补 |
| 4 | numeric_invalid | 无法解析/非有限数值的 usable_value 为空 |
| 8 | physical_range_invalid | 有明确物理边界的错误转为空，原值和原因保留 |
| 16 | near_sensor_limit_review | 功率达到量程 90%，保留数值 |
| 32 | long_constant_review | 常值连续至少 1440 分钟，保留数值 |
| 64 | fractional_window_state_review | 窗状态分钟均值在 (0,1)，保留数值 |
| 128 | unresolved_category | 风向 PPC 等原记号保留，数值投影不可用 |

qc_bits 可组合。位 16/32/64 不使数值不可用。常值长度使用全段回顾性信息，只用于审计，不直接作为预测输入、删值依据或未来已知特征。upstream_fill_status=unknown 表示不能识别作者逐点填补；is_new_imputed=False 表示本次未新增插补。

## 面板、区间与覆盖分母

主面板 panel13 固定排除 rice_cooker_w；panel14 保留全部 14 台。必要设备缺一个，panel_power_w 就为空。available_sum_w 仅为诊断，当全部设备缺失时也为空。

覆盖与严格核验分析区间为 [2021-05-31,2022-06-01)，527040 分钟、8784 小时、366 日。标准表另保留 2022-06-01 00:00 单条，不把它当作完整日期。coverage_* 的月份、年份边界同时报告区间内分母与完整自然月/年分母，避免把局部月份 100% 误读成整月完整。

gap_report 中源变量缺口覆盖全部发布位置（含末端单条），面板缺口限定在分析区间。qc_summary 也使用全部源位置；coverage_* 使用完整日历分析区间。核对设备缺测总数时先裁切到同一范围，不能把末端缺测的一条误认为计数错误。

coverage_overall、hourly、daily、monthly、yearly 均含 14 个设备和两个面板，设备 valid_rate 不能代替面板联合覆盖。published_nonempty_rate 不是原始实测率。长缺口按实际位置报告，不删除后重新拼接时间。

## 读取示例（在项目根目录）

```python
from pathlib import Path
import pandas as pd

root = Path('.')
std = root / 'data/standardized/cn_obee_v1_noimpute_v1.0.0'
p = pd.read_csv(std / 'power_minute.csv.gz', float_precision='round_trip')
p['timestamp'] = pd.to_datetime(p['timestamp']).dt.tz_convert('Asia/Shanghai')
panel = pd.read_csv(std / 'panel_minute.csv.gz')
panel = panel.loc[panel['panel_id'].eq('panel13')].copy()
panel['timestamp'] = pd.to_datetime(panel['timestamp']).dt.tz_convert('Asia/Shanghai')
panel = panel.set_index('timestamp').sort_index()
panel = panel.loc[panel.index < pd.Timestamp('2022-06-01', tz='Asia/Shanghai')]
assert panel.index.is_unique
# 仍保留全部缺口；不要在这里 dropna 后压缩日历。
```
'''
    write(ROOT/'task01/DATA_CONTRACT.md', contract)

    common = f'''## 任务一完成后的实际承接

{headline}

统一入口：标准表位于 `../data/standardized/cn_obee_v1_noimpute_v1.0.0/`；[面板定义](../task01/reports/panel_definition.json)、[数据字典](../task01/reports/data_dictionary.csv)、[字段和读取约定](../task01/DATA_CONTRACT.md)、[实际质量报告](../task01/reports/quality_report.md)。原件无需再次清洗。14 个不完整自然日仍保留在时间轴上，全部缺测不能写成 0。

'''
    specifics = {
    2: f'''### 按此顺序继续

1. 读取 `power_minute.csv.gz` 和 `panel_minute.csv.gz`，固定筛选 panel13；用 `panel_definition.json` 核对列清单。排除标准表末端 2022-06-01 00:00 的单条记录，仅在 [2021-05-31, 2022-06-01) 聚合。
2. 按左标签分钟近似积分，不跨缺口延长任何样本：有效分钟 `P_W/60000` kWh。小时要求 60/60 联合有效；日要求 24/24 严格小时。保存所有小时与日，完整指标为空的同时保留覆盖及排除原因。
3. 发布 `data/derived/task02/hourly_panel13.csv` 和 `daily_panel13.csv`，字段与任务一核验表对齐；逐设备小时表另存 `hourly_appliance.csv`，保证同区间分项可相加。
4. 与任务一的 [strict_hourly_check](../task01/reports/strict_hourly_check.csv) 和 [strict_daily_check](../task01/reports/strict_daily_check.csv) 对照，预期主面板 {summary['complete_hour_counts']['panel13']} 个合格小时、352 个合格日。计数不一致先检查末端、面板或筛选规则，不修改标准数据凑数。
5. 典型 24 小时曲线主版统一使用 352 个完整日，再按月或季节分组，保存均值、分位数和 n_days。小时热图保留日历空缺并以独立颜色表示。
6. 月度表使用下方实际支持。2021-08 至 2022-05 可发布严格完整月电量；2021-05 是文件边界部分月，2021-06、07 有缺口，仅报告完整日样本均值/分布及有效时段累计，不命名为完整月电量。不要将 2021-05 与 2022-05 合并成一个“五月”月份样本而不披露。
7. 本次先执行严格版。若需短缺口估计，另起派生版本，先给出方法、比例和与严格版的电量/峰值差异，不覆盖标准表。

### 已知样本支持

{table(supports)}

### 本任务应交付

- `hourly_panel13.csv`：timestamp, panel_id, data_version, usable_minutes, coverage, hour_complete, valid_duration_energy_kwh, energy_kwh, mean_power_kw。
- `daily_panel13.csv`：date, panel_id, valid_hours, day_complete, coverage, valid_duration_energy_kwh, energy_kwh, mean_power_kw。
- `monthly_support.csv`：year_month, file_boundary_complete, calendar_days, complete_days, usable_minutes, coverage, complete_month_energy_kwh, complete_day_mean_energy_kwh；完整月指标对不合格月份为空。
- `typical_hourly_profile.csv`、覆盖热图和日/月解释报告；保存 `derivation_manifest.json`，记录输入哈希、版本、规则与排除数。

交给任务三的是带质量的日表和同组完整日小时曲线；任务四是严格小时表及分钟入口；任务五还需要逐设备明细；任务六使用连续小时表，保留无效标签。

''',
    3: '''### 按此顺序继续

1. 先完成任务二 `data/derived/task02/daily_panel13.csv`、`hourly_panel13.csv`。从 366 天完整日期轴建立 `date_dimension.csv`，与日表左连接，保留 14 个不合格日和排除原因。主分析仅用 352 个严格日。
2. 数据年份是 **2021 和 2022**。先按自然星期生成 weekday/weekend；再依据[2021 年国务院办公厅安排](https://app.www.gov.cn/govdata/gov/202011/26/465359/article.html)与[2022 年安排](https://app.www.gov.cn/govdata/gov/202110/25/477434/article.html)建立 actual_workday/actual_restday。保存具体假期与调休表、原来源和获取时间。本次仅提供来源，尚未生成最终日期标签。
3. 官方日历应先覆盖完整年份，再截取分析区间，以便处理跨年元旦；调休上班覆盖周末默认值。字段至少 date, year_month, season, weekday, natural_day_type, actual_day_type, holiday_name, is_makeup_workday, source_url。
4. 两种日类型分别比较日电量和 24 小时曲线。每组列出完整/排除天数与月份组成；当前 2021-06、07 缺测集中，先按同月比较，再给全样本描述。
5. 若按气象季节，预先声明 3–5 春、6–8 夏、9–11 秋、12–2 冬。2021-05 只有一天，不把它当独立完整春季；同一春季跨数据端点的问题须在分层方案中解释。年月份是基本匹配层，不能只按月份数字混合年份。
6. 先报告均值差、相对差及日数，再按日/连续日块 bootstrap。建议固定随机种子 42、2000 次作为初始配置；块长及敏感性应依据相关性审查，不预先声称置信区间可靠。
7. 用同一组日期计算每小时两类日曲线；避免每个小时随意换样本。比较大量小时/月时说明探索性或多重检验处理。

### 本任务应交付

保存至 `data/derived/task03/`：`date_dimension.csv`、`holiday_calendar_2021_2022.csv`、`day_type_support.csv`、`day_type_summary.csv`、`hourly_day_type_profile.csv`、`stratified_comparison.csv` 和 `derivation_manifest.json`。summary 应同时包含自然星期及实际日类型，附 n_days、排除数、月份组成、差值、相对差、区间及抽样参数。

验收：日期键唯一且共 366 行；完整日共 352 行；自然日类型与实际日类型分开；节假日/调休有可追溯来源；不把分钟记录当独立样本。将日期标签交给任务四案例选择及任务六日历特征。

''',
    4: '''### 按此顺序继续

1. 接任务二的 `hourly_panel13.csv` 和 `daily_panel13.csv`，用 day_complete 明确选择 352 个完整日；保留其余 14 日的质量清单。输入目标为 mean_power_kw。
2. 每日计算 peak_kw、valley_kw、peak_valley_kw、mean_kw、load_factor。负荷率分母为日峰值，分母为 0 时为空。分钟峰值另从标准分钟面板生成 minute_record_peak_w，不与小时均值峰混合。
3. 以同一 float64 读数相等判断并列，不先把小时负荷四舍五入再取峰。另输出长表 `daily_extrema_times.csv`：date, kind, hour_start, tied_count, weight=1/tied_count。峰谷统计保留全部并列时刻。
4. 连续小时索引上用 shift(1) 计算变化，并同时检查时间差等于 1h 且两个 hour_complete 均为 True。缺口两侧不相减。可单列跨午夜变化，不把它误称同日内变化。
5. 若描述“大变化”，先声明阈值。例如全期描述可报告分位数，但作为任务六特征或高峰阈值的参数只能在训练区间 [2021-05-31,2022-03-09) 拟合，写清单位与用途。
6. 案例规则先落盘：在同一年月份的严格自然工作日/周末中选接近各组日电量中位数的日期；高负荷案例按预先声明分位数选择。使用实际休息日标签时接任务三，若标签尚未完成可先用自然星期并注明。并列候选用最早日期作为可复现选择。
7. 为选中日期从标准分钟表抽取完整设备曲线，记录 panel13、峰小时及峰分钟。与任务五共用 `case_manifest.csv`，保留异常标记，不进行平滑或削峰。

### 本任务应交付

保存至 `data/derived/task04/`：`daily_peak_valley.csv`、`daily_extrema_times.csv`、`peak_hour_frequency.csv`、`hourly_changes.csv`、`case_manifest.csv` 和 `derivation_manifest.json`；另附案例图及分钟峰/小时峰对照。

验收：主日指标恰有 352 个完整日；每个日期每种并列极值的 weight 之和为 1；hourly_changes 的有效行均确实相隔 1h；案例设备范围和任务五一致；负荷率在非零峰值时满足 0–1。

''',
    5: f'''### 按此顺序继续

1. 同时读取标准 `power_minute.csv.gz`、`appliance_quality/`、`panel_minute.csv.gz` 及 `panel_definition.json`。主贡献表固定 panel13，用与任务二相同的 352 个严格完整日，或另行明确的全体共同有效分钟集合。两种时间口径分开命名。
2. 主面板 13 台共同有效分钟为 {int(overall.loc['panel13','usable_minutes']):,}；全分钟贡献如采用这个集合，分子和分母都使用这一集合。若用完整日口径，应以这 352 天重新计算有效分钟数，不直接借用前一分母。
3. 对共同有效集合各设备积分，贡献=设备 kWh/同集合 panel13 kWh。保留小数精度，贡献和在容差内应为 1。面板电量为 0 的区间占比为空。
4. 电饭煲补充表必须切换为 panel14 并对全体 14 台重新计算。panel14 共 {int(overall.loc['panel14','usable_minutes']):,} 个共同有效分钟、{summary['complete_day_counts']['panel14']} 个严格完整日，最后共同有效为 2021-11-09 18:38。有效集合非连续，不能只截到这个末端就当成全段完整。
5. 使用任务四 `case_manifest.csv` 的日期和峰时。小时峰贡献取同一峰小时每设备平均功率；分钟峰贡献取同一分钟，不用单设备各自峰值相加冒充同时总峰。
6. 逐设备制定运行阈值表：appliance_id, on_threshold_w, off_threshold_w, min_on_minutes, min_off_minutes, evidence, fitted_period。先研究待机及功率分布，再确定阈值；若阈值也进入预测，拟合期限定为训练段。**空调3最大仅 0.71 W**，本版不能给它编造明确压缩机启动事件；无法判定的运行状态应为 unknown。
7. 源缺测运行状态为 unknown；带迟滞或最短持续时间的状态机遇缺口应中断，重新观测时按预先定义初始化规则处理，不跨缺口自动接续。minute_state 表保留 on/off/unknown。
8. 两台或多台设备重叠的分母是相同分钟里所有比较设备状态已知的数量，报告 unknown 比例。不同设备对的分母可不同，不能只看百分比不报分母。全局排名若要横向比较，另固定共同已知集合。
9. 环境与行为只作独立的可选关联分析。设备与房间映射见数据字典和官方 Notebook；电水壶按作者 Notebook 归到客厅，不能凭设备名称推断厨房。房间气压 Pa 与室外 hPa 比较前另建换算字段。

### 本任务应交付

保存至 `data/derived/task05/`：`contribution_panel13.csv`、`contribution_panel14_supplement.csv`、`peak_contribution.csv`、`operation_thresholds.csv`、`minute_operation_state.csv.gz`、`overlap_summary.csv`、`case_manifest.csv` 和 `derivation_manifest.json`。每个贡献表含 panel_id、sample_scope、区间/日期清单、共同有效分钟、设备 kWh、面板分母 kWh 和占比。

验收：同表固定设备/时间集合，设备电量和等于面板电量，占比和约为 1；14 台补充与 13 台主表明确分开；缺测未归为关闭；运行重叠保留分钟尺度；不可从“未检测到运动”断言无人。

''',
    6: f'''### 已冻结的真实边界与候选样本

E = `2022-06-01 00:00+08:00`。训练 `[2021-05-31,2022-03-09)`，验证 `[2022-03-09,2022-04-06)`，测试 `[2022-04-06,2022-06-01)`。均为左闭右开，北京时间。不要重新挑测试周。

{table(split)}

表中 eligible_origins 是前 168 小时和后 24 小时均严格有效的保守候选数，尚非最终模型特征过滤后的数量。[逐日起点质量](../task01/reports/forecast_origin_quality.csv)、[冻结切分](../task01/reports/split_manifest.json)已经生成，可以直接作为 split 起点维表。训练最早在文件层面有 7 天上下文的起点是 2021-06-07，部分起点因 6—7 月缺测仍需排除。

### 按此顺序继续

1. 接任务二 `hourly_panel13.csv`，重建完整 8784 小时本地索引并核对任务一 strict_hourly_check；保留空目标。主目标为 mean_power_kw，不更换设备范围。
2. 读取上面的 split_manifest 和 forecast_origin_quality，先写 `data/derived/task06/experiment_config.json`。本版建议固定前 168h 完整历史和未来 24h 严格目标的保守规则，再构建日级起点×24目标长表。若后续放宽历史缺失规则，另建敏感性版本并重报样本数。
3. 每天 D 00:00 一次发布 h=0..23。逐个特征保存 latest_source_time 和 available_at，二者不能超过 origin。可用历史是截至 D-1 23:00 的小时（假设该小时在 00:00 已最终可用）；没有实测发布延迟，必须披露该假设，也可预先另设 1h 延迟敏感性实验。
4. 昨日同期 `y[D+h-24h]`、上周同期 `y[D+h-168h]` 为两个持续性基线。模型可用起点前 168 小时向量、过去 24/168h 均值/极值和已知日历。直接 h 步预测不能使用当天实际 lag1。历史滚动窗口始终止于 origin 之前。
5. 两类节假日/调休特征接任务三的 2021/2022 官方日历；日期字段未来可知。主版不加未来真实天气、设备功率、活动或室温；天气尚无带发布时间的历史预报，PPC 风向也未解决。
6. 以 LightGBM 24 个直接模型或一个带 horizon 的模型为主方法，先固定模型形式。检查本机依赖版本，保存 requirements 和随机种子。只用训练数据拟合；有限参数候选在验证期选择，参数表与选择标准先写入配置。此处没有训练模型，不能填写预测成绩。
7. 主版不标准化、不填补目标。候选模型若有缺失处理/编码/缩放，全部只从训练期拟合；本版常值段 QC 用全段回顾信息，不可作为预测特征或用来剔除测试标签。
8. 主比较掩码在看模型表现前固定为：保守起点有效、目标有效、两条基线输入有效、模型输入满足预先声明规则。输出 `common_score_mask.csv`，逐起点/horizon 保存 mask 和排除原因；先确认各 split 的候选数与本页一致，再记录额外特征导致的排除。
9. 高负荷阈值建议事先选训练期严格有效小时目标的 q90，保存数值和训练区间。MAE、RMSE 单位 kW，高负荷 MAE 只取同一共同掩码且目标超过该固定阈值的小时，并报告数量。若无样本，指标为空。
10. 峰值指标只在 24h 完整评分日计算。峰值大小误差单位 kW；峰时采用 24h 环形距离，真实与预测的并列峰集合保留，对两集合取最小环形距离并同时报告并列日数。所有模型使用相同定义，不能只给某个模型放宽并列规则。
11. 建议先固定“训练期拟合，验证选参后首次测试前以训练+验证重训一次，测试期固定模型”。若采用其他重训安排，应在测试前改配置；高负荷阈值仍固定在最初训练段。保存训练与重训截止日、模型和处理参数，测试只作最终评估。
12. 每个起点保存三个方法在相同 24 小时上的预测和实际值/掩码。以日或连续周块统计误差不确定性；报告测试为 2022-04-06 至 05-31 的春季到初夏，不能直接解释为全年效果。

### 本任务应交付

保存至 `data/derived/task06/`：`split_manifest.json`（引用冻结版本）、`experiment_config.json`、`feature_catalog.csv`、`origin_quality.csv`、`common_score_mask.csv`、`predictions.csv`、`metrics.csv`、`daily_peak_metrics.csv`、模型文件、训练日志、最终依赖版本与 `derivation_manifest.json`。

predictions 至少包含 origin, target_timestamp, horizon, split, model, y_true_kw, y_pred_kw, score_mask, exclusion_reason；feature_catalog 含特征定义、所需历史、来源时间及可获知时间规则。验收须检查所有使用的历史时间早于 origin、模型拟合截止不越界、同一主比较样本上三方法一一对应、测试连续 56 个日历日起点均保留。

'''
    }
    marker = '## 任务一完成后的实际承接'
    for number in range(2,7):
        base = (source/f'task{number:02d}/README.md').read_text(encoding='utf-8-sig')
        # Idempotent refresh: remove only our earlier handoff section if re-run.
        if marker in base:
            start = base.index(marker)
            end = base.index('## 仍需完成的预处理', start)
            base = base[:start] + base[end:]
        if number == 6:
            base = base.replace('尚未划分真实日期、训练模型或进行评估', '任务一已冻结真实日期与候选起点，尚未构造特征、训练模型或进行评估')
        base = base.replace('## 仍需完成的预处理', common + specifics[number] + '## 仍需完成的预处理', 1)
        write(ROOT/f'task{number:02d}/README.md', base)

    root = (source/'README.md').read_text(encoding='utf-8-sig')
    root = root.replace('本方案对应《家庭用电规律与负荷变化分析作业规划》中的六项任务，重点设计任务一，以及任务二至六还需要完成的预处理。', '本项目对应《家庭用电规律与负荷变化分析作业规划》中的六项任务，已完成任务一，并明确任务二至六基于实际数据的后续实施步骤。')
    root = root.replace('尚未进行逐行质量审计或清洗，具体覆盖率、可用日期、异常数量和训练集边界均须在实际审计后填写，不能将论文中的统计当作本次清洗结果。', 'task01 已于 2026-11-10 完成逐行审计与无新增插补标准化，实际结论、交付数据和运行方法见下文及[任务一质量报告](task01/reports/quality_report.md)。')
    root = root.replace('下载、核对官方文件大小和 MD5，并完整解压出 8 个 CSV', '下载、核对官方文件大小和 MD5，并完整解压出 8 个 CSV')
    root = root.replace('只有联合有效覆盖和连续时段审计通过后，才锁定该面板；目前不预先宣称它达到 95%。', '实际联合覆盖已审计为 96.8207%，已锁定 panel13/v1.0.0；2021 年 6—7 月低覆盖的限制仍须单独披露。')
    root = root.replace('以下是方案中的验收要求，目前尚未执行：', '以下为验收口径，task01 已按实际文件执行；逐项结果见[验收表](task01/reports/acceptance_checks.csv)，样本与限制见[质量报告](task01/reports/quality_report.md)：')
    root = root.replace('未来任务一应交付：', '任务一已交付：')
    root = root.replace('| 层次 | 未来产物 |', '| 层次 | 对应产物 |')
    root = root.replace('正式映射要读到真实表头后填写；本文不虚构列名', '正式映射已按真实表头填写，见 task01/reports/data_dictionary.csv')
    root = root.replace('| 一 数据可信度 | 发布原件、分钟数据、全部缺口、来源与质量 | 真实文件审计、数据字典、面板选择、版本锁定和质量验收 |', '| 一 数据可信度 | 发布原件、分钟数据、全部缺口、来源与质量 | 已完成审计、字典、面板、版本锁定和质量验收 |')
    root = root.replace('发布原件、官方元数据及下载来源清单已保存；其余清洗与质量审计产物尚待生成，本项目目前不包含已清洗数据。', '发布原件和原下载清单保留，官方补充 Notebook.pdf 已另存；标准分钟表、逐设备质量、字典、覆盖/缺口/异常报告、面板与切分、可复现程序均已生成。task02–06 已更新实际输入和具体实施步骤，其分析与建模尚未执行。')
    if '## 本次执行结果' in root:
        b=root.index('## 本次执行结果'); e=root.index('## 参考论文和数据链接',b); root=root[:b]+root[e:]
    at=root.index('## 参考论文和数据链接')
    executed=f'''## 本次执行结果

{headline}

- 标准入口：[分钟电器与面板表](data/standardized/cn_obee_v1_noimpute_v1.0.0/)、[逐设备字典](task01/reports/data_dictionary.csv)、[数据读取约定](task01/DATA_CONTRACT.md)。
- 14 台共同有效率 {summary['panel_coverage']['panel14']:.4%}，只用于共同有效时段补充。没有独立整户总表。
- 主面板 352 个严格完整日；2021-06、07 缺测集中，不能按完整月报告电量；2021-05 只有 1 个观测日。末端 2022-06-01 00:00 单条保留但不算新的一天。
- 冻结训练 [2021-05-31,2022-03-09)、验证 [2022-03-09,2022-04-06)、测试 [2022-04-06,2022-06-01)，都是北京时间左闭右开区间。
- 运行入口：`python task01/run_task01.py`；验收结果见[质量报告](task01/reports/quality_report.md)，继续步骤见 task02–06 各 README。

'''
    root=root[:at]+executed+root[at:]
    write(ROOT/'README.md', root)
    write(ROOT/'data/raw/README.md', '''# CN-OBEE 发布原件与补充来源

原件：CN-OBEE 条目 v1，DOI https://doi.org/10.6084/m9.figshare.23686476.v1；集合 v1：https://doi.org/10.6084/m9.figshare.c.6742536.v1。

原归档、8 个解压 CSV、官方元数据与原下载清单均保留不修改。原清单的 quality_audit_status=not_yet_performed 描述下载时状态，当前审计状态见覆盖它的独立[审计清单](../../task01/reports/source_manifest_audited.json)，无需篡改历史记录。

- `archives/The CN-OBEE dataset.zip`：官方大小 10,986,996 字节，MD5 6ba07a621463cb13c5d0b28d8219b293；SHA-256 04df16a1ccb67714d0ad4b310188427509cd7aee8d30a348abccf86fbe5884b0。
- `extracted/The CN-OBEE dataset/`：8 个 CSV，真实结构、编码、范围及 SHA-256 见审计清单。
- `source_manifest.json`、`figshare_metadata.json`：既有下载记录和官方元数据。
- `support/Notebook.pdf`：补存的官方 Code 条目 v1 材料，条目 24278092，https://doi.org/10.6084/m9.figshare.24278092.v1。实际是 PDF 版代码指南，未假称取得 .ipynb。相关元数据、大小、MD5、SHA-256 和下载时间见 support/support_manifest.json；未执行其中代码。

这里的 raw 表示下载发布原件，数据已由作者规则化、前向保持、部分空调补零。不是未经处理的传感器事件流。标准化与本次质量结论见[任务一 README](../../task01/README.md)。
''')
    manifest_files=sorted([p for p in S.rglob('*') if p.is_file()]+[p for p in R.rglob('*') if p.is_file() and p.name!='output_manifest.json'])
    def digest(p):
        h=hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda:f.read(1048576),b''): h.update(b)
        return h.hexdigest()
    write(R/'output_manifest.json',json.dumps(dict(data_version=summary['data_version'],files=[dict(path=p.relative_to(ROOT).as_posix(),size_bytes=p.stat().st_size,sha256=digest(p)) for p in manifest_files]),ensure_ascii=False,indent=2))
    print('Updated root README, task01 report/contract, task02-task06 handoffs, raw README and artifact inventory.')

if __name__=='__main__':
    main()
