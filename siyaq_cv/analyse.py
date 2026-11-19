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


def _picture(v):
    c = v.get("crop")
    if not c:
        return None
    t, b, l, r = c
    W, H = v["src_width"], v["src_height"]
    return [round(l / W, 4), round(t / H, 4), round((r - l) / W, 4), round((b - t) / H, 4)]


def _lane_summary(evs, votes, times=None):
    """Type of the recording car's two lane lines, and of the line crossed in the lane change."""
    left, li = lanes.side_type(votes, "left")
    right, ri = lanes.side_type(votes, "right")
    out = {"model": "TwinLiteNet (BDD100K)", "left_line": left, "right_line": right,
           "visible": bool(li["frames_seen"] or ri["frames_seen"]), "crossed_line_type": None}
    lc = next((e for e in evs if e["type"] == "lane_change"), None)
    if lc and lc["measures"].get("direction"):
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
        typed = sorted(x[0] for x in votes.get(side, []) if x[1] and f0 <= x[0] <= f1)
        if typed:                       # a vote over the lane-model frames of that stretch
            w = {"basis": "estimated", "frames": [typed[0], typed[-1]]}
            if times:
                w["time_s"] = [events._t(typed[0], times), events._t(typed[-1], times)]
            lc.setdefault("sources", {}).update({k: w for k in ("crossed_line_type", "crossed_line_frames",
                                                                 "crossed_line_solid_share")})
        out["crossed_line_type"] = typ
    return out


def _rear_stop(frames, tracks, mb, b, crash, times, evs):
    """Rear camera: sudden stop of the recording car (the front vehicle). Vehicle B behind closes in fast (its
    time-to-collision falls below TTC_SUDDEN_STOP_S) while the background, seen through the rear camera, almost stops
    moving (the recording car slows sharply). Exploratory: there are no rear-camera clips in the evaluation data."""
    lows = [k for k in sorted(mb) if k < crash and abs(mb[k]["centre_offset"]) <= 0.15
            and mb[k]["ttc_s"] is not None and mb[k]["ttc_s"] < config.TTC_SUDDEN_STOP_S]
    if not lows:
        return None
    s0 = lows[0]
    bg = motion.background_still(frames, tracks, s0 - 15, crash - 1)
    pre = [v for k, v in bg.items() if k < s0]
    post = [v for k, v in bg.items() if k >= s0]
    if len(pre) < 3 or len(post) < 3:
        return None
    m_pre, m_post = float(np.median(pre)), float(np.median(post))
    if m_pre <= config.STILL_PX or m_post > config.REAR_STOP_DROP * m_pre:
        return None
    win = {"basis": "estimated", "frames": [max(1, s0 - 15), crash - 1],
           "time_s": [events._t(max(1, s0 - 15), times), events._t(crash - 1, times)]}
    at0 = {"basis": "observed", "frame": int(s0), "time_s": events._t(s0, times)}
    e = {"type": "sudden_stop", "vehicle": "A", "track_id": None, "start": s0, "end": crash,
         "sources": {"ttc_at_start_s": at0, "b_distance_start_m": at0, "background_motion_before_px": win,
                     "background_motion_after_px": win, "slowdown_share": win},
         "measures": {"ttc_at_start_s": mb[s0]["ttc_s"], "b_distance_start_m": mb[s0]["distance_m"],
                      "background_motion_before_px": events._r(m_pre), "background_motion_after_px": events._r(m_post),
                      "slowdown_share": events._r(1 - m_post / m_pre), "duration_s": events._r((crash - s0) / config.FPS, 1),
                      "status": "exploratory"}}
    e["start_t"], e["end_t"] = events._t(e["start"], times), events._t(e["end"], times)
    return e


def _rear_sides(evs):
    """Rear camera that is not mirrored: the left of the picture is the car's right. Sides of Vehicle B and of the
    passing vehicles are turned into the car's own left/right (the recording car's own lane change is read from the
    background's rotation, which has the same sign for a front and a rear camera)."""
    flip = {"left": "right", "right": "left"}
    for e in evs:
        m = e.get("measures") or {}
        if e["type"] == "lane_change" and e["vehicle"] == "B" and m.get("direction") in flip:
            m["direction"] = flip[m["direction"]]
        if e["type"] == "overtaking" and m.get("side") in flip:
            m["side"] = flip[m["side"]]
        if e["type"] == "lane_change" and m.get("crossed_line_side") in flip:
            m["crossed_line_side"] = flip[m["crossed_line_side"]]


