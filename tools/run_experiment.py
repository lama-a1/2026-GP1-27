"""Run one Siyaq experiment: the full Sprint 2 engine on a set of dataset clips, with optional setting changes,
and compare the output with the reference labels at each evidence level.

    python tools/run_experiment.py --exp-id EXP-007 --title "Frozen baseline" \
        --dataset /path/to/Siyaq_Part1/dataset --splits train,val

    python tools/run_experiment.py --exp-id EXP-008 --title "..." --dataset ... --splits train \
        --set LANE_ONSET_MPS=0.5 --hypothesis "..." --baseline EXP-007

What it writes (paths relative to the repository root):
    results/<EXP>_<clip>/prediction.json   engine output without the per-frame track and lane-line arrays
    results/<EXP>_<clip>/comparison.json   prediction vs each reference level, with the level written on every value
    results/<EXP>_<clip>/diagnostics.csv   per-frame values for Vehicle B and the camera motion
    results/<EXP>_<clip>/run_metadata.json code version, settings, library versions, timing
    results/<EXP>_SUMMARY/metrics.json     aggregate metrics per split and per evidence level
    experiments/configs/<EXP>.json         the full engine configuration used
    experiments/EXPERIMENT_LOG.csv         one row appended per run

Rules built in:
  * the Test split is refused unless --final is given (final, frozen evaluation only);
  * human-reviewed ground truth, source annotations and unreviewed draft labels are never mixed in one metric;
  * a metric without an approved reference is written as "Pending approved Ground Truth".
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FPS = 10
COLLISION_TOL = 5          # frames = 0.5 s at 10 fps (same as Siyaq_Part1/evaluation/siyaq_eval.py)
TIOU_THR = 0.3             # an interval event is matched when temporal IoU >= 0.3 (same as siyaq_eval.py)
B_IOU_THR = 0.5            # predicted Vehicle B box vs reviewed box at the review frame
PENDING = "Pending approved Ground Truth"
LOG_FIELDS = ["exp_id", "date", "title", "status", "decision", "hypothesis", "changes", "baseline_exp", "code_commit",
              "config_file", "splits", "n_clips", "reference_levels", "key_results", "results_path", "notes"]


# ----------------------------------------------------------------------------------------------- references
def load_index(dataset):
    with open(Path(dataset) / "dataset_index.csv", newline="") as f:
        return {r["clip_id"]: r for r in csv.DictReader(f)}


def load_human():
    p = ROOT / "experiments" / "ground_truth" / "human_reviewed.json"
    return json.loads(p.read_text())["clips"] if p.exists() else {}


def load_draft(path):
    if not path or not Path(path).exists():
        return {}
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    head = rows[0]
    out = {}
    for r in rows[1:]:
        d = dict(zip(head, r))
        if d.get("clip_id"):
            out[str(d["clip_id"])] = d
    return out


def _int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def draft_events(d):
    """Draft-label events in the engine's vocabulary."""
    ev = {}
    if d.get("lane_change_vehicle") and _int(d.get("lane_change_start")) is not None:
        ev["lane_change"] = {"vehicle": str(d["lane_change_vehicle"])[-1], "direction": str(d.get("lane_change_direction") or "").lower(),
                             "start": _int(d["lane_change_start"]), "end": _int(d["lane_change_end"])}
    if d.get("sudden_stop_vehicle") and _int(d.get("sudden_stop_start")) is not None:
        ev["sudden_stop"] = {"start": _int(d["sudden_stop_start"]), "end": _int(d["sudden_stop_end"])}
    if d.get("safe_distance"):
        ev["safe_distance"] = str(d["safe_distance"])
    return ev


# ----------------------------------------------------------------------------------------------- helpers
def tiou(a, b):
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]) + 1)
    uni = max(a[1], b[1]) - min(a[0], b[0]) + 1
    return inter / uni if uni > 0 else 0.0


def box_iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def git_commit():
    try:
        c = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "siyaq_cv"], capture_output=True, text=True,
                               timeout=10).stdout.strip()
        return c or None, bool(dirty)
    except Exception:
        return None, None


