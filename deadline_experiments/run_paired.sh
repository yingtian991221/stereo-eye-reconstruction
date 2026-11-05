#!/usr/bin/env bash
set -euo pipefail
# Separate from playback. Never run this concurrently with readiness trials.
OUT=${1:?new output directory}
PACKETS=${2:?directory containing driving_*_0039.pir}
DATA=${3:?dataset root containing original per-workload test_numba.py}
NUMBA_PYTHON=${4:?Python executable with Numba installed}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
CUDA_HOME=${CUDA_HOME:-/home/yingtian/stereo-fov-20261027/toolchain/root/usr/local/cuda-11.4}
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
mkdir "$OUT"
nvcc -O3 -std=c++14 --fmad=false -arch=sm_72 "$ROOT/deadline_experiments/paired_full.cu" -o "$OUT/paired_full"
mkdir "$OUT/paired_cpp"
for workload in 15_300 15_800 35_300 35_800; do
    "$OUT/paired_full" "$PACKETS/driving_${workload}_0039.pir" "$OUT/paired_cpp/driving_${workload}.csv"
done
"$NUMBA_PYTHON" "$ROOT/deadline_experiments/paired_numba.py" --source-root "$ROOT" --data-root "$DATA" --packets "$PACKETS" --out "$OUT/paired_numba"
