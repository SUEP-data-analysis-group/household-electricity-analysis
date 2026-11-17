"""从设备有效性独立重建正式交付样本，不调用交付整理函数。"""
import numpy as np
import pandas as pd
from common import *


def verify_delivery(power, valid, main_mask):
    rice=read(INPUT/'standardized/power_minute.csv.gz',usecols=['rice_cooker_w']).iloc[:len(power),0]
    p13=valid.all(axis=1).to_numpy()
    p14=p13 & np.isfinite(rice.to_numpy())
    expected={'panel13_all_common_valid':p13,
              'panel13_complete_352d':main_mask,
              'panel14_all_common_valid':p14,
              'panel14_complete_148d':np.repeat(p14.reshape(-1,1440).all(axis=1),1440)}
    actual=read(OUT/'sample_minute_masks.csv.gz')
    times=pd.DatetimeIndex(pd.to_datetime(actual.timestamp,utc=True).dt.tz_convert(TZ))
    assert times.equals(power.index) and times.is_unique
    assert set(actual.columns)=={'timestamp'}|set(expected)
    days=read(OUT/'sample_support_by_day.csv')
    assert not days.duplicated(['sample_scope','date']).any()
    assert set(days.sample_scope)==set(expected)
    for scope,mask in expected.items():
        assert np.array_equal(actual[scope],mask),scope
        counts=pd.Series(mask,index=power.index.strftime('%Y-%m-%d')).groupby(level=0).sum()
        counts=counts[counts.gt(0)]
        got=days[days.sample_scope.eq(scope)].set_index('date').sort_index()
        assert got.index.tolist()==counts.index.tolist()
        assert np.array_equal(got.valid_minutes,counts)
        assert np.array_equal(got.day_complete,counts.eq(1440))
    for name in ['contribution_panel13.csv','contribution_panel14_supplement.csv']:
        table=read(OUT/name)
        for (panel_id,scope),part in table.groupby(['panel_id','sample_scope']):
            mask=expected[scope]
            ds=days[days.sample_scope.eq(scope)]
            assert part.minutes.eq(mask.sum()).all()
            assert part.n_days.eq(len(ds)).all()
            assert part.n_complete_days.eq(ds.day_complete.sum()).all()
            assert part.n_partial_days.eq((~ds.day_complete).sum()).all()
            assert part.date_list_file.eq('sample_support_by_day.csv').all()
            assert part.date_list_scope.eq(scope).all()
            assert part.sample_mask_file.eq('sample_minute_masks.csv.gz').all()
            assert part.sample_mask_column.eq(scope).all()
            selected=power.index[mask]
            assert pd.to_datetime(part.period_first_minute).eq(selected[0]).all()
            assert pd.to_datetime(part.period_last_minute).eq(selected[-1]).all()
    peaks=read(OUT/'peak_contribution.csv')
    hour=peaks.level.eq('hour_peak')
    assert peaks.panel_id.eq('panel13').all()
    assert np.array_equal(peaks.common_valid_minutes,np.where(hour,60,1))
    assert np.array_equal(peaks.sample_scope,np.where(hour,'panel13_daily_peak_hours_352d','task04_case_minute_record_peaks'))
    starts=pd.to_datetime(peaks.period_start,utc=True)
    ends=pd.to_datetime(peaks.period_end_exclusive,utc=True)
    assert starts.equals(pd.to_datetime(peaks.timestamp).dt.tz_localize(TZ).dt.tz_convert('UTC').rename('period_start'))
    assert np.array_equal((ends-starts).dt.total_seconds()/60,peaks.common_valid_minutes)
    np.testing.assert_allclose(peaks.energy_kwh,peaks.value_kw*peaks.common_valid_minutes/60,rtol=1e-14,atol=1e-14)
    np.testing.assert_allclose(peaks.denominator_kwh,peaks.panel_kw*peaks.common_valid_minutes/60,rtol=1e-14,atol=1e-14)
    return ['exact_minute_masks_four_scopes','date_lists_include_partial_dates',
            'contribution_sample_metadata_matches_masks','peak_panel_scope_interval_and_energy_metadata']
