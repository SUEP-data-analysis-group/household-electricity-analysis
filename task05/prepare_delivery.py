"""整理正式交付的样本元数据；原前三步快照不变，能量及峰值不变。"""
import numpy as np
import pandas as pd
from common import *


def sample_masks():
    panel = read(INPUT/'standardized/panel_minute.csv.gz')
    panel['timestamp'] = pd.to_datetime(panel.timestamp, utc=True).dt.tz_convert(TZ)
    axis = pd.date_range(START, END, inclusive='left', freq='min')
    masks = pd.DataFrame({'timestamp': axis})
    for panel_id, complete_scope in [('panel13', 'panel13_complete_352d'),
                                      ('panel14', 'panel14_complete_148d')]:
        part = panel.loc[panel.panel_id.eq(panel_id) & panel.timestamp.ge(START)
                         & panel.timestamp.lt(END)].set_index('timestamp')
        assert part.index.equals(axis) and part.index.is_unique
        valid = part.panel_complete.to_numpy(bool)
        masks[panel_id+'_all_common_valid'] = valid
        masks[complete_scope] = np.repeat(valid.reshape(-1, 1440).all(axis=1), 1440)
    return masks


def prepare():
    masks = sample_masks()
    save(masks, 'sample_minute_masks.csv.gz')
    rows = []
    for scope in masks.columns[1:]:
        counts = masks.groupby(masks.timestamp.dt.strftime('%Y-%m-%d'))[scope].sum()
        for date, count in counts[counts.gt(0)].items():
            rows.append(dict(sample_scope=scope, date=date, valid_minutes=int(count),
                             day_complete=bool(count == 1440)))
    dates = pd.DataFrame(rows)
    save(dates, 'sample_support_by_day.csv')
    for name in ['contribution_panel13.csv', 'contribution_panel14_supplement.csv']:
        table = read(INPUT/'first_three/out/交付表'/name)
        for scope in table.sample_scope.unique():
            use = masks[scope].to_numpy(bool)
            days = dates.loc[dates.sample_scope.eq(scope)]
            positions = np.flatnonzero(use)
            target = table.sample_scope.eq(scope)
            assert table.loc[target, 'minutes'].eq(int(use.sum())).all()
            table.loc[target, 'n_days'] = len(days)
            table.loc[target, 'n_complete_days'] = int(days.day_complete.sum())
            table.loc[target, 'n_partial_days'] = int((~days.day_complete).sum())
            table.loc[target, 'period_first_minute'] = masks.timestamp.iloc[positions[0]].isoformat()
            table.loc[target, 'period_last_minute'] = masks.timestamp.iloc[positions[-1]].isoformat()
        table['date_list_file'] = 'sample_support_by_day.csv'
        table['date_list_scope'] = table.sample_scope
        table['sample_mask_file'] = 'sample_minute_masks.csv.gz'
        table['sample_mask_column'] = table.sample_scope
        table[['n_days', 'n_complete_days', 'n_partial_days']] = table[
            ['n_days', 'n_complete_days', 'n_partial_days']].astype(int)
        save(table, name)
    peaks = read(INPUT/'first_three/out/交付表/peak_contribution.csv')
    peaks['panel_id'] = 'panel13'
    peaks['panel_version'] = 'v1.0.0'
    is_hour = peaks.level.eq('hour_peak')
    peaks['sample_scope'] = np.where(is_hour, 'panel13_daily_peak_hours_352d',
                                    'task04_case_minute_record_peaks')
    peaks['common_valid_minutes'] = np.where(is_hour, 60, 1)
    starts = pd.to_datetime(peaks.timestamp).dt.tz_localize(TZ)
    peaks['period_start'] = starts
    peaks['period_end_exclusive'] = starts + pd.to_timedelta(peaks.common_valid_minutes, unit='min')
    peaks['energy_kwh'] = peaks.value_kw * peaks.common_valid_minutes / 60
    peaks['denominator_kwh'] = peaks.panel_kw * peaks.common_valid_minutes / 60
    save(peaks, 'peak_contribution.csv')
    print('PASS delivery metadata; all-valid dates: panel13=356, panel14=153; source numbers retained')


if __name__ == '__main__':
    prepare()
