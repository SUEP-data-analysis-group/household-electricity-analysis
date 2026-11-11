# 标准数据与质量字段约定

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
