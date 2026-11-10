"""Evaluate saved experiment predictions against labels completed in CVAT (no engine run, no change to results).

    python tools/eval_cvat_labels.py --export <project_datumaro.zip> \
        --jobs experiments/ground_truth/cvat_2026-11-10_completed_jobs.csv --exp EXP-008 --eval-id EVAL-001

What it does
  1. Reads a CVAT *project* export (Datumaro 1.0). The project export numbers the frames of all tasks one after the
     other, in task-ID order: siyaq_CCD_1 (2000 frames), siyaq_CCD_2 (1950), siyaq_DADA (3500). The offsets were
     checked against the per-task exports of 4 Nov (identical pre-annotation boxes).
  2. Keeps ONLY the jobs listed in --jobs (the jobs the team marked as completed). Every other job in the export is
     ignored: it is not reference data.
  3. Maps each job to its clip through experiments/dataset/clip_job_map_v2.csv and checks that the labels are complete.
  4. Compares the saved predictions results/<EXP>_<clip>/prediction.json with the labels of complete clips.
     The engine is not run and no existing result file is changed.

Evidence level written to the outputs: "cvat_completed_unreviewed" = labelled and marked complete by the annotator;
the export does not record a second-person review, so these labels are NOT approved ground truth
(experiments/ground_truth/human_reviewed.json is unchanged).

Outputs
  experiments/ground_truth/cvat_completed_<date>.json      extracted labels + completeness checks per clip
  results/<EVAL>_cvat_vs_<EXP>/per_clip.csv, per_clip.json, metrics.json, run_metadata.json
"""
import argparse, csv, datetime as dt, hashlib, json, statistics as st, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from run_experiment import FPS, COLLISION_TOL, TIOU_THR, B_IOU_THR, tiou, box_iou   # same rules as the experiments

LEVEL = "cvat_completed_unreviewed"
TASKS = {"siyaq_CCD_1": {"offset": 0, "frames": 2000}, "siyaq_CCD_2": {"offset": 2000, "frames": 1950},
         "siyaq_DADA": {"offset": 3950, "frames": 3500}}
JOB_BASE = {"siyaq_CCD_2": 4699037, "siyaq_DADA": 4699079}   # job ID = base + start_frame / 50 (checked on the team sheet)
B_FRAME_TOL = 3


def load_export(path):
    p = Path(path)
    if p.suffix == ".zip":
        with zipfile.ZipFile(p) as z:
            name = next(n for n in z.namelist() if n.endswith("default.json"))
            raw = z.read(name)
    else:
        raw = p.read_bytes()
    d = json.loads(raw)
    labels = [l["name"] for l in d["categories"]["label"]["labels"]]
    return d["items"], labels, hashlib.md5(raw).hexdigest()


def extract(items, labels, g0, real, size):
    """All labels of one 50-frame job. Boxes are normalised to 0-1 like the predictions."""
    H, W = size
    tags, b_boxes, other_tracks, b_tracks, lines, beyond = [], {}, set(), set(), [], []
    for f in range(50):
        for a in items[g0 + f]["annotations"]:
            name = labels[a["label_id"]]
            if f >= real:
                beyond.append((f, name))
            if a["type"] == "label":
                tags.append({"frame": f, "label": name, **a["attributes"]})
            elif a["type"] == "bbox":
                x, y, w, h = a["bbox"]
                box = [round(x / W, 4), round(y / H, 4), round((x + w) / W, 4), round((y + h) / H, 4)]
                tid = a["attributes"].get("track_id")
                if a["attributes"].get("role") == "Vehicle B":
                    b_tracks.add(tid); b_boxes[f] = box
                else:
                    other_tracks.add(tid)
            elif a["type"] == "polyline":
                lines.append({"frame": f, "line_type": a["attributes"].get("line_type")})
    return tags, b_boxes, b_tracks, other_tracks, lines, beyond


def first(tags, label):
    return next((t for t in tags if t["label"] == label), None)


