"""Evaluation rules shared by the Siyaq evaluation tools: how a prediction is compared with the CVAT labels.

    collision      correct when the predicted impact frame is within COLLISION_TOL frames (0.5 s) of the label
    Vehicle B      identity correct when the mean box IoU over the frames both have a box is >= B_IOU_THR
    lane change    matched when the temporal IoU of the intervals is >= TIOU_THR; rear-end clips count as "no lane change"
    sudden stop    presence (yes/no) compared with the label
    safe distance  the last safe_distance tag at or before the labelled impact, compared with the prediction
"""
import statistics as st

FPS = 10
COLLISION_TOL = 5          # frames = 0.5 s at 10 fps
TIOU_THR = 0.3             # an interval event is matched when temporal IoU >= 0.3
B_IOU_THR = 0.5            # predicted Vehicle B box vs labelled box
B_FRAME_TOL = 3
LEVEL = "cvat_labels"


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


def sd_at(ref, frame):
    vals = [s for s in ref["safe_distance"] if frame is None or s["frame"] <= frame]
    return (vals[-1] if vals else ref["safe_distance"][0])["value"] if ref["safe_distance"] else None


def compare(ref, pred, human=None):
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
    h = (human or {}).get(ref["clip_id"])
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


