"""Independently recompute logged metrics from saved pixels, including holds."""
import argparse
import gzip
import json
import struct
from pathlib import Path
import numpy as np
import pandas as pd

def audit(root,clip):
    cfg=json.loads((root/'config.json').read_text());n=cfg['count'];w,h=960,540;size=w*h*3
    sources=[];gt=[]
    with gzip.open(clip,'rb') as f:
        magic,cw,ch,cn,start=struct.unpack('<8s4I',f.read(24));assert (cw,ch,cn)==(w,h,n)
        boot=np.frombuffer(f.read(size*2),np.uint8).reshape(2,h,w,3).copy()
        for i in range(n):
            f.read(48);sources.append(np.frombuffer(f.read(size),np.uint8).reshape(h,w,3).copy())
            f.read(w*h*6);gt.append(np.frombuffer(f.read(size*2),np.uint8).reshape(2,h,w,3).copy())
    selected=[0,n//4-1,n//4,n//2-1,n//2,3*n//4-1,3*n//4,n-1]
    x0,x1,y0,y1=w*3//8,w*5//8,h*3//8,h*5//8
    count=0;max_mse_error=0.;max_psnr_error=0.;holds=0;received=0
    for policy in ['Full','Half','Dynamic_whole','Dynamic_center']:
        log=pd.read_csv(root/'replay'/('phase_'+policy+'_r0.csv')).set_index('index')
        indices=range(n) if policy=='Dynamic_whole' else selected
        previous=boot
        with gzip.open(root/'replay'/('phase_'+policy+'_r0.bgr.gz'),'rb') as f:
            for i in indices:
                pair=np.frombuffer(f.read(size*2),np.uint8).reshape(2,h,w,3)
                e=(pair.astype(np.float64)-gt[i].astype(np.float64))**2
                r=log.loc[i];mse=e.mean();center=e[:,y0:y1,x0:x1].mean()
                edge=(e[:,y0-4:y1+4,x0-4:x1+4].sum()-e[:,y0+4:y1-4,x0+4:x1-4].sum())/(2*3*((x1-x0+8)*(y1-y0+8)-(x1-x0-8)*(y1-y0-8)))
                max_mse_error=max(max_mse_error,abs(mse-r.display_stereo_mse),abs(center-r.display_center_mse),abs(edge-r.display_boundary_mse))
                max_psnr_error=max(max_psnr_error,abs(10*np.log10(65025/mse)-r.display_stereo_psnr_db))
                if r.accepted:
                    assert np.array_equal(pair[1-int(r.target)],sources[i]);received+=1
                elif policy=='Dynamic_whole':
                    assert np.array_equal(pair,previous);holds+=1
                previous=pair.copy();count+=1
            assert not f.read(1)
    assert max_mse_error<1e-6 and max_psnr_error<1e-8
    result=dict(saved_stereo_pairs_checked=count,held_pairs_checked=holds,received_eye_images_checked=received,
                maximum_logged_mse_error=max_mse_error,maximum_logged_psnr_error_db=max_psnr_error,
                standard_float_metrics_verified=True,actual_pixel_hold_verified=True)
    (root/'image_metric_audit.json').write_text(json.dumps(result,indent=2));print(result)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--clip',type=Path,required=True)
    a=p.parse_args();audit(a.root,a.clip)
