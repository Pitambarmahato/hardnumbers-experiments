#!/bin/sh
for q in Q4_K_M MXFP4; do
  echo "=== $q ==="
  llama-perplexity -m openai_gpt-oss-20b-$q.gguf -f wiki.test.raw -c 512 --chunks 60 -ngl 99 2>&1 | grep -E "PPL|Final|perplexity:|tokens per second|total time"
  sleep 20
done
echo ALLDONE