def analyse_video(path, accident_type=None, thumbnails=True, camera="front"):
    camera = "rear" if camera == "rear" else "front"
    t0 = time.time()
    v = video.load(path)
    frames, times, W, H = v["frames"], v["times"], v["width"], v["height"]
    tracks, classes = detect_track.track(frames)
    t_det = time.time() - t0
    flow = motion.flow_series(frames, tracks)
    meas = {tid: motion.vehicle_measures(tr, classes[tid], W, H, flow["box_flow"].get(tid)) for tid, tr in tracks.items()}
    b = events.pick_vehicle_b(tracks, W, H, len(frames))
    evs, crash = events.analyse(meas, b, flow, times, accident_type, camera=camera)
    t1 = time.time()
    lane_frames, lane_info, lane_band = {}, None, None
    try:
        lane_frames, votes, lane_band = lanes.analyse(frames, tracks, lanes.masks(frames, lanes.frames_to_check(len(frames), crash)))
        lane_info = _lane_summary(evs, votes, times)
    except Exception as exc:                       # the lane model is an extra: the analysis goes on without it
        lane_info = {"error": str(exc)[:200]}
    t_lane = time.time() - t1
    uses_lines = config.LANE_LINE_RULE != "off" or any(v.get("LANE_LINE_RULE", "off") != "off" for v in config.LANE_BY_TYPE.values())
    if lane_frames and uses_lines:
        # the lane lines need the impact frame, so the rules that use them run once the lines are known
        scene = {"b_boxes": {f: [x1 / W, y1 / H, x2 / W, y2 / H] for f, (x1, y1, x2, y2, *_) in tracks.get(b, {}).items()},
                 "lanes": {f: [{"points": [[x / W, y / H] for x, y in ln["points"]], "ego_side": ln["ego_side"]} for ln in lns]
                           for f, lns in lane_frames.items()},
                 "lane_band": None if not lane_band else [lane_band[0] / H, lane_band[1] / H]}
        evs, crash = events.analyse(meas, b, flow, times, accident_type, scene, camera=camera)
        lane_info = _lane_summary(evs, votes, times)
    if camera == "rear" and crash is not None and b is not None:
        stop = _rear_stop(frames, tracks, meas.get(b, {}), b, crash, times, evs)
        if stop:
            evs.append(stop)
            per = config.LANE_BY_TYPE.get(events.report_type(accident_type)) or {}
            if per.get("SAFE_SUDDEN_STOP", config.SAFE_SUDDEN_STOP):
                for e in evs:     # the recording car stopped and B behind could not: B's distance was not enough
                    if e["type"] == "following_distance":
                        e["measures"]["safe_distance"] = "Not maintained"
        if not config.REAR_MIRRORED:
            _rear_sides(evs)
            if lane_info and "left_line" in lane_info:
                lane_info["left_line"], lane_info["right_line"] = lane_info["right_line"], lane_info["left_line"]
        evs.sort(key=lambda e: (e["start"], e["type"] != "collision"))
    # R4 (exploratory): the front vehicle reverses into a standing recording car; added beside the other events
    # (front camera only: with the rear camera B is the vehicle behind)
    if camera == "front" and crash is not None and b is not None:
        rev = events.reversing(meas.get(b), b, motion.background_still(frames, tracks, crash - config.REVERSE_WINDOW, crash - 1),
                               crash, times)
        if rev:
            evs.append(rev)
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
        # camera chosen by the user; with "rear" Vehicle B is behind the recording car, and left/right are the car's
        # own sides (the rear picture is taken as not mirrored, config.REAR_MIRRORED)
        "camera": camera,
        "video": {"fps": config.FPS, "frames": len(frames), "duration_s": v["duration_s"],
                  "window_start_s": v["window_start_s"], "width": v.get("src_width"), "height": v.get("src_height"),
                  "source_fps": round(v.get("src_fps", 0), 2),
                  # an end card of a repost (TikTok, Instagram...) cut off before the analysis: where it started (s)
                  "end_card_s": v.get("end_card_s"),
                  # black bars cut off before the analysis: the picture's [left, top, width, height] as shares of the
                  # original frame (the boxes below are relative to that picture), or None
                  "picture": _picture(v)},
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
        # road band used for the lane lines, as shares of the image height: [top, bottom]; the bottom is where the
        # road meets the bonnet (90th percentile of the lane lines' lowest points)
        "lane_band": None if not lane_band else [round(lane_band[0] / H, 4), round(lane_band[1] / H, 4)],
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
    ap.add_argument("--camera", choices=["front", "rear"], default="front")
    ap.add_argument("--out", default="result.json")
    a = ap.parse_args()
    r = analyse_video(a.video, a.type, camera=a.camera)
    json.dump(r, open(a.out, "w"), ensure_ascii=False)
    for e in r["events"]:
        print(f"{e['start_t']:6.1f}s  {e['type']:<19} {e['vehicle']:<6} {json.dumps(e['measures'], ensure_ascii=False)}")
    print("time:", r["timing_s"])


if __name__ == "__main__":
    main()
