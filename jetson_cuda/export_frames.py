"""Export portable little-endian frames. Requires NumPy/Pillow, never Numba."""
import argparse
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image

CONFIG = {
    'driving_15_300': ('15mm_focallength/scene_forwards/aaa', '8_left', '8_right', 'gray_depth', 'gray_u_past', 'gray_v_past', 0, 299),
    'driving_15_800': ('15mm_focallength/scene_forwards/bbb', '14_left', '14_right', '05_depth', '025_u_past', '025_v_past', -1, 779),
    'driving_35_300': ('35mm_focallength/scene_forwards/aaa', '14_left', '14_right', '05_depth', '025_u_past', '025_v_past', 0, 299),
    'driving_35_800': ('35mm_focallength/scene_forwards/bbb', '8_left', '8_right', '05_depth', '025_u_past', '025_v_past', -1, 779),
}


def read(folder, sub, frame, color=False):
    with Image.open(folder / sub / ('%04d.png' % frame)) as im:
        if color:
            return np.asarray(im.convert('RGB'))[:, :, ::-1].copy()
        return np.asarray(im).astype('<u2')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--workload', choices=['all'] + list(CONFIG), default='all')
    p.add_argument('--frames', default='39', help='Comma-separated odd frame IDs, or all')
    p.add_argument('--sample-count', type=int, help='Evenly spaced odd frames per workload; overrides --frames')
    a = p.parse_args()
    if a.sample_count is not None and a.sample_count < 1:
        p.error('--sample-count must be positive')
    keys = list(CONFIG) if a.workload == 'all' else [a.workload]
    a.out.mkdir(parents=True, exist_ok=True)
    records = []
    for key in keys:
        rel, left, prev, depth, u, v, offset, last = CONFIG[key]
        folder = a.data_root / rel
        frames = list(range(7, last + 1, 2)) if a.frames == 'all' else sorted(set(map(int, a.frames.split(','))))
        if a.sample_count is not None:
            available = list(range(7, last + 1, 2))
            indices = np.linspace(0, len(available) - 1, min(a.sample_count, len(available))).astype(int)
            frames = [available[i] for i in indices]
        max_d = np.load(folder / 'max_array.npy', allow_pickle=False)
        max_uv = np.load(folder / 'max_uv_past.npy', allow_pickle=False)
        min_uv = np.load(folder / 'min_uv_past.npy', allow_pickle=False)
        for frame in frames:
            if frame < 7 or frame > last or frame % 2 == 0:
                raise ValueError('Invalid frame %s for %s (odd 7..%s)' % (frame, key, last))
            images = [read(folder, left, frame, True), read(folder, prev, frame - 1, True)]
            d = read(folder, depth, frame)
            flow = np.stack([read(folder, u, frame + offset), read(folder, v, frame + offset)], axis=2).astype('<u2')
            gt = read(folder, 'right', frame, True)
            h, w = d.shape
            if any(im.shape != (h, w, 3) for im in images + [gt]) or flow.shape != (h, w, 2):
                raise ValueError('Shape mismatch')
            params = [float(max_d[frame - 1]), *map(float, max_uv[frame - 1]), *map(float, min_uv[frame - 1])]
            if not np.all(np.isfinite(params)) or params[0] < 0:
                raise ValueError('Invalid motion parameters')
            payload = struct.pack('<8sII5d', b'PIRFRM1\0', w, h, *params)
            payload += b''.join(im.tobytes() for im in images) + d.tobytes() + flow.tobytes() + gt.tobytes()
            name = '%s_%04d.pir' % (key, frame)
            (a.out / name).write_bytes(payload)
            records.append(dict(file=name, workload=key, frame=frame, bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(), source=str(folder), params=params))
            print(name, len(payload), flush=True)
    # Manifest paths are relative to the manifest, so the entire directory can move.
    (a.out / 'manifest.txt').write_text(''.join(r['file'] + '\n' for r in records), encoding='utf-8')
    (a.out / 'metadata.json').write_text(json.dumps({'format': 'PIRFRM1', 'frames': records}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
