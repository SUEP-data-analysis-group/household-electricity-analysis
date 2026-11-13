# task03 版本迭代

## 当前推荐：task03_v1.1.0_20261113

2026-11-13 根据验收补齐交付，并在同日正式合入仓库。标准数据和固定面板仍为 `cn_obee_v1_noimpute_v1.0.0`、`panel13/v1.0.0`。

- 补齐 10 个正式 CSV 和派生清单；独立包附当前 task02 的日表、小时表和清单。
- 更新 task02 输入哈希，在导入记录的 `previous_import` 中保留旧来源与哈希。
- 核验严格小时目标及不完整小时空值；适配仓库和独立包布局。
- 完整仓库运行额外核对 task01 面板哈希及小时/日参考表；独立包如实记录参考表未附带。
- 增加完整 ZIP、校验和及解压复跑日志，确保 10 CSV 哈希相同。正式上传时把本页和新版 README 一并打入 ZIP。
- 仓库打包为独立 ZIP 时同步调整清单中的相对路径，并注明 task01 参考表不随包附带；先直接核验包内原文件，再复跑生成和再次核验。
- 保留原统计方法与主要结果：自然周末/实际休息日的同月标准化差值约 +0.520/+0.434 kWh/日，两项 95% 区间均覆盖 0。36 项任务核验通过。

此次上传只整理活动目录、版本说明并更新 ZIP，没有进一步修改已补齐的 10 个 CSV，沿用本派生版本号。

## 原始本地交付：2026-11-12

原版没有显式派生版本号。实际收到 23 个代码、配置、说明、来源和报告文件，缺少说明声称已附带的正式 `data/` 及三个 task02 输入。原主要统计可通过隔离复算重现，但原包不是完整交付。

此次从修订前备份逐字节保存原件，历史入口为 [task03-original-20261112/task03](https://github.com/SUEP-data-analysis-group/household-electricity-analysis/tree/task03-original-20261112/task03)。这是 2026-11-13 创建的历史快照；此前 GitHub 仅有预留 README，不能把本地工作日期当成旧版公开发布日期。快照未补入后来生成的数据，也没有回填 Git 日期。

[原件逐文件哈希](https://github.com/SUEP-data-analysis-group/household-electricity-analysis/blob/main/docs/history/task03-original-20261112.files.json)可用于辨认旧版文件。旧 `REQUIREMENTS.md` 和官方来源继续保留作任务/来源参考；当前执行状态以 README、派生清单和实际日志为准。

## 上游与后续使用

当前版承接 `task02_v1.1.0_20261113`。task04 复用日期标签，task06 只使用预测时已公开的日历字段；不能把事后电量、覆盖率、完整性作为日前已知特征。

[全项目版本记录](https://github.com/SUEP-data-analysis-group/household-electricity-analysis/blob/main/CHANGELOG.md)说明 task01 至当前版本的完整迭代。
