#!/usr/bin/env bash
# Dispatches to one of the three harnesses under test, all pointed at the
# same host Ollama model. Expects:
#   HARNESS       - "dsh" | "opencode" | "aider"
#   TASK_PROMPT   - the task text
# Runs in /workspace (the task repo, mounted by the caller).
# Writes /workspace/out/{log.txt,exit_code,duration_seconds}.
set -uo pipefail

mkdir -p /workspace/out
LOG=/workspace/out/log.txt
MODEL="qwen3-14b-ctx16k"

start=$(date +%s.%N)

case "$HARNESS" in
  dsh)
    dsh --profile headless "$TASK_PROMPT" >"$LOG" 2>&1
    ;;
  opencode)
    opencode run -m "ollama/${MODEL}" "$TASK_PROMPT" >"$LOG" 2>&1
    ;;
  aider)
    aider --model "ollama/${MODEL}" --message "$TASK_PROMPT" --yes --no-analytics >"$LOG" 2>&1
    ;;
  *)
    echo "Unknown HARNESS: $HARNESS" >"$LOG"
    exit_code=2
    ;;
esac

exit_code=${exit_code:-$?}
end=$(date +%s.%N)

echo "$exit_code" > /workspace/out/exit_code
echo "$end - $start" | bc > /workspace/out/duration_seconds 2>/dev/null \
  || python3 -c "print($end - $start)" > /workspace/out/duration_seconds

exit 0
