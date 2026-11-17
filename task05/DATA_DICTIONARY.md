# Task05 后三步数据字典

所有正式表位于包根目录 `data/derived/task05/`。版本 `task05_v1.0.1_20261117`；源版本 `cn_obee_v1_noimpute_v1.0.0`；时区 Asia/Shanghai。CSV 普通文件为 UTF-8-BOM，`.csv.gz` 为 gzip 压缩 UTF-8。空单元格为缺失/不可定义，数值 0 为实际计数0或已知率0，二者不能互换。比率存储为0—1，报告显示为百分数。

## 索引、范围与设备

| 字段/值 | 含义 |
|---|---|
| timestamp | 分钟区间或小时区间起点，源文件带+08:00；继承峰表不带偏移的文本按北京时间解释 |
| appliance_id、appliance_i、appliance_j | 固定设备ID；i/j方向影响条件比例，不影响对称重叠率 |
| panel13_complete_352d | 352完整日，506880分钟，主贡献与主重叠范围 |
| panel13_all_common_valid | 510284个13台功率共同有效分钟，仅继承的能量补充范围 |
| all_calendar_527040 | 366日日历轴527040分钟，运行状态/重叠补充范围，保留缺口 |
| panel14_all_common_valid / panel14_complete_148d | 217643共同有效分钟 / 148完整日213120分钟；能量独立补充 |
| pairwise_known | 同一scope内该设备对均非unknown的分钟集合 |
| S12_common_known | 同一scope内预先固定12台设备均非unknown的分钟集合 |
| S12 | panel13去除空调3；完整名单在config.json中 |
| threshold_version | 每设备规则版本，不是人工状态真值版本 |

## operation_thresholds.csv（13行）

| 字段 | 含义/单位 |
|---|---|
| on_threshold_w / off_threshold_w | 连续证据的上下阈值，W；含等号≥/≤；空调3阈值留空 |
| min_on_minutes / min_off_minutes | 连续阈值证据确认长度，分钟；不是输出状态段的最短长度 |
| state_meaning / off_meaning | on/off的电功率代理含义；off不等于无人、拔电或完整停机 |
| detection_status | rule_proxy_only为规则代理；unidentifiable为运行不可识别 |
| evidence / evidence_file | 训练期阈值制定依据与证据表 |
| fitted_start / fitted_end_exclusive / fitted_period | 训练取证区间[2021-05-31,2022-03-09)，北京时间 |
| training_usable_minutes / training_max_w / training_median_w | 训练有效分钟数/功率最大值W/功率中位数W |
| threshold_selection | manual_training_distribution_and_run_review，训练分布与持续段手工审查，不是监督训练 |
| confirmation | 连续阈值确认；等待分钟unknown；不回填 |
| future_minutes_required | False，当前状态不需要当前时刻之后的分钟 |
| maximum_confirmation_delay_minutes | 相对首次阈值证据的最大额外确认等待：max(min_on,min_off)-1；持续候选被打断则重新计数 |

## minute_operation_state.csv.gz（527040行）

`timestamp`、13个设备同名状态列、13个 `设备ID__reason` 原因列及 `any_qc_review`。

- 状态为on/off/unknown，计算内部编码1/0/-1。
- 原因码：0已知；1源缺测/无效；2运行不可识别；3起始/缺口后迟滞区间未初始化；4等待on确认；5等待off确认。
- any_qc_review：该分钟任一panel13设备带bit16或32。不是整分钟无效标志，不代表13台都有问题；不参与自动删值。
- 源缺测重置状态机；不压缩缺口。空调3全期unknown；有效功率仍计能量。

## operation_support.csv（26行）、monthly_operation_support.csv（169行）

| 字段 | 含义 |
|---|---|
| observed_minutes / calendar_minutes | 指定范围/指定月份的日历分钟数 |
| known_minutes / unknown_minutes | 该设备on或off分钟数 / unknown分钟数 |
| on_minutes / off_minutes | 该设备已确认on / off分钟数 |
| unknown_fraction | unknown_minutes / observed_minutes |
| on_rate_given_known | on_minutes / known_minutes；known=0时留空 |
| unknown_原因名_minutes | 每种非0原因的unknown计数；求和等于unknown_minutes |
| on_qc16_review_minutes / on_qc32_review_minutes | 本设备on分钟中带对应复核bit的数量，允许重复交集，不据此删值 |
| year_month | 月历归属，首月仅2021-05-31，其他月保留原支持；不当作13个等长月份 |

## confirmed_on_segments.csv（18484行）

| 字段 | 含义 |
|---|---|
| start / end_exclusive | 最大连续已确认on段的左闭右开时刻 |
| confirmed_on_minutes | 此段已确认on分钟数 |
| energy_kwh | 此段原功率ΣW/60000，不包含unknown等待分钟 |
| left_boundary / right_boundary | 原轴窗口边界、相邻off或unknown；不把unknown两侧连接 |
| interpretation | 仅已确认on段，不能解释为完整设备周期或人工验证开机次数 |

## overlap_summary.csv（288行）

两个scope各有78个逐对分母记录+66个S12统一分母记录。每个scope一共有144行。

