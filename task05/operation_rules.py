"""逐分钟因果确认状态机：0 off、1 on、-1 unknown；从不回填。"""
import numpy as np

REASONS={0:'known',1:'source_missing_or_invalid',2:'operation_not_identifiable',
         3:'uninitialized_hysteresis_band',4:'pending_on_confirmation',5:'pending_off_confirmation'}

def classify(power,valid,on_threshold,off_threshold,min_on=1,min_off=1,identifiable=True):
    power=np.asarray(power,dtype=float);valid=np.asarray(valid,dtype=bool)
    if len(power)!=len(valid): raise ValueError('Power/quality length mismatch')
    states=np.full(len(power),-1,dtype=np.int8)
    reasons=np.full(len(power),2,dtype=np.uint8)
    if not identifiable:
        reasons[~valid|~np.isfinite(power)]=1
        return states,reasons
    if not (np.isfinite(on_threshold) and on_threshold>off_threshold>=0 and min_on>=1 and min_off>=1):
        raise ValueError('Invalid hysteresis/confirmation parameters')
    stable=-1;candidate=-1;count=0
    for i in range(len(power)):
        x=power[i]
        if not valid[i] or not np.isfinite(x):
            stable=-1;candidate=-1;count=0;reasons[i]=1
            continue
        if stable==-1:
            if x>=on_threshold: target=1
            elif x<=off_threshold: target=0
            else:
                candidate=-1;count=0;reasons[i]=3
                continue
        elif stable==0: target=1 if x>=on_threshold else 0
        else: target=0 if x<=off_threshold else 1
        if target==stable:
            candidate=-1;count=0;states[i]=stable;reasons[i]=0
        else:
            if candidate==target: count+=1
            else: candidate=target;count=1
            needed=min_on if target==1 else min_off
            if count>=needed:
                stable=target;candidate=-1;count=0;states[i]=stable;reasons[i]=0
            else: reasons[i]=4 if target==1 else 5
    return states,reasons
