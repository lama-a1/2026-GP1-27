"""Lane lines with TwinLiteNet, and whether each line of the recording car's lane is solid or dashed.

TwinLiteNet (Che et al., 2023, MIT licence, trained on BDD100K) gives a lane-line mask per frame
(ONNX export of the official weights, run with onnxruntime like YOLO). From the masks we
  1. find where the road meets the bonnet (the lowest rows the lines reach in the clip),
  2. group the mask pieces into lane lines (a dashed line is several pieces on one straight line),
  3. take the two lines of the recording car's lane: the nearest line left and right of the image centre
     at the bonnet,
  4. look at the band of road just above the bonnet, in the image itself, for paint along each line:
     a solid line has paint on almost every row, a dashed line has a gap with paint on both sides of it
     (rows hidden behind a tracked vehicle are skipped),
  5. vote over the frames.
The crossed line of a lane change is the recording car's lane line on the side the change happened.
The model is slow on a CPU (about 0.5 s a frame), so only every LANE_STEP-th frame of the seconds before
the impact is used.
"""
import os

import cv2
import numpy as np

from . import config

_SESSION = None
IN_W, IN_H = 640, 360


def _session():
    global _SESSION
    if _SESSION is None:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = max(1, min(2, os.cpu_count() or 1))
        _SESSION = ort.InferenceSession(config.LANE_MODEL_PATH, opts, providers=["CPUExecutionProvider"])
    return _SESSION


def masks(frames, which):
    """Lane-line mask (uint8 0/1, IN_H x IN_W) for each frame index in `which`."""
    s = _session()
    name = s.get_inputs()[0].name
    out = {}
    for f in which:
        im = cv2.resize(frames[f], (IN_W, IN_H), interpolation=cv2.INTER_LINEAR)
        x = np.ascontiguousarray(im[:, :, ::-1].transpose(2, 0, 1))[None].astype(np.float32) / 255.0
        _, ll = s.run(None, {name: x})
        out[f] = (ll[0, 1] > ll[0, 0]).astype(np.uint8)
    return out


def _pieces(mask):
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = []
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] < config.LANE_MIN_PIXELS:
            continue
        ys, xs = np.nonzero(lab == i)
        if ys.max() - ys.min() < 4:                     # flat blobs (stop lines, arrows, text)
            continue
        a, b = np.polyfit(ys, xs, 1)
        if abs(a) > 4:                                   # almost horizontal
            continue
        out.append({"a": a, "b": b, "ymin": int(ys.min()), "ymax": int(ys.max()), "ys": ys, "xs": xs})
    return out


def _lines(pieces):
    """Pieces lying on one straight line form one lane line."""
    lines = []
    for p in sorted(pieces, key=lambda p: -(p["ymax"] - p["ymin"])):
        for L in lines:
            if all(abs(L["a"] * y + L["b"] - (p["a"] * y + p["b"])) <= config.LANE_JOIN_PX for y in (p["ymin"], p["ymax"])):
                L["parts"].append(p)
                ys = np.concatenate([q["ys"] for q in L["parts"]]); xs = np.concatenate([q["xs"] for q in L["parts"]])
                L["a"], L["b"] = np.polyfit(ys, xs, 1)
                break
        else:
            lines.append({"a": p["a"], "b": p["b"], "parts": [p]})
    for L in lines:
        L["ymin"] = min(q["ymin"] for q in L["parts"]); L["ymax"] = max(q["ymax"] for q in L["parts"])
        L["rows"] = set(np.concatenate([q["ys"] for q in L["parts"]]).tolist())
    return lines


def _paint(img, L, rows):
    """For each row: is there road paint on the line? (the line is brighter than the road on both sides of it)

    TwinLiteNet was trained on BDD100K, where dashed lines are drawn as one continuous line, so its mask
    is continuous for dashed lines too. Solid / dashed is therefore read from the image itself along the line."""
    out = np.zeros(rows.size, bool)
    for i, r in enumerate(rows):
        x = int(round(L["a"] * r + L["b"]))
        w = max(3, int(round(config.LANE_PAINT_W * r / IN_H)))       # lines look wider closer to the bonnet
        lo, hi = x - w, x + w + 1
        if lo - 3 * w < 0 or hi + 3 * w > IN_W:
            continue
        line = img[r, lo:hi].max()
        road = np.median(np.concatenate([img[r, lo - 3 * w:lo - w], img[r, hi + w:hi + 3 * w]]))
        out[i] = line - road >= config.LANE_PAINT_CONTRAST
    return out


