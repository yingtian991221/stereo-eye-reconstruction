"""Encode original Driving left-eye PNGs into a controlled HEVC test stream."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

WORKLOADS = {'15_300': '15mm_focallength/scene_forwards/aaa',
             '15_800': '15mm_focallength/scene_forwards/bbb',
             '35_300': '35mm_focallength/scene_forwards/aaa',
             '35_800': '35mm_focallength/scene_forwards/bbb'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ffmpeg', required=True)
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    records = []
    for name, rel in WORKLOADS.items():
        folder = a.data_root / rel / 'left'
        files = sorted(folder.glob('*.png'))
        count = int(name.split('_')[1])
        assert [f.name for f in files] == [f'{i:04d}.png' for i in range(1, count+1)]
        output = a.out / f'driving_{name}.mp4'
        cmd = [a.ffmpeg, '-hide_banner', '-nostdin', '-n', '-framerate', '90', '-start_number', '1',
               '-i', str(folder / '%04d.png'), '-frames:v', str(count), '-an',
               '-c:v', 'libx265', '-preset', 'veryfast', '-tune', 'zerolatency',
               '-x265-params', 'bframes=0:keyint=90:min-keyint=90:scenecut=0:pools=4',
               '-b:v', '8M', '-maxrate', '8M', '-bufsize', '8M', '-pix_fmt', 'yuv420p',
               '-tag:v', 'hvc1', '-movflags', '+faststart', str(output)]
        with (a.out / f'driving_{name}.encode.log').open('w') as log:
            subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
        records.append(dict(workload=name, frames=count, width=960, height=540, fps=90,
                            codec='HEVC', input='original left-eye ground truth PNG',
                            target_bitrate_bps=8000000, b_frames=0, key_interval=90,
                            output=str(output), bytes=output.stat().st_size,
                            sha256=hashlib.sha256(output.read_bytes()).hexdigest(), command=cmd))
        (a.out / 'encoding.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
        print(name, 'encoded', count, 'frames', flush=True)


if __name__ == '__main__':
    main()
