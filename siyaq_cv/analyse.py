"""Siyaq Sprint 2 - analyse one dashcam video: detect and track vehicles, measure their movement,
and extract the traffic events with the measures behind each one.

    from siyaq_cv.analyse import analyse_video
    result = analyse_video("crash.mp4", accident_type="REAR_END")     # accident type chosen by the user

    python -m siyaq_cv.analyse crash.mp4 --type LANE_CHANGE --out result.json

The accident type is NOT predicted: it comes from the case form and is only stored with the result.
"""
import argparse
import base64
import json
import time

import cv2
import numpy as np

from . import config, detect_track, events, lanes, motion, video

LINE_COLOUR = {"Solid": (40, 40, 230), "Dashed": (230, 140, 30), "Unclear": (0, 190, 255)}


def _thumb(frame, tracks, f, highlight, width=480, lines=None):
    im = frame.copy()
    for ln in lines or []:
        cv2.polylines(im, [np.array(ln["points"], np.int32)], False, LINE_COLOUR[ln["line_type"]], 2)
    for tid, t in tracks.items():
        if f in t:
            x1, y1, x2, y2 = map(int, t[f][:4])
            col = (40, 40, 230) if tid == highlight else (90, 200, 90)
            cv2.rectangle(im, (x1, y1), (x2, y2), col, 3 if tid == highlight else 1)
            cv2.putText(im, ("B" if tid == highlight else str(tid)), (x1 + 2, max(14, y1 - 4)), 0, 0.5, col, 2)
    s = width / im.shape[1]
    im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 72])
    return base64.b64encode(buf.tobytes()).decode()


def _lane_summary(evs, votes):
    """Type of the recording car's two lane lines, and of the line crossed in the lane change."""
    left, li = lanes.side_type(votes, "left")
    right, ri = lanes.side_type(votes, "right")
    out = {"model": "TwinLiteNet (BDD100K)", "left_line": left, "right_line": right,
           "visible": bool(li["frames_seen"] or ri["frames_seen"]), "crossed_line_type": None}
    lc = next((e for e in evs if e["type"] == "lane_change"), None)
    if lc:
        d = lc["measures"]["direction"]
        if lc["vehicle"] == "B":
            # B moving left came from the right lane, so it crossed the recording car's right line (and the other way round)
            side, f0, f1 = ("right" if d == "left" else "left"), lc["start"] - 10, lc["end"]
        else:
            # the recording car crosses its own line on the side it turns to; read it before the car is over it
            side, f0, f1 = d, lc["start"] - 10, lc["start"] + 2
        typ, info = lanes.side_type(votes, side, f0, f1)
        lc["measures"].update({"crossed_line_side": side, "crossed_line_type": typ,
                               "crossed_line_frames": info["frames_typed"], "crossed_line_solid_share": info.get("solid_share")})
        out["crossed_line_type"] = typ
    return out


def analyse_video(path, accident_type=None, thumbnails=True):
    t0 = time.time()
    v = video.load(path)
    frames, times, W, H = v["frames"], v["times"], v["width"], v["height"]
    tracks, classes = detect_track.track(frames)
    t_det = time.time() - t0
    flow = motion.flow_series(frames, tracks)
    meas = {tid: motion.vehicle_measures(tr, classes[tid], W, H, flow["box_flow"].get(tid)) for tid, tr in tracks.items()}
    b = events.pick_vehicle_b(tracks, W, H, len(frames))
    evs, crash = events.analyse(meas, b, flow, times)
    t1 = time.time()
    lane_frames, lane_info = {}, None
    try:
        lane_frames, votes, _ = lanes.analyse(frames, tracks, lanes.masks(frames, lanes.frames_to_check(len(frames), crash)))
        lane_info = _lane_summary(evs, votes)
    except Exception as exc:                       # the lane model is an extra: the analysis goes on without it
        lane_info = {"error": str(exc)[:200]}
    t_lane = time.time() - t1
    if thumbnails:
        for e in evs:
            near = min(lane_frames, key=lambda k: abs(k - e["start"])) if lane_frames and e["type"] == "lane_change" else None
            e["thumbnail_jpeg"] = _thumb(frames[e["start"]], tracks, e["start"], b if e["vehicle"] == "B" else e.get("track_id"),
                                         lines=lane_frames.get(near) if near is not None else None)
    mb = meas.get(b, {})
    series = {"t": times,
              "a_heading_rate_deg_s": [round(x, 2) for x in flow["yaw_rate"]],
              "a_pitch_px": [round(x, 2) for x in flow["pitch_px"]],
              "jolt": [round(x, 2) for x in flow["jolt"]],
              "b_distance_m": [mb[k]["distance_m"] if k in mb else None for k in range(len(frames))],
              "b_ttc_s": [mb[k]["ttc_s"] if k in mb else None for k in range(len(frames))],
              "b_rel_speed_mps": [mb[k]["rel_speed_mps"] if k in mb else None for k in range(len(frames))]}
    return {
        "version": config.VERSION, "detector": config.MODEL, "accident_type": accident_type,
        "video": {"fps": config.FPS, "frames": len(frames), "duration_s": v["duration_s"],
                  "window_start_s": v["window_start_s"], "width": v.get("src_width"), "height": v.get("src_height"),
                  "source_fps": round(v.get("src_fps", 0), 2)},
        "assumptions": {"camera_fov_deg": config.CAMERA_FOV_DEG, "real_heights_m": config.REAL_HEIGHT_M},
        "quality": video.quality(frames),
        "vehicle_b": b, "collision_frame": crash,
        "vehicles": [{"track_id": tid, "role": "B" if tid == b else "other", **events.behaviour(meas[tid], classes[tid])}
                     for tid in sorted(tracks)],
        # boxes normalised to 0..1 so the page can draw them over the original video at any size
        "tracks": {str(tid): [[f, round(x1 / W, 4), round(y1 / H, 4), round(x2 / W, 4), round(y2 / H, 4)]
                              for f, (x1, y1, x2, y2, _) in sorted(tr.items())] for tid, tr in tracks.items()},
        "measures_b": {str(k): mb[k] for k in sorted(mb)},
        "series": series,
        "events": evs,
        "lane_markings": lane_info,
        "crossed_line_type": (lane_info or {}).get("crossed_line_type"),
        # lane lines on the frames the lane model read, points normalised to 0..1 like the boxes
        "lanes": [{"frame": f, "points": [[round(x / W, 4), round(y / H, 4)] for x, y in ln["points"]],
                   "line_type": ln["line_type"], "ego_side": ln["ego_side"]}
                  for f in sorted(lane_frames) for ln in lane_frames[f]],
        "timing_s": {"detection_tracking": round(t_det, 1), "lanes": round(t_lane, 1), "total": round(time.time() - t0, 1)},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--type", choices=["REAR_END", "LANE_CHANGE"])
    ap.add_argument("--out", default="result.json")
    a = ap.parse_args()
    r = analyse_video(a.video, a.type)
    json.dump(r, open(a.out, "w"), ensure_ascii=False)
    for e in r["events"]:
        print(f"{e['start_t']:6.1f}s  {e['type']:<19} {e['vehicle']:<6} {json.dumps(e['measures'], ensure_ascii=False)}")
    print("time:", r["timing_s"])


if __name__ == "__main__":
    main()