def _type(L, img, y_top, y_bot, hidden):
    """('Solid' | 'Dashed' | None, share of the band with paint) from the band of road just above the bonnet."""
    rows = np.arange(y_top, y_bot + 1)
    xs = (L["a"] * rows + L["b"]).astype(int)
    keep = (xs >= 0) & (xs < IN_W)
    rows, xs = rows[keep], xs[keep]
    rows = rows[~hidden[rows, xs]]
    if rows.size < config.LANE_MIN_BAND_ROWS:
        return None, None
    present = _paint(img, L, rows)
    cover = float(present.mean())
    if cover < config.LANE_MIN_COVER:
        return None, cover                               # too little paint to judge
    idx = np.nonzero(present)[0]
    # longest stretch without paint that has paint above and below it (rows behind a vehicle were removed)
    inner_gap = int(np.max(np.diff(idx)) - 1) if idx.size >= 2 else 0     # counted in visible rows only
    if cover >= config.LANE_SOLID_COVER and inner_gap < config.LANE_GAP_ROWS:
        return "Solid", cover
    if inner_gap >= config.LANE_GAP_ROWS:
        return "Dashed", cover
    return None, cover


def analyse(frames, tracks, frame_masks):
    """Lane lines per analysed frame (points in the 640 px work frame) + votes for the recording car's two lines."""
    H, W = frames[0].shape[:2]
    sx, sy = W / IN_W, H / IN_H
    per = {f: _lines(_pieces(m)) for f, m in frame_masks.items()}
    bottoms = [L["ymax"] for ls in per.values() for L in ls if L["ymax"] - L["ymin"] >= 15]
    if not bottoms:
        return {f: [] for f in per}, {"left": [], "right": []}, None
    y_bot = int(np.percentile(bottoms, 90))              # where the road meets the bonnet
    y_top = max(0, y_bot - int(IN_H * config.LANE_BAND_FRAC))
    out, votes = {}, {"left": [], "right": []}
    for f, lines in sorted(per.items()):
        hidden = np.zeros((IN_H, IN_W), bool)
        for t in tracks.values():
            if f in t:
                x1, y1, x2, y2 = t[f][:4]
                hidden[max(0, int(y1 / sy)):int(y2 / sy) + 1, max(0, int(x1 / sx)):int(x2 / sx) + 1] = True
        rgb = cv2.resize(frames[f], (IN_W, IN_H), interpolation=cv2.INTER_AREA).astype(np.int16)
        img = (rgb[:, :, 1] + rgb[:, :, 2]) // 2          # mean of green and red: white and yellow paint are both bright
        for L in lines:
            L["x_bot"] = L["a"] * y_bot + L["b"]
        cx = IN_W / 2
        left = [L for L in lines if L["x_bot"] < cx and L["ymax"] >= y_top]
        right = [L for L in lines if L["x_bot"] >= cx and L["ymax"] >= y_top]
        ego = {"left": max(left, key=lambda L: L["x_bot"]) if left else None,
               "right": min(right, key=lambda L: L["x_bot"]) if right else None}
        res = []
        for L in lines:
            typ, cover = _type(L, img, y_top, y_bot, hidden)
            side = next((k for k, v in ego.items() if v is L), None)
            if side:
                votes[side].append((f, typ, cover))
            ys = np.linspace(min(L["ymax"], y_bot), L["ymin"], 6)
            res.append({"points": [[round(float((L["a"] * y + L["b"]) * sx), 1), round(float(y * sy), 1)] for y in ys],
                        "line_type": typ or "Unclear", "ego_side": side,
                        "coverage": None if cover is None else round(cover, 2)})
        out[f] = res
    return out, votes, (y_top * sy, y_bot * sy)


def side_type(votes, side, f0=None, f1=None):
    """Majority type of the recording car's left / right lane line over frames f0..f1."""
    v = [x for x in votes.get(side, []) if (f0 is None or x[0] >= f0) and (f1 is None or x[0] <= f1)]
    typed = [x for x in v if x[1]]
    info = {"frames_seen": len(v), "frames_typed": len(typed)}
    if len(typed) < config.LANE_MIN_VOTES:
        return "Unclear", info
    solid = sum(1 for x in typed if x[1] == "Solid") / len(typed)
    info["solid_share"] = round(solid, 2)
    if solid >= config.LANE_VOTE:
        return "Solid", info
    if solid <= 1 - config.LANE_VOTE:
        return "Dashed", info
    return "Unclear", info


def frames_to_check(n, crash):
    """Which frames to run the lane model on: the seconds before the impact, every LANE_STEP-th frame."""
    end = n - 1 if crash is None else crash
    start = max(0, end - config.LANE_SECONDS * config.FPS)
    return list(range(start, end + 1, config.LANE_STEP))
