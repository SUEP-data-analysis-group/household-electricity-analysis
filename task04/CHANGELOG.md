# task04 版本记录

## task04_v1.0.1_20261114：仓库发布版

2026-11-14，承接用户已审核的本地 `task04_v1.0.0_20261114`。正式数据统一发布到仓库根目录 `data/derived/task04/`，程序、来源、测试和报告位于 `task04/`。

- 自动识别完整仓库根目录，直接读取 task01—task03 的已有数据；保留独立包和显式 source/output 参数支持。
- 调整 README 的相对数据链接、运行命令和版本标记，避免在仓库中重复附带约 90 MB 的 inputs。
- 重新生成报告与派生清单，记录实际运行环境和当前代码哈希。
- **11 份 CSV（含 gzip）与审核版逐字节相同**，案例、阈值、面板、样本和统计方法没有改变。

当前入口：[正式数据](../data/derived/task04/)、[README](README.md)、[报告](reports/task04_report.html)。历史标签：[task04_v1.0.1_20261114](https://github.com/SUEP-data-analysis-group/household-electricity-analysis/tree/task04_v1.0.1_20261114)。

## task04_v1.0.0_20261114：已审核本地独立包

首次完成任务四：352 个完整日日指标、715 条全部并列极值时刻、48 行时刻频率、8,784 行连续小时变化、4 个案例、5,760 条案例分钟曲线、52 行设备质量记录及 8 张图。有效变化 8,500 对，其中同日内 8,147 对、跨午夜 353 对。

独立包有 63 个文件，包含 24 个必需数据/规则输入和 4 份原要求/约定；已通过 114 项独立核验、9 个边界测试和重复生成的 11 CSV 哈希一致检查。

该审核版本以 [task04_v1.0.0_20261114](https://github.com/SUEP-data-analysis-group/household-electricity-analysis/tree/task04_v1.0.0_20261114/task04) 保存完整原字节。历史标签使用独立包目录结构，包含 inputs/ 和包内 data/；默认 main 使用上面的仓库结构。两个标签均于本次上传时创建，不倒填公开发布日期。

[全项目版本记录](../CHANGELOG.md)继续记录 task01—task04 的交付与后续入口。
