"""后三步共用的路径、时间轴及输入校验。"""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
INPUT=HERE/'inputs'
OUT=ROOT/'data/derived/task05'
REPORT=HERE/'reports'
VERSION='task05_v1.0.1_20261117'
TZ='Asia/Shanghai'
START=pd.Timestamp('2021-05-31',tz=TZ)
END=pd.Timestamp('2022-06-01',tz=TZ)
TRAIN_END=pd.Timestamp('2022-03-09',tz=TZ)

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now(): return datetime.now(timezone(timedelta(hours=8))).isoformat()
def read(path,**kw): return pd.read_csv(path,float_precision='round_trip',**kw)
def save(frame,name):
    OUT.mkdir(parents=True,exist_ok=True)
    if name.endswith('.gz'):
        import gzip
        with open(OUT/name,'wb') as raw:
            with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as gz:
                gz.write(frame.to_csv(index=False).encode('utf-8'))
    else: frame.to_csv(OUT/name,index=False,encoding='utf-8-sig')
def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def devices():
    return json.loads((INPUT/'task01/panel_definition.json').read_text(encoding='utf-8'))['panels'][0]['devices']

def load_power_quality():
    devs=devices()
    p=read(INPUT/'standardized/power_minute.csv.gz',usecols=['timestamp']+devs)
    source_timestamps=p.timestamp.to_numpy(copy=True)
    p['timestamp']=pd.to_datetime(p.timestamp,utc=True).dt.tz_convert(TZ)
    window=p.timestamp.ge(START)&p.timestamp.lt(END)
    p=p.loc[window].set_index('timestamp')
    expected=pd.date_range(START,END,inclusive='left',freq='min')
    assert p.index.equals(expected) and p.index.is_unique and len(p)==527040
    masks={}; flags={}
    for dev in devs:
        q=read(INPUT/'appliance_quality'/(dev+'.csv.gz'),usecols=['timestamp','usable_value','is_usable','qc_bits','is_new_imputed'])
        # 原始时间文本逐项一致，再复用已经校验过的裁剪掩码；避免13次重复解析全轴。
        assert np.array_equal(q.timestamp.to_numpy(),source_timestamps),dev+' quality time axis'
        q=q.loc[window]
        valid=q.is_usable.to_numpy(bool)&np.isfinite(q.usable_value.to_numpy(float))
        assert not q.is_new_imputed.any()
        np.testing.assert_allclose(p[dev].to_numpy(),q.usable_value.to_numpy(),equal_nan=True,rtol=0,atol=0)
        masks[dev]=valid; flags[dev]=q.qc_bits.to_numpy(np.uint16)
    return p,pd.DataFrame(masks,index=p.index),pd.DataFrame(flags,index=p.index)

def complete_day_mask(index):
    d=read(INPUT/'task02/daily_panel13.csv')
    dates=pd.to_datetime(d.date,utc=True).dt.tz_convert(TZ)
    days=pd.DatetimeIndex(dates.loc[d.day_complete])
    assert len(days)==352
    return index.normalize().isin(days)
