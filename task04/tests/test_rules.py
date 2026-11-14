"""Analytical edge cases for the production rules, independent of real outcomes."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from run_task04 import build_daily,build_changes,fit_thresholds,choose_cases

TZ='Asia/Shanghai'

def one_day(values):
    date=pd.Timestamp('2021-08-02',tz=TZ)
    times=pd.date_range(date,periods=24,freq='h')
    h=pd.DataFrame(dict(timestamp=times,mean_power_kw=values,hour_complete=True))
    d=pd.DataFrame(dict(date=[date],day_complete=[True],energy_kwh=[float(np.sum(values))]))
    dim=pd.DataFrame(dict(date=[date],natural_day_type=['weekday'],actual_day_type=['actual_workday']))
    return h,d,dim

class RuleTests(unittest.TestCase):
    def test_exact_ties_keep_all_and_share_weight(self):
        h,d,dim=one_day(np.array([1.,1.]+[.25]*22))
        result,ext,freq=build_daily(h,d,dim)
        self.assertEqual(result.peak_tied_count.iloc[0],2)
        self.assertEqual(ext.loc[ext.kind.eq('peak'),'hour'].tolist(),[0,1])
        self.assertTrue(ext.loc[ext.kind.eq('peak'),'weight'].eq(.5).all())
        self.assertAlmostEqual(freq.loc[freq.kind.eq('valley'),'proportion'].sum(),1)

    def test_close_values_are_not_rounded_into_ties(self):
        h,d,dim=one_day(np.array([np.nextafter(1.,2.),1.]+[.25]*22))
        result,ext,_=build_daily(h,d,dim)
        self.assertEqual(result.peak_tied_count.iloc[0],1)
        self.assertEqual(ext.loc[ext.kind.eq('peak'),'hour'].tolist(),[0])

    def test_zero_peak_is_undefined_load_factor(self):
        h,d,dim=one_day(np.zeros(24))
        result,ext,freq=build_daily(h,d,dim)
        self.assertTrue(np.isnan(result.load_factor.iloc[0]))
        self.assertEqual(len(ext),48)
        self.assertTrue(ext.tied_count.eq(24).all())
        self.assertAlmostEqual(freq.loc[freq.kind.eq('peak'),'weighted_days'].sum(),1)

    def test_incomplete_day_does_not_become_a_daily_extreme(self):
        h,d,dim=one_day(np.arange(24,dtype=float))
        broken=h.copy();broken.timestamp+=pd.Timedelta(days=1)
        broken.loc[0,'hour_complete']=False;broken.loc[0,'mean_power_kw']=np.nan
        dd=pd.concat([d,d.assign(date=d.date+pd.Timedelta(days=1),day_complete=False,energy_kwh=np.nan)])
        dm=pd.concat([dim,dim.assign(date=dim.date+pd.Timedelta(days=1))])
        result,ext,_=build_daily(pd.concat([h,broken]),dd,dm)
        self.assertEqual(len(result),1);self.assertEqual(ext.date.nunique(),1)

    def test_non_adjacent_timestamps_never_subtract(self):
        times=pd.DatetimeIndex([pd.Timestamp('2021-08-02',tz=TZ)+pd.Timedelta(hours=i) for i in [0,1,3,4]])
        result=build_changes(pd.DataFrame(dict(timestamp=times,mean_power_kw=[1.,2.,99.,100.],hour_complete=True)))
        self.assertEqual(result.valid_change.tolist(),[False,True,False,True])
        self.assertTrue(np.isnan(result.delta_kw.iloc[2]))
        self.assertEqual(result.exclusion_reason.iloc[2],'non_adjacent_timestamp')

    def test_invalid_hours_break_both_edges(self):
        times=pd.date_range('2021-08-02',periods=4,freq='h',tz=TZ)
        result=build_changes(pd.DataFrame(dict(timestamp=times,mean_power_kw=[1.,np.nan,5.,9.],hour_complete=[True,False,True,True])))
        self.assertEqual(result.valid_change.tolist(),[False,False,False,True])
        self.assertEqual(result.delta_kw.iloc[3],4.)

    def test_midnight_is_valid_but_not_intra_day(self):
        times=pd.date_range('2021-08-02 23:00',periods=2,freq='h',tz=TZ)
        result=build_changes(pd.DataFrame(dict(timestamp=times,mean_power_kw=[1.,2.],hour_complete=True)))
        self.assertTrue(result.valid_change.iloc[1]);self.assertTrue(result.is_cross_midnight.iloc[1])
        self.assertFalse(result.is_intra_day.iloc[1])

    def test_threshold_excludes_both_out_of_training_endpoints(self):
        origin=pd.Timestamp('2021-08-02',tz=TZ)
        times=pd.date_range(origin-pd.Timedelta(hours=1),periods=5,freq='h')
        h=pd.DataFrame(dict(timestamp=times,mean_power_kw=[999.,0.,1.,2.,10000.],hour_complete=True))
        threshold=fit_thresholds(h,build_changes(h),{'train':[origin.isoformat(),(origin+pd.Timedelta(hours=3)).isoformat()]})
        self.assertEqual(threshold['train_change_pairs'],2)
        self.assertEqual(threshold['train_abs_hour_change_q95_kw'],1.)
        self.assertAlmostEqual(threshold['train_hourly_load_q90_kw'],1.8)

    def test_case_selection_ties_choose_earliest_date(self):
        dates=pd.date_range('2021-08-01','2021-08-31',tz=TZ)
        d=pd.DataFrame(dict(date=dates,day_complete=True))
        metrics=pd.DataFrame(dict(date=dates,year_month='2021-08',
            natural_day_type=np.where(dates.weekday<5,'weekday','weekend'),energy_kwh=1.,peak_kw=2.))
        cases=choose_cases(metrics,d)
        self.assertEqual(cases.date.dt.strftime('%Y-%m-%d').tolist(),['2021-08-02','2021-08-01','2021-08-01','2021-08-01'])

if __name__=='__main__':unittest.main()
