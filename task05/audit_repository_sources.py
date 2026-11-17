"""核对自包含输入与仓库task01—04来源；显式记录版本差异。"""
from common import *


def main():
    mappings={'standardized':'data/standardized/cn_obee_v1_noimpute_v1.0.0',
              'appliance_quality':'data/standardized/cn_obee_v1_noimpute_v1.0.0/appliance_quality',
              'task01':'task01/reports','task02':'data/derived/task02',
              'task03':'data/derived/task03','task04':'data/derived/task04',
              'task02_reference':'data/derived/task02'}
    results=[]
    imported=json.loads((INPUT/'import_manifest.json').read_text(encoding='utf-8'))
    for entry in imported['files']:
        source=ROOT/entry['local_path']
        rel=source.relative_to(INPUT)
        if rel.parts[0] not in mappings:
            continue
        target=ROOT/mappings[rel.parts[0]]/Path(*rel.parts[1:])
        if rel.parts[0]=='task04' and rel.name in ['config.json','README.md','DATA_DICTIONARY.md']:
            target=ROOT/'task04'/rel.name
        if rel.as_posix()=='task04/verification_task04.json':
            target=ROOT/'task04/reports/verification.json'
        assert target.is_file(),str(target)
        identical=sha(source)==sha(target)
        comparison='identical_sha256'
        if not identical:
            if rel.as_posix()=='task02/hourly_panel13.csv':
                old=read(source);new=read(target)
                cols=[c for c in old if c in new and c!='mean_power_kw']
                pd.testing.assert_frame_equal(old[cols],new[cols],check_exact=True)
                strict=old.hour_complete
                pd.testing.assert_series_equal(old.loc[strict,'mean_power_kw'],new.loc[strict,'mean_power_kw'],check_exact=True)
                assert new.loc[~strict,'mean_power_kw'].isna().all()
                comparison='strict_hour_targets_exact; four_legacy_partial_means_not_used'
            elif rel.parts[0]=='task04' and rel.name in ['config.json','README.md','DATA_DICTIONARY.md',
                                                                      'derivation_manifest.json','verification_task04.json']:
                # task04的仓库适配版更新了版本、路径及记录；全部实际派生表在其他行逐字节核对。
                comparison='archived_task04_v1.0.0_metadata_vs_repository_v1.0.1; derived_data_checked_separately'
            else:
                raise AssertionError('Unexpected source difference: '+str(rel))
        results.append(dict(input=entry['local_path'],repository_path=target.relative_to(ROOT).as_posix(),
                            input_sha256=sha(source),repository_sha256=sha(target),comparison=comparison,passed=True))
    assert len(results)==39
    write_json(OUT/'repository_source_audit.json',dict(generated_at=now(),all_pass=True,
               repository_baseline='88bf9752227f05b526e80ce15b7392845fd0dbe7',files=results))
    print('PASS 39 repository source comparisons; task04 data unchanged, legacy partial-hour means gated')


if __name__=='__main__':
    main()
