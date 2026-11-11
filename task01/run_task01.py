"""Reproducible CN-OBEE v1 audit. Raw files are opened read-only.

Usage (from project root): python task01/run_task01.py
Staging: python task01/run_task01.py --raw-root ORIGINAL/data/raw
No network, interpolation, smoothing, scaling, or model fitting is performed.
"""
import argparse
import gc
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(__file__).with_name('config.json')
C = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
VERSION = C['data_version']
TZ = C['timezone']
STD = ROOT / 'data/standardized' / VERSION
REPORT = ROOT / 'task01/reports'
APPLIANCES = {
    'electric kettle': ('electric_kettle_w', '电水壶', 'living_room (publisher notebook grouping)'),
    'fridge': ('fridge_w', '冰箱', 'kitchen'),
    'rice cooker': ('rice_cooker_w', '电饭煲', 'kitchen'),
    'computer': ('computer_w', '电脑', 'home_office'),
    'TV': ('tv_w', '电视', 'living_room'),
    'upstairs water heater': ('upstairs_water_heater_w', '楼上热水器', 'upstairs'),
    'downstairs water heater': ('downstairs_water_heater_w', '楼下热水器', 'downstairs'),
    'washing machine': ('washing_machine_w', '洗衣机', 'unconfirmed_room'),
    **{f'air conditioner#{i}': (f'air_conditioner_{i}_w', f'空调{i}', room) for i, room in enumerate(
        ['master_bedroom', 'secondary_bedroom', 'cloakroom', 'home_office', 'living_room', 'kitchen'], 1)},
}
ENV = {
    'dry-bulb temperature (°C)': ('temperature_c', '干球温度', 'degC', 'numeric'),
    'relative humidity (%)': ('relative_humidity_pct', '相对湿度', '%', 'numeric'),
    'air pressure (Pa)': ('air_pressure_pa', '室内气压', 'Pa', 'numeric'),
    'window state (0/1)': ('window_state', '窗状态的分钟发布值', '0..1', 'window'),
    'east window state (0/1)': ('east_window_state', '东窗状态的分钟发布值', '0..1', 'window'),
    'occupancy presence (0/1)': ('motion_detected', '该分钟检测到运动', '0/1', 'motion'),
    'atmospheric pressure (hPa)': ('atmospheric_pressure_hpa', '室外大气压', 'hPa', 'numeric'),
    'wind speed (m/s)': ('wind_speed_ms', '风速', 'm/s', 'numeric'),
    'wind direction': ('wind_direction_raw', '风向原发布记号，PPC含义未确认', 'degree if numeric', 'category'),
    'ground temperature (°C)': ('ground_temperature_c', '地面温度', 'degC', 'numeric'),
    'horizontal total solar radiation intensity (W/m2)': ('solar_total_wm2', '水平面总太阳辐射强度', 'W/m2', 'numeric'),
    'horizontal diffuse solar radiation intensity (W/m2)': ('solar_diffuse_wm2', '水平面散射太阳辐射强度', 'W/m2', 'numeric'),
}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def jsave(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False), encoding='utf-8')


