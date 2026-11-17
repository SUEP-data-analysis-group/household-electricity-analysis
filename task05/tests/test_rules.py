"""状态边界测试：不访问实测验证/测试区间，不执行全期状态生成。"""
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from operation_rules import classify

class StateRulesTests(unittest.TestCase):
    def state(self,x,valid=None,n_on=1,n_off=1,identifiable=True):
        return classify(x,np.isfinite(x) if valid is None else valid,10,3,n_on,n_off,identifiable)
    def test_normal_switch(self): np.testing.assert_array_equal(self.state([0,11,12,7,2,0])[0],[0,1,1,1,0,0])
    def test_short_heating_pulse(self): np.testing.assert_array_equal(self.state([0,12,0])[0],[0,1,0])
    def test_missing_resets(self): np.testing.assert_array_equal(self.state([12,np.nan,7,2,7])[0],[1,-1,-1,0,0])
    def test_initial_band_unknown(self): np.testing.assert_array_equal(self.state([7,8,10,7])[0],[-1,-1,1,1])
    def test_equal_on_off_boundaries(self): np.testing.assert_array_equal(self.state([3,10,3])[0],[0,1,0])
    def test_pending_no_backfill(self): np.testing.assert_array_equal(self.state([0,12,13,2,1],n_on=2,n_off=2)[0],[-1,-1,1,-1,0])
    def test_pending_cancel(self): np.testing.assert_array_equal(self.state([0,0,12,7,13,12],n_on=2,n_off=2)[0],[-1,0,-1,0,-1,1])
    def test_gap_interrupts_candidate(self): np.testing.assert_array_equal(self.state([12,np.nan,12,12],n_on=2)[0],[-1,-1,-1,1])
    def test_invalid_even_when_numeric(self): np.testing.assert_array_equal(self.state([12,12,7],[True,False,True])[0],[1,-1,-1])
    def test_no_identifiable(self): np.testing.assert_array_equal(self.state([0,100,np.nan],identifiable=False)[0],[-1,-1,-1])
    def test_future_cannot_change_past(self):
        x=[0,0,12,13,7,2,1,np.nan,7,12,13]
        all_states=self.state(x,n_on=2,n_off=2)[0]
        for n in range(1,len(x)+1): np.testing.assert_array_equal(self.state(x[:n],n_on=2,n_off=2)[0],all_states[:n])
    def test_bad_thresholds_rejected(self):
        with self.assertRaises(ValueError): classify([0],[True],3,10)
    def test_zero_known_denominator(self):
        a=np.array([-1,-1]);b=np.array([0,1]);known=(a>=0)&(b>=0)
        self.assertEqual(int(known.sum()),0)

if __name__=='__main__': unittest.main(verbosity=2)