| 字段 | 含义 |
|---|---|
| sample_scope / denominator_scope | 日历/日期范围，以及逐对已知或S12共同已知的选择 |
| observed_minutes | scope全部观测分钟 |
| known_minutes | 该行真实分母，所需设备均已知的分钟数 |
| unknown_fraction | (observed_minutes-known_minutes)/observed_minutes |
| both_on_minutes | 分母集合内i、j同时on分钟数 |
| overlap_rate | both_on_minutes / known_minutes |
| i_on_known_minutes / j_on_known_minutes | 分母集合内i/j分别on的分钟数 |
| p_j_on_given_i_on | both_on / i_on_known_minutes |
| p_i_on_given_j_on | both_on / j_on_known_minutes |
| union_on_minutes | 分母集合内至少i或j为on的分钟数 |
| jaccard | both_on / union_on_minutes |
| both_on_with_qc_review_minutes | 共同on中任一对应设备带bit16/32的分钟数 |
| metric_definition | 主重叠率定义与unknown排除说明 |

各率使用自己的分母；任一分母为0则该率留空。涉及空调3的12对×2范围共24行，known_minutes=0、overlap_rate为空。不能当作重叠为0。S12排名仅用同scope和S12_common_known行。

## overlap_group_summary.csv（4行）、concurrent_device_count.csv（54行）

前者为两个scope×panel13_all_known/S12_common_known。包含device_ids、观测/已知分钟、unknown比例、at_least_two_on_minutes、at_least_two_on_rate和mean_on_device_count。后两项的分母均为集合共同已知分钟数。全13台共同已知为0，对应比例和均值留空。

后者按n_on（同时on的设备数）统计n_minutes和rate_given_common_known。主S12共同已知499217分钟；补充502578分钟。全13台的计数行保留0，但率为空。

## case_operation_state.csv.gz（5760行）

4个案例各1440分钟。包含case_id、原分钟状态和原因、any_qc_review、panel13_power_kw和13个 `设备ID__power_w` 原功率。不能把功率W列与面板kW列直接相加。案例日期/日类型/小时峰/分钟峰来自原case_manifest，不重新挑选。

## threshold_sensitivity_support.csv（39行）、threshold_sensitivity_overlap.csv（198行）

threshold_scale为0.8/1/1.2，同时乘on和off阈值；持续确认长度固定。support为每比例×13设备；overlap为每比例×66个S12设备对，范围固定352完整日，每方案使用自身S12共同已知分钟分母（499263/499217/499606）。主阈值不按敏感性输出再优化。

## 对账、清单与继承表

- upstream_hour_reconciliation.csv：8784小时。minute_recomputed_kw仅严格小时有值；inherited_mean_kw保留原列；strict_target_kw对所有不完整小时留空；partial_mean_not_target标出4个原列非空但不能作完整小时目标的位置。
- AB_upstream_reaudit.json：输入哈希、同集合能量/小时/峰/案例的实现自查；不等于Task06实际模型交叉审核。
- C_state_rule_audit.json：全期生成前冻结规则、四类样例和13个单元测试；自动自查，不冒充人工审批。
- verification_task05.json：独立算法全期状态、原因、分母、率和继承哈希复核；不验证物理状态准确率。
- state_generation_record.json：状态、规则、配置和预审证据哈希及实际运行环境。
- derivation_manifest.json：输入/代码/规则/输出SHA-256、样本范围、继承关系；自身和最后核验日志不自包含哈希，避免循环。
- training_*.csv/json：仅训练期分布、常见值、候选高功率段长度及取证范围。q1为100%分位数（最大值），不是1%分位数；q0.01等才表示1%。
- rule_boundary_examples.csv：正常开关、1分钟脉冲、缺口重置、不可识别四类合成短例，数值是测试用例，不是住户实测片段。
- contribution_panel13.csv：保留同伴数值、修正样本元数据的正式表，含每scope的13个设备及 `__panel13__` 合计行；汇总时不要再把合计当第14个设备重复求和。
- contribution_panel14_supplement.csv：保留原数值、修正样本元数据的panel14及同集合ref13；ref13中的电饭煲行数值为空是排除，不是电量0；`__panel14__`是总计行。
- peak_contribution.csv：原小时峰与分钟峰统一使用value_kw和panel_kw，单位均kW；分钟峰的W值已在原表除1000，不要再次视作W。
- case_manifest.csv：按字节承接原task04清单，4行。其他继承字段与前三步README一致；原source role等部分中文显示异常不改写其字节或数值。

## 2026-11-17 样本与峰贡献字段修订

贡献表n_days为范围实际涉及日期数：panel13全共同有效356日、完整日352；panel14全共同有效153日、完整日148。n_complete_days/n_partial_days分列完整/部分日，不混作相同概念。分钟、电量、分母、份额保留原数值。

date_list_file=sample_support_by_day.csv，结合date_list_scope筛选sample_scope；该表的valid_minutes是该日期实际纳入分钟，day_complete表示1440分钟。sample_mask_file=sample_minute_masks.csv.gz，结合sample_mask_column选择布尔列，精确复现四种范围。全527040行连续轴，不以首末时刻代替稀疏掩码。

peak_contribution增加panel_id/panel_version、sample_scope、common_valid_minutes、period_start/period_end_exclusive、energy_kwh、denominator_kwh。小时为60分钟，案例分钟峰为1分钟；能量=平均功率kW×时长小时。原value_kw/panel_kw、share、全部并列时间和weight不变。分钟峰仍为单分钟贡献，不与小时峰混合汇总。
