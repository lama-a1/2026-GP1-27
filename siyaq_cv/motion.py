"""Optical-flow motion of the recording car, and per-vehicle distance / speed measures.

Optical flow - Farneback dense flow, the method of the W&B "Predicting vehicle speed from dashcam video"
reference. The article turns flow into km/h with a CNN trained on 20,400 frames with speed labels from one
fixed camera. Siyaq's videos come from many different, uncalibrated dashcams and have no speed labels,
and a check against the GPS speed printed on 4 CCD clips showed that flow alone cannot give the recording
car's km/h reliably across cameras (best correlation about 0.5). So the flow is used for what it measures
well without calibration:
  * horizontal flow of the background -> heading change of the recording car (its own lane change)
  * flow inside each vehicle box minus the background -> sideways motion of that vehicle
  * mean image change -> the impact jolt
Distance - pinhole model, as in the Vehicle-Distance-Measurement-System reference:
        d = H_real * f / h_box        (H_real per class: car 1.55 m, bus 3.0 m, truck 2.5 m)
    with f from an assumed 110 deg field of view, plus the off-centre correction sqrt(Z^2 + X^2).
Speed of the other vehicle relative to the recording car = change of that distance over time, and
time-to-collision = box height / growth rate (needs no calibration at all).
"""
import math

import cv2
import numpy as np

from . import config


def focal_px(width):
    return (width / 2) / math.tan(math.radians(config.CAMERA_FOV_DEG) / 2)


def _smooth(x, k=5):
    x = np.asarray(x, float)
    out = x.copy()
    for i in range(len(x)):
        w = x[max(0, i - k // 2): i + k // 2 + 1]
        w = w[~np.isnan(w)]
        out[i] = np.median(w) if w.size else np.nan
    return out


def flow_series(frames, tracks):
    """Per frame: jolt, background shift (px at 640 width), heading rate (deg/s), pitch shift, per-track box flow."""
    n = len(frames)
    W = frames[0].shape[1]
    s = config.FLOW_WIDTH / W
    boxes_at = {}
    for tid, t in tracks.items():
        for f, b in t.items():
            boxes_at.setdefault(f, []).append((tid, b))
    prev = cv2.cvtColor(cv2.resize(frames[0], None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
    h, w = prev.shape
    small_prev = cv2.resize(prev, (160, 90)).astype(np.float32)
    jolt, ego_dx, pitch, box_flow = [0.0], [0.0], [0.0], {}
    for i in range(1, n):
        cur = cv2.cvtColor(cv2.resize(frames[i], None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        small = cv2.resize(cur, (160, 90)).astype(np.float32)
        jolt.append(float(np.abs(small - small_prev).mean()))
        small_prev = small
        fl = cv2.calcOpticalFlowFarneback(prev, cur, None, **config.FARNEBACK)
        bg = np.ones((h, w), bool)
        bg[: int(0.35 * h)] = False          # sky
        bg[int(0.85 * h):] = False           # hood
        for tid, b in boxes_at.get(i, []):
            x1, y1, x2, y2 = [int(v * s) for v in b[:4]]
            bg[max(0, y1):y2, max(0, x1):x2] = False
        dx = float(np.median(fl[..., 0][bg])) if bg.any() else 0.0
        dy = float(np.median(fl[..., 1][bg])) if bg.any() else 0.0
        ego_dx.append(dx / s)
        pitch.append(dy / s)
        for tid, b in boxes_at.get(i, []):
            x1, y1, x2, y2 = [int(v * s) for v in b[:4]]
            patch = fl[max(0, y1):max(y1 + 1, y2), max(0, x1):max(x1 + 1, x2)]
            if patch.size:
                box_flow.setdefault(tid, {})[i] = (round((float(np.median(patch[..., 0])) - dx) / s, 2),
                                                   round((float(np.median(patch[..., 1])) - dy) / s, 2))
        prev = cur
    f640 = focal_px(W)
    yaw = [math.degrees(math.atan(d / f640)) * config.FPS for d in ego_dx]      # deg per second
    return {"jolt": jolt, "ego_dx": ego_dx, "pitch_px": pitch, "yaw_rate": yaw, "box_flow": box_flow}


def vehicle_measures(boxes, cls, width, height, box_flow=None):
    """Per frame for one track: distance (m), sideways position (m), relative speeds, TTC."""
    f = focal_px(width)
    H = config.REAL_HEIGHT_M.get(cls, 1.55)
    fr = sorted(boxes)
    zs, xs = [], []
    for k in fr:
        x1, y1, x2, y2 = boxes[k][:4]
        z = H * f / max(y2 - y1, 1.0)
        zs.append(z)
        xs.append(((x1 + x2) / 2 - width / 2) * z / f)            # sideways offset in metres
    zsm = _smooth(zs, 5)
    out = {}
    for i, k in enumerate(fr):
        x1, y1, x2, y2 = boxes[k][:4]
        hpx = y2 - y1
        rel = ttc = lat_v = None
        j = max(0, i - 3)
        if i - j >= 2 and k - fr[j] <= 6:
            dt = (k - fr[j]) / config.FPS
            rel = (zsm[i] - zsm[j]) / dt                          # m/s, negative = getting closer
            h0 = boxes[fr[j]][3] - boxes[fr[j]][1]
            growth = (hpx - h0) / max(h0, 1) / dt                 # scale change per second
            ttc = 1 / growth if growth > 1e-3 else None
            lat_v = (xs[i] - xs[j]) / dt
        bf = box_flow.get(k) if box_flow else None
        out[k] = {
            "distance_m": round(float(math.hypot(zsm[i], xs[i])), 2),
            "lateral_m": round(float(xs[i]), 2),
            "centre_offset": round(((x1 + x2) / 2 - width / 2) / width, 4),
            "height_frac": round(hpx / width, 4),
            "rel_speed_mps": None if rel is None else round(float(rel), 2),
            "lateral_speed_mps": None if lat_v is None else round(float(lat_v), 2),
            "ttc_s": None if ttc is None else round(float(ttc), 2),
            "flow_dx_px": None if bf is None else bf[0],
            # the box touches the left or right side of the image: part of the vehicle is outside the picture,
            # so its centre (and the sideways position) is biased towards the image
            "at_edge": bool(x1 <= config.EDGE_PX or x2 >= width - config.EDGE_PX),
        }
    return out
