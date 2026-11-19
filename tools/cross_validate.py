"""Repeated stratified k-fold cross-validation of the Siyaq event rules on the team's CVAT labels.

    python tools/cross_validate.py --videos <folder with dataset_index.csv and videos/> --out cv_output
    python tools/cross_validate.py ... --labels data/ground_truth/cvat_labels.json --folds 5 --repeats 5 --seed 42

How it works
  1. The engine (siyaq_cv) runs once per clip; its output is cached in --cache (a clip is only re-run when the engine
     code changes). Detection, tracking and the measures do not depend on the thresholds, so the folds only replay
     the event rules (siyaq_cv.events.analyse) with different thresholds, which takes milliseconds.
  2. The clips are split with RepeatedStratifiedKFold (scikit-learn), stratified by source dataset x accident type.
  3. In every fold the thresholds are chosen by grid search on the TRAINING folds only (the lane-change thresholds
     separately for each accident type of the report, as the engine uses them: siyaq_cv/config.py LANE_BY_TYPE) (candidate values and their
     published sources: siyaq_cv/threshold_grid.py), then the held-out fold is scored with them. The held-out fold
     never takes part in the choice, which avoids the optimistic bias of choosing thresholds on all clips first
     (Varma & Simon 2006; Cawley & Talbot 2010; Vabalas et al. 2019).
  4. The same folds score three reference systems: the engine with its default thresholds, and two simple
     baselines (majority class of the training folds; impact at the median impact frame of the training folds).
  5. Results: mean +- standard deviation over the folds, a bootstrap 95 % confidence interval over the clips,
     how often each threshold value was chosen, and the thresholds chosen on all clips (the values to put in
     siyaq_cv/config.py).

Outputs (in --out): cv_results.xlsx, cv_results.json, per_clip.csv
"""
import argparse
import copy
import csv
import hashlib
import itertools
import json
import random
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from siyaq_cv import config, events  # noqa: E402
from siyaq_cv.threshold_grid import GRID, STAGES  # noqa: E402
from scoring import COLLISION_TOL, TIOU_THR, B_IOU_THR, B_FRAME_TOL, box_iou, tiou, sd_at  # noqa: E402

METRICS = ["collision", "vehicle_b", "lane_change", "sudden_stop", "safe_distance", "lane_change_vehicle"]
# lane_change_vehicle: the same lane-change labels scored on WHICH vehicle changed lane (A, B or none) only, without the
# timing (temporal IoU); reported next to lane_change, never used to choose thresholds
TUNED = list(GRID)


# ----------------------------------------------------------------------------------------- engine runs (cached)
def engine_fingerprint():
    h = hashlib.sha256()
    for p in sorted((ROOT / "siyaq_cv").glob("*.py")):
        if p.name != "threshold_grid.py":
            h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()[:12]


def run_engine(clip, video, cache):
    """Engine output for one clip, without pictures; cached per engine version."""
    path = cache / f"{clip}.json"
    fp = engine_fingerprint()
    if path.exists():
        r = json.loads(path.read_text())
        if r.get("_engine") == fp:
            return r
    from siyaq_cv.analyse import analyse_video
    r = analyse_video(str(video), thumbnails=False)
    keep = {k: r[k] for k in ("vehicle_b", "collision_frame", "measures_b", "series", "events", "tracks", "video", "lanes", "lane_band")}
    keep["_engine"] = fp
    path.write_text(json.dumps(keep))
    return keep


# ----------------------------------------------------------------------------------------- replay with thresholds
def replay(r, th):
    """Event rules of one clip with the thresholds `th` (detection/tracking/measures unchanged)."""
    saved = {k: getattr(config, k) for k in th}
    try:
        for k, v in th.items():
            setattr(config, k, v)
        b = r["vehicle_b"]
        mb = {int(k): v for k, v in r["measures_b"].items()}
        s = r["series"]
        n = len(s["t"])
        flow = {"jolt": s["jolt"], "yaw_rate": s["a_heading_rate_deg_s"], "ego_dx": [0.0] * n}
        scene = {"b_boxes": {int(x[0]): x[1:5] for x in r["tracks"].get(str(b), [])} if b is not None else {},
                 "lanes": {}, "lane_band": r.get("lane_band")}
        for ln in r.get("lanes", []):
            scene["lanes"].setdefault(int(ln["frame"]), []).append(ln)
        evs, crash = events.analyse({b: mb} if b is not None else {}, b, flow, s["t"], None, scene)
    finally:
        for k, v in saved.items():
            setattr(config, k, v)
    boxes = r["tracks"].get(str(b), []) if b is not None else []
    return {"events": evs, "collision_frame": crash, "vehicle_b": b, "vehicle_b_boxes": boxes}


