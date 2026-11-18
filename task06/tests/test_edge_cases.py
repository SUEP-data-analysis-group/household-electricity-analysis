"""Small explicit counterexamples; expectations do not reuse production arithmetic."""
import numpy as np
import pandas as pd

from task06.common import Q, CATEGORIES, NUMERIC
from task06.evaluation import peak_metrics, high_metrics, publish_interval, repeated_q90, bootstrap_indices
from task06.modeling import select_candidate, Encoder


def test_peak_required_counterexamples():
    y=np.zeros(24); y[12]=2
    assert peak_metrics(y,np.ones(24))["peak_time_h"]==12
    y=np.zeros(24); y[[6,18]]=2
    p=np.zeros(24); p[18]=1
    assert peak_metrics(y,p)["peak_time_h"]==0
    y=np.zeros(24); y[23]=2
    p=np.zeros(24); p[0]=1
    result=peak_metrics(y,p)
    assert result["peak_time_h"]==23 and result["peak_time_circular_h"]==1
    assert np.isnan(peak_metrics(np.ones(24),p)["peak_time_h"])
    assert peak_metrics(np.ones(24),p)["peak_abs_kw"]==0


def test_exact_ties_and_predicted_flat_retained():
    y=np.zeros(24); y[12]=1; y[13]=np.nextafter(1.,2.)
    p=np.ones(24)
    result=peak_metrics(y,p)
    assert result["true_tie_count"]==1 and result["predicted_tie_count"]==24
    assert result["peak_time_h"]==13 and result["predicted_flat"]
    y[12]=y[13]
    assert peak_metrics(y,p)["true_tie_count"]==2


def test_high_load_empty_and_under_vs_miss():
    result=high_metrics([0,Q],[0,0])
    assert result["n_H"]==0 and np.isnan(result["FNR_H"])
    result=high_metrics([1.,2.],[1.2,2.1])
    assert result["U_H_kw"]==0 and np.isnan(result["conditional_gap_H_kw"])
    result=high_metrics([2.,2.],[1.,0.5])
    assert result["under_rate_H"]==1 and result["FNR_H"]==.5
    assert result["U_H_kw"]==1.25 and result["gap_q90_H_kw"]==1.45


def test_interval_gate_boundary():
    a=np.ones(10000); a[:500]=np.nan
    assert publish_interval(a)["valid_repetitions"]==9500
    assert publish_interval(a)["ci_low"]==1
    a[500]=np.nan
    assert np.isnan(publish_interval(a)["ci_low"])


def test_weighted_quantile_subset_recomputation():
    gap=np.array([0.,1.,3.]); day=np.array([0,1,1])
    weights=np.array([[2,1],[0,2],[4,0],[0,0]])
    got=repeated_q90(gap,day,weights)
    assert np.isclose(got[0],2.4)  # sorted [0,0,1,3]
    assert got[1]==3 and got[2]==0 and np.isnan(got[3])


def test_block_indices_invariants():
    ix=bootstrap_indices("paired_week7",200)
    blocks=ix.reshape(200,8,7)
    assert (blocks[:,:,0]%7==0).all() and (np.diff(blocks,axis=2)==1).all()
    for L in [3,7,14]:
        ix=bootstrap_indices(f"moving_day_{L}",200)
        assert ix.min()>=0 and ix.max()<56
        for start in range(0,56,L):
            assert (np.diff(ix[:,start:min(start+L,56)],axis=1)==1).all()


def test_deterministic_selection_ties():
    rows=[dict(params={"alpha":a},validation_mae_kw=1.+i*1e-13) for i,a in enumerate([.0001,.001,.01,.1])]
    assert select_candidate(rows,"Linear-L1")["params"]["alpha"]==.1
    rows=[dict(params=p,validation_mae_kw=1.) for p in [
        dict(n_estimators=500,num_leaves=7,min_child_samples=80),
        dict(n_estimators=200,num_leaves=15,min_child_samples=80),
        dict(n_estimators=200,num_leaves=7,min_child_samples=40),
        dict(n_estimators=200,num_leaves=7,min_child_samples=80)]]
    assert select_candidate(rows,"Full")["params"]==dict(n_estimators=200,num_leaves=7,min_child_samples=80)


def test_fixed_categories_and_numeric_only_scaling():
    x=pd.DataFrame({f:[values[0],values[-1]] for f,values in CATEGORIES.items()})
    for f in NUMERIC:
        x[f]=[1.,3.]
    enc=Encoder("Linear-L1",True).fit(x)
    z=enc.transform(x)
    assert z.shape==(2,78)
    assert (z[NUMERIC].to_numpy()==[[-1.]*11,[1.]*11]).all()
    assert set(np.unique(z.drop(columns=NUMERIC)))=={0.,1.}
