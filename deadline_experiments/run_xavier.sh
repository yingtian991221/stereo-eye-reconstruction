#!/usr/bin/env bash
set -euo pipefail
# Run from an isolated experiment directory. Inputs must already be exported.
# Never changes power mode or clocks and never overwrites an existing run.
CUDA_HOME=${CUDA_HOME:-/home/yingtian/stereo-fov-20261027/toolchain/root/usr/local/cuda-11.4}
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:?new output directory}; PROFILE=${2:?profile clip}; EVAL=${3:?evaluation clip}
mkdir "$OUT"
nvcc -O3 -std=c++14 --fmad=false -arch=sm_72 -Xcompiler -pthread "$ROOT/deadline_experiments/readiness.cu" -lz -o "$OUT/readiness"
"$OUT/readiness" --self-test > "$OUT/self_test.log"
"$OUT/readiness" profile "$PROFILE" "$OUT/profile.csv"
python3 "$ROOT/deadline_experiments/prepare.py" "$OUT/profile.csv" "$OUT/frozen"
cp "$OUT/frozen/"* "$OUT/"
mkdir "$OUT/replay"
(nvpmodel -q; uname -a; "$CUDA_HOME/bin/nvcc" --version) > "$OUT/environment.txt" 2>&1
tegrastats --interval 1000 > "$OUT/tegrastats.log" & TELEMETRY_PID=$!
trap 'kill "$TELEMETRY_PID" 2>/dev/null || true' EXIT
"$OUT/readiness" replay "$EVAL" "$OUT/replay" "$OUT/release_plan.csv" "$OUT/estimates.csv" 3 | tee "$OUT/replay.log"
"$OUT/readiness" replay "$EVAL" "$OUT/replay" "$OUT/release_plan_generous.csv" "$OUT/estimates.csv" 3 | tee "$OUT/generous.log"
# Analyze on the host with NumPy/pandas/matplotlib. No plotting during playback.
