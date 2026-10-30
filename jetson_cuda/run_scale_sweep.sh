#!/usr/bin/env bash
set -euo pipefail
BASE=/home/yingtian/stereo-scales-20261029
export PATH="/home/yingtian/stereo-fov-20261027/toolchain/root/usr/local/cuda-11.4/bin:$PATH"
cd "$BASE"
set +e
/home/yingtian/venvs/stereo-numba/bin/python src/evaluate_levels.py \
  --binary "$BASE/pirate_bench" \
  --manifest /home/yingtian/stereo-fov-full-20261027/fov_full1068/manifest.txt \
  --levels 96x54,240x135,480x270,720x405 --timing resident \
  --batch-size 32 --warmup 3 --repeats 5 --quality-runs 1 --fast-resample \
  --out "$BASE/full1068"
STATUS=$?
echo "$STATUS" > "$BASE/exit_code"
exit "$STATUS"