# ----------------------------------------------------------------------------------------- per-clip scoring
def _vehicle(v):
    if not v:
        return "none"
    v = str(v).replace("Vehicle", "").strip().upper()
    return v if v in ("A", "B") else "none"


def score(ref, pred):
    """Per clip: 1/0 for each element whose labels are valid, None when the element cannot be scored."""
    v = ref["valid_for"]
    out = dict.fromkeys(METRICS)
    crash = pred["collision_frame"]
    if v["collision"]:
        out["collision"] = int(crash is not None and abs(crash - ref["collision_frame"]) <= COLLISION_TOL)
    if v["vehicle_b"]:
        boxes = {int(x[0]): x[1:5] for x in pred["vehicle_b_boxes"]}
        common = [f for f in boxes if str(f) in ref["vehicle_b"]["boxes"]]
        mi = st.mean(box_iou(boxes[f], ref["vehicle_b"]["boxes"][str(f)]) for f in common) if common else 0.0
        out["vehicle_b"] = int(mi >= B_IOU_THR)
    lc = next((e for e in pred["events"] if e["type"] == "lane_change"), None)
    if v["lane_change"]:
        g = ref["lane_change"]
        gv, pv = _vehicle(g and g.get("vehicle")), _vehicle(lc and lc.get("vehicle"))
        ok = gv == pv
        if ok and g and lc and None not in (g.get("start"), g.get("end")):
            ok = tiou((lc["start"], lc["end"]), (g["start"], g["end"])) >= TIOU_THR
        out["lane_change"] = int(ok)
        out["lane_change_vehicle"] = int(gv == pv)
        out["_lc_ref"], out["_lc_pred"] = gv != "none", lc is not None
    ss = next((e for e in pred["events"] if e["type"] == "sudden_stop"), None)
    if v["sudden_stop"]:
        out["sudden_stop"] = int(bool(ref["sudden_stop"]) == (ss is not None))
        out["_ss_ref"], out["_ss_pred"] = bool(ref["sudden_stop"]), ss is not None
    fd = next((e for e in pred["events"] if e["type"] == "following_distance"), None)
    if v["safe_distance"]:
        rv = sd_at(ref, ref["collision_frame"])
        if rv in ("Maintained", "Not maintained"):
            p = fd["measures"].get("safe_distance") if fd else None
            out["safe_distance"] = int(p == rv)
    return out


def accuracy(rows, m):
    vals = [r[m] for r in rows if r.get(m) is not None]
    return sum(vals) / len(vals) if vals else None


def prf(rows, ref_key, pred_key, metric):
    """Precision / recall / F1 of an event's presence (matched = present in both and scored correct)."""
    tp = sum(1 for r in rows if r.get(ref_key) and r.get(pred_key) and r.get(metric) == 1)
    fp = sum(1 for r in rows if r.get(pred_key) and not (r.get(ref_key) and r.get(metric) == 1))
    fn = sum(1 for r in rows if r.get(ref_key) and not (r.get(pred_key) and r.get(metric) == 1))
    p = tp / (tp + fp) if tp + fp else None
    rc = tp / (tp + fn) if tp + fn else None
    f = 2 * p * rc / (p + rc) if p and rc else (0.0 if p is not None and rc is not None else None)
    return p, rc, f


# ----------------------------------------------------------------------------------------- choosing thresholds
TYPES = ("REAR_END", "LANE_CHANGE")
LANE_KEYS = events.LANE_KEYS


