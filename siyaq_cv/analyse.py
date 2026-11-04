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

from . import config, detect_track, events, motion, video

def _thumb(frame, tracks, f, highlight, width=480):
    im = frame.copy()
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
    if thumbnails:
        for e in evs:
            e["thumbnail_jpeg"] = _thumb(frames[e["start"]], tracks, e["start"], b if e["vehicle"] == "B" else e.get("track_id"))
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
        "timing_s": {"detection_tracking": round(t_det, 1), "total": round(time.time() - t0, 1)},
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
