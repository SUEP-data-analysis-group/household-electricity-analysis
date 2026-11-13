# task02 版本迭代

## 当前推荐：task02_v1.1.0_20261113

2026-11-13 验收修订，随后正式合入仓库。输入仍为 `cn_obee_v1_noimpute_v1.0.0` 和固定 `panel13/v1.0.0`，新增插补为 0。

- 将 4 个部分小时的 `mean_power_kw` 改为空，使全部 281 个不完整小时保持严格目标缺失；有效片段均值另存 `observed_duration_mean_power_kw`。
- 增加月度 312 行、季节时期 120 行曲线及两张图。正式交付为 8 CSV、1 清单、报告和 6 图。
- 把“整年电量”改为“352 个完整日合计约 2739.60 kWh”，修正缺测断线，删去缺乏证据的设备/作息归因。
- 补充 19 项输入/规则/程序和 15 项输出哈希；核验严格均值、NaN、全量 114192 条分项和曲线。
- 支持 `--source-root`。正式上传时补充历史绝对路径到当前根目录的映射，保留清单的原始来源记录。
- 本次上传没有进一步改变已修订的 8 个 CSV，派生版本号沿用；数值核验和文件哈希均通过。

与原版逐字节相同的 5 个 CSV：daily_panel13、hourly_appliance、weekly_support、monthly_support、typical_hourly_profile。hourly_panel13 修订字段，monthly_typical_hourly_profile、seasonal_typical_hourly_profile 为新增。

## 原始公开交付：2026-11-11

原版没有单独的派生版本号。发布 6 CSV、1 清单、程序/报告及 4 图；严格小时电量和完整日统计基本正确，但存在部分小时均值、缺少分期曲线、表述与核验不足等问题。

历史入口：[task02-original-20261111](https://github.com/SUEP-data-analysis-group/household-electricity-analysis/tree/task02-original-20261111)，对应原提交 `e058aba7c9fe80ae6119a77d2003895c1befbd43`。该标签在 2026-11-13 补建，保留历史，不作为当前下游输入。

## 基础数据版本与下游兼容

task01 数据 `v1.0.0` 与 task02 派生 `v1.1.0` 指不同对象。当前 task03 必须接收本版日表、小时表和派生清单；task04—task06 按 README 使用严格负荷与完整性标记。

[全项目版本记录](https://github.com/SUEP-data-analysis-group/household-electricity-analysis/blob/main/CHANGELOG.md)列出全部交付阶段、历史标签和后续任务入口。