ENGINE_ROOT = ROOT


def code_fingerprint():
    h = hashlib.sha256()
    for p in sorted((ENGINE_ROOT / "siyaq_cv").glob("*.py")):
        h.update(p.name.encode()); h.update(p.read_bytes())
    return h.hexdigest()[:16]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def portable(v):
    """Paths inside the engine folder are stored relative to it, so no machine-specific folder enters the results."""
    if isinstance(v, str) and v.startswith(str(ENGINE_ROOT)):
        return str(Path(v).relative_to(ENGINE_ROOT))
    return v


def config_snapshot(config):
    return {k: portable(getattr(config, k)) for k in dir(config) if k.isupper() and isinstance(getattr(config, k), (int, float, str, bool, dict, list, tuple))}


def apply_overrides(config, sets):
    changed = {}
    for kv in sets:
        k, v = kv.split("=", 1)
        if not hasattr(config, k):
            raise SystemExit(f"unknown setting {k}")
        old = getattr(config, k)
        try:
            v = type(old)(v) if not isinstance(old, bool) else v.lower() in ("1", "true", "yes")
        except (TypeError, ValueError):
            pass
        setattr(config, k, v)
        changed[k] = {"from": old, "to": v}
    return changed


# ----------------------------------------------------------------------------------------------- per clip
def compare(cid, row, r, human, draft):
    """Prediction vs every reference level. Every value carries its evidence level."""
    out = {"clip_id": cid, "split": row["split"], "accident_type": row["accident_type"]}
    crash = r.get("collision_frame")
    src = _int(row.get("crash_start_frame"))
    out["collision"] = {"predicted_frame": crash, "predicted_s": None if crash is None else round(crash / FPS, 2)}
    out["collision"]["vs_source_annotation"] = None if src is None else {
        "level": "source_annotation", "reference_frame": src,
        "error_frames": None if crash is None else crash - src,
        "hit_within_0_5s": crash is not None and abs(crash - src) <= COLLISION_TOL}
    h = human.get(cid, {})
    if "collision_frame" in h:
        out["collision"]["vs_human_gt"] = {"level": "human_reviewed", "reference_frame": h["collision_frame"],
                                           "error_frames": None if crash is None else crash - h["collision_frame"],
                                           "hit_within_0_5s": crash is not None and abs(crash - h["collision_frame"]) <= COLLISION_TOL}
    # Vehicle B (human only: draft labels name B in words, not as a box)
    if "vehicle_b" in h:
        vb = h["vehicle_b"]
        b = r.get("vehicle_b")
        boxes = {int(x[0]): x[1:5] for x in r.get("_tracks", {}).get(str(b), [])} if b is not None else {}
        near = min(boxes, key=lambda k: abs(k - vb["frame"])) if boxes else None
        iou = box_iou(boxes[near], vb["box"]) if near is not None and abs(near - vb["frame"]) <= 3 else 0.0
        out["vehicle_b"] = {"level": "human_reviewed", "predicted_track": b, "review_frame": vb["frame"],
                            "box_iou": round(iou, 3), "correct": iou >= B_IOU_THR}
    lc = next((e for e in r["events"] if e["type"] == "lane_change"), None)
    plc = None if lc is None else {"vehicle": lc["vehicle"], "direction": lc["measures"].get("direction"),
                                   "start": lc["start"], "end": lc["end"]}
    out["lane_change"] = {"predicted": plc}
    refs = []
    if "lane_change" in h:
        refs.append(("human_reviewed", h["lane_change"]))
    d = draft_events(draft.get(cid, {}))
    if "lane_change" in d:
        refs.append(("draft_unreviewed", d["lane_change"]))
    for level, g in refs:
        m = {"level": level, "reference": g}
        if plc:
            m.update({"tiou": round(tiou((plc["start"], plc["end"]), (g["start"], g["end"])), 3),
                      "start_error_frames": plc["start"] - g["start"], "end_error_frames": plc["end"] - g["end"],
                      "direction_correct": plc["direction"] == g["direction"], "vehicle_correct": plc["vehicle"] == g["vehicle"]})
        out["lane_change"]["vs_" + level] = m
    if cid in draft and "lane_change" not in d:          # the draft says: no lane change in this clip
        out["lane_change"]["vs_draft_unreviewed"] = {"level": "draft_unreviewed", "reference": None}
    # draft-only events
    ss = next((e for e in r["events"] if e["type"] == "sudden_stop"), None)
    out["sudden_stop"] = {"predicted": None if ss is None else [ss["start"], ss["end"]],
                          "vs_draft_unreviewed": {"level": "draft_unreviewed",
                                                  "reference": None if "sudden_stop" not in d else [d["sudden_stop"]["start"], d["sudden_stop"]["end"]]}
                          if cid in draft else None}
    fd = next((e for e in r["events"] if e["type"] == "following_distance"), None)
    out["following_distance"] = {"predicted": None if fd is None else fd["measures"].get("safe_distance"),
                                 "vs_draft_unreviewed": {"level": "draft_unreviewed", "reference": d.get("safe_distance")} if cid in draft else None}
    return out


