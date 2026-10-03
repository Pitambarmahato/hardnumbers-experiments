"""Print bytes per (tensor kind, storage type) for a GGUF. Usage: tensor_anatomy.py file.gguf"""
import re, sys
from collections import defaultdict
from gguf import GGUFReader

r = GGUFReader(sys.argv[1])
agg = defaultdict(lambda: [0, 0])
for t in r.tensors:
    k = (re.sub(r"blk\.\d+\.", "", t.name), t.tensor_type.name)
    agg[k][0] += 1
    agg[k][1] += int(t.n_bytes)
total = sum(b for _, b in agg.values())
print(f"# {sys.argv[1]}  total {total/2**30:.2f} GiB")
for (k, ty), (n, b) in sorted(agg.items(), key=lambda x: -x[1][1]):
    print(f"{k:28s} {ty:8s} n={n:3d} {b/2**30:6.3f} GiB {100*b/total:5.1f}%")
