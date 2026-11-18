# 完成 task06 双延迟日前预测、配对评价与独立核验

task06 原先只有任务说明。本提交实现固定 panel13 的 0h 与 1h 条件性日前回测，拆分发布资格和事后评分，冻结特征、共同掩码及参数选择；完整运行两条基线、同特征线性中位数回归、LightGBM-L1 Full 与两项固定参数消融。新增来源可获知性审计、完整日标签拟合截止检查、一次重训、模型/处理器保存、全部预定指标和四种配对时间块 bootstrap（每场景每算法 10000 次），附设计、报告、资源实测、一键/分阶段入口与独立核验。

测试均为 56 日、1344 小时。Full MAE 在 0h/1h 为 0.095704/0.095287 kW，按冻结规则均稳定优于两条基线：主差值区间上界<0，且 8/8 固定周块 MAE 更低。0h 的 Linear-L1 MAE 为 0.094460 kW，略优于 Full。高负荷仅 17 小时，Full 的高负荷误差与日峰幅度低估存在恶化，不宣称峰值可靠；没有根据测试成绩换模型。

实际验证：专用 Python 3.12 CPU 环境，12 组独立验收与 8 项边界测试通过；独立 CSV 算术重算总体/高负荷/日峰/日/时距/周指标、40 个完整 10000 次 MAE 差值区间，另直接复算 15360 个重抽样指标；验证未来记录删除/扰动、目标质量/QC 不影响发布，以及 1h 回退、标签截止、模型加载复现。328 个 task01—05 及原始/标准数据文件字节保持一致。完整复跑记录另见 reports/reproduction_check.json。

复核入口：

```powershell
python -m pip install -r task06/requirements.txt
python task06/run_task06.py verify
python task06/run_task06.py all --output-root work/task06_reproduction/data --report-root work/task06_reproduction/reports
```

报告入口为 task06/reports/task06_report.html，正式数据为 data/derived/task06/。测试仅覆盖单户 2022-04-06 至 05-31；公开时分未知、真实在线可用性和上游逐点填补身份仍受限。局部区间不代表同时显著，评价差值区间不代表未来负荷预测区间。主分支由仓库维护者合并。
