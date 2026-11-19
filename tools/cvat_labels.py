"""Extract the team's CVAT labels into data/ground_truth/cvat_labels.json (one entry per clip).

    python tools/cvat_labels.py --export <CVAT project export, Datumaro 1.0>.zip

The project export numbers the frames of all tasks one after the other, in task order: siyaq_CCD_1 (2000 frames),
siyaq_CCD_2 (1950), siyaq_DADA (3500). Every 50-frame job is one clip; data/dataset/clip_job_map_v2.csv says which.
Excluded clips (rain/snow) are skipped. Each clip records its labels and a completeness check ("issues"); an element
(collision, Vehicle B, lane change, ...) is only used in the evaluation when its own labels are sound ("valid_for").
"""
import argparse, csv, datetime as dt, hashlib, json, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from scoring import LEVEL, B_FRAME_TOL   # noqa: E402

TASK_IDS = {2740516: "siyaq_CCD_1", 2740517: "siyaq_CCD_2", 2740522: "siyaq_DADA",
            "2740516": "siyaq_CCD_1", "2740517": "siyaq_CCD_2", "2740522": "siyaq_DADA"}
TASKS = {"siyaq_CCD_1": {"offset": 0, "frames": 2000}, "siyaq_CCD_2": {"offset": 2000, "frames": 1950},
         "siyaq_DADA": {"offset": 3950, "frames": 3500}}


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


def extract_api(job, real, size):
    """Same output as extract(), from one job read through the CVAT REST API (tools/cvat_api_dump.js).
    Tracks keep only their key frames there, so boxes are interpolated linearly between key frames, as CVAT does."""
    W, H = size
    tags, b_boxes, other_tracks, b_tracks, lines, beyond = [], {}, set(), set(), [], []
    for f, name, attrs in job["tags"]:
        if f >= real:
            beyond.append((f, name))
        tags.append({"frame": f, "label": name, **attrs})
    for tr in job["tracks"]:
        keys = sorted((s for s in tr["shapes"] if s[2] == "rectangle"), key=lambda s: s[0])
        if not keys:
            if any(s[2] == "polyline" for s in tr["shapes"]):
                lines += [{"frame": s[0], "line_type": tr["attrs"].get("line_type")} for s in tr["shapes"]]
            continue
        boxes = {}
        for a, b in zip(keys, keys[1:] + [None]):
            if a[1]:                                  # outside: hidden until the next key frame
                continue
            end = b[0] if b else 50
            for f in range(a[0], min(end, 50)):
                if b and not b[1] and b[0] > a[0]:
                    t = (f - a[0]) / (b[0] - a[0])
                    pts = [a[3 + i] + t * (b[3 + i] - a[3 + i]) for i in range(4)]
                else:
                    pts = a[3:7]
                boxes[f] = [round(pts[0] / W, 4), round(pts[1] / H, 4), round(pts[2] / W, 4), round(pts[3] / H, 4)]
        if tr["attrs"].get("role") == "Vehicle B":
            b_tracks.add(tr["id"]); b_boxes.update(boxes)
        else:
            other_tracks.add(tr["id"])
        beyond += [(f, tr["label"]) for f in boxes if f >= real]
    for f, name, typ, attrs, *pts in job["shapes"]:
        if typ == "rectangle" and attrs.get("role") == "Vehicle B":
            b_boxes[f] = [round(pts[0] / W, 4), round(pts[1] / H, 4), round(pts[2] / W, 4), round(pts[3] / H, 4)]
            b_tracks.add(f"shape{f}")
        elif typ == "polyline":
            lines.append({"frame": f, "line_type": attrs.get("line_type")})
    return tags, b_boxes, b_tracks, other_tracks, lines, beyond


def build_reference(job, row, items, labels, idx, extracted=None):
    task = row["task"]
    f0 = int(row["task_frames"].split("-")[0])
    real = int(row["real_frames"])
    if extracted is None:
        size = items[TASKS[task]["offset"] + f0]["image"]["size"]
        extracted = extract(items, labels, TASKS[task]["offset"] + f0, real, size)
    tags, bb, bt, ot, lines, beyond = extracted
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
        # a lane change before a rear-end impact is allowed (rule R3); it must still have a start and an end
        L = ref["lane_change"]
        if L["start"] is None or L["end"] is None:
            issues.append("lane change start/end missing")
        elif L["start"] > L["end"]:
            issues.append("lane change start after end")
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
        # Lane-change clips need a complete lane change; rear-end clips are scored as "no lane change" or, when a lane
        # change is tagged before the impact (rule R3), as that lane change, which must then be complete as well
        "lane_change": (ref["lane_change"] is not None and None not in (ref["lane_change"]["start"], ref["lane_change"]["end"])
                        and ref["lane_change"]["start"] <= ref["lane_change"]["end"]) or ((acc or {}).get("value") == "Rear-end" and not ref["lane_change"]),
        "sudden_stop": not S or None not in (S["start"], S["end"]),
        "safe_distance": bool(sd),
        "accident_type": bool(acc)}
    return ref

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--export", help="CVAT project export (Datumaro 1.0), .zip or default.json")
    src.add_argument("--api-dump", help="JSON written by tools/cvat_api_dump.js (annotations read through the CVAT API)")
    ap.add_argument("--out", default=str(ROOT / "data" / "ground_truth" / "cvat_labels.json"))
    a = ap.parse_args()
    dump = None
    if a.export:
        items, labels, md5 = load_export(a.export)
        if len(items) != sum(t["frames"] for t in TASKS.values()):
            raise SystemExit(f"export has {len(items)} frames; expected {sum(t['frames'] for t in TASKS.values())} (task layout changed?)")
    else:
        raw = Path(a.api_dump).read_bytes()
        dump, items, labels, md5 = json.loads(raw), None, None, hashlib.md5(raw).hexdigest()
        by_pos = {(TASK_IDS[j["task"]], j["start"]): (jid, j) for jid, j in dump["jobs"].items()}
    ds = ROOT / "data" / "dataset"
    jm = list(csv.DictReader(open(ds / "clip_job_map_v2.csv")))
    idx = {r["clip_id"]: r for r in csv.DictReader(open(ds / "dataset_index.csv"))}
    refs = []
    for row in jm:
        if row["active_v2"] != "yes":
            continue
        f0 = int(row["task_frames"].split("-")[0])
        job = f"{row['task']}#{row['job_number_in_task']}"
        if dump is None:
            refs.append(build_reference(job, row, items, labels, idx))
            continue
        hit = by_pos.get((row["task"], f0))
        if hit is None:
            print(f"  {row['clip_id']}: job not in the API dump"); continue
        jid, j = hit
        size = dump["sizes"][str(j["task"])]
        r = build_reference(int(jid), row, None, None, idx, extracted=extract_api(j, int(row["real_frames"]), size))
        r["cvat_state"] = j.get("state")
        refs.append(r)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({
        "_about": "Labels of every active clip, extracted from the CVAT project export by tools/cvat_labels.py. "
                  "Boxes are normalised 0-1. Do not edit by hand: fix the labels in CVAT and export again.",
        "level": LEVEL, "export_md5": md5, "extracted_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "clips": {r["clip_id"]: r for r in refs}}, indent=1))
    bad = [r for r in refs if not r["complete"]]
    print(f"{len(refs)} clips written to {a.out}; {len(refs) - len(bad)} complete, {len(bad)} with issues")
    for r in bad:
        print(f"  {r['clip_id']} ({r['task']} job {r['job_id']}): " + "; ".join(r["issues"]))


if __name__ == "__main__":
    main()
