#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 2 ]]; then
  echo 'Usage: bash jetson_cuda/run_levels.sh DATA_ROOT NEW_OUTDIR [SAMPLES_PER_WORKLOAD=16] [REPEATS=100]' >&2
  exit 2
fi
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
data_root=$1
out=$2
samples=${3:-16}
repeats=${4:-100}
if [[ -e "$out" ]]; then
  echo "Refusing to overwrite existing experiment: $out" >&2
  exit 2
fi
export PATH=/usr/local/cuda/bin:$PATH
mkdir -p "$out"
nvcc -O3 -std=c++14 --fmad=false -arch=sm_72 \
  "$root/jetson_cuda/pirate_bench.cu" -o "$out/pirate_bench"
python3 "$root/jetson_cuda/export_frames.py" --data-root "$data_root" \
  --out "$out/packets" --sample-count "$samples"
python3 "$root/jetson_cuda/evaluate_levels.py" --binary "$out/pirate_bench" \
  --manifest "$out/packets/manifest.txt" --out "$out/evaluation" \
  --repeats "$repeats" --quality-runs 3 --timing both --batch-frames
