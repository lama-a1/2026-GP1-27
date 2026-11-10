"""Per-clip error analysis of an EVAL run (reference vs prediction, difference, category, likely cause).

    python tools/eval_error_analysis.py --eval results/EVAL-001_cvat_vs_EXP-008 --exp EXP-008

Reads per_clip.json of the evaluation, the extracted CVAT labels and the saved diagnostics.csv / prediction.json of the
experiment. Writes error_analysis.csv and error_analysis.md into the evaluation folder. Nothing else is changed.

Categories
  OK                    prediction matches the reference under the evaluation rule
  System error          the reference is sound and the prediction does not match
  Annotation missing    the label needed for this field is absent: the field stays pending
  Annotation conflict   the label contradicts another source (approved review, dataset index, accident type)
  Pending definition    reference and system may not measure the same thing; not counted as an error yet
The "likely cause" column is computed from the saved diagnostics, not guessed; "check visually" means it was not.
"""
import argparse, csv, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from run_experiment import COLLISION_TOL, TIOU_THR   # noqa: E402

TTC_SUDDEN = None
try:
    sys.path.insert(0, str(ROOT))
    from siyaq_cv import config as _c
    TTC_SUDDEN = _c.TTC_SUDDEN_STOP_S
except Exception:
    pass


def diag(exp, clip):
    rows = list(csv.DictReader(open(ROOT / "results" / f"{exp}_{clip}" / "diagnostics.csv")))
    tracked = [int(r["frame"]) for r in rows if r["b_tracked"] == "1"]
    jolt = [float(r["jolt"] or 0) for r in rows]
    ttc = {int(r["frame"]): float(r["ttc_s"]) for r in rows if r["ttc_s"] not in ("", None)}
    return rows, tracked, jolt, ttc


