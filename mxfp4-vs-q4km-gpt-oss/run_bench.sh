#!/bin/sh
for q in Q4_K_M MXFP4; do
  echo "=== $q ===" 
  llama-bench -m openai_gpt-oss-20b-$q.gguf -p 512 -n 128 -r 3 -ngl 99 -o md 2>&1 | grep -v "^load_backend\|^ggml_"
  sleep 20
done
echo ALLDONE
