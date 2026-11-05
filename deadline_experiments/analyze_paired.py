"""Summarize the bounded matched original Full implementation control."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image

WORKLOADS={'driving_15_300':'15mm_focallength/scene_forwards/aaa',
           'driving_15_800':'15mm_focallength/scene_forwards/bbb',
           'driving_35_300':'35mm_focallength/scene_forwards/aaa',
           'driving_35_800':'35mm_focallength/scene_forwards/bbb'}

def analyze(root,data):
    rows=[]
    meta=json.loads((root/'paired_numba/metadata.json').read_text())
    for key,folder in WORKLOADS.items():
        cpp=pd.read_csv(root/'paired_cpp'/(key+'.csv'))
        nb=pd.read_csv(root/'paired_numba'/(key+'.csv'))
        a=np.asarray(Image.open(root/'paired_cpp'/(key+'.csv.ppm'))).astype(np.float64)
        b=np.asarray(Image.open(root/'paired_numba'/(key+'.png'))).astype(np.float64)
        gt=np.asarray(Image.open(data/folder/'right/0039.png').convert('RGB')).astype(np.float64)
        score=lambda x:float(10*np.log10(65025/np.mean((x-gt)**2)))
        assert abs(score(b)-meta[key]['standard_psnr_db'])<1e-8
        assert meta[key]['all_inputs_equal'] and len(cpp)==len(nb)==50
        rows.append(dict(workload=key,frame=39,repetitions=50,
            cpp_gpu_mean_ms=cpp.gpu_ms.mean(),numba_gpu_mean_ms=nb.gpu_ms.mean(),
            cpp_wall_mean_ms=cpp.wall_ms.mean(),numba_wall_mean_ms=nb.wall_ms.mean(),
            cpp_standard_right_psnr_db=score(a),numba_standard_right_psnr_db=score(b),
            output_difference_mse=float(np.mean((a-b)**2)),
            differing_pixel_fraction=float(np.mean(np.any(a!=b,axis=2)))))
    out=pd.DataFrame(rows);out.to_csv(root/'paired_summary.csv',index=False);print(out.to_string(index=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--data',type=Path,required=True)
    a=p.parse_args();analyze(a.root,a.data)
