#!/bin/zsh
# Full matrix: 3 repeats x 5 scenarios x 3 variants = 45 runs (about 45 min). Skips finished runs. An s3 run whose kill landed after the load is repeated once.
cd "$(dirname "$0")"
mkdir -p results/full
for rep in 0 1 2; do for sc in s1 s2 s3 s4 s5; do for v in naive idem-local idem-e2e; do
  f=results/full/$sc-$v-r$rep.json
  [ -f $f ] && continue
  echo "== $sc $v r$rep $(date +%T)"; .venv/bin/python3 run.py --variant $v --scenario $sc --rep $rep | tail -2
  if [ $sc = s3 ] && grep -q '"kill_during_load": false' $f; then echo "RERUN (kill after load)"; rm $f; .venv/bin/python3 run.py --variant $v --scenario $sc --rep $rep | tail -1; fi
done; done; done
echo DONE
