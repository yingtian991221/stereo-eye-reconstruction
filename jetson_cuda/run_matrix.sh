#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 2 ]]; then
  echo "Usage: PIRATE_BIN=./build/pirate_bench bash jetson_cuda/run_matrix.sh MANIFEST OUTDIR [REPEATS]" >&2
  exit 2
fi
manifest=$1
out=$2
repeats=${3:-100}
binary=${PIRATE_BIN:-./build/pirate_bench}
mkdir -p "$out"
{
  date -Is
  uname -a
  cat /etc/nv_tegra_release 2>/dev/null || true
  nvcc --version || true
  command -v nvpmodel >/dev/null && nvpmodel -q || true
} > "$out/environment.txt" 2>&1
"$binary" --self-test | tee "$out/self_test.txt"
for size in '160 90' '320 180' '480 270'; do
  read -r width height <<< "$size"
  for timing in resident stream; do
    extra=()
    [[ $timing == stream ]] && extra=(--stream)
    "$binary" --manifest "$manifest" --roi-width "$width" --roi-height "$height" \
      --warmup 10 --repeats "$repeats" --csv "$out/${timing}_${width}x${height}.csv" \
      "${extra[@]}" | tee "$out/${timing}_${width}x${height}.log"
  done
done
