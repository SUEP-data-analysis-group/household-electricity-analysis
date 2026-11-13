# Task03 交付说明

已按原任务要求完成「比较工作日与休息日」。本包包含本任务代码、配置、来源、报告、6 张图和全部派生表，并附上从同伴 task02 原字节复制的 3 个必要输入。

直接双击打开 `task03/reports/task03_report.html` 查看完整报告，无需安装 Python。文字版报告在 `task03/reports/task03_report.md`。

主结果：控制同年月份组成后，自然周末日电量比自然工作日高约 0.520 kWh（+6.80%），实际休息日比实际工作日高约 0.434 kWh（+5.64%）；两套 95% 区间均包含 0，不能据此断言存在稳定差异。

样本为固定 13 台监测设备，366 个自然日中 352 个完整日；排除 14 个缺测日，未新增插补。主月度标准化比较因 2021 年 5 月仅 1 天而采用其余 351 个完整日。只解释该住户观测期内的关联。

安装依赖并复现（在本说明所在目录运行）：

```bash
python -m pip install -r task03/requirements.txt
python task03/run_task03.py
python task03/verify_task03.py
```

附带的核验日志为 35 项全部通过。主程序先核验 task02 输入内部一致性；如果在完整项目仓库中运行，还会与 task01 标准文件哈希和小时、日核验表对照。独立成果包中无需附带体积较大的标准分钟原件。

目录：

```text
task03/                    代码、配置、README、原要求、官方来源、报告和图
data/derived/task02/       同伴的日表、小时表、原派生清单（仅必要输入）
data/derived/task03/       本任务全部正式派生结果
```

task02 的原清单保留原字节，因此其中也列出未随本包附带的其他 task02 成果。输入来源及哈希另见 `task03/sources/task02_import_manifest.json`；本任务数据版本、规则与输出校验值见 `data/derived/task03/derivation_manifest.json`。

后续成员可使用 `date_dimension.csv` 的日类型标签；预测仅使用事先已知日历字段，不使用当日电量和质量结果。
