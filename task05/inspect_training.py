"""先审查训练期分布及候选阈值连续段，再人工冻结逐设备判据。"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from common import *

def main():
    OUT.mkdir(parents=True,exist_ok=True); (REPORT/'figures').mkdir(parents=True,exist_ok=True)
    p,valid,qc=load_power_quality()
    train=p.index<TRAIN_END
    bins=np.array([-.001,0,.5,1,2,5,10,20,50,100,200,500,1000,2000,4000])
    stats=[]; hist=[]; runs=[]; modes=[]
    fig,axes=plt.subplots(5,3,figsize=(14,16))
    for ax,dev in zip(axes.flat,p):
        x=p[dev].to_numpy(); ok=valid[dev].to_numpy()&train
        y=x[ok]
        row=dict(appliance_id=dev,fitted_start=START.isoformat(),fitted_end_exclusive=TRAIN_END.isoformat(),
            n_calendar_minutes=int(train.sum()),n_usable=int(ok.sum()),n_qc16=int(((qc[dev].to_numpy()&16!=0)&ok).sum()),n_qc32=int(((qc[dev].to_numpy()&32!=0)&ok).sum()))
        for q in [0,.1,.25,.5,.75,.9,.95,.99,.999,1]: row['q'+str(q)]=float(np.quantile(y,q))
        stats.append(row)
        for interval,count in pd.cut(y,bins).value_counts().sort_index().items():
            hist.append(dict(appliance_id=dev,bin_left_w=float(interval.left),bin_right_w=float(interval.right),n_minutes=int(count)))
        for value,count in pd.Series(y).value_counts().head(10).items(): modes.append(dict(appliance_id=dev,power_w=float(value),n_minutes=int(count)))
        for threshold in [1,5,10,20,50,100,150,200,300,500]:
            active=ok&(x>=threshold)
            changes=np.diff(np.r_[False,active,False].astype(np.int8)); lengths=np.flatnonzero(changes==-1)-np.flatnonzero(changes==1)
            runs.append(dict(appliance_id=dev,threshold_w=threshold,on_minutes=int(active.sum()),n_segments=len(lengths),
                one_minute_segments=int((lengths==1).sum()),median_segment_minutes=float(np.median(lengths)) if len(lengths) else None,
                p95_segment_minutes=float(np.quantile(lengths,.95)) if len(lengths) else None,max_segment_minutes=int(lengths.max()) if len(lengths) else None))
        ax.hist(np.log10(1+y),bins=65,color='#24788a');ax.set_yscale('log');ax.set_title(dev,fontsize=9);ax.set_xlabel('log10(1 + W)');ax.set_ylabel('minutes log scale')
    for ax in axes.flat[len(p.columns):]: ax.axis('off')
    fig.suptitle('Training only 2021-05-31 to 2022-03-09 exclusive',fontsize=15)
    fig.tight_layout(rect=[0,0,1,.97]);fig.savefig(REPORT/'figures/01_training_distributions.png',dpi=140);plt.close(fig)
    for frame,name in [(stats,'training_distribution.csv'),(hist,'training_histogram.csv'),(modes,'training_modes.csv'),(runs,'training_candidate_run_lengths.csv')]: save(pd.DataFrame(frame),name)
    write_json(OUT/'training_inspection.json',dict(generated_at=now(),fitted_start=START.isoformat(),fitted_end_exclusive=TRAIN_END.isoformat(),
        training_calendar_minutes=int(train.sum()),not_used='validation and test values',
        evidence_files=[dict(path=name,sha256=sha(OUT/name)) for name in ['training_distribution.csv','training_histogram.csv','training_modes.csv','training_candidate_run_lengths.csv']]))
    print('PASS training inspection',int(train.sum()),'calendar minutes; 13 devices; no validation/test used')

if __name__=='__main__': main()
