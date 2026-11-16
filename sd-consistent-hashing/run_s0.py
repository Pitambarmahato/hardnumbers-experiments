#!/usr/bin/env python3
"""S0 (offline): consistent hashing vs mod-N, no servers.

Hashes 100,000 keys and measures, for mod-N and for a hash ring with V virtual nodes per node:
  - share of keys that change owner when a node is added (3 -> 4) or removed (3 -> 2)
  - per-node load balance: coefficient of variation (std/mean) and peak-to-average (max/mean)
A ring's layout is random-ish, so each ring config is repeated over 50 node-name salts (min/median/max).
Deterministic: same keys, same salts, same hash -> same numbers. Standard library only.

Usage: python3 run_s0.py [--keys 100000] [--trials 50] [--out results/s0.json]
Pre-registered hypotheses: docs/kw-sd-consistent-hashing.md (H1-H6, amendment A1).
"""
import argparse, bisect, hashlib, json, platform, statistics as st, sys, time
from pathlib import Path

HERE = Path(__file__).parent
VNODES = [1, 10, 50, 150, 500]


def h64(s):
    return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")


def ring(nodes, v, salt):
    """Sorted (point, node) list; a node's points depend only on (salt, node, i), so adding a node keeps the rest."""
    pts = sorted((h64(f"{salt}/node-{n}#{i}"), n) for n in nodes for i in range(v))
    return [p for p, _ in pts], [n for _, n in pts]


def ring_owners(key_hashes, points, owners):
    n = len(points)
    return [owners[bisect.bisect_left(points, kh) % n] for kh in key_hashes]


def load_stats(owner_list, nodes):
    counts = [owner_list.count(n) for n in nodes]
    mean = sum(counts) / len(counts)
    return {"cv_pct": 100 * st.pstdev(counts) / mean, "peak_avg": max(counts) / mean, "counts": counts}


def moved(a, b):
    return sum(x != y for x, y in zip(a, b)) / len(a)


def spread(vals):
    return {"min": min(vals), "median": st.median(vals), "max": max(vals)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keys", type=int, default=100000)
    ap.add_argument("--trials", type=int, default=50)
    ap.add_argument("--out", default="results/s0.json")
    a = ap.parse_args()
    t0 = time.time()
    K = a.keys
    kh = [h64(f"key:{i}") for i in range(K)]

    # ---- mod-N: no layout, one value ----
    m3, m4, m2 = ([h % n for h in kh] for n in (3, 4, 2))
    modn = {
        "moved_add_3_to_4": moved(m3, m4), "moved_remove_3_to_2": moved(m3, m2),
        "load_n3": load_stats(m3, range(3)), "load_n4": load_stats(m4, range(4)),
    }

    # ---- ring: V virtual nodes, repeated over salts ----
    rings = {}
    for v in VNODES:
        rows = {"add": [], "remove": [], "cv3": [], "cv4": [], "pa3": [], "pa4": []}
        for t in range(a.trials):
            salt = f"t{t}"
            o3 = ring_owners(kh, *ring([0, 1, 2], v, salt))
            o4 = ring_owners(kh, *ring([0, 1, 2, 3], v, salt))
            o2 = ring_owners(kh, *ring([0, 1], v, salt))      # node 2 removed
            # self-check: on a ring, every key that moves when node 3 is added moves TO node 3
            assert all(n4 == 3 for n3, n4 in zip(o3, o4) if n3 != n4), "ring moved a key somewhere other than the new node"
            # and removal only moves the removed node's keys
            assert all(n3 == 2 for n3, n2 in zip(o3, o2) if n3 != n2), "ring moved a key that the removed node did not own"
            l3, l4 = load_stats(o3, range(3)), load_stats(o4, range(4))
            assert sum(l3["counts"]) == K and sum(l4["counts"]) == K
            rows["add"].append(moved(o3, o4)); rows["remove"].append(moved(o3, o2))
            rows["cv3"].append(l3["cv_pct"]); rows["cv4"].append(l4["cv_pct"])
            rows["pa3"].append(l3["peak_avg"]); rows["pa4"].append(l4["peak_avg"])
        rings[v] = {k: spread(x) for k, x in rows.items()}
        print(f"V={v:<4} add median {rings[v]['add']['median']:.1%}  cv(4 nodes) median {rings[v]['cv4']['median']:.1f}%  [{time.time()-t0:.0f}s]", flush=True)

    gate_modn = modn["moved_add_3_to_4"]
    gate_ring = rings[150]["add"]["median"]
    gate = gate_modn > 0.50 and gate_ring < 0.35
    out = {
        "meta": {"keys": K, "trials": a.trials, "vnodes": VNODES, "hash": "blake2b-64", "python": platform.python_version(),
                 "seconds": round(time.time() - t0, 1), "key_format": "key:{i}", "salts": "t0..t%d" % (a.trials - 1)},
        "modn": modn, "ring": {str(v): r for v, r in rings.items()},
        "gate": {"rule": "mod-N moves >50% and ring V=150 median moves <35% (3 -> 4 nodes)", "modn": gate_modn, "ring_v150_median": gate_ring, "pass": gate},
    }
    p = HERE / a.out
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(out, indent=1))
    print(f"\nGATE {'PASS' if gate else 'FAIL'}: mod-N {gate_modn:.1%} (need >50%), ring V=150 {gate_ring:.1%} (need <35%)")
    print("wrote", p)
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main())
