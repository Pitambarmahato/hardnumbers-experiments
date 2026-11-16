#!/bin/zsh
# Full online matrix: 3 repeats x 4 scenarios x 4 schemes = 48 runs, ~50 min. Skips finished runs, so it can be restarted.
cd "$(dirname "$0")"
for rep in 0 1 2; do for sc in s1 s2 s3 s4; do for sch in modn ring1 ring10 ring150; do
  f=results/online/$sc-$sch-r$rep.json
  [ -f $f ] && continue
  echo "== $sc $sch r$rep $(date +%T)"; .venv/bin/python3 online.py --scenario $sc --scheme $sch --rep $rep | tail -1 || echo FAILED
done; done; done
echo DONE
