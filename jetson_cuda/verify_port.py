"""Workstation check of exported packets and CUDA output PSNR; no Numba needed."""
import argparse
import ast
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from export_frames import CONFIG


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--csv', type=Path, required=True)
    p.add_argument('--dump-prefix', type=Path, required=True)
    a = p.parse_args()
    records = json.loads((a.package / 'metadata.json').read_text(encoding='utf-8'))['frames']
    with a.csv.open(newline='', encoding='utf-8') as f:
        rows = {(r['frame'], r['mode']): r for r in csv.DictReader(f)}
    count = 0
    for index, record in enumerate(records):
        packet = (a.package / record['file']).read_bytes()
        assert hashlib.sha256(packet).hexdigest() == record['sha256']
        folder = a.data_root / CONFIG[record['workload']][0]
        tree = ast.parse((folder / 'test_numba.py').read_text(encoding='utf-8'))
        func = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'calculate_psnr')
        ns = {'np': np}
        exec(compile(ast.Module(body=[func], type_ignores=[]), '<original-psnr>', 'exec'), ns)
        with Image.open(folder / 'right' / ('%04d.png' % record['frame'])) as im:
            gt = np.asarray(im.convert('RGB'))
        for mode in ('full', 'half_base', 'fov'):
            with Image.open(str(a.dump_prefix) + '_%d_%s.ppm' % (index, mode)) as im:
                out = np.asarray(im.convert('RGB'))
            expected = ns['calculate_psnr'](out, gt)
            actual = float(rows[(record['file'], mode)]['legacy_right_psnr_db'])
            if not np.isclose(expected, actual, atol=1e-7, rtol=0):
                raise AssertionError((record['file'], mode, expected, actual))
            count += 1
    print('VERIFIED: %d packet hashes; %d CUDA output scores match original PSNR' % (len(records), count))


if __name__ == '__main__':
    main()