def analyse(c, ref, exp, approved):
    clip = c["clip_id"]
    rows, tracked, jolt, ttc = diag(exp, clip)
    out = []
    add = lambda field, r, p, d, cat, cause: out.append({"clip_id": clip, "accident_type": c["accident_type"], "field": field,
                                                        "reference": r, "prediction": p, "difference": d, "category": cat, "likely_cause": cause})
    # collision
    co = c.get("collision")
    if co:
        rf, pf, e = co["reference_frame"], co["predicted_frame"], co["error_frames"]
        near = [f for f in tracked if abs(f - rf) <= 3]
        top = max(range(len(jolt)), key=lambda f: jolt[f])
        if co["hit_within_0_5s"]:
            add("collision", rf, pf, e, "OK", "")
        elif not near:
            span = f"{min(tracked)}-{max(tracked)}" if tracked else "never"
            add("collision", rf, pf, e, "System error",
                f"Vehicle B not tracked within 3 frames of the impact (tracked {span}); strongest image jolt at frame {top}")
        else:
            add("collision", rf, pf, e, "System error", f"B tracked at the impact; strongest jolt at frame {top}, chosen frame {pf}: check visually")
    # Vehicle B
    vb = c.get("vehicle_b")
    if vb is None:
        add("vehicle_b", "", "", "", "Annotation missing", "no Vehicle B role in the label")
    elif not vb["identity_correct"]:
        add("vehicle_b", "labelled B", f"track {vb['predicted_track']}", f"mean IoU {vb['mean_iou_common_frames']}", "System error",
            f"predicted B overlaps the labelled B only near the end (IoU at collision {vb['box_iou_at_collision']}): another vehicle or a looser box; check visually")
    elif not vb["tracked_at_collision"]:
        pb = sorted(int(b[0]) for b in json.loads((ROOT / "results" / f"{exp}_{clip}" / "prediction.json").read_text()).get("vehicle_b_boxes", []))
        rf = vb["reference_frame"]
        why = (f"no predicted B box within 3 frames of the impact (boxes at frames {pb[0]}-{pb[-1]}, measured {len(tracked)} frames)"
               if not any(abs(f - rf) <= 3 for f in pb) else f"B box present at the impact but IoU {vb['box_iou_at_collision']} (box off)")
        add("vehicle_b", "labelled B", f"track {vb['predicted_track']}", f"identity OK (IoU {vb['mean_iou_common_frames']}); not at impact",
            "System error", "correct vehicle; " + why)
    else:
        add("vehicle_b", "labelled B", f"track {vb['predicted_track']}", f"IoU {vb['mean_iou_common_frames']}", "OK", "")
    # lane change
    lc = c.get("lane_change")
    if lc is None:
        why = "lane change tagged in a rear-end clip" if any("rear-end" in i for i in c["issues"]) else "lane change label incomplete"
        add("lane_change", "", "", "", "Annotation conflict" if "rear-end" in why else "Annotation missing", why)
    else:
        g, p = lc["reference"], lc["predicted"]
        fmt = lambda x: "none" if not x else f"{x['start']}-{x['end']} {x.get('direction') or ''}".strip()
        conflict = ""
        if clip in approved and "lane_change" in approved[clip] and g:
            a = approved[clip]["lane_change"]
            if (a["start"], a["end"]) != (g["start"], g["end"]):
                conflict = f"approved review gives {a['start']}-{a['end']}"
        if conflict:
            add("lane_change", fmt(g), fmt(p), "" if not p or not g else f"tIoU {lc.get('tiou')}", "Annotation conflict", conflict)
        elif g and p:
            ok = lc["tiou"] >= TIOU_THR
            se = lc["start_error_frames"]
            cause = "" if ok and abs(se) <= 5 else ("onset earlier than the label (EXP-006 definition)" if se < -5 else "")
            if lc.get("direction_correct") is False:
                cause = (cause + "; " if cause else "") + "wrong direction"
            add("lane_change", fmt(g), fmt(p), f"tIoU {lc['tiou']}, start {se:+d}, end {lc['end_error_frames']:+d}",
                "OK" if ok and not cause else "System error", cause or "")
        elif g and not p:
            add("lane_change", fmt(g), "none", "missed", "System error",
                f"no lane-change event; Vehicle B tracked in {len(tracked)} frames" + (" (short track)" if len(tracked) < 15 else ""))
        elif p and not g:
            add("lane_change", "none (rear-end)", fmt(p), "spurious", "System error", "lane change reported in a rear-end clip")
        else:
            add("lane_change", "none", "none", "", "OK", "")
    # sudden stop
    ss = c.get("sudden_stop")
    if ss is None:
        add("sudden_stop", "", "", "", "Annotation missing", "sudden stop start/end not paired")
    else:
        g, p = ss["reference"], ss["predicted"]
        f = lambda x: "none" if not x else f"{x[0]}-{x[1]}"
        if g and not p:
            win = [ttc[k] for k in ttc if g[0] - 5 <= k <= g[1]]
            m = min(win) if win else None
            if (c.get("lane_change") or {}).get("predicted"):
                why = "not checked: the rule skips sudden stop when a lane change by B is reported (here a spurious one)"
            elif m is None:
                why = "no TTC for B in the labelled window (B not tracked)"
            elif TTC_SUDDEN is not None and m < TTC_SUDDEN:
                why = f"TTC fell to {m:.2f} s, but not while B was centred ahead (rule needs |centre offset| <= 0.15)"
            else:
                why = f"lowest TTC of B in the labelled window {m:.2f} s (rule: < {TTC_SUDDEN} s)"
            add("sudden_stop", f(g), "none", "missed", "System error", why)
        elif p and not g:
            add("sudden_stop", "none", f(p), "spurious", "System error", "TTC below the threshold without a labelled stop")
        else:
            add("sudden_stop", f(g), f(p), "" if not (g and p) else f"tIoU {ss.get('tiou')}", "OK", "")
    # safe distance
    sd = c.get("safe_distance")
    if sd is None:
        add("safe_distance", "", "", "", "Annotation missing", "no safe_distance tag")
    elif sd["agree"] is None:
        add("safe_distance", sd["reference_at_collision"], sd["predicted"] or "none", "",
            "Annotation missing" if sd["reference_at_collision"] not in ("Maintained", "Not maintained") else "System error",
            "label is Unclear" if sd["reference_at_collision"] not in ("Maintained", "Not maintained") else "no following-distance verdict")
    else:
        add("safe_distance", sd["reference_at_collision"], sd["predicted"], "agree" if sd["agree"] else "disagree",
            "OK" if sd["agree"] else "Pending definition",
            "" if sd["agree"] else "label is the judgement at the impact; the system verdict uses image size of B at one earlier frame")
    # accident type vs dataset index
    if c.get("accident_type_vs_index") is False:
        add("accident_type", c["accident_type"], ref["accident_type_in_dataset_index"] + " (dataset index, draft)", "differs",
            "Annotation conflict", "CVAT label differs from the draft accident type in dataset_index.csv")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", required=True)
    ap.add_argument("--exp", default="EXP-008")
    ap.add_argument("--labels", default=str(ROOT / "experiments" / "ground_truth" / "cvat_completed_2026-11-10.json"))
    a = ap.parse_args()
    ev = Path(a.eval)
    pcs = json.loads((ev / "per_clip.json").read_text())
    refs = json.loads(Path(a.labels).read_text())["clips"]
    approved = json.loads((ROOT / "experiments" / "ground_truth" / "human_reviewed.json").read_text())["clips"]
    rows = [r for c in pcs for r in analyse(c, refs[c["clip_id"]], a.exp, approved)]
    with open(ev / "error_analysis.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    cats = {}
    for r in rows:
        cats.setdefault(r["field"], {}).setdefault(r["category"], 0)
        cats[r["field"]][r["category"]] += 1
    md = ["# Error analysis — " + ev.name, "", "| Field | " + " | ".join(["OK", "System error", "Annotation missing", "Annotation conflict", "Pending definition"]) + " |",
          "|---|---|---|---|---|---|"]
    for fld, cc in cats.items():
        md.append(f"| {fld} | " + " | ".join(str(cc.get(k, 0)) for k in ["OK", "System error", "Annotation missing", "Annotation conflict", "Pending definition"]) + " |")
    md += ["", "| Clip | Type | Field | Reference | Prediction | Difference | Category | Likely cause |", "|---|---|---|---|---|---|---|---|"]
    md += [f"| {r['clip_id']} | {r['accident_type']} | {r['field']} | {r['reference']} | {r['prediction']} | {r['difference']} | {r['category']} | {r['likely_cause']} |"
           for r in rows if r["category"] != "OK"]
    (ev / "error_analysis.md").write_text("\n".join(md) + "\n")
    print(json.dumps(cats, indent=1))


if __name__ == "__main__":
    main()
