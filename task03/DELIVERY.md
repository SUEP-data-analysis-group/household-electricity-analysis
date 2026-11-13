# Task03 完整成果包说明（2026-11-13 修订）

本次已补齐此前遗漏的 10 个正式 CSV、派生清单，以及修订版 task02 的日表、小时表和派生清单。主要统计结论保持一致，具体内容见 README.md 与 reports/task03_report.html。

独立文件夹或完整 ZIP 解压后的结构为：

```text
README.md、run_task03.py、verify_task03.py、package_task03.py、config.json
sources/                 官方通知与修订版 task02 导入记录
reports/                 HTML/Markdown 报告、6 张图及实际核验日志
data/derived/task02/      3 个必要的修订版输入
data/derived/task03/      10 个正式 CSV 和派生清单
```

在独立包根目录运行：

```powershell
python -m pip install -r requirements.txt
python run_task03.py
python verify_task03.py
python package_task03.py
```

完整 ZIP、校验值与解压复跑日志保存在 deliverables/。打包程序会先核验解压后的原文件，再实际复跑并再次核验，核对全部 10 个结果 CSV 的 SHA-256；只有通过才报告成功。独立包清单使用独立布局路径，并保留来源核验状态、如实说明未附带 task01 参考表。不要只转发代码/报告文件夹而漏掉 data/。

所有迭代和旧版入口见 [CHANGELOG.md](CHANGELOG.md)。

合入本地“家庭用电分析方案”项目时，代码、配置、sources、reports 放到 task03/，派生文件放到项目 data/derived/task03/。在主项目根目录以 python task03/run_task03.py、python task03/verify_task03.py 运行；必要输入使用同一套修订版 task02 数据。
