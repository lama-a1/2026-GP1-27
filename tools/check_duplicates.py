"""Near-duplicate check across dataset splits (GP report Section 4.4.3, leakage).

Five frames per clip (first, quarter, middle, three-quarter, last) are reduced to a 256-bit difference hash.
For every pair of clips the smallest Hamming distance over the 5 x 5 frame pairs is computed. Near-identical
frames usually differ by fewer than 15 bits.

    python tools/check_duplicates.py --dataset /path/to/Siyaq_Part1/dataset [--out experiments/history/duplicate_check.json]
"""
import argparse, csv, itertools, json
from pathlib import Path

import cv2
import numpy as np


def dhash(im, n=16):
    g = cv2.cvtColor(cv2.resize(im, (n + 1, n)), cv2.COLOR_BGR2GRAY)
    return (g[:, 1:] > g[:, :-1]).flatten()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--out", default="experiments/history/duplicate_check.json")
    ap.add_argument("--threshold", type=int, default=15)
    a = ap.parse_args()
    rows = list(csv.DictReader(open(Path(a.dataset) / "dataset_index.csv")))
    H, split = {}, {}
    for r in rows:
        cap = cv2.VideoCapture(str(Path(a.dataset) / r["file"]))
        fr = []
        while True:
            ok, im = cap.read()
            if not ok:
                break
            fr.append(im)
        idx = [0, len(fr) // 4, len(fr) // 2, 3 * len(fr) // 4, len(fr) - 1]
        H[r["clip_id"]] = [dhash(fr[i]) for i in idx]
        split[r["clip_id"]] = r["split"]
    pairs = sorted((min(int((x != y).sum()) for x in H[a_] for y in H[b]), a_, b) for a_, b in itertools.combinations(H, 2))
    cross = [p for p in pairs if split[p[1]] != split[p[2]]]
    out = {"n_clips": len(H), "n_pairs": len(pairs), "threshold_bits": a.threshold,
           "pairs_below_threshold": [p for p in pairs if p[0] < a.threshold],
           "closest_pairs": [{"bits": d, "a": x, "b": y, "split_a": split[x], "split_b": split[y]} for d, x, y in pairs[:10]],
           "closest_cross_split_pairs": [{"bits": d, "a": x, "b": y, "split_a": split[x], "split_b": split[y]} for d, x, y in cross[:10]]}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("n_clips", "n_pairs", "pairs_below_threshold")}), out["closest_pairs"][0], out["closest_cross_split_pairs"][0])


if __name__ == "__main__":
    main()
