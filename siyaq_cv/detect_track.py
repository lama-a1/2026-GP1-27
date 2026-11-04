"""Vehicle detection (YOLOv8 exported to ONNX, no PyTorch) and a light ByteTrack-style IoU tracker."""
import cv2
import numpy as np

from . import config

_session = None


class _Detector:
    def __init__(self, path):
        try:
            import onnxruntime as ort
            so = ort.SessionOptions()
            so.intra_op_num_threads = 1
            self.ort = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
            self.inp = self.ort.get_inputs()[0].name
            self.net = None
        except ImportError:                       # OpenCV DNN works too (a bit slower)
            self.ort = None
            self.net = cv2.dnn.readNetFromONNX(path)

    def __call__(self, frame):
        h, w = frame.shape[:2]
        s = 640 / max(h, w)
        nh, nw = int(round(h * s)), int(round(w * s))
        canvas = np.full((640, 640, 3), 114, np.uint8)
        top, left = (640 - nh) // 2, (640 - nw) // 2
        canvas[top:top + nh, left:left + nw] = cv2.resize(frame, (nw, nh))
        blob = cv2.dnn.blobFromImage(canvas, 1 / 255.0, (640, 640), swapRB=True)
        if self.ort is not None:
            out = self.ort.run(None, {self.inp: blob})[0]
        else:
            self.net.setInput(blob)
            out = self.net.forward()
        p = out[0].T                               # 8400 x 84: cx, cy, w, h, 80 class scores
        cls_ids = list(config.CLASSES)
        scores = p[:, 4:][:, cls_ids]
        best = scores.argmax(1)
        conf = scores[np.arange(len(p)), best]
        keep = conf >= config.CONF_LOW
        p, conf, best = p[keep], conf[keep], best[keep]
        if not len(p):
            return []
        cx, cy, bw, bh = p[:, 0], p[:, 1], p[:, 2], p[:, 3]
        x1 = (cx - bw / 2 - left) / s
        y1 = (cy - bh / 2 - top) / s
        boxes = np.stack([x1, y1, bw / s, bh / s], 1)
        idx = cv2.dnn.NMSBoxes(boxes.tolist(), conf.tolist(), config.CONF_LOW, config.NMS_IOU)
        dets = []
        for i in np.array(idx).flatten():
            x, y, ww, hh = boxes[i]
            dets.append((max(0.0, float(x)), max(0.0, float(y)), min(float(w), float(x + ww)), min(float(h), float(y + hh)), float(conf[i]),
                         config.CLASSES[cls_ids[best[i]]]))
        return dets


def detector():
    global _session
    if _session is None:
        _session = _Detector(config.MODEL_PATH)
    return _session


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def track(frames):
    """Returns ({track_id: {frame: (x1, y1, x2, y2, score)}}, {track_id: class})."""
    det = detector()
    active, tracks, classes, next_id = {}, {}, {}, 1
    for f, frame in enumerate(frames):
        dets = det(frame)
        # predicted position = last box + last velocity
        pred = {}
        for tid, a in active.items():
            b, v = a["box"], a["vel"]
            pred[tid] = [b[0] + v[0], b[1] + v[1], b[2] + v[0], b[3] + v[1]]
        used_t, used_d = set(), set()
        for stage in ("high", "low"):
            pairs = []
            for di, d in enumerate(dets):
                if di in used_d or (stage == "high" and d[4] < config.CONF_HIGH):
                    continue
                for tid, p in pred.items():
                    if tid not in used_t:
                        iou = _iou(d, p)
                        if iou >= config.MATCH_IOU:
                            pairs.append((iou, tid, di))
            for iou, tid, di in sorted(pairs, reverse=True):
                if tid in used_t or di in used_d:
                    continue
                used_t.add(tid)
                used_d.add(di)
                d, a = dets[di], active[tid]
                gap = f - a["last"]
                a["vel"] = [((d[0] + d[2]) - (a["box"][0] + a["box"][2])) / 2 / gap,
                            ((d[1] + d[3]) - (a["box"][1] + a["box"][3])) / 2 / gap]
                a["box"], a["last"] = list(d[:4]), f
                tracks[tid][f] = d[:5]
        for di, d in enumerate(dets):
            if di not in used_d and d[4] >= config.CONF_HIGH:
                active[next_id] = {"box": list(d[:4]), "vel": [0.0, 0.0], "last": f}
                tracks[next_id] = {f: d[:5]}
                classes[next_id] = d[5]
                next_id += 1
        for tid in [t for t, a in active.items() if f - a["last"] > config.MAX_LOST]:
            del active[tid]
    tracks, classes = link_tracks(tracks, classes)
    tracks = {t: b for t, b in tracks.items() if len(b) >= config.MIN_TRACK_LEN}
    return tracks, {t: classes[t] for t in tracks}


def link_tracks(tracks, classes):
    """Join a track that ends with one that starts a few frames later at the predicted place and size
    (fast cut-ins and short occlusions otherwise split one vehicle into two IDs)."""
    changed = True
    while changed:
        changed = False
        ids = sorted(tracks, key=lambda t: min(tracks[t]))
        for a in ids:
            if a not in tracks:
                continue
            fa = sorted(tracks[a])
            last = fa[-1]
            pa = fa[-2] if len(fa) > 1 else last
            ba, bp = tracks[a][last], tracks[a][pa]
            step = max(1, last - pa)
            vx = ((ba[0] + ba[2]) - (bp[0] + bp[2])) / 2 / step
            vy = ((ba[1] + ba[3]) - (bp[1] + bp[3])) / 2 / step
            best = None
            for b in ids:
                if b == a or b not in tracks:
                    continue
                first = min(tracks[b])
                gap = first - last
                if not 1 <= gap <= config.LINK_MAX_GAP:
                    continue
                bb = tracks[b][first]
                px, py = (ba[0] + ba[2]) / 2 + vx * gap, (ba[1] + ba[3]) / 2 + vy * gap
                w = max(ba[2] - ba[0], 1.0)
                dist = ((bb[0] + bb[2]) / 2 - px) ** 2 + ((bb[1] + bb[3]) / 2 - py) ** 2
                ratio = (bb[3] - bb[1]) / max(ba[3] - ba[1], 1.0)
                if dist ** 0.5 < 0.6 * w and 0.6 < ratio < 1.7 and (best is None or dist < best[0]):
                    best = (dist, b)
            if best:
                tracks[a].update(tracks.pop(best[1]))
                classes.pop(best[1], None)
                changed = True
    return tracks, classes