def build_reference(job, row, items, labels, idx):
    task = row["task"]
    f0 = int(row["task_frames"].split("-")[0])
    real = int(row["real_frames"])
    size = items[TASKS[task]["offset"] + f0]["image"]["size"]
    tags, bb, bt, ot, lines, beyond = extract(items, labels, TASKS[task]["offset"] + f0, real, size)
    acc = first(tags, "accident_type")
    col = [t for t in tags if t["label"] == "collision"]
    lcs, lce = first(tags, "lane_change_start"), first(tags, "lane_change_end")
    sss, sse = first(tags, "sudden_stop_start"), first(tags, "sudden_stop_end")
    sd = [t for t in tags if t["label"] == "safe_distance"]
    clip = row["clip_id"]
    ref = {"job_id": job, "task": task, "task_frames": row["task_frames"], "clip_id": clip, "split": idx[clip]["split"],
           "real_frames": real, "level": LEVEL,
           "accident_type": acc.get("value") if acc else None,
           "accident_type_in_dataset_index": idx[clip]["accident_type"],
           "source_crash_frame": int(idx[clip]["crash_start_frame"]) if idx[clip].get("crash_start_frame") not in (None, "") else None,
           "collision_frame": col[0]["frame"] if col else None, "collision_visibility": col[0].get("visibility") if col else None,
           "vehicle_b": None, "lane_change": None, "sudden_stop": None,
           "crossed_line_type": (first(tags, "crossed_line_type") or {}).get("value"),
           "safe_distance": [{"frame": t["frame"], "value": t.get("value")} for t in sd],
           "lane_markings": len(lines), "other_vehicle_tracks": len(ot)}
    if bb:
        cf = ref["collision_frame"]
        cand = [f for f in bb if cf is None or f <= cf]
        rf = max(cand) if cand else min(bb)
        ref["vehicle_b"] = {"n_tracks": len(bt), "frames": [min(bb), max(bb)], "n_boxed_frames": len(bb),
                            "reference_frame": rf, "box": bb[rf], "boxes": {str(k): v for k, v in sorted(bb.items())}}
    if lcs or lce:
        ref["lane_change"] = {"vehicle": "B" if (lcs or lce or {}).get("vehicle") == "Vehicle B" else (lcs or lce or {}).get("vehicle"),
                              "direction": (lcs or {}).get("direction", "").lower() or None,
                              "start": lcs["frame"] if lcs else None, "end": lce["frame"] if lce else None}
    if sss or sse:
        ref["sudden_stop"] = {"start": sss["frame"] if sss else None, "end": sse["frame"] if sse else None}
    # completeness: what a complete clip must contain under the labelling protocol
    issues = []
    if not acc:
        issues.append("no accident_type tag")
    elif acc.get("value") != idx[clip]["accident_type"]:
        issues.append(f"accident_type {acc.get('value')} differs from dataset index ({idx[clip]['accident_type']})")
    if len(col) != 1:
        issues.append(f"{len(col)} collision tags (expected 1)")
    if not bb:
        issues.append("no Vehicle B box")
    elif len(bt) > 1:
        issues.append(f"Vehicle B has {len(bt)} tracks")
    elif ref["collision_frame"] is not None and abs(ref["vehicle_b"]["reference_frame"] - ref["collision_frame"]) > B_FRAME_TOL:
        issues.append(f"last Vehicle B box at frame {ref['vehicle_b']['reference_frame']}, collision at {ref['collision_frame']}")
    lc_type = (acc or {}).get("value") == "Lane-change"
    if lc_type:
        L = ref["lane_change"]
        if not L or L["start"] is None or L["end"] is None:
            issues.append("lane change start/end missing")
        else:
            if L["start"] > L["end"]:
                issues.append("lane change start after end")
            if not L["direction"]:
                issues.append("lane change direction missing")
    elif ref["lane_change"]:
        issues.append("lane change tagged in a rear-end clip")
    S = ref["sudden_stop"]
    if S and (S["start"] is None or S["end"] is None):
        issues.append("sudden stop start/end not paired")
    if not sd:
        issues.append("no safe_distance tag")
    if beyond:
        issues.append(f"{len(beyond)} labels after the last real frame ({real})")
    ref["issues"] = issues
    ref["complete"] = not issues
    # per-element validity: an element can be evaluated when its own labels are sound
    ref["valid_for"] = {
        "collision": len(col) == 1 and col[0]["frame"] < real,
        "vehicle_b": bool(bb) and len(bt) == 1,
        "lane_change": (lc_type and ref["lane_change"] is not None and None not in (ref["lane_change"]["start"], ref["lane_change"]["end"])
                        and ref["lane_change"]["start"] <= ref["lane_change"]["end"]) or ((acc or {}).get("value") == "Rear-end" and not ref["lane_change"]),
        "sudden_stop": not S or None not in (S["start"], S["end"]),
        "safe_distance": bool(sd),
        "accident_type": bool(acc)}
    return ref


