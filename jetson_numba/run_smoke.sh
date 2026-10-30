#!/usr/bin/env bash
set -euo pipefail
# Override these for another Jetson installation.
export CUDA_HOME="${CUDA_HOME:-/home/yingtian/stereo-fov-20261027/toolchain/root/usr/local/cuda-11.4}"
export PATH="$CUDA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$CUDA_HOME/lib64:${LD_LIBRARY_PATH:-}"
PYTHON="${PYTHON:-/home/yingtian/venvs/stereo-numba/bin/python}"
exec "$PYTHON" "$(dirname "$0")/run_smoke.py" "$@"
