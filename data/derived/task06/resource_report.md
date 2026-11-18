# 本地资源预检与实测



Python：`C:\Users\user\Documents\Codex\2026-11-18\files-pasted-by-the-user-task06\work\.venv\Scripts\python.exe`；3.12.14 (main, Aug 25 2026, 14:01:42) [MSC v.1944 64 bit (AMD64)]。

CPU：Intel64 Family 6 Model 186 Stepping 2, GenuineIntel；14 物理核 / 20 逻辑 CPU，本任务模型线程 4。

预检总内存 31.62 GiB，可用 15.24 GiB。



已实际完成导入与两个模型的小样本拟合，然后在保守完整训练集完成代表候选预检。依赖精确锁定见 requirements.txt。

特征与输入检查实测 85.518 秒，包含上游字节哈希、输入核验、两场景构造和审计表写盘；每场景 8784×20 原始字段、78 个编码维度。

LightGBM 代表候选全训练集实测 0.717 秒；Linear-L1 实测 10.015 秒。

bootstrap 小批次 500 次实测 0.013595 秒，线性推算每 10000 次 0.2719 秒；这只测充分统计量内核，未包含 q90 与文件 I/O，不能等同正式耗时。

预检推算训练和 bootstrap 总耗时 118.5 秒，属于推算；下表为正式分阶段墙钟实测。Python 启动、人工编码、网络和报告核验不计入该预检估算。



| stage | runs | measured_wall_seconds |
| --- | --- | --- |
| prepare_inputs_and_features | 1 | 85.517765 |
| preflight_fit | 2 | 10.853804 |
| validation_candidate | 24 | 40.146521 |
| initial_ablation | 4 | 0.722927 |
| one_time_refit | 8 | 14.779642 |
| frozen_predictions | 1 | 42.090077 |
| point_evaluation | 1 | 14.378094 |
| bootstrap | 8 | 6.046038 |
| report_generation | 2 | 17.588012 |
| phase_verify | 1 | 67.943678 |



已记录阶段进程峰值最大 317.6 MiB。内存按进程 RSS/Windows peak working set 记录，阶段开始/结束另有数值；不是整个系统或所有子进程的峰值。



结论：本地可完成。无需云 CPU，也无 GPU 需求证据。主要模型开销来自 HiGHS 线性规划；日历/审计写盘和独立核验也有开销。没有因节省时间减少候选或最终重抽样次数。

HiGHS 的 threads 选项由 SciPy 发出 OptimizeWarning 后原样传入 HiGHS；该警告和成功求解迭代数均保留，未换用其他回归器。

最初受限网络下 Git DNS 失败，后已成功获取；uv 缓存路径权限问题已通过任务目录缓存修复。它们不属于算力不足。CIM CPU 型号接口不可访问，使用 platform.processor 与 psutil 记录硬件。



若迁移：4 CPU 线程、8 GB RAM、Python 3.12，无需 GPU。依次执行 `python -m pip install -r task06/requirements.txt` 与 `python task06/run_task06.py all`。恢复时从 prepare/preflight/train/predict/evaluate/report/verify/manifest 已完成检查点的下一阶段运行；预测后 train 会拒绝重新选参。



日志时间采用 UTC ISO 格式；业务切分和所有预测时间均为 Asia/Shanghai。拟合数据截止是历史信息截止，不代表已模拟真实在线计算与发布延迟。

独立目录完整一键复跑的观测阶段跨度 301.489 秒；从首阶段开始时间到最后报告结束时间推算，排除解释器启动和最终清单 I/O。12 份关键表（含 105408 行预测）完全一致。该复跑验证可复现性，未修改参数或根据测试成绩重新选择模型。