"""Read-only checks against the actual release, including the saved quality tables."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'task01/reports'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--raw-root',type=Path,default=ROOT/'data/raw')
    args=parser.parse_args()
    checks=0
    def check(ok,label):
        nonlocal checks
        if not ok: raise AssertionError(label)
        checks+=1
    summary=json.loads((REPORT/'audit_summary.json').read_text(encoding='utf-8'))
    manifest=json.loads((REPORT/'output_manifest.json').read_text(encoding='utf-8'))
    for record in manifest['files']:
        p=ROOT/record['path']
        check(p.is_file() and p.stat().st_size==record['size_bytes'] and digest(p)==record['sha256'],f'Output integrity: {p.name}')
    source=json.loads((args.raw_root/'source_manifest.json').read_text(encoding='utf-8-sig'))
    for record in source['files']:
        check(digest(args.raw_root/record['relative_path'])==record['sha256'],f'Raw unchanged: {record["name"]}')
    log=json.loads((REPORT/'processing_log.json').read_text(encoding='utf-8'))
    check(digest(ROOT/'task01/run_task01.py')==log['pipeline_sha256'],'Pipeline hash matches executed code')
    check(digest(ROOT/'task01/config.json')==log['config_sha256'],'Rule hash matches executed rules')
    std=ROOT/'data/standardized'/summary['data_version']
    p=pd.read_csv(std/'power_minute.csv.gz',float_precision='round_trip')
    timestamps=pd.DatetimeIndex(pd.to_datetime(p.timestamp)).tz_convert('Asia/Shanghai')
    check(timestamps.is_unique and timestamps.is_monotonic_increasing,'Unique, sorted saved index')
    check(len(p)==527041 and str(timestamps[-1])=='2022-06-01 00:00:00+08:00','Final singleton retained')
    appliance_cols=[c for c in p if c.endswith('_w')]
    check(len(appliance_cols)==14,'All fourteen source devices preserved')
    # Every quality table is checked in chunks, including all original numeric values.
    for col in appliance_cols:
        n=0
        for q in pd.read_csv(std/'appliance_quality'/f'{col}.csv.gz',
            usecols=['source_row_id','source_value','usable_value','is_usable','is_new_imputed','upstream_fill_status'],
            float_precision='round_trip',chunksize=150000):
            expected=p[col].iloc[n:n+len(q)].to_numpy()
            check(np.array_equal(expected,q.source_value.to_numpy(),equal_nan=True),f'Quality source values: {col}:{n}')
            check(np.array_equal(expected,q.usable_value.to_numpy(),equal_nan=True),f'Quality usable values: {col}:{n}')
            check(np.array_equal(q.source_row_id.to_numpy(),np.arange(n+2,n+2+len(q))),f'Quality line provenance: {col}:{n}')
            check(np.array_equal(q.is_usable.to_numpy(),np.isfinite(expected)),f'Quality mask: {col}:{n}')
            check(not q.is_new_imputed.any() and q.upstream_fill_status.eq('unknown').all(),f'Quality imputation semantics: {col}:{n}')
            n+=len(q)
        check(n==len(p),f'Quality rows: {col}')
    panel=pd.read_csv(std/'panel_minute.csv.gz',float_precision='round_trip')
    for panel_id,cols in [('panel13',[c for c in appliance_cols if c!='rice_cooker_w']),('panel14',appliance_cols)]:
        f=panel[panel.panel_id.eq(panel_id)]
        expected=p[cols].sum(axis=1,min_count=len(cols)).to_numpy()
        check(len(f)==len(p) and np.allclose(expected,f.panel_power_w,equal_nan=True,atol=1e-9,rtol=1e-12),f'Saved {panel_id} sum and missingness')
        n=p[cols].notna().sum(axis=1).to_numpy()
        check(np.array_equal(n,f.n_usable),f'Saved {panel_id} usable count')
        check(f.loc[n==0,'available_sum_w'].isna().all(),f'Saved {panel_id} all-missing diagnostic')
    hourly=pd.read_csv(REPORT/'strict_hourly_check.csv')
    daily=pd.read_csv(REPORT/'strict_daily_check.csv')
    for name in ('panel13','panel14'):
        h=hourly[hourly.panel_id.eq(name)]
        d=daily[daily.panel_id.eq(name)]
        check(len(h)==8784 and len(d)==366,f'{name} full calendar retained')
        check(h.loc[~h.hour_complete,'energy_kwh'].isna().all(),f'{name} incomplete hour has no full energy')
        check(d.loc[~d.day_complete,'energy_kwh'].isna().all(),f'{name} incomplete day has no full energy')
        check(d.day_complete.sum()==summary['complete_day_counts'][name],f'{name} strict day count')
    origins=pd.read_csv(REPORT/'forecast_origin_quality.csv')
    check(len(origins)==366 and origins.origin.is_unique,'Every calendar forecast origin retained')
    check(origins.split.eq('test').sum()==56 and origins.split.eq('validation').sum()==28,'Fixed 56/28 day splits')
    check(pd.read_csv(REPORT/'acceptance_checks.csv').passed.all(),'Pipeline acceptance checks')
    # Validate authored relative links, allowing original raw files during staging verification.
    files=[ROOT/'README.md',ROOT/'task01/README.md',ROOT/'task01/DATA_CONTRACT.md',REPORT/'quality_report.md',ROOT/'data/raw/README.md']
    files += [ROOT/f'task{i:02d}/README.md' for i in range(2,7)]
    for file in files:
        body=file.read_text(encoding='utf-8')
        for link in re.findall(r'\[[^\]]*\]\(([^)]+)\)',body):
            if '://' in link or link.startswith('#'): continue
            target=(file.parent/link.split('#')[0]).resolve()
            exists=target.exists()
            if not exists:
                try: exists=(args.raw_root/target.relative_to((ROOT/'data/raw').resolve())).exists()
                except ValueError: pass
            check(exists,f'Relative link in {file.relative_to(ROOT)}: {link}')
    for i in range(2,7):
        text=(ROOT/f'task{i:02d}/README.md').read_text(encoding='utf-8')
        check(text.count('## 任务一完成后的实际承接')==1 and '### 本任务应交付' in text,f'Task {i} actionable handoff')
    print(json.dumps(dict(status='passed',checks=checks,raw_files_unchanged=True,
          quality_cells_checked=527041*14,main_complete_days=summary['complete_day_counts']['panel13']),ensure_ascii=True))

if __name__=='__main__': main()
