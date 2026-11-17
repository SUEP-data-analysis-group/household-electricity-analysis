"""把用户提供的前三步和相关来源复制到 task05 本地，不修改外部成果。"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first-three', type=Path, default=Path('E:/task05_前三步'))
    parser.add_argument('--task04', type=Path, default=Path('E:/task04/task04/data/derived/task04'))
    parser.add_argument('--task02', type=Path, default=Path('E:/task0203/task02/data/derived/task02'))
    parser.add_argument('--task03', type=Path, default=Path('E:/task0203/task03/data/derived/task03'))
    parser.add_argument('--quality', type=Path, default=ROOT/'data/standardized/cn_obee_v1_noimpute_v1.0.0/appliance_quality')
    args=parser.parse_args()
    target=HERE/'inputs'; target.mkdir(parents=True, exist_ok=True)
    records=[]
    def copy(source, destination):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        assert sha(source)==sha(destination)
        records.append(dict(source=str(source), local_path=destination.relative_to(ROOT).as_posix(),
                            bytes=destination.stat().st_size, sha256=sha(destination)))
    for folder in ['standardized','task01','task02','task04']:
        for path in (args.first_three/'inputs'/folder).rglob('*'):
            if path.is_file(): copy(path,target/folder/path.relative_to(args.first_three/'inputs'/folder))
    for name in ['code','out']:
        for path in (args.first_three/name).rglob('*'):
            if path.is_file(): copy(path,target/'first_three'/name/path.relative_to(args.first_three/name))
    copy(args.first_three/'说明.md',target/'first_three/说明.md')
    panel=json.loads((target/'task01/panel_definition.json').read_text(encoding='utf-8'))
    devices=panel['panels'][0]['devices']
    for device in devices: copy(args.quality/(device+'.csv.gz'),target/'appliance_quality'/(device+'.csv.gz'))
    copy(ROOT/'task01/reports/split_manifest.json',target/'task01/split_manifest.json')
    copy(args.task03/'date_dimension.csv',target/'task03/date_dimension.csv')
    for name in ['task05_task06_实施分析_20261114.md','Task05_Task06_数据口径与审核节点.md']:
        copy(Path('E:/')/name,target/'requirements'/name)
    comparisons=[]
    for name in ['case_manifest.csv','case_minute_curves.csv.gz','case_hourly_curves.csv','case_quality_summary.csv','daily_extrema_times.csv','thresholds.json']:
        a=target/'task04'/name; b=args.task04/name
        comparisons.append(dict(file='task04/'+name, comparison='sha256',equal=sha(a)==sha(b)))
    for name in ['daily_panel13.csv','hourly_appliance.csv','hourly_panel13.csv']:
        a=target/'task02'/name; b=args.task02/name
        if sha(a)==sha(b): comparisons.append(dict(file='task02/'+name,comparison='sha256',equal=True))
        else:
            import pandas as pd
            aa=pd.read_csv(a,float_precision='round_trip');bb=pd.read_csv(b,float_precision='round_trip')
            common=[c for c in aa if c in bb]
            same=[c for c in common if c!='mean_power_kw']
            pd.testing.assert_frame_equal(aa[same],bb[same],check_exact=True)
            strict=aa.hour_complete
            pd.testing.assert_series_equal(aa.loc[strict,'mean_power_kw'],bb.loc[strict,'mean_power_kw'],check_exact=True)
            assert bb.loc[~strict,'mean_power_kw'].isna().all()
            differences=int((aa.loc[~strict,'mean_power_kw'].notna()).sum())
            copy(b,target/'task02_reference'/name)
            comparisons.append(dict(file='task02/'+name,comparison='strict_targets_and_other_common_columns_exact',equal=True,
                common_columns=common,extra_columns_other=[c for c in bb if c not in aa],
                inherited_incomplete_hour_mean_nonnull=differences,
                resolution='Preserve inherited file; gate mean_power_kw by hour_complete. Newer strict reference archived separately. No partial-hour value is a complete-hour target.'))
    assert all(x['equal'] for x in comparisons)
    record=dict(imported_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),files=records,source_comparisons=comparisons)
    (target/'import_manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print('PASS copied',len(records),'files;',len(comparisons),'cross-package comparisons')

if __name__=='__main__': main()
