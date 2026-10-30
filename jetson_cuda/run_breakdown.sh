#!/usr/bin/env bash
set -euo pipefail
# All inputs must already be decoded. This script does not change power mode.
BINARY=$(realpath "$1")
MANIFEST=$(realpath "$2")
OUT="$3"
mkdir "$OUT"
mkdir "$OUT/raw"
{
  date -Iseconds
  nvpmodel -q || true
  cat /var/lib/nvpmodel/status
  cat /sys/devices/system/cpu/online
  cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq
  cat /sys/devices/17000000.gv11b/devfreq/17000000.gv11b/max_freq
  cat /sys/devices/17000000.gv11b/devfreq/17000000.gv11b/governor
  sha256sum "$BINARY" "$MANIFEST"
} > "$OUT/environment.txt" 2>&1
tegrastats --interval 200 --logfile "$OUT/tegrastats.log" &
MONITOR=$!
(
  echo 'unix_time,gpu_hz,cpu0_khz'
  while true; do
    read -r gpu < /sys/devices/17000000.gv11b/devfreq/17000000.gv11b/cur_freq
    read -r cpu < /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq
    printf '%s,%s,%s\n' "$(date +%s.%N)" "$gpu" "$cpu"
    sleep 0.2
  done
) > "$OUT/frequencies.csv" &
FREQUENCIES=$!
trap 'kill "$MONITOR" "$FREQUENCIES" 2>/dev/null || true' EXIT
for roi in 80x46 160x90 320x180 480x270 640x360; do
  width=${roi%x*}
  height=${roi#*x}
  for timing in resident stream; do
    args=()
    if [[ "$timing" == stream ]]; then args+=(--stream); fi
    "$BINARY" --manifest "$MANIFEST" --roi-width "$width" --roi-height "$height" \
      --warmup 10 --repeats 100 --fast-resample "${args[@]}" \
      --csv "$OUT/raw/${roi}_${timing}.csv" > "$OUT/raw/${roi}_${timing}.log" 2>&1
    echo "$roi $timing COMPLETE"
  done
done
date -Iseconds > "$OUT/COMPLETE"