def _search(clips, stages, start, th_of, refs, runs):
    """Greedy staged grid search; th_of(cand, clip) gives the thresholds used for a clip."""
    th = dict(start)
    for keys, metric in stages:
        best = None
        for vals in itertools.product(*[GRID[k] for k in keys]):
            cand = dict(th, **dict(zip(keys, vals)))
            rows = [score(refs[c], replay(runs[c], th_of(cand, c))) for c in clips]
            a = accuracy(rows, metric)
            if a is not None and (best is None or a > best[0] + 1e-9):
                best = (a, dict(zip(keys, vals)))
        if best:
            th.update(best[1])
    return th


def choose(clips, preds_cache, refs, runs, types=None):
    """Staged grid search on the given (training) clips. Returns {report type: thresholds}.

    The lane-change stages are searched separately on the clips of each report type (the accident type given by the
    user; config.LANE_BY_TYPE); the other stages are searched on all clips with those lane-change values."""
    start = {k: getattr(config, k) for k in TUNED}
    lane_stages = [st_ for st_ in STAGES if st_[1] == "lane_change"]
    other = [st_ for st_ in STAGES if st_[1] != "lane_change"]
    per = {t: _search([c for c in clips if types[c] == t], lane_stages, start, lambda cand, c: cand, refs, runs)
           for t in TYPES}

    def th_of(cand, c):
        return dict(cand, **{k: per[types[c]][k] for k in LANE_KEYS})
    shared = _search(clips, other, start, th_of, refs, runs)
    return {t: dict(shared, **{k: per[t][k] for k in LANE_KEYS}) for t in TYPES}


def baseline_rows(train, test, refs):
    """Simple references fitted on the training clips: majority class, median impact frame."""
    def maj(values, default):
        values = [x for x in values if x is not None]
        return max(set(values), key=values.count) if values else default
    lc_maj = maj([_vehicle(refs[c]["lane_change"] and refs[c]["lane_change"].get("vehicle")) for c in train
                  if refs[c]["valid_for"]["lane_change"]], "none")
    ss_maj = maj([bool(refs[c]["sudden_stop"]) for c in train if refs[c]["valid_for"]["sudden_stop"]], False)
    sd_maj = maj([sd_at(refs[c], refs[c]["collision_frame"]) for c in train if refs[c]["valid_for"]["safe_distance"]
                  and sd_at(refs[c], refs[c]["collision_frame"]) in ("Maintained", "Not maintained")], "Maintained")
    med = int(st.median([refs[c]["collision_frame"] for c in train if refs[c]["valid_for"]["collision"]] or [25]))
    out = []
    for c in test:
        ref = refs[c]
        v = ref["valid_for"]
        r = dict.fromkeys(METRICS)
        r["clip_id"] = c
        if v["collision"]:
            r["collision"] = int(abs(med - ref["collision_frame"]) <= COLLISION_TOL)
        if v["lane_change"]:
            r["lane_change"] = r["lane_change_vehicle"] = int(_vehicle(ref["lane_change"] and ref["lane_change"].get("vehicle")) == lc_maj)
        if v["sudden_stop"]:
            r["sudden_stop"] = int(bool(ref["sudden_stop"]) == ss_maj)
        if v["safe_distance"]:
            rv = sd_at(ref, ref["collision_frame"])
            if rv in ("Maintained", "Not maintained"):
                r["safe_distance"] = int(rv == sd_maj)
        out.append(r)
    return out


def bootstrap_ci(values, n=2000, seed=0):
    values = [v for v in values if v is not None]
    if not values:
        return None, None
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


