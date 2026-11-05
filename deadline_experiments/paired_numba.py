"""Same input packet, original Numba kernels, same full-clear/debug-mask work."""
import argparse
import csv
import hashlib
import json
import struct
import sys
import time
from pathlib import Path
import numpy as np
from PIL import Image
from numba import cuda


def main():
    p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--data-root',type=Path,required=True);p.add_argument('--packets',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(exist_ok=False)
    sys.path.insert(0,str(a.source_root))
    import benchmark_reconstruction_speed as speed
    from reproduce_quality import WORKLOADS
    meta={}
    for key,relative in WORKLOADS.items():
        folder=a.data_root/relative;data=speed.load_frame(folder,key,39,1.0)
        packet=(a.packets/(key+'_0039.pir')).read_bytes();magic,w,h,*params=struct.unpack_from('<8sII5d',packet);n=w*h;off=56
        fields=[('left',np.uint8,(h,w,3)),('previous',np.uint8,(h,w,3)),('depth','<u2',(h,w)),('flow','<u2',(h,w,2))]
        for name,dtype,shape in fields:
            count=int(np.prod(shape));arr=np.frombuffer(packet,dtype=dtype,count=count,offset=off).reshape(shape);off+=arr.nbytes
            assert np.array_equal(data[name],arr),(key,name)
        assert np.array_equal(np.r_[data['max_d'],data['max_uv'],data['min_uv']],params)
        gt=np.frombuffer(packet,dtype=np.uint8,count=n*3,offset=off).reshape(h,w,3)
        scope=speed.original_functions(folder/'test_numba.py');b=speed.device_buffers(data,data['left'].shape)
        grid=((h+31)//32,(w+31)//32)
        def run():speed.launch_pipeline(scope,b,grid,grid,1.0)
        for _ in range(20):run()
        cuda.synchronize();start=cuda.event(timing=True);end=cuda.event(timing=True);rows=[]
        for i in range(50):
            t=time.perf_counter();start.record();run();end.record();end.synchronize()
            rows.append(dict(iteration=i,wall_ms=(time.perf_counter()-t)*1000,gpu_ms=cuda.event_elapsed_time(start,end)))
        result=b['right2'].copy_to_host();mse=np.mean((result.astype(np.float64)-gt.astype(np.float64))**2)
        with (a.out/(key+'.csv')).open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        Image.fromarray(result[:,:,::-1]).save(a.out/(key+'.png'))
        meta[key]=dict(packet_sha256=hashlib.sha256(packet).hexdigest(),all_inputs_equal=True,
                       source_sha256=hashlib.sha256((folder/'test_numba.py').read_bytes()).hexdigest(),
                       standard_psnr_db=float(10*np.log10(65025/mse)))
    (a.out/'metadata.json').write_text(json.dumps(meta,indent=2))
    print('COMPLETE matched Numba inputs and measurements')


if __name__=='__main__':main()
