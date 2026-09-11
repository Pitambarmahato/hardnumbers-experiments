#!/usr/bin/env bash
cd "$(dirname "$0")"
while true; do
  out=$(python3 run_bench.py 2>&1)
  echo "$out"
  if echo "$out" | grep -q "All .* runs complete"; then
    echo "DONE_ALL"
    break
  fi
done