# ----------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--videos", required=True, help="folder with dataset_index.csv and the clip videos (column 'file')")
    ap.add_argument("--labels", default=str(ROOT / "data" / "ground_truth" / "cvat_labels.json"))
    ap.add_argument("--index", default=str(ROOT / "data" / "dataset" / "dataset_index.csv"))
    ap.add_argument("--cache", default=str(ROOT / ".cv_cache"))
    ap.add_argument("--out", default=str(ROOT / "cv_output"))
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    from sklearn.model_selection import RepeatedStratifiedKFold

    idx = {r["clip_id"]: r for r in csv.DictReader(open(a.index))}
    refs = json.loads(Path(a.labels).read_text())["clips"]
    clips = sorted(c for c in refs if c in idx)
    missing = sorted(set(idx) - set(refs))
    cache = Path(a.cache); cache.mkdir(parents=True, exist_ok=True)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    runs, t0 = {}, time.time()
    for k, c in enumerate(clips, 1):
        runs[c] = run_engine(c, Path(a.videos) / idx[c]["file"], cache)
        print(f"\rengine {k}/{len(clips)}  {time.time() - t0:.0f} s", end="", flush=True)
    print()
    default1 = {k: getattr(config, k) for k in TUNED}
    default = {t: default1 for t in TYPES}
    types = {c: events.report_type(idx[c]["accident_type"]) for c in clips}
    group = [f"{idx[c]['source']}|{idx[c]['accident_type']}" for c in clips]

    cv = RepeatedStratifiedKFold(n_splits=a.folds, n_repeats=a.repeats, random_state=a.seed)
    folds, per_clip, chosen = [], [], []
    for f, (tr, te) in enumerate(cv.split(clips, group)):
        train, test = [clips[i] for i in tr], [clips[i] for i in te]
        th = choose(train, None, refs, runs, types)
        chosen.append(th)
        rows = []
        for c in test:
            r = score(refs[c], replay(runs[c], th[types[c]])); r.update(clip_id=c, fold=f, repeat=f // a.folds, system="cross-validated")
            rows.append(r)
            d = score(refs[c], replay(runs[c], default[types[c]])); d.update(clip_id=c, fold=f, repeat=f // a.folds, system="default thresholds")
            rows.append(d)
        for b in baseline_rows(train, test, refs):
            b.update(fold=f, repeat=f // a.folds, system="baseline"); rows.append(b)
        per_clip += rows
        fr = {"fold": f + 1, "repeat": f // a.folds + 1, "n_train": len(train), "n_test": len(test)}
        for sysname in ("cross-validated", "default thresholds", "baseline"):
            rs = [r for r in rows if r["system"] == sysname]
            for m in METRICS:
                fr[f"{sysname}|{m}"] = accuracy(rs, m)
        folds.append(fr)
        print(f"fold {f + 1}/{a.folds * a.repeats}: " +
              ", ".join(f"{m} {fr['cross-validated|' + m]:.2f}" for m in METRICS if fr["cross-validated|" + m] is not None))

    summary = []
    for sysname in ("cross-validated", "default thresholds", "baseline"):
        for m in METRICS:
            vals = [fr[f"{sysname}|{m}"] for fr in folds if fr[f"{sysname}|{m}"] is not None]
            # per clip: mean correctness over the repeats, then a bootstrap interval over the clips
            by_clip = {}
            for r in per_clip:
                if r["system"] == sysname and r.get(m) is not None:
                    by_clip.setdefault(r["clip_id"], []).append(r[m])
            lo, hi = bootstrap_ci([st.mean(v) for v in by_clip.values()])
            summary.append({"system": sysname, "measure": m, "n_clips": len(by_clip),
                            "mean": st.mean(vals) if vals else None, "std": st.stdev(vals) if len(vals) > 1 else None,
                            "min": min(vals) if vals else None, "max": max(vals) if vals else None, "ci95_low": lo, "ci95_high": hi})
    cvrows = [r for r in per_clip if r["system"] == "cross-validated"]
    lc_p, lc_r, lc_f = prf(cvrows, "_lc_ref", "_lc_pred", "lane_change")
    ss_p, ss_r, ss_f = prf(cvrows, "_ss_ref", "_ss_pred", "sudden_stop")

    stability = []
    for k in TUNED:
        for t in (TYPES if k in LANE_KEYS else (None,)):
            counts = {}
            for th in chosen:
                v = th[t or TYPES[0]][k]
                counts[v] = counts.get(v, 0) + 1
            top = max(counts, key=counts.get)
            stability.append({"threshold": k + (f" ({t})" if t else ""), "default": default1[k], "most_chosen": top,
                              "times_chosen": counts[top], "of_folds": len(chosen),
                              "all_choices": json.dumps({str(x): n for x, n in sorted(counts.items())})})
    final = choose(clips, None, refs, runs, types)

    result = {"settings": {"folds": a.folds, "repeats": a.repeats, "seed": a.seed, "n_clips": len(clips),
                           "clips_without_labels": missing, "stratified_by": "source x accident type",
                           "collision_tolerance_frames": COLLISION_TOL, "lane_change_tiou": TIOU_THR,
                           "vehicle_b_iou": B_IOU_THR, "engine": engine_fingerprint()},
              "summary": summary, "lane_change_prf": {"precision": lc_p, "recall": lc_r, "f1": lc_f},
              "sudden_stop_prf": {"precision": ss_p, "recall": ss_r, "f1": ss_f},
              "threshold_stability": stability, "final_thresholds_all_clips": final,
              "folds": folds}
    (out / "cv_results.json").write_text(json.dumps(result, indent=1, default=str))
    with open(out / "per_clip.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["system", "repeat", "fold", "clip_id"] + METRICS, extrasaction="ignore")
        w.writeheader(); w.writerows(per_clip)
    write_excel(out / "cv_results.xlsx", result, per_clip, idx)
    print(json.dumps({"summary": [s for s in summary if s["system"] == "cross-validated"], "final": final}, indent=1, default=str))
    print("written:", out)


def write_excel(path, res, per_clip, idx):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook()
    bold, head = Font(name="Arial", bold=True), PatternFill("solid", fgColor="D9E2DC")

    def sheet(ws, rows, cols, widths=None):
        ws.append(cols)
        for c in ws[1]:
            c.font, c.fill = bold, head
        for r in rows:
            ws.append([r.get(c) for c in cols])
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.font = Font(name="Arial")
                if isinstance(c.value, float):
                    c.number_format = "0.0%" if 0 <= c.value <= 1 else "0.00"
        for i, w in enumerate(widths or [18] * len(cols), 1):
            ws.column_dimensions[chr(64 + i) if i <= 26 else "A"].width = w

    ws = wb.active; ws.title = "Summary"
    sheet(ws, res["summary"], ["system", "measure", "n_clips", "mean", "std", "min", "max", "ci95_low", "ci95_high"],
          [20, 16, 9, 10, 10, 10, 10, 11, 11])
    ws.append([])
    ws.append(["mean / std / min / max: over the folds; ci95: bootstrap over the clips (per-clip mean over the repeats)"])
    ws.append(["Lane change (cross-validated)", "precision", res["lane_change_prf"]["precision"], "recall",
               res["lane_change_prf"]["recall"], "F1", res["lane_change_prf"]["f1"]])
    ws.append(["Sudden stop (cross-validated)", "precision", res["sudden_stop_prf"]["precision"], "recall",
               res["sudden_stop_prf"]["recall"], "F1", res["sudden_stop_prf"]["f1"]])
    sheet(wb.create_sheet("Folds"), res["folds"], list(res["folds"][0].keys()) if res["folds"] else [])
    sheet(wb.create_sheet("Thresholds"), res["threshold_stability"] +
          [{"threshold": "FINAL (all clips) -> config.py", "most_chosen": json.dumps(res["final_thresholds_all_clips"])}],
          ["threshold", "default", "most_chosen", "times_chosen", "of_folds", "all_choices"], [30, 10, 14, 13, 9, 60])
    rows = [dict(r, source=idx[r["clip_id"]]["source"], accident_type=idx[r["clip_id"]]["accident_type"]) for r in per_clip]
    sheet(wb.create_sheet("PerClip"), rows, ["system", "repeat", "fold", "clip_id", "source", "accident_type"] + METRICS)
    m = wb.create_sheet("Method")
    for line in __doc__.strip().splitlines():
        m.append([line])
    m.column_dimensions["A"].width = 120
    for cell in m["A"]:
        cell.alignment = Alignment(wrap_text=False)
    wb.save(path)


if __name__ == "__main__":
    main()
