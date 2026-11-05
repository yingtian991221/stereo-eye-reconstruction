"""Render actual held/accepted stereo outputs; no rerun or synthetic pixels."""
import argparse
import gzip
import json
import struct
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


def visualize(root,clip,ffmpeg=None):
    cfg=json.loads((root/'config.json').read_text());n=cfg['count'];w,h=960,540;size=w*h*3
    indices=[0,n//4-1,n//4,n//2-1,n//2,3*n//4-1,3*n//4,n-1]
    selected=[n//4-1,n//2-1,3*n//4-1,n-1]
    previews={}
    output=root/'visuals';output.mkdir(exist_ok=True)
    for policy in ['Full','Half','Dynamic_whole','Dynamic_center']:
        path=root/'replay'/('phase_'+policy+'_r0.bgr.gz')
        frames=list(range(n)) if policy=='Dynamic_whole' else indices
        images={}
        pipe=None
        if policy=='Dynamic_whole' and ffmpeg:
            pipe=subprocess.Popen([str(ffmpeg),'-y','-f','rawvideo','-pixel_format','rgb24','-video_size','1920x540','-framerate','90','-i','pipe:0','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',str(output/'simulated_display_90fps.mp4')],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=(output/'ffmpeg.log').open('w'))
        with gzip.open(path,'rb') as f:
            for i in frames:
                raw=f.read(size*2)
                if len(raw)!=size*2:raise ValueError('truncated displayed images')
                pair=np.frombuffer(raw,np.uint8).reshape(2,h,w,3)[:,:,:,::-1]
                if i in indices:
                    images[i]=Image.fromarray(pair[(cfg['first_frame']+i)%2].copy())
                    Image.fromarray(np.concatenate(pair,axis=1)).save(output/('%s_i%03d_stereo.png'%(policy,i)))
                if pipe:pipe.stdin.write(np.concatenate(pair,axis=1).tobytes())
            if f.read(1):raise ValueError('extra displayed images')
        if pipe:
            pipe.stdin.close()
            if pipe.wait()!=0:raise RuntimeError('ffmpeg failed')
        previews[policy]=images
    gt={}
    with gzip.open(clip,'rb') as f:
        magic,cw,ch,cn,start=struct.unpack('<8s4I',f.read(24));assert (cw,ch,cn)==(w,h,n)
        f.read(size*2)
        for i in range(n):
            f.read(48);f.read(size+w*h*2+w*h*4);raw=f.read(size*2)
            if i in indices:gt[i]=Image.fromarray(np.frombuffer(raw,np.uint8).reshape(2,h,w,3)[(cfg['first_frame']+i)%2,:,:,::-1].copy())
    previews={'GT (current frame)':gt,**previews}
    canvas=Image.new('RGB',(1420,5*235+65),'white');draw=ImageDraw.Draw(canvas)
    try:font=ImageFont.truetype('arial.ttf',22)
    except OSError:font=ImageFont.load_default()
    for col,i in enumerate(selected):draw.text((160+col*315,10),'Input frame %d'%(cfg['first_frame']+i),fill='black',font=font)
    for row,(policy,imgs) in enumerate(previews.items()):
        labels=None
        if policy!='GT (current frame)':labels=pd.read_csv(root/'replay'/('phase_'+policy+'_r0.csv')).set_index('index')
        draw.text((4,65+row*235),'GT' if labels is None else policy.replace('_','\n'),fill='black',font=font)
        for col,i in enumerate(selected):
            canvas.paste(imgs[i].resize((310,174)),(160+col*315,65+row*235))
            text='GT' if labels is None else 'Shown frame %d'%labels.loc[i,'display_frame']
            draw.text((160+col*315,242+row*235),text,fill='black',font=font)
    canvas.save(output/'phase_contact_sheet.png')
    # Full-resolution center crops around phase boundaries, using the target
    # reconstruction eye rather than accidentally showing the transmitted eye.
    transition=[n//4-1,n//4,n//2-1,n//2,3*n//4-1,3*n//4]
    zoom=Image.new('RGB',(6*330,3*250+65),'white');draw=ImageDraw.Draw(zoom)
    for col,i in enumerate(transition):
        draw.text((col*330+3,5),'Frame %d (%s)'%(cfg['first_frame']+i,'R' if (cfg['first_frame']+i)%2 else 'L'),fill='black',font=font)
        for row,policy in enumerate(['GT (current frame)','Dynamic_whole','Dynamic_center']):
            img=previews[policy][i].crop((w//2-160,h//2-90,w//2+160,h//2+90))
            zoom.paste(img,(col*330,65+row*250))
            label='GT'
            if row:
                r=pd.read_csv(root/'replay'/('phase_'+policy+'_r0.csv')).set_index('index').loc[i]
                label='%s: %s\nshown %d'%('Whole' if row==1 else 'Center',r['config'],r['display_frame'])
            draw.text((col*330+3,248+row*250),label,fill='black',font=font)
    zoom.save(output/'transition_center_crops.png')
    (output/'README.txt').write_text('Actual simulated display output; contact sheets use the current target reconstruction eye. Full stereo PNGs retained.\nCenter crops are 320x180 source pixels at 1:1, with transmitted/reconstructed eye alternation labeled.\nMP4 is the 96-frame Dynamic_whole sequence at the modeled 90Hz clock, not a physical-display recording.\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--clip',type=Path,required=True);p.add_argument('--ffmpeg',type=Path)
    a=p.parse_args();visualize(a.root,a.clip,a.ffmpeg)
