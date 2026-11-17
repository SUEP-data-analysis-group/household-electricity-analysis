# -*- coding: utf-8 -*-
"""按 task05 README 的正式交付命名，整理前三个步骤的表（不改动任何数值）

README 要求每个贡献表含：panel_id、sample_scope、区间/日期清单、共同有效分钟、
设备 kWh、面板分母 kWh、占比；peak_contribution 要含尺度、并列权重与 case_id。
"""
import shutil
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parents[1]
INP = BASE / "inputs"
OUT = BASE / "out"
DELIV = OUT / "交付表"

DELIV.mkdir(parents=True, exist_ok=True)

support = pd.read_csv(OUT / "A_sample_support.csv")
span = {row.sample_scope: (row.first, row.last, row.n_samples) for row in support.itertuples()}

# panel14 的 148 个严格完整日：从面板分钟表按 panel_id=panel14、panel_complete 重算，
# 并与 A 节点声明的 148 日 / 213120 分钟对账，避免另写一套规则。
pm = pd.read_csv(INP / "standardized" / "panel_minute.csv.gz",
                 usecols=["timestamp", "panel_id", "panel_complete"])
pm["timestamp"] = pd.to_datetime(pm["timestamp"], utc=True).dt.tz_convert("Asia/Shanghai")
p14 = pm[(pm["panel_id"] == "panel14") & (pm["panel_complete"])].copy()
p14["date"] = p14["timestamp"].dt.strftime("%Y-%m-%d")
per_day = p14.groupby("date").size()
days14 = per_day[per_day == 1440].index.sort_values()
assert len(days14) == 148, "panel14 完整日数应为 148，实际 %d" % len(days14)
assert len(p14) == 217643, "panel14 共同有效分钟应为 217643，实际 %d" % len(p14)
assert int(per_day[per_day == 1440].sum()) == 213120, "148 日分钟数应为 213120"

sub14 = p14[p14["date"].isin(days14)]
span["panel14_complete_148d"] = (
    sub14["timestamp"].min().isoformat(),
    sub14["timestamp"].max().isoformat(),
    213120,
)
print("panel14 完整日 148 天 / 213120 分钟，与 A 节点一致")

DATE_LIST = {
    "panel13_complete_352d": "A_sample_day_list_panel13.csv",
    "panel13_all_common_valid": "（不逐日列举：按 panel_complete=True 的共同有效分钟判定，规则见 A_sample_support.csv 的 definition 列）",
    "panel14_all_common_valid": "A_sample_day_list_panel14.csv",
    "panel14_complete_148d": "A_sample_day_list_panel14.csv",
}


pd.DataFrame({"date": days14, "panel_id": "panel14",
              "valid_minutes": 1440, "day_complete": True}) \
    .to_csv(OUT / "A_sample_day_list_panel14.csv", index=False, encoding="utf-8-sig")

def with_span(df):
    df = df.copy()
    df["period_first_minute"] = df["sample_scope"].map(lambda s: span[s][0])
    df["period_last_minute"] = df["sample_scope"].map(lambda s: span[s][1])
    df["date_list_file"] = df["sample_scope"].map(DATE_LIST)
    order = ["panel_id", "sample_scope", "period_first_minute", "period_last_minute",
             "date_list_file", "n_days", "minutes", "appliance_id",
             "energy_kwh", "denominator_kwh", "share"]
    rest = [c for c in df.columns if c not in order]
    return df[order + rest]


b13 = pd.read_csv(OUT / "B_contribution_panel13.csv")
with_span(b13).to_csv(DELIV / "contribution_panel13.csv", index=False, encoding="utf-8-sig")

b14 = pd.read_csv(OUT / "B_contribution_panel14_supplement.csv")
with_span(b14).to_csv(DELIV / "contribution_panel14_supplement.csv", index=False, encoding="utf-8-sig")

# 峰时表不需要补列，直接二进制复制，保证与核验过的文件逐字节相同
shutil.copyfile(OUT / "C_peak_contribution.csv", DELIV / "peak_contribution.csv")

shutil.copyfile(INP / "task04" / "case_manifest.csv", DELIV / "case_manifest.csv")

# 交付表与原表的数值必须一致（补列会重写 CSV，浮点末位按容差比）
tol = 1e-12
for a, b in (("B_contribution_panel13.csv", "contribution_panel13.csv"),
             ("B_contribution_panel14_supplement.csv", "contribution_panel14_supplement.csv"),
             ("C_peak_contribution.csv", "peak_contribution.csv")):
    x = pd.read_csv(OUT / a)
    y = pd.read_csv(DELIV / b)
    assert len(x) == len(y), "%s 行数不一致" % b
    bad = []
    for col in [c for c in x.columns if c in y.columns]:
        if pd.api.types.is_numeric_dtype(x[col]):
            if (x[col] - y[col]).abs().max() > tol:
                bad.append(col)
        elif x[col].astype(str).tolist() != y[col].astype(str).tolist():
            bad.append(col)
    print("%-40s 行数 %d，逐列一致：%s%s" % (b, len(x), "是" if not bad else "否", "" if not bad else "（差异列 %s）" % bad))

print("交付表已生成：", ", ".join(sorted(p.name for p in DELIV.iterdir())))
