# task04 字段与读取约定

数值 CSV 为 UTF-8 BOM，空值为空单元格；gzip 可由 pandas 直接读取。读取数值使用 float_precision='round_trip'，时间显式转 Asia/Shanghai。布尔为 True/False。除报告显示外不主动舍入；不完整/不可定义值不能填 0。

## 日指标和极值

- `date`：北京时间自然日零点；`panel_id/panel_version/data_version`：固定范围与标准版本；`natural_day_type/actual_day_type/year_month`：任务三标签。
- `energy_kwh`：task02 严格完整日电量；`peak_kw/valley_kw`：该日 24 个严格小时均值最大/最小；`peak_valley_kw`：二者之差；`mean_kw`：24 小时均值；`load_factor`：mean_kw/peak_kw，零峰为空。
- `peak_tied_count/valley_tied_count`：相同 float64 读数的并列小时数；`hour_count=24/day_complete=True`：主日样本支持。
- 极值长表 `kind`=peak/valley；`hour_start`：完整小时时间戳；`hour`：本地小时；`value_kw`：极值；`tied_count`：该日该类并列数；`weight=1/tied_count`。
- 时刻频率 `weighted_days`：该小时的日期权重之和；`proportion=weighted_days/n_days`；`days_with_extreme_at_hour` 是未分权的涉及日数，不能与权重合计混用。

## 连续小时变化

- `timestamp/previous_timestamp`：当前/上一行小时起点；`current_mean_power_kw/previous_mean_power_kw` 为对应严格负荷；`current_hour_complete/previous_hour_complete` 为质量。
- `elapsed_hours`：两时间点实际相差小时数；首行为空。`valid_change` 要求有前一行、相差恰为 1h、双方完整。
- `exclusion_reason`：no_previous_hour、non_adjacent_timestamp、both_hours_incomplete、current_hour_incomplete 或 previous_hour_incomplete；有效行为空。
- `is_cross_midnight/is_intra_day` 仅描述日界关系，不替代 valid_change；首行均 False。`delta_kw`=当前减前一小时，`abs_delta_kw` 为绝对值，二者在无效行都为空。
- `is_large_change`：只在有效行定义，绝对变化严格大于训练 q95；无效行为空。单位是 kW 的 1h 均值差，不是分钟变化率。
- 变化汇总 `n_pairs` 是该 scope 的有效分母；p95_abs_delta_kw 属全期该 scope 的描述分位数，不是训练参数。

## 分钟与案例

- `minute_record_peak_w/kw`：完整日标准面板的分钟记录最大值，W 与 kW 分列；`hour_peak_kw` 是同日日最大小时均值；`minute_to_hour_peak_ratio` 分母转为同单位，零小时峰为空。
- `minute_peak_times/minute_record_peak_times/peak_hour_starts/valley_hour_starts`：JSON 字符串，保留全部并列时间，均含 +08:00；`minute_peak_tied_count` 为分钟并列数。
- `case_id`：稳定案例编号 C01–C04；`case_type/label`：自然工作日、自然周末、同月高电量、全期最大小时峰；`selection_metric/selection_target/selection_distance/candidate_days/comparison_month`：可复现选择依据。
- `device_ids`：JSON 固定 13 台列表；`window_start/window_end_exclusive`：同一 24h 左闭右开；`complete_minutes=1440/n_devices=13`；`review_flag_minutes` 为任一设备有 bit16/32 标记的分钟数，不是丢弃数。
- 分钟曲线的 `*_w` 是同一分钟设备功率 W；`panel_power_w` 是固定 13 台同时求和；`source_row_id/source_present` 保留 power_minute 的来源行信息；逐设备 `*_w_qc_bits` 原样来自 task01 QC。
- QC 位 1=源缺失、2=时间缺行、4=非数值/非有限、8=物理错误、16=近量程复核、32=长常值复核；可叠加。`combined_qc_bits` 是 13 台按位或；`any_review_flag` 仅表示出现 16/32；`new_imputed_devices=0`。完整案例仍可有复核标记，不据此删值。
- `case_quality_summary` 每例每设备一行。`usable_minutes/unusable_minutes` 是功率可用支持；`source_or_physical_invalid_minutes` 数 bit1/2/4/8；两个 review 字段数 bit16/32；`new_imputed_minutes` 数新增插补；`qc_unique_bits` 保留出现的位值。

## 清单和阈值

thresholds.json 的训练区间沿用 task01；变化阈值两端都在训练段，分位数算法 linear。全期探索阈值明确单列，不供预测参数拟合。derivation_manifest.json 的输入有 GitHub 提交及 SHA-256；输出 `scope=output_root` 相对 --output-root，`scope=task_directory` 相对脚本目录。原输入文件中的历史绝对路径只作历史来源，不用于本任务定位文件。