def diagnostics(path, r):
    mb = r.get("measures_b", {})
    ser = r.get("series", {})
    n = len(ser.get("t", []))
    cols = ["frame", "time_s", "b_tracked", "distance_m", "lateral_m", "lateral_speed_mps", "height_frac", "centre_offset",
            "rel_speed_mps", "ttc_s", "at_edge", "flow_dx_px", "jolt", "a_heading_rate_deg_s"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for i in range(n):
            m = mb.get(str(i))
            w.writerow([i, ser["t"][i], int(m is not None)] +
                       [None if m is None else m.get(k) for k in cols[3:12]] +
                       [ser.get("jolt", [None] * n)[i], ser.get("a_heading_rate_deg_s", [None] * n)[i]])


# ----------------------------------------------------------------------------------------------- aggregate
def aggregate(comps, timings):
    import statistics as st
    res = {}
    for split in sorted({c["split"] for c in comps}):
        cs = [c for c in comps if c["split"] == split]
        S = {"n_clips": len(cs)}
        # collision vs source annotation
        v = [c["collision"]["vs_source_annotation"] for c in cs if c["collision"].get("vs_source_annotation")]
        errs = [x["error_frames"] for x in v if x["error_frames"] is not None]
        S["collision_vs_source_annotation"] = {
            "level": "source_annotation", "n": len(v), "n_no_prediction": sum(x["error_frames"] is None for x in v),
            "hit_rate_within_0_5s": round(sum(x["hit_within_0_5s"] for x in v) / len(v), 3) if v else None,
            "mae_s": round(st.mean(abs(e) for e in errs) / FPS, 2) if errs else None,
            "median_abs_error_s": round(st.median(abs(e) for e in errs) / FPS, 2) if errs else None,
            "mean_signed_error_s": round(st.mean(errs) / FPS, 2) if errs else None}
        hv = [c["collision"]["vs_human_gt"] for c in cs if c["collision"].get("vs_human_gt")]
        S["collision_vs_human_gt"] = {"level": "human_reviewed", "n": len(hv),
                                      "hits": sum(x["hit_within_0_5s"] for x in hv),
                                      "errors_frames": [x["error_frames"] for x in hv]} if hv else PENDING
        vb = [c["vehicle_b"] for c in cs if c.get("vehicle_b")]
        S["vehicle_b_identification"] = {"level": "human_reviewed", "n": len(vb), "correct": sum(x["correct"] for x in vb),
                                         "clips": {c["clip_id"]: c["vehicle_b"]["correct"] for c in cs if c.get("vehicle_b")}} if vb else PENDING
        for level in ("human_reviewed", "draft_unreviewed"):
            tp = fp = fn = 0
            ti, se, ee, dirok = [], [], [], []
            n_ref = 0
            for c in cs:
                lc = c["lane_change"]
                m = lc.get("vs_" + level)
                if m is None:
                    continue           # this clip has no reference at this level
                g = m.get("reference")
                p = lc["predicted"]
                n_ref += 1
                if g and p:
                    ti.append(m["tiou"]); se.append(m["start_error_frames"]); ee.append(m["end_error_frames"])
                    dirok.append(m["direction_correct"])
                    if m["tiou"] >= TIOU_THR:
                        tp += 1
                    else:
                        fp += 1; fn += 1
                elif p and not g:
                    fp += 1
                elif g and not p:
                    fn += 1
            if n_ref == 0:
                S["lane_change_" + level] = PENDING if level == "human_reviewed" else None
                continue
            P = tp / (tp + fp) if tp + fp else None
            Rr = tp / (tp + fn) if tp + fn else None
            F = 2 * P * Rr / (P + Rr) if P and Rr else (0.0 if P is not None and Rr is not None else None)
            S["lane_change_" + level] = {
                "level": level, "n_clips_with_reference_row": n_ref, "n_matched_pairs": len(ti), "tp": tp, "fp": fp, "fn": fn,
                "precision": None if P is None else round(P, 3), "recall": None if Rr is None else round(Rr, 3),
                "f1": None if F is None else round(F, 3),
                "mean_tiou": round(st.mean(ti), 3) if ti else None,
                "start_mae_frames": round(st.mean(abs(x) for x in se), 2) if se else None,
                "start_mean_error_frames": round(st.mean(se), 2) if se else None,
                "end_mae_frames": round(st.mean(abs(x) for x in ee), 2) if ee else None,
                "direction_accuracy": round(sum(dirok) / len(dirok), 3) if dirok else None}
        # draft-only: sudden stop presence and following-distance verdict
        ssd = [c["sudden_stop"]["vs_draft_unreviewed"] for c in cs if c["sudden_stop"].get("vs_draft_unreviewed")]
        if ssd:
            pairs = [(c["sudden_stop"]["predicted"] is not None, c["sudden_stop"]["vs_draft_unreviewed"]["reference"] is not None)
                     for c in cs if c["sudden_stop"].get("vs_draft_unreviewed")]
            tp = sum(p and g for p, g in pairs); fp = sum(p and not g for p, g in pairs); fn = sum(g and not p for p, g in pairs)
            S["sudden_stop_presence_draft_unreviewed"] = {"level": "draft_unreviewed", "n": len(pairs), "tp": tp, "fp": fp, "fn": fn,
                                                          "agreement": round(sum(p == g for p, g in pairs) / len(pairs), 3)}
        fdd = [(c["following_distance"]["predicted"], c["following_distance"]["vs_draft_unreviewed"]["reference"])
               for c in cs if c["following_distance"].get("vs_draft_unreviewed")]
        fdd = [(p, g) for p, g in fdd if g in ("Maintained", "Not maintained")]
        if fdd:
            S["safe_distance_draft_unreviewed"] = {"level": "draft_unreviewed", "n_with_clear_draft_value": len(fdd),
                                                   "agreement": round(sum(p == g for p, g in fdd) / len(fdd), 3),
                                                   "n_no_prediction": sum(p is None for p, _ in fdd)}
        S["sudden_stop_human_reviewed"] = PENDING
        S["safe_distance_human_reviewed"] = PENDING
        tt = [timings[c["clip_id"]] for c in cs if c["clip_id"] in timings]
        if tt:
            S["processing_time_s"] = {"n": len(tt), "mean_total": round(st.mean(t["total"] for t in tt), 2),
                                      "median_total": round(st.median(t["total"] for t in tt), 2),
                                      "max_total": round(max(t["total"] for t in tt), 2),
                                      "mean_detection_tracking": round(st.mean(t["detection_tracking"] for t in tt), 2),
                                      "mean_lanes": round(st.mean(t["lanes"] for t in tt), 2)}
        res[split] = S
    res["not_measurable_yet"] = {
        "vehicle_detection_precision_recall": PENDING + " (CVAT exports contain only imported YOLO boxes)",
        "tracking_mota_idf1": PENDING + " (no reviewed per-frame tracks)",
        "lane_line_segmentation": PENDING + " (no lane-line polylines reviewed)",
        "solid_dashed_accuracy": PENDING + " (no reviewed line types)"}
    return res


# ----------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exp-id", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--dataset", required=True, help="folder with dataset_index.csv and videos/")
    ap.add_argument("--splits", default="train,val")
    ap.add_argument("--clips", default="", help="comma-separated clip ids (default: all clips of the splits)")
    ap.add_argument("--set", action="append", default=[], help="engine setting override KEY=VALUE (repeatable)")
    ap.add_argument("--hypothesis", default="")
    ap.add_argument("--baseline", default="")
    ap.add_argument("--draft-labels", default="", help="draft_labels.xlsx (unreviewed); reported separately")
    ap.add_argument("--code-commit", default="", help="record this commit if git is not available here")
    ap.add_argument("--engine-root", default="", help="folder holding another siyaq_cv version (e.g. extracted with "
                                                     "'git archive <commit> siyaq_cv'); default: this repository")
    ap.add_argument("--final", action="store_true", help="allow the Test split (final frozen evaluation only)")
    ap.add_argument("--status", default="Completed")
    ap.add_argument("--decision", default="")
    ap.add_argument("--notes", default="")
    a = ap.parse_args()

    if any((ROOT / "results").glob(f"{a.exp_id}_*")):
        raise SystemExit(f"results/{a.exp_id}_* already exists: use a new experiment ID (earlier results are never overwritten)")
    splits = [s.strip() for s in a.splits.split(",") if s.strip()]
    if "test" in splits and not a.final:
        raise SystemExit("Refusing the Test split: it is reserved for the final frozen evaluation (use --final only then).")

    global ENGINE_ROOT
    if a.engine_root:
        ENGINE_ROOT = Path(a.engine_root).resolve()
        sys.path.insert(0, str(ENGINE_ROOT))
        if not a.code_commit:
            raise SystemExit("--engine-root needs --code-commit (the commit the engine was extracted from)")
    from siyaq_cv import analyse, config
    if Path(analyse.__file__).resolve().parents[1] != ENGINE_ROOT:
        raise SystemExit(f"engine imported from {analyse.__file__}, expected {ENGINE_ROOT}")
    changed = apply_overrides(config, a.set)
    index = load_index(a.dataset)
    human = load_human()
    draft = load_draft(a.draft_labels)
    clips = [c for c in (a.clips.split(",") if a.clips else index) if c and index[c]["split"] in splits]

    commit, dirty = git_commit()
    if a.engine_root:
        dirty = None                     # extracted from git history, not this working tree
    commit = a.code_commit or commit
    cfg = config_snapshot(config)
    cfg_path = ROOT / "experiments" / "configs" / f"{a.exp_id}.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"exp_id": a.exp_id, "overrides": changed, "config": cfg}, indent=1, default=str))
    env = {"python": sys.version.split()[0], "platform": platform.platform(), "machine": platform.machine(),
           "cpu_count": os.cpu_count()}
    for mod in ("numpy", "cv2", "onnxruntime"):
        try:
            env[mod] = __import__(mod).__version__
        except Exception:
            env[mod] = None
    models = {Path(p).name: sha256(p)[:16] for p in (config.MODEL_PATH, config.LANE_MODEL_PATH) if Path(p).exists()}

    comps, timings, failures = [], {}, []
    for i, cid in enumerate(clips, 1):
        row = index[cid]
        out = ROOT / "results" / f"{a.exp_id}_{cid}"
        out.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        try:
            r = analyse.analyse_video(str(Path(a.dataset) / row["file"]), row["accident_type"].upper().replace("-", "_"),
                                      thumbnails=False)
        except Exception as exc:                           # a failed clip is recorded, never dropped silently
            failures.append({"clip_id": cid, "error": f"{type(exc).__name__}: {exc}"[:300]})
            (out / "run_metadata.json").write_text(json.dumps({"exp_id": a.exp_id, "clip_id": cid, "failed": failures[-1]}, indent=1))
            continue
        r["_tracks"] = r.get("tracks", {})
        comp = compare(cid, row, r, human, draft)
        pred = {k: v for k, v in r.items() if k not in ("tracks", "_tracks", "lanes", "series")}
        pred["vehicle_b_boxes"] = r["_tracks"].get(str(r.get("vehicle_b")), [])
        (out / "prediction.json").write_text(json.dumps(pred, indent=1, default=str))
        (out / "comparison.json").write_text(json.dumps(comp, indent=1))
        diagnostics(out / "diagnostics.csv", r)
        timings[cid] = r["timing_s"]
        (out / "run_metadata.json").write_text(json.dumps({
            "exp_id": a.exp_id, "title": a.title, "clip_id": cid, "split": row["split"], "source": row["source"],
            "video_file": row["file"], "code_commit": commit, "code_dirty": dirty, "code_fingerprint": code_fingerprint(),
            "config_file": str(cfg_path.relative_to(ROOT)), "overrides": changed,
            "engine_root": f"git archive {commit}" if a.engine_root else "repository", "models_sha256_16": models,
            "environment": env, "timing_s": r["timing_s"], "wall_time_s": round(time.time() - t0, 2),
            "run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}, indent=1, default=str))
        comps.append(comp)
        print(f"[{i}/{len(clips)}] {cid} {row['split']} crash={r.get('collision_frame')} B={r.get('vehicle_b')} "
              f"{r['timing_s']['total']}s", flush=True)

    summary = aggregate(comps, timings)
    summary["_run"] = {"exp_id": a.exp_id, "title": a.title, "hypothesis": a.hypothesis, "baseline": a.baseline,
                       "dataset_index_md5": hashlib.md5((Path(a.dataset) / "dataset_index.csv").read_bytes()).hexdigest(),
                       "engine_root": "repository" if not a.engine_root else f"git archive {commit}",
                       "code_commit": commit, "code_fingerprint": code_fingerprint(), "overrides": changed,
                       "splits": splits, "n_clips": len(clips), "n_failed": len(failures), "failures": failures,
                       "environment": env, "models_sha256_16": models,
                       "settings": {"collision_tolerance_frames": COLLISION_TOL, "tiou_threshold": TIOU_THR,
                                    "vehicle_b_box_iou": B_IOU_THR, "fps": FPS}}
    sdir = ROOT / "results" / f"{a.exp_id}_SUMMARY"
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "metrics.json").write_text(json.dumps(summary, indent=1, default=str))

    key = []
    for s in splits:
        S = summary.get(s, {})
        c = S.get("collision_vs_source_annotation") or {}
        key.append(f"{s}: collision hit@0.5s={c.get('hit_rate_within_0_5s')} (n={c.get('n')}, source annotations)")
        vb = S.get("vehicle_b_identification")
        if isinstance(vb, dict):
            key.append(f"{s}: Vehicle B {vb['correct']}/{vb['n']} (human-reviewed)")
    log = ROOT / "experiments" / "EXPERIMENT_LOG.csv"
    new = not log.exists()
    with open(log, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"exp_id": a.exp_id, "date": dt.date.today().isoformat(), "title": a.title, "status": a.status,
                    "decision": a.decision, "hypothesis": a.hypothesis,
                    "changes": "; ".join(f"{k}: {v['from']} -> {v['to']}" for k, v in changed.items()) or "none",
                    "baseline_exp": a.baseline, "code_commit": commit, "config_file": str(cfg_path.relative_to(ROOT)),
                    "splits": "+".join(splits), "n_clips": len(clips),
                    "reference_levels": "source_annotation; human_reviewed; draft_unreviewed (reported separately)",
                    "key_results": " | ".join(key), "results_path": f"results/{a.exp_id}_*", "notes": a.notes})
    print(json.dumps({s: summary[s] for s in splits if s in summary}, indent=1, default=str))


if __name__ == "__main__":
    main()
