# -*- coding: utf-8 -*-
"""生成交付包的 derivation_manifest.json：记录输入/代码/输出哈希、样本口径与核验结果"""
import hashlib
import json
import platform
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
INP = BASE / "inputs"
OUT = BASE / "out"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def entry(path, role):
    return {"file": str(path.relative_to(BASE)), "role": role,
            "bytes": path.stat().st_size, "sha256": sha256_of(path)}


input_files = [
    (INP / "standardized" / "panel_minute.csv.gz", "task01 面板分钟功率与联合完整性"),
    (INP / "standardized" / "power_minute.csv.gz", "task01 分设备分钟功率（无插补）"),
    (INP / "task01" / "panel_definition.json", "task01 panel13/panel14 设备名单"),
    (INP / "task02" / "daily_panel13.csv", "task02 日级完整性"),
    (INP / "task02" / "hourly_appliance.csv", "task02 分设备小时电量"),
    (INP / "task02" / "hourly_panel13.csv", "task02 面板小时电量"),
    (INP / "task04" / "daily_extrema_times.csv", "task04 全部峰/谷小时与并列"),
    (INP / "task04" / "case_manifest.csv", "task04 四个案例清单"),
    (INP / "task04" / "case_hourly_curves.csv", "task04 案例小时曲线"),
    (INP / "task04" / "case_minute_curves.csv.gz", "task04 案例分钟曲线"),
    (INP / "task04" / "case_quality_summary.csv", "task04 案例质量汇总"),
    (INP / "task04" / "thresholds.json", "task04 训练期阈值（本步骤未使用）"),
]

code_files = [
    (BASE / "code" / "run_A_input_audit.py", "A 节点：输入锁定与样本集合"),
    (BASE / "code" / "run_B_contribution.py", "B 节点：三种分母贡献主表与对账"),
    (BASE / "code" / "run_C_peak_contribution.py", "第三步：峰时贡献与四案例"),
    (BASE / "code" / "make_delivery_tables.py", "按 README 命名整理交付表"),
    (BASE / "code" / "make_manifest.py", "生成本清单"),
    (BASE / "code" / "verify_package.py", "交付包自校验"),
]

handoff_files = []

output_files = [
    (OUT / "A_input_inventory.csv", "输入清单"),
    (OUT / "A_sample_support.csv", "样本支持表"),
    (OUT / "A_sample_day_list_panel13.csv", "主完整日逐日名单"),
    (OUT / "A_sample_day_list_panel14.csv", "panel14 的 148 个完整日名单"),
    (OUT / "A_time_axis_check.csv", "三个应展示时间点证据"),
    (OUT / "A_audit.json", "A 节点机读核验"),
    (OUT / "B_contribution_panel13.csv", "主/补充贡献表（步骤内命名）"),
    (OUT / "B_contribution_panel14_supplement.csv", "14 台独立补充（步骤内命名）"),
    (OUT / "B_hour_reconcile.csv", "8448 小时键逐设备对账"),
    (OUT / "B_reconcile.json", "B 节点机读核验"),
    (OUT / "C_peak_contribution.csv", "峰时贡献明细（步骤内命名）"),
    (OUT / "C_peak_summary.csv", "两种峰时汇总口径"),
    (OUT / "C_case_peak.csv", "四案例峰时与分钟峰"),
    (OUT / "C_reconcile.json", "第三步机读核验"),
    (OUT / "交付表" / "contribution_panel13.csv", "README 命名：主面板贡献表"),
    (OUT / "交付表" / "contribution_panel14_supplement.csv", "README 命名：14 台补充表"),
    (OUT / "交付表" / "peak_contribution.csv", "README 命名：峰时贡献表"),
    (OUT / "交付表" / "case_manifest.csv", "README 命名：案例清单（原样承接 task04）"),
]

audit = json.loads((OUT / "A_audit.json").read_text(encoding="utf-8"))
brecon = json.loads((OUT / "B_reconcile.json").read_text(encoding="utf-8"))
crecon = json.loads((OUT / "C_reconcile.json").read_text(encoding="utf-8"))

manifest = {
    "task": "task05 前三个步骤（输入锁定与样本集合 / 三种分母与贡献主表 / 峰时贡献与四案例）",
    "owner": "胡敏嘉",
    "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "data_version": "cn_obee_v1_noimpute_v1.0.0",
    "panel_version": "panel13/v1.0.0",
    "task04_version": "task04_v1.0.0_20261114（独立交付包；派生表与仓库 v1.0.1 逐字节一致）",
    "environment": {"python": sys.version.split()[0], "pandas": pd.__version__,
                    "platform": platform.platform()},
    "sample_scopes": [
        {"sample_scope": "panel13_complete_352d", "minutes": 506880, "days": 352,
         "panel_energy_kwh": brecon["main_scope"]["panel_energy_kwh"], "role": "主结果"},
        {"sample_scope": "panel13_all_common_valid", "minutes": 510284,
         "panel_energy_kwh": brecon["supplement_scope"]["panel_energy_kwh"], "role": "补充结果"},
        {"sample_scope": "panel14_all_common_valid", "minutes": 217643, "days": 148,
         "panel_energy_kwh": brecon["panel14"]["all_common_valid"]["panel_energy_kwh"],
         "role": "14 台独立补充"},
    ],
    "rules": {
        "energy": "E = sum(P_W over M) / 60000  kWh",
        "share": "share_i = E_i / E_panel；E_panel=0 时为空",
        "denominator": "三个 scope 各自独立分母，不互相借用",
        "peak_hours": "task04 daily_extrema_times.csv 中 kind=peak 全量继承，共 363 个区间",
        "tie_rule": "逐日按 1/tied_count 等权后再跨天汇总；与峰时段累计能量占比分开报告",
        "cases": "C01—C04 按 task04 case_manifest 原样承接，不重选",
    },
    "inputs": [entry(p, r) for p, r in input_files],
    "code": [entry(p, r) for p, r in code_files],
    "outputs": [entry(p, r) for p, r in output_files],
    "checks": {"A": audit["checks"], "B": brecon["checks"], "C": crecon["checks"],
               "A_all_pass": audit["all_pass"], "B_all_pass": brecon["all_pass"],
               "C_all_pass": crecon["all_pass"]},
    "not_in_this_package": [
        "operation_thresholds.csv（逐设备运行阈值，第④步）",
        "minute_operation_state.csv.gz（分钟运行状态，第⑤步）",
        "overlap_summary.csv（重叠分母与 unknown 比例，第⑥步）",
        "报告正文（task05 报告需与④⑤⑥合并后统写）",
    ],
}
manifest["all_pass"] = all(manifest["checks"][k] for k in ("A_all_pass", "B_all_pass", "C_all_pass"))

(OUT / "derivation_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print("derivation_manifest.json 已生成，all_pass =", manifest["all_pass"])
print("输入 %d 项、代码 %d 项、输出 %d 项" % (len(input_files), len(code_files), len(output_files)))
