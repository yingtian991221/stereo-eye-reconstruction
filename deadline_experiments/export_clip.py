"""Export a chronological alternating-eye clip without changing source data.

Raw losslessly stored decoded RGB/depth/flow arrays are inputs, not a codec
benchmark. Right-to-left reconstruction uses horizontal reflection of geometry.
"""
import argparse
import gzip
import hashlib
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image


def image(folder, name, frame, color=False):
    p = folder / name / ('%04d.png' % frame)
    with Image.open(p) as im:
        return np.asarray(im.convert('RGB'))[:, :, ::-1].copy() if color else np.asarray(im).astype('<u2')


def export(folder, out, start, count):
    if out.exists():
        raise FileExistsError(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # The archived even-eye function references missing 7_depth_right and casts
    # to uint8. Use the available symmetric uint16 maps for BOTH directions.
    params = {name: np.load(folder / (name + '.npy'), allow_pickle=False) for name in
              ['max_array', 'max_array_right', 'max_uv_past', 'min_uv_past',
               'max_uv_left_past', 'min_uv_left_past']}
    boot = [image(folder, '8_' + e, start-1, True) for e in ['left', 'right']]
    h, w, _ = boot[0].shape
    with gzip.open(out, 'wb', compresslevel=1) as f:
        f.write(struct.pack('<8s4I', b'PIRSEQ2\0', w, h, count, start))
        for b in boot:
            f.write(b.tobytes())
        for frame in range(start, start+count):
            # odd: transmit left/reconstruct right; even: the opposite.
            target = frame % 2
            src = image(folder, '8_' + ('left' if target else 'right'), frame, True)
            depth = image(folder, 'gray_depth' if target else 'gray_depth_right', frame)
            flow = np.stack([image(folder, 'gray_' + c + ('_past' if target else '_left_past'), frame)
                             for c in ['u', 'v']], axis=2).astype('<u2')
            suffix = '' if target else '_right'
            motion = '_past' if target else '_left_past'
            d = float(params['max_array'+suffix][frame-1])
            umax, vmax = map(float, params['max_uv'+motion][frame-1])
            umin, vmin = map(float, params['min_uv'+motion][frame-1])
            if not target:
                depth = depth[:, ::-1].copy()
                flow = flow[:, ::-1].copy()
                flow[:, :, 0] = 65535-flow[:, :, 0]
                umax, umin = -umin, -umax
            assert depth.shape == (h, w) and flow.shape == (h, w, 2)
            f.write(struct.pack('<2I5d', frame, target, d, umax, vmax, umin, vmin))
            for a in [src, depth, flow, image(folder, 'left', frame, True), image(folder, 'right', frame, True)]:
                f.write(a.tobytes())
    meta = dict(format='PIRSEQ2', source=str(folder), start=start, count=count, width=w, height=h,
                sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
                codec_inputs='existing 8_left/8_right PNG decoded arrays, unchanged across strategies',
                maps='gray_depth/gray_depth_right, gray_u/v[_left]_past; uint16',
                history='bootstrap from decoded 8_left/8_right, never ground truth',
                left_geometry='horizontal reflection with u sign inversion; no disparity re-estimation')
    out.with_suffix('.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(json.dumps(meta), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--folder', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--start', type=int, required=True)
    p.add_argument('--count', type=int, required=True)
    a = p.parse_args()
    export(a.folder, a.out, a.start, a.count)
