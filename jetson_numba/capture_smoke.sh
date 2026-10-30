#!/usr/bin/env bash
set -euo pipefail
# This script records the current mode; it never changes power/clock settings.
OUT="$1"
DATA="$2"
mkdir "$OUT"
{
  date -Iseconds
  nvpmodel -q || true
  cat /sys/devices/system/cpu/online
  cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq
  cat /sys/devices/17000000.gv11b/devfreq/17000000.gv11b/max_freq
  cat /sys/devices/17000000.gv11b/devfreq/17000000.gv11b/governor
} > "$OUT/environment.txt" 2>&1
tegrastats --interval 200 --logfile "$OUT/tegrastats.log" &
MONITOR=$!
trap 'kill "$MONITOR" 2>/dev/null || true' EXIT
set +e
bash "$(dirname "$0")/run_smoke.sh" --data-root "$DATA" --out "$OUT/result.json" --repeats 100 > "$OUT/run.log" 2>&1
STATUS=$?
set -e
echo "$STATUS" > "$OUT/exit_code"
exit "$STATUS"
