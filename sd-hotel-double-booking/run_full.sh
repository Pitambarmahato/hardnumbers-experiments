#!/bin/zsh
# Full matrix: 3 repeats x 3 scenarios x 5 variants = 45 runs. Skips finished runs.
cd "$(dirname "$0")"
mkdir -p results/full
docker compose up -d --wait pg
for rep in 0 1 2; do for sc in s1 s2 s3; do for v in naive pessimistic optimistic exclusion exclusion-retry; do
  f=results/full/$sc-$v-r$rep.json
  [ -f $f ] && continue
  echo "== $sc $v r$rep $(date +%T)"; .venv/bin/python3 run.py --variant $v --scenario $sc --rep $rep | tail -1
done; done; done
echo DONE
