"""Single-plane HEVC timing probes plus a bit-exact uint16 byte-packing control."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

PATHS = {'15_300': ('15mm_focallength/scene_forwards/aaa', 'gray_depth', 'gray_u_past', 'gray_v_past'),
         '15_800': ('15mm_focallength/scene_forwards/bbb', '05_depth', '025_u_past', '025_v_past'),
         '35_300': ('35mm_focallength/scene_forwards/aaa', '05_depth', '025_u_past', '025_v_past'),
         '35_800': ('35mm_focallength/scene_forwards/bbb', '05_depth', '025_u_past', '025_v_past')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ffmpeg', required=True)
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--count', type=int, default=120)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    records = []
    for group, (rel, *dirs) in PATHS.items():
        root = a.data_root / rel
        for channel, subdir in [('rgb', 'left')] + list(zip(['depth', 'u', 'v'], dirs)):
            variants = ['rgb'] if channel == 'rgb' else ['q8_lossy', 'pack16_lossless']
            for variant in variants:
                packed = variant == 'pack16_lossless'
                width, height = (1920 if packed else 960), 540
                name = f'{group}_{channel}_{variant}'
                video = a.out / (name + '.mp4')
                cmd = [a.ffmpeg, '-hide_banner', '-nostdin', '-n']
                if channel == 'rgb':
                    cmd += ['-framerate', '90', '-start_number', '1', '-i', str(root / subdir / '%04d.png')]
                else:
                    cmd += ['-f', 'rawvideo', '-pixel_format', 'yuv420p', '-video_size', f'{width}x{height}',
                            '-framerate', '90', '-i', 'pipe:0']
                params = 'bframes=0:keyint=90:min-keyint=90:scenecut=0:pools=4'
                if packed: params += ':lossless=1'
                cmd += ['-frames:v', str(a.count), '-an', '-c:v', 'libx265', '-preset', 'veryfast',
                        '-tune', 'zerolatency', '-x265-params', params]
                bitrate = 8000000 if channel == 'rgb' else (500000 if channel == 'depth' else 250000)
                if not packed: cmd += ['-b:v', str(bitrate), '-maxrate', str(bitrate), '-bufsize', str(bitrate)]
                cmd += ['-pix_fmt', 'yuv420p', '-tag:v', 'hvc1', '-movflags', '+faststart', str(video)]
                with (a.out / (name + '.encode.log')).open('w') as log:
                    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if channel != 'rgb' else subprocess.DEVNULL,
                                            stdout=log, stderr=subprocess.STDOUT)
                    if channel != 'rgb':
                        chroma = bytes([128]) * (width*height//2)
                        for i in range(1, a.count+1):
                            array = np.asarray(Image.open(root / subdir / f'{i:04d}.png'))
                            assert array.dtype == np.uint16 and array.shape == (540,960)
                            if packed:
                                y = np.concatenate([(array >> 8).astype('u1'), (array & 255).astype('u1')], axis=1)
                            else:
                                y = ((array.astype('u4') + 128)//257).astype('u1')
                            proc.stdin.write(y.tobytes()); proc.stdin.write(chroma)
                        proc.stdin.close()
                    if proc.wait(): raise RuntimeError('Encoding failed: '+name)
                quality = {}
                if channel != 'rgb':
                    decoded = subprocess.check_output([a.ffmpeg, '-v', 'error', '-i', str(video),
                                                       '-an', '-f', 'rawvideo', '-pix_fmt', 'yuv420p', 'pipe:1'])
                    assert len(decoded) == a.count*width*height*3//2
                    total_abs, max_error, changed = 0, 0, 0
                    for index in range(a.count):
                        y = np.frombuffer(decoded, dtype='u1', count=width*height,
                                          offset=index*width*height*3//2).reshape(height,width)
                        restored = ((y[:,:960].astype('u2') << 8) | y[:,960:]) if packed else y.astype('u2')*257
                        original = np.asarray(Image.open(root/subdir/f'{index+1:04d}.png'))
                        error = np.abs(restored.astype('i4')-original.astype('i4'))
                        total_abs += int(error.sum()); max_error = max(max_error,int(error.max()))
                        changed += int(np.count_nonzero(error))
                    quality = dict(reconstructed_uint16_mae=total_abs/(a.count*960*540),
                                   reconstructed_uint16_max_error=max_error, changed_values=changed,
                                   compared_values=a.count*960*540, bit_exact=(changed==0),
                                   verification_decoder='local FFmpeg software hevc; raw Y plane',
                                   hardware_bit_exactness_verified=False)
                    if packed: assert changed == 0, (name, quality)
                records.append(dict(name=name, group=group, channel=channel, variant=variant,
                                    frames=a.count, source_frames=f'1..{a.count}, consecutive',
                                    source=str(root/subdir), width=width, height=height, fps=90,
                                    target_bitrate_bps=None if packed else bitrate, command=cmd,
                                    file=str(video), bytes=video.stat().st_size,
                                    bitrate_container_bps=video.stat().st_size*8*90/a.count,
                                    sha256=hashlib.sha256(video.read_bytes()).hexdigest(), **quality))
                (a.out/'encoding.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
                print(name,'OK',quality.get('bit_exact','RGB'),flush=True)
    (a.out/'COMPLETE').write_text('All videos encoded; all pack16 values round-trip exactly\n')


if __name__ == '__main__':
    main()