def sd_at(ref, frame):
    vals = [s for s in ref["safe_distance"] if frame is None or s["frame"] <= frame]
    return (vals[-1] if vals else ref["safe_distance"][0])["value"] if ref["safe_distance"] else None


def compare(ref, pred, human):
    c = {"clip_id": ref["clip_id"], "split": ref["split"], "accident_type": ref["accident_type"], "complete": ref["complete"],
         "issues": ref["issues"]}
    v = ref["valid_for"]
    crash = pred.get("collision_frame")
    if v["collision"]:
        e = None if crash is None else crash - ref["collision_frame"]
        c["collision"] = {"reference_frame": ref["collision_frame"], "predicted_frame": crash, "error_frames": e,
                          "hit_within_0_5s": e is not None and abs(e) <= COLLISION_TOL,
                          "source_annotation_frame": ref.get("source_crash_frame"),
                          "equals_source_annotation": ref.get("source_crash_frame") == ref["collision_frame"]}
    if v["vehicle_b"]:
        boxes = {int(b[0]): b[1:5] for b in pred.get("vehicle_b_boxes", [])}
        rf = ref["vehicle_b"]["reference_frame"]
        near = min(boxes, key=lambda k: abs(k - rf)) if boxes else None
        iou = box_iou(boxes[near], ref["vehicle_b"]["box"]) if near is not None and abs(near - rf) <= B_FRAME_TOL else 0.0
        common = [f for f in boxes if str(f) in ref["vehicle_b"]["boxes"]]
        mi = round(st.mean(box_iou(boxes[f], ref["vehicle_b"]["boxes"][str(f)]) for f in common), 3) if common else None
        # identity: the predicted Vehicle B track is the labelled vehicle (mean IoU >= 0.5 over the frames where both have a box)
        # at_collision: the predicted B box is still present and overlaps the label within 3 frames of the collision
        c["vehicle_b"] = {"reference_frame": rf, "predicted_track": pred.get("vehicle_b"),
                          "identity_correct": mi is not None and mi >= B_IOU_THR, "mean_iou_common_frames": mi,
                          "n_common_frames": len(common), "box_iou_at_collision": round(iou, 3), "tracked_at_collision": iou >= B_IOU_THR,
                          "last_predicted_frame": max(boxes) if boxes else None}
    lc = next((e for e in pred["events"] if e["type"] == "lane_change"), None)
    plc = None if lc is None else {"direction": lc["measures"].get("direction"), "start": lc["start"], "end": lc["end"]}
    if v["lane_change"]:
        g = ref["lane_change"]
        m = {"reference": g, "predicted": plc}
        if g and plc:
            m.update({"tiou": round(tiou((plc["start"], plc["end"]), (g["start"], g["end"])), 3),
                      "start_error_frames": plc["start"] - g["start"], "end_error_frames": plc["end"] - g["end"],
                      "direction_correct": plc["direction"] == g["direction"] if g["direction"] in ("left", "right") else None})
        c["lane_change"] = m
    ss = next((e for e in pred["events"] if e["type"] == "sudden_stop"), None)
    if v["sudden_stop"]:
        g = ref["sudden_stop"]
        m = {"reference": None if not g else [g["start"], g["end"]], "predicted": None if ss is None else [ss["start"], ss["end"]]}
        if g and ss:
            m["tiou"] = round(tiou((ss["start"], ss["end"]), (g["start"], g["end"])), 3)
        c["sudden_stop"] = m
    fd = next((e for e in pred["events"] if e["type"] == "following_distance"), None)
    if v["safe_distance"]:
        ref_val = sd_at(ref, ref["collision_frame"])
        p = None if fd is None else fd["measures"].get("safe_distance")
        c["safe_distance"] = {"reference_at_collision": ref_val, "predicted": p,
                              "agree": None if ref_val not in ("Maintained", "Not maintained") or p is None else p == ref_val}
    c["accident_type_vs_index"] = ref["accident_type"] == ref["accident_type_in_dataset_index"] if v["accident_type"] else None
    # agreement with the approved human-reviewed labels, where both exist (information only)
    h = human.get(ref["clip_id"])
    if h:
        a = {}
        if "lane_change" in h and ref["lane_change"]:
            a["lane_change"] = {"approved": [h["lane_change"]["start"], h["lane_change"]["end"]],
                                "cvat": [ref["lane_change"]["start"], ref["lane_change"]["end"]]}
        if "collision_frame" in h:
            a["collision_frame"] = {"approved": h["collision_frame"], "cvat": ref["collision_frame"]}
        if "vehicle_b" in h and ref["vehicle_b"]:
            hb = h["vehicle_b"]; cb = ref["vehicle_b"]["boxes"].get(str(hb["frame"]))
            a["vehicle_b_box_iou_at_approved_frame"] = None if cb is None else round(box_iou(cb, hb["box"]), 3)
        c["vs_approved_human_review"] = a
    return c