def csvsave(df, path, index=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    compression = {'method': 'gzip', 'compresslevel': 3, 'mtime': 0} if path.suffix == '.gz' else None
    df.to_csv(path, index=index, encoding='utf-8', na_rep='', compression=compression)


def runs(mask):
    a = np.asarray(mask, dtype=bool)
    edges = np.diff(np.r_[False, a, False].astype(np.int8))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def longest(mask):
    return max((e - b for b, e in runs(mask)), default=0)


def print_stage(message):
    print(message, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-root', type=Path, default=ROOT / 'data/raw')
    args = parser.parse_args()
    raw = args.raw_root.resolve()
    started = datetime.now(timezone.utc).isoformat()
    STD.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((raw / 'source_manifest.json').read_text(encoding='utf-8-sig'))
    dictionary, structures, audits, gaps, anomalies, checks = [], [], [], [], [], []
    coverage_h, coverage_d, coverage_m, coverage_y, coverage_all, env_coverage = [], [], [], [], [], []
    modified, category_records, qc_summary = [], [], []
    power = None

    def check(name, ok, detail):
        checks.append(dict(check=name, passed=bool(ok), detail=detail))
        if not ok:
            csvsave(pd.DataFrame(checks), REPORT / 'acceptance_checks.csv')
            raise AssertionError(f'{name}: {detail}')

    archive = raw / manifest['archive']['relative_path']
    check('archive_sha256', sha(archive) == manifest['archive']['sha256'], sha(archive))
    import zipfile
    with zipfile.ZipFile(archive) as z:
        check('archive_crc', z.testzip() is None, 'Every archive entry CRC checked')

    for item in manifest['files']:
        path = raw / item['relative_path']
        digest = sha(path)
        check(f"source_sha256:{path.name}", digest == item['sha256'], digest)
        print_stage(f'Reading {path.name}')
        tokens = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8')
        source_time = tokens.pop('time')
        time = pd.DatetimeIndex(pd.to_datetime(source_time, format='%Y-%m-%d %H:%M:%S', errors='coerce')).tz_localize(TZ)
        freq = 'h' if path.name == 'Outdoor_weather.csv' else 'min'
        step = 60 if freq == 'h' else 1
        duplicate_n = int(time.duplicated().sum())
        invalid_n = int(time.isna().sum())
        aligned = bool((time == time.floor(freq)).all()) if not invalid_n else False
        grid = pd.date_range(time.min(), time.max(), freq=freq, name='timestamp')
        absent = int(len(grid.difference(time)))
        audit = dict(source_file=path.name, rows=len(tokens), columns=len(tokens.columns) + 1,
                     first_timestamp=str(time.min()), last_timestamp_inclusive=str(time.max()),
                     expected_grid_rows=len(grid), missing_grid_rows=absent,
                     unparseable_times=invalid_n, duplicate_timestamps=duplicate_n,
                     conflict_timestamps=duplicate_n, off_grid_rows=int((time != time.floor(freq)).sum()),
                     sorted=bool(time.is_monotonic_increasing), timezone=TZ, frequency=freq)
        audits.append(audit)
        # Release-pinned audit: refuse to silently resolve an unexpected version's conflicts.
        check(f'time_index:{path.name}', not invalid_n and not duplicate_n and aligned and time.is_monotonic_increasing,
              'Unique, parseable, sorted, aligned. Unexpected timestamp defects require explicit new rules.')
        check(f'grid_completeness:{path.name}', absent == 0, f'{absent} missing source rows')
        source_ids = np.arange(2, len(tokens) + 2, dtype=np.int64)  # 1-based physical CSV lines including header.
        frame = pd.DataFrame(index=grid)
        quality = pd.DataFrame(index=grid)
        frame['source_file'] = path.name
        frame['source_row_id'] = source_ids
        frame['source_time'] = source_time.to_numpy()
        frame['source_present'] = True
        quality['source_row_id'] = source_ids
        numeric = pd.DataFrame(index=grid)
        token_missing_counts = {}

        dictionary.append(dict(source_file=path.name, source_column='time', standard_column='timestamp',
            meaning_zh='北京时间时间戳', object=path.stem, unit=TZ, dtype='datetime with offset',
            quantity_kind='time', source_sampling=freq, upstream_processing='publisher regularized',
            time_semantics='local Beijing time; minute label starts [t,t+1min); weather hourly interval unconfirmed',
            valid_rule='parse exactly; no UTC reinterpretation', unit_conversion='none'))
        for col in tokens:
            t = tokens[col]
            missing = t.str.strip().str.lower().isin(['', 'nan', 'na', 'null', 'none'])
            v = pd.to_numeric(t.mask(missing), errors='coerce').astype(float).to_numpy()
            nonfinite = ~np.isfinite(v) & ~missing.to_numpy()
            flags = np.where(missing, 1, 0).astype(np.uint16)
            flags[nonfinite] |= 4
            invalid = nonfinite.copy()
            is_power = path.name == 'Power.csv'
            if is_power:
                name, meaning, location = APPLIANCES[col]
                kind, unit = 'power', 'W'
                limit = C['sensor_limits_w']['air_conditioner_and_water_heater' if ('air conditioner' in col or 'water heater' in col) else 'other']
                bad_range = np.isfinite(v) & ((v < 0) | (v > limit))
                flags[bad_range] |= 8
                invalid |= bad_range
                near = np.isfinite(v) & (v >= C['near_limit_review_fraction'] * limit) & ~bad_range
                flags[near] |= 16
                for b, e in runs(near):
                    anomalies.append(dict(source_file=path.name, variable=name, reason='near_sensor_limit_review',
                        start=str(grid[b]), end_exclusive=str(grid[e-1] + pd.Timedelta(minutes=step)),
                        duration_minutes=(e-b)*step, value=float(v[b]), action='retain'))
                # Retrospective descriptive flags only. They are not model features or deletion rules.
                equal = np.r_[False, (v[1:] == v[:-1]) & np.isfinite(v[1:])]
                boundaries = np.r_[0, np.flatnonzero(~equal)[1:], len(v)]
                for b, e in zip(boundaries[:-1], boundaries[1:]):
                    if (e-b) * step >= C['constant_review_minutes'] and np.isfinite(v[b]):
                        flags[b:e] |= 32
                        anomalies.append(dict(source_file=path.name, variable=name, reason='long_constant_review',
                            start=str(grid[b]), end_exclusive=str(grid[e-1] + pd.Timedelta(minutes=step)),
                            duration_minutes=(e-b)*step, value=float(v[b]), action='retain; event-driven/upstream-held values possible'))
                valid_rule = f'0 <= power <= {limit} W; paper Table 2; near-limit/constant flags retain value'
                upstream = 'minute mean; forward-held by publisher; some AC off periods zero-filled; point identity unknown'
            else:
                name, meaning, unit, kind = ENV[col]
                location = path.stem
                bad_range = np.zeros(len(v), dtype=bool)
                if kind == 'category':
                    flags[nonfinite] = 128  # Preserve unexplained category, not a fabricated numeric value.
                    invalid = nonfinite
                    for token, count in t[nonfinite].value_counts().items():
                        category_records.append(dict(source_file=path.name, source_column=col, token=token,
                            count=int(count), action='preserve raw; numeric direction unavailable; semantic unconfirmed'))
                    frame['wind_direction_deg'] = v
                    valid_rule = 'raw token retained; numeric projection only when parseable; PPC unresolved'
                else:
                    if 'humidity' in name:
                        bad_range = np.isfinite(v) & ((v < 0) | (v > 100))
                    elif kind in ('window', 'motion'):
                        bad_range = np.isfinite(v) & ((v < 0) | (v > 1))
                        fractional = np.isfinite(v) & (v > 0) & (v < 1)
                        if kind == 'window':
                            flags[fractional] |= 64
                        else:
                            bad_range |= fractional
                    flags[bad_range] |= 8
                    invalid |= bad_range
                    valid_rule = 'finite; humidity 0..100; motion 0/1; window minute means 0..1, fractions retained'
                upstream = 'motion: any trigger=1, normal gaps=0; window/environment: minute mean and publisher forward hold; per-point provenance unknown'
            usable = v.copy()
            usable[invalid] = np.nan
            if kind == 'category':
                frame[name] = t.to_numpy()
            else:
                frame[name] = usable
            numeric[name] = usable
            quality[name + '_qc_bits'] = flags
            qc_summary.append(dict(source_file=path.name, entity=name, source_positions=len(v),
                source_nonempty_positions=int((~missing).sum()), usable_numeric_positions=int(np.isfinite(usable).sum()),
                zero_positions=int((usable == 0).sum()), minimum=float(np.nanmin(usable)) if np.isfinite(usable).any() else None,
                maximum=float(np.nanmax(usable)) if np.isfinite(usable).any() else None,
                **{flag + '_count': int(((flags & bit) != 0).sum()) for flag, bit in C['qc_bits'].items()},
                new_imputed_positions=0))
            if invalid.any():
                for n in np.flatnonzero(invalid):
                    modified.append(dict(source_file=path.name, source_row_id=int(source_ids[n]),
                        variable=name, source_token=t.iloc[n], reason='unresolved_category' if kind == 'category' else 'numeric_or_physical_invalid',
                        action='raw retained; numeric usable_value unavailable'))
            dictionary.append(dict(source_file=path.name, source_column=col, standard_column=name,
                meaning_zh=meaning, object=location, unit=unit, dtype='string' if kind == 'category' else 'float64',
                quantity_kind=kind, source_sampling=freq, upstream_processing=upstream,
                time_semantics=C['minute_semantics'] if is_power else ('hourly; averaging interval unconfirmed' if freq == 'h' else 'published minute'),
                valid_rule=valid_rule, unit_conversion='none; hPa and Pa intentionally kept distinct'))
            for b, e in runs(~np.isfinite(usable)):
                gaps.append(dict(source_file=path.name, entity=name, reason='unresolved_category' if kind == 'category' and np.any(nonfinite[b:e]) else 'source_value_missing_or_invalid',
                    start=str(grid[b]), last_missing_timestamp=str(grid[e-1]),
                    end_exclusive=str(grid[e-1] + pd.Timedelta(minutes=step)),
                    missing_positions=e-b, duration_minutes=(e-b)*step,
                    gap_group='short_le_2min' if (e-b)*step <= C['short_gap_max_minutes'] else 'long_gt_2min'))
            token_missing_counts[col] = t[missing].value_counts(dropna=False).to_dict()
            if is_power:
                q = pd.DataFrame(dict(timestamp=grid, appliance_id=name, source_file=path.name,
                    source_row_id=source_ids, source_time=source_time.to_numpy(), source_token=t.to_numpy(),
                    source_value=v, usable_value=usable, source_present=True, is_usable=np.isfinite(usable),
                    qc_bits=flags, upstream_fill_status='unknown', is_new_imputed=False))
                labels = {int(bit): '|'.join(k for k, b in C['qc_bits'].items() if bit & b) or 'published_value_usable' for bit in np.unique(flags)}
                q['qc_flags'] = pd.Series(flags).map(labels).to_numpy()
                csvsave(q, STD / 'appliance_quality' / f'{name}.csv.gz')
                del q
            else:
                valid = pd.Series(np.isfinite(usable), index=grid)
                # Auxiliary coverage never filters the independent power timeline.
                for period, part in valid.resample('MS'):
                    env_coverage.append(dict(source_file=path.name, entity=name, month=str(period),
                        expected_positions=len(part), usable_positions=int(part.sum()),
                        coverage=float(part.mean()), step_minutes=step))
        structure = dict(audit, encoding='utf-8 (strict)', delimiter=',', file_size_bytes=path.stat().st_size,
                         sha256=digest, missing_token_counts=token_missing_counts)
        structures.append(structure)
        if path.name == 'Outdoor_weather.csv':
            dictionary.append(dict(source_file=path.name, source_column='wind direction', standard_column='wind_direction_deg',
                meaning_zh='从原风向记号严格数值解析得到的投影，无法解析时为空', object='Outdoor_weather', unit='degree',
                dtype='float64', quantity_kind='derived_numeric_projection', source_sampling='h',
                upstream_processing='original tokens preserved in wind_direction_raw',
                time_semantics='hourly; averaging interval unconfirmed', valid_rule='numeric parse only; PPC not guessed', unit_conversion='none'))
        quality['upstream_fill_status'] = 'unknown'
        quality['is_new_imputed'] = False
        filename = 'power_minute.csv.gz' if path.name == 'Power.csv' else f'{path.stem.lower()}.csv.gz'
        csvsave(frame, STD / filename, index=True)
        if not is_power:
            csvsave(quality, STD / 'auxiliary_quality' / filename, index=True)
        if path.name == 'Power.csv':
            power = numeric
        del tokens, frame, quality, numeric
        gc.collect()

    assert power is not None
    start, last = power.index[0], power.index[-1]
    # Complete file-boundary natural days; final single midnight belongs to no complete new day.
    begin = start.ceil('D')
    E = last.floor('D') + (pd.Timedelta(days=1) if last.time().hour == 23 and last.time().minute == 59 else pd.Timedelta(0))
    analysis = power.loc[(power.index >= begin) & (power.index < E)]
    panels = {'panel13': [c for c in power if c != 'rice_cooker_w'], 'panel14': list(power.columns)}
    masks = {c: analysis[c].notna() for c in analysis}
    published_masks = {c: analysis[c].notna() for c in analysis}  # Verified below: no power values modified.
    panel_frames, strict_hour_frames, strict_day_frames, panel_info = [], [], [], []
    for panel_id, cols in panels.items():
        complete = power[cols].notna().all(axis=1)
        n = power[cols].notna().sum(axis=1)
        available = power[cols].sum(axis=1, min_count=1)
        value = available.where(complete)
        panel_frames.append(pd.DataFrame(dict(timestamp=power.index, panel_id=panel_id,
            panel_version=C['panel_version'], n_expected=len(cols), n_usable=n.to_numpy(),
            panel_complete=complete.to_numpy(), panel_power_w=value.to_numpy(), available_sum_w=available.to_numpy())))
        masks[panel_id] = complete.loc[analysis.index]
        published_masks[panel_id] = masks[panel_id]
        for b, e in runs(~masks[panel_id]):
            gaps.append(dict(source_file='Power.csv', entity=panel_id, reason='one_or_more_required_appliances_unusable',
                start=str(analysis.index[b]), last_missing_timestamp=str(analysis.index[e-1]),
                end_exclusive=str(analysis.index[e-1] + pd.Timedelta(minutes=1)), missing_positions=e-b,
                duration_minutes=e-b, gap_group='short_le_2min' if e-b <= 2 else 'long_gt_2min'))
        x = value.loc[analysis.index]
        hourly = x.resample('h').agg(['count', 'sum'])
        hourly['sum'] = x.resample('h').sum(min_count=1)
        hourly['panel_id'] = panel_id
        hourly['expected_minutes'] = 60
        hourly['coverage'] = hourly['count'] / 60
        hourly['hour_complete'] = hourly['count'] == 60
        hourly['valid_duration_energy_kwh'] = hourly['sum'] / 60000
        hourly['energy_kwh'] = hourly['valid_duration_energy_kwh'].where(hourly['hour_complete'])
        hourly['mean_power_kw'] = hourly['energy_kwh']
        hourly = hourly.rename(columns={'count': 'usable_minutes'}).drop(columns='sum')
        hourly.index.name = 'timestamp'
        strict_hour_frames.append(hourly.reset_index())
        daily = pd.DataFrame(index=x.resample('D').count().index)
        daily['panel_id'] = panel_id
        daily['valid_hours'] = hourly['hour_complete'].resample('D').sum()
        daily['expected_hours'] = 24
        daily['day_complete'] = daily['valid_hours'] == 24
        daily['valid_minutes'] = x.resample('D').count()
        daily['coverage'] = daily['valid_minutes'] / 1440
        daily['valid_duration_energy_kwh'] = x.resample('D').sum(min_count=1) / 60000
        daily['energy_kwh'] = daily['valid_duration_energy_kwh'].where(daily['day_complete'])
        daily['mean_power_kw'] = daily['energy_kwh'] / 24
        daily.index.name = 'date'
        strict_day_frames.append(daily.reset_index())
        good = complete[complete].index
        panel_info.append(dict(panel_id=panel_id, panel_version=C['panel_version'], devices=cols,
            target_name='固定监测面板总负荷', independent_whole_home_meter=False,
            analysis_start=str(begin), analysis_end_exclusive=str(E),
            first_common_valid=str(good.min()), last_common_valid_inclusive=str(good.max()),
            admission_coverage=float(masks[panel_id].mean()),
            admitted_as_main=panel_id == 'panel13' and masks[panel_id].mean() >= C['coverage_admission'],
            strict_complete_days=int(daily['day_complete'].sum()), strict_complete_hours=int(hourly['hour_complete'].sum()),
            rule='all listed devices usable; otherwise panel missing; available_sum_w diagnostic only'))
        # Independently re-sum individual device integrals within exactly the same complete hours/days.
        sums = analysis[cols].resample('h').sum(min_count=1).sum(axis=1) / 60000
        hvalid = hourly['hour_complete']
        herror = float((sums[hvalid] - hourly.loc[hvalid, 'energy_kwh']).abs().max())
        dvalid = daily['day_complete']
        dfromh = hourly['energy_kwh'].resample('D').sum(min_count=24)
        derror = float((dfromh[dvalid] - daily.loc[dvalid, 'energy_kwh']).abs().max())
        check(f'appliance_vs_panel_hourly:{panel_id}', herror <= C['absolute_tolerance_kwh'], f'max absolute error {herror} kWh')
        check(f'minute_vs_hour_vs_day:{panel_id}', derror <= C['absolute_tolerance_kwh'], f'max absolute error {derror} kWh')
        check(f'panel_missing_rule:{panel_id}', value[~complete].isna().all() and available[n == 0].isna().all(), 'Incomplete panel missing, all-missing diagnostic missing')

    print_stage('Computing hourly/daily/monthly/yearly coverage')
    for entity, usable in masks.items():
        vals = analysis[entity] if entity in analysis else analysis[panels[entity]].sum(axis=1, min_count=len(panels[entity]))
        pub = published_masks[entity]
        allrow = dict(entity=entity, expected_minutes=len(usable), usable_minutes=int(usable.sum()),
            published_nonempty_minutes=int(pub.sum()), published_nonempty_rate=float(pub.mean()),
            usable_rate=float(usable.mean()), longest_gap_minutes=longest(~usable),
            zero_minutes=int((vals == 0).sum()), zero_rate_among_usable=float((vals == 0).sum()/usable.sum()) if usable.sum() else None,
            first_usable=str(vals.first_valid_index()), last_usable=str(vals.last_valid_index()), new_imputed_count=0,
            scope='complete_calendar_span; final singleton excluded')
        coverage_all.append(allrow)
        for freq, destination, label, full_expected in [('h', coverage_h, 'hour', 60), ('D', coverage_d, 'day', 1440), ('MS', coverage_m, 'month', None), ('YS', coverage_y, 'year', None)]:
            for period, part in usable.resample(freq):
                expected = full_expected or (period.days_in_month * 1440 if freq == 'MS' else (366 if period.is_leap_year else 365)*1440)
                valid_n = int(part.sum())
                row = dict(entity=entity, period_start=str(period), period_type=label,
                    expected_minutes_in_span=len(part), full_calendar_expected_minutes=expected,
                    file_boundary_complete=len(part) == expected, usable_minutes=valid_n,
                    published_nonempty_rate=valid_n/len(part), usable_rate=valid_n/len(part),
                    longest_gap_minutes=longest(~part), strict_period_complete=len(part) == expected and valid_n == expected,
                    new_imputed_minutes=0, exclusion_reason='' if len(part) == expected and valid_n == expected else ('file_boundary_partial;' if len(part) != expected else '') + ('missing_required_values' if valid_n != len(part) else ''))
                destination.append(row)

    h = pd.concat(strict_hour_frames, ignore_index=True)
    d = pd.concat(strict_day_frames, ignore_index=True)
    panel_minutes = pd.concat(panel_frames, ignore_index=True)
    csvsave(panel_minutes, STD / 'panel_minute.csv.gz')
    csvsave(h, REPORT / 'strict_hourly_check.csv')
    csvsave(d, REPORT / 'strict_daily_check.csv')
    for name, records in [('coverage_hourly.csv.gz', coverage_h), ('coverage_daily.csv', coverage_d),
                          ('coverage_monthly.csv', coverage_m), ('coverage_yearly.csv', coverage_y),
                          ('coverage_overall.csv', coverage_all), ('auxiliary_coverage_monthly.csv', env_coverage),
                          ('qc_summary.csv', qc_summary),
                          ('gap_report.csv', gaps), ('data_dictionary.csv', dictionary),
                          ('time_index_audit.csv', audits), ('anomaly_report.csv', anomalies)]:
        csvsave(pd.DataFrame(records), REPORT / name)
    csvsave(pd.DataFrame(modified, columns=['source_file','source_row_id','variable','source_token','reason','action']), REPORT / 'value_change_log.csv')
    csvsave(pd.DataFrame(category_records, columns=['source_file','source_column','token','count','action']), REPORT / 'unresolved_categories.csv')
    for filename, cols in [('quarantine.csv', ['source_file','source_row_id','source_time','reason']),
                           ('duplicates.csv',['source_file','timestamp','kept_row','removed_row']),
                           ('conflicts.csv',['source_file','timestamp','variable','source_rows','source_values','resolution'])]:
        csvsave(pd.DataFrame(columns=cols), REPORT / filename)

    main_hour = h[h.panel_id == 'panel13'].set_index('timestamp')
    main_day = d[d.panel_id == 'panel13'].set_index('date')
    test_start = E - pd.Timedelta(days=C['test_days'])
    val_start = test_start - pd.Timedelta(days=C['validation_days'])
    origins = []
    for origin in pd.date_range(begin, E, freq='D', inclusive='left'):
        context = main_hour.loc[(main_hour.index >= origin - pd.Timedelta(days=7)) & (main_hour.index < origin)]
        target = main_hour.loc[(main_hour.index >= origin) & (main_hour.index < origin + pd.Timedelta(days=1))]
        history_ok = len(context) == 168 and bool(context['hour_complete'].all())
        target_ok = len(target) == 24 and bool(target['hour_complete'].all())
        previous_day = main_hour['mean_power_kw'].reindex(target.index - pd.Timedelta(days=1))
        previous_week = main_hour['mean_power_kw'].reindex(target.index - pd.Timedelta(days=7))
        pair_mask = target['mean_power_kw'].notna().to_numpy() & previous_day.notna().to_numpy() & previous_week.notna().to_numpy()
        split = 'test' if origin >= test_start else 'validation' if origin >= val_start else 'train'
        reasons = []
        if len(context) < 168: reasons.append('insufficient_7d_file_history')
        elif not history_ok: reasons.append('missing_history_hour')
        if not target_ok: reasons.append('missing_target_hour')
        origins.append(dict(origin=str(origin), split=split, history_hours_present=len(context),
            history_7d_complete=history_ok, target_complete=target_ok,
            usable_target_hours=int(target['hour_complete'].sum()), paired_baseline_valid_hours=int(pair_mask.sum()),
            conservative_eligible_origin=history_ok and target_ok,
            conservative_eligible_target_hours=24 if history_ok and target_ok else 0,
            exclusion_reasons=';'.join(reasons)))
    origin_frame = pd.DataFrame(origins)
    csvsave(origin_frame, REPORT / 'forecast_origin_quality.csv')
    split_summary = origin_frame.groupby('split', sort=False).agg(calendar_origins=('origin','size'),
        history_complete_origins=('history_7d_complete','sum'), full_target_origins=('target_complete','sum'),
        eligible_origins=('conservative_eligible_origin','sum'),
        eligible_target_hours=('conservative_eligible_target_hours','sum'),
        valid_target_hours=('usable_target_hours','sum'),
        paired_baseline_valid_hours=('paired_baseline_valid_hours','sum')).reset_index()
    csvsave(split_summary, REPORT / 'forecast_split_quality.csv')
    split_manifest = dict(timezone=TZ, data_version=VERSION, panel_id='panel13', panel_version=C['panel_version'],
        E=str(E), train=[str(begin), str(val_start)], validation=[str(val_start),str(test_start)], test=[str(test_start),str(E)],
        intervals='left-closed right-open; contiguous calendar days, no compression', release_time='D 00:00 Asia/Shanghai',
        required_history_hours=168, availability_assumption='previous hour final by D 00:00; publication latency unavailable, must be stated in task06',
        conservative_mask='previous 168 hourly targets and next 24 target hours all strict-valid; future feature selection not implemented',
        first_possible_origin=str(begin + pd.Timedelta(days=7)))
    jsave(REPORT / 'split_manifest.json', split_manifest)
    check('main_panel_95pct_admission', panel_info[0]['admitted_as_main'], panel_info[0]['admission_coverage'])
    check('test_8weeks_calendar', int((E-test_start).days) == 56, split_manifest['test'])
    check('test_has_eligible_origins', int(split_summary.loc[split_summary.split == 'test','eligible_origins'].iloc[0]) > 0, 'See forecast_split_quality.csv')
    power_changes = [r for r in modified if r['source_file'] == 'Power.csv']
    check('zero_new_imputation', not C['new_imputation'], 'No new filled cells')
    check('power_source_values_unchanged', len(power_changes) == 0, f'{len(power_changes)} power cells invalidated')
    # Verify every power cell in the saved wide table, including blanks and endpoint, after CSV round trip.
    saved = pd.read_csv(STD / 'power_minute.csv.gz', float_precision='round_trip')
    check('saved_power_numeric_roundtrip', np.array_equal(saved[list(power)].to_numpy(), power.to_numpy(), equal_nan=True), 'All 7,378,574 source power positions checked')
    check('saved_timezone_and_order', pd.DatetimeIndex(pd.to_datetime(saved.timestamp)).tz_convert(TZ).equals(power.index), 'Every saved timestamp checked')
    csvsave(pd.DataFrame(checks), REPORT / 'acceptance_checks.csv')
    jsave(REPORT / 'panel_definition.json', dict(main_panel='panel13', panel_version=C['panel_version'], panels=panel_info,
        selection_evidence='13-device joint coverage exceeds 95%; contains full calendar span and supports fixed forecast windows; 14-device supplementary only'))
    jsave(REPORT / 'source_manifest_audited.json', dict(original_manifest='data/raw/source_manifest.json',
        version=manifest['version'], doi=manifest['doi'], download_time_utc=manifest['downloaded_at_utc'],
        archive_sha256=sha(archive), files=structures, content_modified=False,
        support_manifest='data/raw/support/support_manifest.json', audit_status='completed'))
    summary = dict(data_version=VERSION, timezone=TZ, analysis_start=str(begin), analysis_end_exclusive=str(E),
        source_start_inclusive=str(start), source_end_inclusive=str(last), minute_grid_rows=len(power),
        analysis_minutes=len(analysis), calendar_days=int((E-begin).days),
        complete_day_counts={p['panel_id']:p['strict_complete_days'] for p in panel_info},
        complete_hour_counts={p['panel_id']:p['strict_complete_hours'] for p in panel_info},
        panel_coverage={p['panel_id']:p['admission_coverage'] for p in panel_info},
        gap_episode_count=len(gaps), anomaly_review_episodes=len(anomalies), modified_power_cells=len(power_changes),
        unresolved_category_records=category_records, new_imputed_cells=0,
        passed_checks=len(checks), split=split_manifest, split_quality=split_summary.to_dict('records'))
    jsave(REPORT / 'audit_summary.json', summary)
    jsave(REPORT / 'processing_log.json', dict(started_at_utc=started, finished_at_utc=datetime.now(timezone.utc).isoformat(),
        pipeline_version='1.0.0', pipeline_sha256=sha(Path(__file__)), config_sha256=sha(CONFIG_PATH),
        python=platform.python_version(), pandas=pd.__version__, numpy=np.__version__,
        source_root=str(raw), output_root=str(ROOT), data_version=VERSION,
        actions=['sha256 and archive CRC verification','strict UTF-8 parsing','localize Asia/Shanghai',
                 'retain all source grid rows and every appliance','no interpolation/no scaling/no smoothing',
                 'physical-bound QC; constant/near-limit descriptive flags retained',
                 'independent auxiliary data; preserve PPC wind-direction token',
                 'fixed 13/14 panels','strict approximate energy audit only','fixed calendar forecast masks',
                 'full saved power numeric and timestamp round-trip check'],
        observed_time_defects=0, new_imputed_cells=0, source_unchanged=True))
    # Inventory is reproducible and lets downstream tasks verify the exact frozen artifacts.
    output_files = sorted([p for p in STD.rglob('*') if p.is_file()] + [p for p in REPORT.rglob('*') if p.is_file() and p.name != 'output_manifest.json'])
    jsave(REPORT / 'output_manifest.json', dict(data_version=VERSION, files=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'), size_bytes=p.stat().st_size, sha256=sha(p)) for p in output_files]))
    print_stage(json.dumps(summary, ensure_ascii=True))


if __name__ == '__main__':
    main()