def summarise(cs):
    S = {"level": LEVEL, "n_clips": len(cs), "n_complete": sum(c["complete"] for c in cs)}
    col = [c["collision"] for c in cs if "collision" in c]
    errs = [x["error_frames"] for x in col if x["error_frames"] is not None]
    S["collision"] = {"n": len(col), "n_no_prediction": sum(x["error_frames"] is None for x in col),
                      "hits_within_0_5s": sum(x["hit_within_0_5s"] for x in col),
                      "hit_rate_within_0_5s": round(sum(x["hit_within_0_5s"] for x in col) / len(col), 3) if col else None,
                      "mae_s": round(st.mean(abs(e) for e in errs) / FPS, 2) if errs else None,
                      "median_abs_error_s": round(st.median(abs(e) for e in errs) / FPS, 2) if errs else None,
                      "mean_signed_error_s": round(st.mean(errs) / FPS, 2) if errs else None,
                      "n_error_above_1s": sum(abs(e) > 10 for e in errs), "n_early_above_1s": sum(e < -10 for e in errs)}
    vb = [c["vehicle_b"] for c in cs if "vehicle_b" in c]
    S["vehicle_b"] = {"n": len(vb), "identity_correct": sum(x["identity_correct"] for x in vb),
                      "identity_accuracy": round(sum(x["identity_correct"] for x in vb) / len(vb), 3) if vb else None,
                      "tracked_at_collision": sum(x["tracked_at_collision"] for x in vb),
                      "median_mean_iou": round(st.median(x["mean_iou_common_frames"] or 0 for x in vb), 3) if vb else None}
    col_src = [c["collision"].get("equals_source_annotation") for c in cs if "collision" in c]
    S["collision"]["n_reference_equal_to_source_annotation"] = sum(bool(x) for x in col_src)
    tp = fp = fn = 0; ti, se, ee, dok = [], [], [], []
    lcs = [c["lane_change"] for c in cs if "lane_change" in c]
    for m in lcs:
        g, p = m["reference"], m["predicted"]
        if g and p:
            ti.append(m["tiou"]); se.append(m["start_error_frames"]); ee.append(m["end_error_frames"])
            if m["direction_correct"] is not None: dok.append(m["direction_correct"])
            if m["tiou"] >= TIOU_THR: tp += 1
            else: fp += 1; fn += 1
        elif p: fp += 1
        elif g: fn += 1
    P = tp / (tp + fp) if tp + fp else None; R = tp / (tp + fn) if tp + fn else None
    S["lane_change"] = {"n_clips": len(lcs), "n_with_reference": sum(m["reference"] is not None for m in lcs),
                        "n_rear_end_without_reference": sum(m["reference"] is None for m in lcs),
                        "tp": tp, "fp": fp, "fn": fn, "precision": None if P is None else round(P, 3),
                        "recall": None if R is None else round(R, 3),
                        "f1": round(2 * P * R / (P + R), 3) if P and R else (0.0 if P is not None and R is not None else None),
                        "mean_tiou": round(st.mean(ti), 3) if ti else None,
                        "start_mae_frames": round(st.mean(abs(x) for x in se), 2) if se else None,
                        "start_mean_error_frames": round(st.mean(se), 2) if se else None,
                        "end_mae_frames": round(st.mean(abs(x) for x in ee), 2) if ee else None,
                        "direction_accuracy": round(sum(dok) / len(dok), 3) if dok else None}
    ss = [c["sudden_stop"] for c in cs if "sudden_stop" in c]
    t = sum(1 for m in ss if m["reference"] and m["predicted"]); f_ = sum(1 for m in ss if m["predicted"] and not m["reference"])
    n_ = sum(1 for m in ss if m["reference"] and not m["predicted"])
    S["sudden_stop_presence"] = {"n": len(ss), "tp": t, "fp": f_, "fn": n_, "tn": len(ss) - t - f_ - n_,
                                 "agreement": round((len(ss) - f_ - n_) / len(ss), 3) if ss else None,
                                 "mean_tiou_when_both": round(st.mean(m["tiou"] for m in ss if "tiou" in m), 3) if any("tiou" in m for m in ss) else None}
    sd = [c["safe_distance"] for c in cs if "safe_distance" in c]
    sdv = [x for x in sd if x["agree"] is not None]
    S["safe_distance"] = {"n_clips": len(sd), "n_clear_reference_and_prediction": len(sdv),
                          "n_reference_unclear": sum(x["reference_at_collision"] not in ("Maintained", "Not maintained") for x in sd),
                          "n_no_prediction": sum(x["predicted"] is None for x in sd),
                          "agreement": round(sum(x["agree"] for x in sdv) / len(sdv), 3) if sdv else None}
    at = [c["accident_type_vs_index"] for c in cs if c["accident_type_vs_index"] is not None]
    S["accident_type_matches_dataset_index"] = {"n": len(at), "matches": sum(at)}
    return S


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", required=True)
    ap.add_argument("--jobs", required=True, help="CSV with a job_id column: the jobs marked complete by the team")
    ap.add_argument("--exp", default="EXP-008")
    ap.add_argument("--eval-id", required=True)
    ap.add_argument("--labels-date", default=dt.date.today().isoformat())
    a = ap.parse_args()
    out = ROOT / "results" / f"{a.eval_id}_cvat_vs_{a.exp}"
    if out.exists():
        raise SystemExit(f"{out} already exists: use a new evaluation ID")
    items, labels, md5 = load_export(a.export)
    if len(items) != sum(t["frames"] for t in TASKS.values()):
        raise SystemExit(f"export has {len(items)} frames; expected {sum(t['frames'] for t in TASKS.values())} (task layout changed?)")
    ds = ROOT / "experiments" / "dataset"
    jm = list(csv.DictReader(open(ds / "clip_job_map_v2.csv")))
    idx = {r["clip_id"]: r for r in csv.DictReader(open(ds / "dataset_index.csv"))}
    human = json.loads((ROOT / "experiments" / "ground_truth" / "human_reviewed.json").read_text())["clips"]
    jobs = [r for r in csv.DictReader(open(a.jobs))]
    refs, notes = [], []
    for j in jobs:
        jid = int(j["job_id"].lstrip("#"))
        task = "siyaq_CCD_2" if JOB_BASE["siyaq_CCD_2"] <= jid < JOB_BASE["siyaq_CCD_2"] + 39 else \
               "siyaq_DADA" if JOB_BASE["siyaq_DADA"] <= jid < JOB_BASE["siyaq_DADA"] + 70 else None
        if task is None:
            notes.append(f"job {jid}: not in a task with known job IDs"); continue
        f0 = (jid - JOB_BASE[task]) * 50
        row = next(r for r in jm if r["task"] == task and int(r["task_frames"].split("-")[0]) == f0)
        if j.get("clip_id") and j["clip_id"] != row["clip_id"]:
            raise SystemExit(f"job {jid}: sheet says {j['clip_id']}, job map says {row['clip_id']}")
        if row["active_v2"] != "yes":
            notes.append(f"job {jid} ({row['clip_id']}): excluded clip, skipped"); continue
        refs.append(build_reference(jid, row, items, labels, idx))
    gt_path = ROOT / "experiments" / "ground_truth" / f"cvat_completed_{a.labels_date}.json"
    gt_path.write_text(json.dumps({
        "_about": "Labels of the CVAT jobs the team marked as completed (yellow on the shared job sheet). Status: completed by the "
                  "annotator; NOT confirmed by a second reviewer, so NOT approved ground truth. Boxes are normalised 0-1. "
                  "Generated by tools/eval_cvat_labels.py; do not edit by hand.",
        "level": LEVEL, "export_md5": md5, "jobs_file": a.jobs,
        "clips": {r["clip_id"]: r for r in refs}}, indent=1))
    cs = []
    for r in refs:
        p = ROOT / "results" / f"{a.exp}_{r['clip_id']}" / "prediction.json"
        if r["split"] == "test":
            notes.append(f"{r['clip_id']}: test split, not evaluated"); continue
        if not p.exists():
            notes.append(f"{r['clip_id']}: no saved {a.exp} prediction"); continue
        cs.append(compare(r, json.loads(p.read_text()), human))
    out.mkdir(parents=True)
    metrics = {s: summarise([c for c in cs if c["split"] == s]) for s in sorted({c["split"] for c in cs})}
    metrics["_run"] = {"eval_id": a.eval_id, "predictions_from": a.exp, "reference_level": LEVEL,
                       "export_md5": md5, "jobs_file": a.jobs, "n_jobs_listed": len(jobs), "n_clips_extracted": len(refs),
                       "n_clips_evaluated": len(cs), "notes": notes,
                       "rules": {"collision_tolerance_frames": COLLISION_TOL, "lane_change_tiou_threshold": TIOU_THR,
                                 "vehicle_b_iou_threshold": B_IOU_THR, "vehicle_b_frame_tolerance": B_FRAME_TOL,
                                 "vehicle_b_identity": "mean IoU >= 0.5 over the frames where both the prediction and the label have a box",
                                 "vehicle_b_at_collision": "predicted box within 3 frames of the labelled collision with IoU >= 0.5",
                                 "rear_end_clips_count_as_no_lane_change": True,
                                 "safe_distance_reference": "last safe_distance tag at or before the collision frame"},
                       "run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1))
    (out / "per_clip.json").write_text(json.dumps(cs, indent=1))
    with open(out / "per_clip.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["clip_id", "split", "accident_type", "complete", "issues", "collision_ref", "collision_pred", "collision_err",
                    "b_identity_ok", "b_mean_iou", "b_at_collision", "b_last_pred_frame", "lc_ref", "lc_pred", "lc_tiou", "lc_dir_ok", "ss_ref", "ss_pred", "sd_ref", "sd_pred"])
        for c in cs:
            co, vb, lc, ss, sd = (c.get(k) or {} for k in ("collision", "vehicle_b", "lane_change", "sudden_stop", "safe_distance"))
            fmt = lambda g: "" if not g else (f"{g['start']}-{g['end']}" if isinstance(g, dict) else f"{g[0]}-{g[1]}")
            w.writerow([c["clip_id"], c["split"], c["accident_type"], c["complete"], "; ".join(c["issues"]),
                        co.get("reference_frame"), co.get("predicted_frame"), co.get("error_frames"),
                        vb.get("identity_correct"), vb.get("mean_iou_common_frames"), vb.get("tracked_at_collision"), vb.get("last_predicted_frame"), fmt(lc.get("reference")), fmt(lc.get("predicted")),
                        lc.get("tiou"), lc.get("direction_correct"), fmt(ss.get("reference")), fmt(ss.get("predicted")),
                        sd.get("reference_at_collision"), sd.get("predicted")])
    print(json.dumps({k: v for k, v in metrics.items() if k != "_run"}, indent=1))
    print("notes:", notes)
    print("written:", gt_path.relative_to(ROOT), out.relative_to(ROOT))


if __name__ == "__main__":
    main()
