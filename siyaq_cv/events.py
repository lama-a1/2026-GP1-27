"""Traffic events detected from the tracks and the optical flow, each with the measures that support it.

Sprint 2 scope: WHAT happened and the numbers behind it. No traffic rule and no fault percentage here
(those are Sprint 3). Vehicle A = the recording car, Vehicle B = the other vehicle in the collision.
"""
import numpy as np

from . import config


def _r(x, d=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), d)


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return float(np.mean(vals)) if vals else None


def _near_f(meas, f, tol=3):
    """(measures, frame) of the tracked frame nearest to f, within tol frames; (None, None) if there is none."""
    ks = [k for k in meas if abs(k - f) <= tol]
    if not ks:
        return None, None
    k = min(ks, key=lambda k: abs(k - f))
    return meas[k], k


def _near(meas, f, tol=3):
    return _near_f(meas, f, tol)[0]


# Where each number of an event comes from (event["sources"][measure]):
#   observed  - read from Vehicle B's tracked box (or the image) in the very frame the number is reported for
#   estimated - computed over a window of observed frames (a mean, a minimum, a rate, a smoothed position)
#   inferred  - reported for a frame where the number was not measured: carried over from the nearest tracked
#               frame (e.g. B is no longer tracked at the impact), or a moment deduced from another event
# The values themselves are unchanged; this only says how far each one can be trusted at the time shown.
def _src_at(ref, src, times):
    if src is None:
        return None
    d = {"basis": "observed" if src == ref else "inferred", "frame": int(src), "time_s": _t(src, times)}
    if src != ref:
        d["reported_for_frame"], d["reported_for_s"] = int(ref), _t(ref, times)
    return d


def _src_win(frames, times, inferred_from=None):
    frames = sorted(int(f) for f in frames)
    if not frames:
        return None
    d = {"basis": "estimated", "frames": [frames[0], frames[-1]], "time_s": [_t(frames[0], times), _t(frames[-1], times)]}
    if inferred_from is not None:              # the window uses a number carried over from another frame
        d["basis"], d["uses_frame"] = "inferred", int(inferred_from)
    return d


def _safety_ttc(m, closing):
    """Seconds until contact with Vehicle B: the box-scale TTC (Dagan et al. 2004) or, without it, distance / closing
    speed. None when the gap is not closing (then the distance is kept)."""
    if m.get("ttc_s") is not None and m["ttc_s"] > 0:
        return m["ttc_s"]
    if closing and closing > 0.2 and m.get("distance_m"):
        return _r(m["distance_m"] / closing)
    return None


def _line_x(points, y):
    """x of a straight lane line (least-squares fit of its points) at height y; all values are shares of the image."""
    ys = np.array([p[1] for p in points], float)
    xs = np.array([p[0] for p in points], float)
    if len(points) < 2 or np.ptp(ys) < 1e-6:
        return None
    a, c = np.polyfit(ys, xs, 1)
    return float(a * y + c)


def _box_near(boxes, f, tol=1):
    ks = [k for k in boxes if abs(k - f) <= tol]
    return boxes[min(ks, key=lambda k: abs(k - f))] if ks else None


def b_lane_states(scene, crash):
    """Per lane-analysed frame up to the impact: is the bottom centre of Vehicle B's box (where it touches the road)
    inside the recording car's lane, between its two lane lines? [(frame, inside)] - frames without a usable line on
    B's side are left out. A lane change is the crossing of the lane marking (Krajewski et al. 2018)."""
    out = []
    boxes, lanes = (scene or {}).get("b_boxes") or {}, (scene or {}).get("lanes") or {}
    for f in sorted(lanes):
        if crash is not None and f > crash:
            continue
        box = _box_near(boxes, f)
        if box is None:
            continue
        xc, yb = (box[0] + box[2]) / 2, box[3]
        ego = {ln["ego_side"]: ln for ln in lanes[f] if ln.get("ego_side") in ("left", "right")}
        xl = _line_x(ego["left"]["points"], yb) if "left" in ego else None
        xr = _line_x(ego["right"]["points"], yb) if "right" in ego else None
        if (xc < 0.5 and xl is None) or (xc >= 0.5 and xr is None):
            continue
        out.append((f, (xl is None or xc > xl) and (xr is None or xc < xr)))
    return out


def b_line_crossing(states):
    """(last frame outside, first frame inside) when B is outside the lane and then stays inside for at least
    LANE_LINE_MIN_IN analysed frames; None otherwise."""
    for i, (f, inside) in enumerate(states):
        if inside and i > 0 and not states[i - 1][1]:
            run = [s_ for s_ in states[i:i + config.LANE_LINE_MIN_IN]]
            if len(run) >= config.LANE_LINE_MIN_IN and all(x[1] for x in run):
                return states[i - 1][0], f
    return None


def pick_vehicle_b(tracks, width, height, n):
    """Vehicle B = the track that comes closest to the recording car in front of it, late in the clip."""
    best, best_s = None, 0
    for tid, boxes in tracks.items():
        sc = 0
        for f, (x1, y1, x2, y2, *_) in boxes.items():
            hfrac = (y2 - y1) / height
            cx = abs((x1 + x2) / 2 - width / 2) / (width / 2)
            sc = max(sc, hfrac * (1.2 - min(cx, 1.0)) * (0.5 + 0.5 * f / max(1, n - 1)))
        if sc > best_s:
            best, best_s = tid, sc
    return best


def collision(meas_b, jolt, n):
    """Impact = Vehicle B is at its closest (largest box) while the image jolts."""
    if not meas_b:
        return None, None
    hmax = max(m["height_frac"] for m in meas_b.values())
    j = np.array(jolt)
    jz = (j - np.median(j)) / (np.median(np.abs(j - np.median(j))) + 1e-6)
    frames = sorted(meas_b)
    best, best_s = None, -1e9
    for f in range(n):
        m = meas_b.get(f) or _near(meas_b, f)
        if m is None:
            continue
        size = m["height_frac"] / hmax
        # the impact is where B is (almost) at its closest. 0.6 let in the moment B cuts in, already near,
        # when the impact itself barely shakes the image (SIYAQ-BUG-001: chosen 2.7 s, real contact 5.0 s)
        if size < config.COLLISION_SIZE_MIN:
            continue
        # no bonus for the last frames of B's track: in a video that goes on after the impact the track can end
        # later (ByteTrack keeps a vehicle through low-score and missed frames), and a later jolt such as B
        # hitting the kerb then won (SIYAQ-BUG-001: chosen 6.2 s).
        s = 2.0 * size + 0.35 * min(jz[f], 8)
        if s > best_s:
            best, best_s = f, s
    if best is None:
        best = max(frames, key=lambda k: meas_b[k]["height_frac"])
    return best, float(jz[best])


def _t(f, times):
    return times[min(max(int(f), 0), len(times) - 1)]


def _closing(ms):
    return [-m["rel_speed_mps"] for m in ms if m["rel_speed_mps"] is not None]


def _lane_change_bounds(mb, fr, xs, p, e, crash):
    """Start and end frame of Vehicle B's lane change (EXP-004).

    Start - when B starts moving sideways towards the recording car's lane, not where B is widest:
      the inward speed is the change of B's smoothed sideways position towards the lane over
      +-LANE_VEL_HALF frames (frames where B's box touches the side of the image are left out: part of B
      is outside the picture there and its centre is biased). From the frame of the fastest inward movement
      between p (widest) and e (closest to the lane), the start goes back while the inward speed stays at
      or above LANE_ONSET_MPS. Without a usable speed (short or edge-cut tracks) the start stays at p.
    End - where B is closest to (or inside) the lane, as before; but if that is B's last tracked frame,
      B is still outside the lane, and the impact follows within the tracker's buffer (the time ByteTrack
      still looks for a lost vehicle), the lane change was cut by the impact and ends there.
    """
    side = np.sign(xs[p]) or 1.0
    k = config.LANE_VEL_HALF
    ok = [not mb[f].get("at_edge", False) for f in fr]
    vin = [None] * len(fr)
    for i in range(len(fr)):
        a, z = max(0, i - k), min(len(fr) - 1, i + k)
        while a < i and not ok[a]:
            a += 1
        while z > i and not ok[z]:
            z -= 1
        if z - a >= 2 and fr[z] - fr[a] <= 3 * k:
            vin[i] = -side * (xs[z] - xs[a]) / ((fr[z] - fr[a]) / config.FPS)

    start = fr[p]
    core = [i for i in range(p, e + 1) if vin[i] is not None]
    if core:
        m = max(core, key=lambda i: vin[i])
        if vin[m] >= config.LANE_ONSET_MPS:
            s = m
            while s - 1 >= p and vin[s - 1] is not None and vin[s - 1] >= config.LANE_ONSET_MPS and fr[s] - fr[s - 1] <= 2:
                s -= 1
            start = fr[s]

    end = fr[e]
    buffer = int(config.FPS / 30.0 * config.BT_TRACK_BUFFER)
    if e == len(fr) - 1 and abs(xs[e]) > config.LANE_IN_M and 0 < crash - fr[e] <= buffer:
        end = crash
    return start, end


LANE_KEYS = ("LANE_SIDE_M", "LANE_SHIFT_M", "LANE_IN_M", "LANE_ONSET_MPS", "EGO_YAW_DEG", "LANE_LINE_RULE")


def report_type(accident_type):
    """REAR_END / LANE_CHANGE from the report's accident type (also accepts the dataset's Rear-end / Lane-change)."""
    t = str(accident_type or "").upper().replace("-", "_").replace(" ", "_")
    return t if t in ("REAR_END", "LANE_CHANGE") else None


def analyse(meas, b, flow, times, accident_type=None, scene=None):
    """Events of one clip. The lane-change thresholds depend on the accident type in the user's report
    (config.LANE_BY_TYPE): a lane-change report makes a lane change far more likely than a rear-end report, so the
    evidence needed differs (thresholds chosen per report type by tools/cross_validate.py)."""
    t = report_type(accident_type)
    per = config.LANE_BY_TYPE.get(t) if t else None
    if not per:
        return _analyse(meas, b, flow, times, scene)
    saved = {k: getattr(config, k) for k in LANE_KEYS}
    try:
        for k in LANE_KEYS:
            setattr(config, k, per[k])
        return _analyse(meas, b, flow, times, scene)
    finally:
        for k, v in saved.items():
            setattr(config, k, v)


def _analyse(meas, b, flow, times, scene=None):
    n = len(times)
    mb = meas.get(b, {}) if b is not None else {}
    events = []
    crash, jz = collision(mb, flow["jolt"], n)
    if crash is None:
        return events, None
    yaw = flow["yaw_rate"]

    # 1) collision
    before = [mb[k] for k in sorted(mb) if crash - 10 <= k < crash]
    ttcs = [m["ttc_s"] for m in before if m["ttc_s"] is not None]
    closing = _closing(before)
    m_c, f_c = (mb[crash], crash) if crash in mb else _near_f(mb, crash)
    m_1s, f_1s = _near_f(mb, crash - 10)
    at_c, win = _src_at(crash, f_c, times), lambda fs: _src_win(fs, times)
    seen = {"basis": "observed", "frame": int(crash), "time_s": _t(crash, times)}
    events.append({"type": "collision", "vehicle": "B", "track_id": b, "start": crash, "end": crash,
                   "b_last_tracked_frame": max(mb), "b_last_tracked_s": _t(max(mb), times), "sources": {
        "time_s": seen, "jolt_score": seen,
        "b_box_height_frac": at_c, "b_distance_at_impact_m": at_c, "b_lateral_at_impact_m": at_c,
        "b_distance_1s_before_m": _src_at(crash - 10, f_1s, times),
        "closing_speed_last_1s_mps": win([k for k in mb if crash - 10 <= k < crash and mb[k]["rel_speed_mps"] is not None]),
        "closing_speed_last_1s_kmh": win([k for k in mb if crash - 10 <= k < crash and mb[k]["rel_speed_mps"] is not None]),
        "min_ttc_last_1s_s": win([k for k in mb if crash - 10 <= k < crash and mb[k]["ttc_s"] is not None]),
        "a_heading_change_last_1s_deg": win(range(max(0, crash - 10), crash)),
    }, "measures": {
        "time_s": _t(crash, times),
        "jolt_score": _r(jz, 1),
        "b_box_height_frac": m_c and m_c["height_frac"],
        "b_distance_at_impact_m": m_c and m_c["distance_m"],
        "b_distance_1s_before_m": m_1s and m_1s["distance_m"],
        "closing_speed_last_1s_mps": _r(_mean(closing)),
        "closing_speed_last_1s_kmh": _r(_mean(closing) * 3.6 if closing else None, 1),
        "min_ttc_last_1s_s": _r(min(ttcs)) if ttcs else None,
        "b_lateral_at_impact_m": m_c and m_c["lateral_m"],
        "a_heading_change_last_1s_deg": _r(sum(yaw[max(0, crash - 10):crash]) / config.FPS, 1),
    }})

    # 2) lane change of Vehicle B: its sideways distance on the road (metres, not image position - a car in the
    #    next lane drifts outwards in the image as it gets closer) shrinks from a neighbouring lane towards ours
    lc = None
    fr = [k for k in sorted(mb) if k <= crash]
    if len(fr) >= 4:
        xs = np.array([mb[k]["lateral_m"] for k in fr], float)
        xs = np.array([np.median(xs[max(0, i - 2): i + 3]) for i in range(len(xs))])
        ax = np.abs(xs)
        cand = [i for i, k in enumerate(fr) if k < crash - 2 and ax[i] >= config.LANE_SIDE_M]
        if cand:
            p = max(cand, key=lambda i: ax[i])
            after = list(range(p + 1, len(fr)))
            inside = [i for i in after if ax[i] <= config.LANE_IN_M and np.sign(xs[i]) in (np.sign(xs[p]), 0)]
            e = inside[0] if inside else (min(after, key=lambda i: ax[i]) if after else p)
            gate_ok = True
            if config.LANE_DETECT_MPS is not None:
                # optional extra check: B must also move towards the lane fast enough at some point between its
                # outermost position and the end (lateral-speed criterion of lane-change detectors, Geurts et al. 2022;
                # a 3.6 m change in 5-6 s averages about 0.65 m/s, Ramanujam 2007)
                side_p = np.sign(xs[p]) or 1.0
                vin = [-side_p * mb[fr[i]]["lateral_speed_mps"] for i in range(p, e + 1)
                       if mb[fr[i]].get("lateral_speed_mps") is not None and not mb[fr[i]].get("at_edge", False)]
                gate_ok = bool(vin) and max(vin) >= config.LANE_DETECT_MPS
            if gate_ok and ax[p] - ax[e] >= config.LANE_SHIFT_M and crash - fr[p] >= 3:
                start, end = _lane_change_bounds(mb, fr, xs, p, e, crash)
                seg = [mb[k] for k in fr if start <= k <= end]
                lat = [abs(m["lateral_speed_mps"]) for m in seg if m["lateral_speed_mps"] is not None]
                flow_dx = [m["flow_dx_px"] for m in seg if m["flow_dx_px"] is not None]
                f_me = end if end in mb else fr[-1]
                ms, me = mb[start], mb[f_me]
                end_src = ({"basis": "observed", "frame": int(end), "time_s": _t(end, times), "from": "track"} if end in mb else
                           {"basis": "inferred", "frame": int(end), "time_s": _t(end, times), "from": "collision",
                            "last_tracked_frame": int(fr[-1]), "last_tracked_s": _t(fr[-1], times)})

                def smooth(i):              # the sideways position is a median over +-2 tracked frames
                    return _src_win(fr[max(0, i - 2): i + 3], times)
                i_s = fr.index(start)
                at_s, at_e = _src_at(start, start, times), _src_at(end, f_me, times)
                segf = [k for k in fr if start <= k <= end]
                lc = {"type": "lane_change", "vehicle": "B", "track_id": b, "start": start, "end": end, "sources": {
                    "event_start": {"basis": "observed", "frame": int(start), "time_s": _t(start, times), "from": "track"},
                    "event_end": end_src,
                    "duration_s": dict(end_src, basis="inferred") if end_src["basis"] == "inferred" else
                                  _src_win([start, end], times),
                    "offset_start": at_s, "b_distance_start_m": at_s,
                    "offset_end": at_e, "b_distance_end_m": at_e,
                    "lateral_start_m": smooth(i_s),
                    "lateral_end_m": smooth(fr.index(end)) if end in fr else
                                     dict(_src_win(fr[-3:], times), basis="inferred", uses_frame=int(fr[-1]),
                                          reported_for_frame=int(end), reported_for_s=_t(end, times)),
                    "lateral_shift_m": _src_win([fr[p], fr[e]], times),
                    "max_lateral_speed_mps": _src_win([k for k in segf if mb[k]["lateral_speed_mps"] is not None], times),
                    "mean_box_flow_dx_px": _src_win([k for k in segf if mb[k]["flow_dx_px"] is not None], times),
                    "seconds_before_collision": {"basis": "observed", "frames": [int(start), int(crash)],
                                                 "time_s": [_t(start, times), _t(crash, times)]},
                }, "measures": {
                    "direction": "left" if xs[p] > 0 else "right",
                    "duration_s": _r((end - start) / config.FPS, 1),
                    "offset_start": ms["centre_offset"], "offset_end": me["centre_offset"],
                    "lateral_start_m": _r(xs[fr.index(start)]) if start in fr else _r(xs[p]),
                    "lateral_end_m": _r(xs[fr.index(end)]) if end in fr else _r(xs[-1]),
                    "lateral_shift_m": _r(ax[p] - ax[e]),
                    "max_lateral_speed_mps": _r(max(lat)) if lat else None,
                    "mean_box_flow_dx_px": _r(_mean(flow_dx), 1),
                    "b_distance_start_m": ms["distance_m"], "b_distance_end_m": me["distance_m"],
                    "seconds_before_collision": _r((crash - start) / config.FPS, 1),
                }}
    # 2b) optional: Vehicle B's lane change from the lane lines (B's road contact point crosses the lane marking)
    if config.LANE_LINE_RULE != "off" and scene:
        states = b_lane_states(scene, crash)
        if len(states) >= config.LANE_LINE_MIN_FRAMES:
            cross = b_line_crossing(states)
            if lc is not None and cross is None and config.LANE_LINE_RULE in ("and", "line"):
                lc = None                                   # the lines show that B did not enter the lane
            elif lc is None and cross is not None and config.LANE_LINE_RULE in ("or", "line"):
                s0, e0 = cross
                box = _box_near(scene["b_boxes"], e0) or [0.5, 0, 0.5, 0]
                lc = {"type": "lane_change", "vehicle": "B", "track_id": b, "start": int(s0), "end": int(e0), "sources": {
                    "event_start": {"basis": "observed", "frame": int(s0), "time_s": _t(s0, times), "from": "lane lines"},
                    "event_end": {"basis": "observed", "frame": int(e0), "time_s": _t(e0, times), "from": "lane lines"},
                }, "measures": {"direction": "right" if (box[0] + box[2]) / 2 < 0.5 else "left",
                                "duration_s": _r((e0 - s0) / config.FPS, 1), "detected_by": "lane-line crossing",
                                "seconds_before_collision": _r((crash - s0) / config.FPS, 1)}}
    # 3) lane change of the recording car (heading change from the background optical flow)
    if lc is None:
        lo = max(1, crash - 30)
        per_frame = np.array(yaw[lo:crash]) / config.FPS          # degrees per frame
        if per_frame.size >= 5:
            total = float(per_frame.sum())
            if abs(total) >= config.EGO_YAW_DEG:
                sign = np.sign(total)
                moving = np.where(np.sign(per_frame) == sign)[0]
                start = lo + int(moving[0]) if moving.size else lo
                m_s, f_s = _near_f(mb, start)
                w = _src_win(range(lo, crash), times)
                lc = {"type": "lane_change", "vehicle": "A", "track_id": None, "start": start, "end": crash, "sources": {
                    "event_end": {"basis": "inferred", "frame": int(crash), "time_s": _t(crash, times), "from": "collision"},
                    "duration_s": w, "heading_change_deg": w, "max_heading_rate_deg_s": w, "background_shift_px": w,
                    "b_lateral_start_m": _src_at(start, f_s, times),
                    "seconds_before_collision": {"basis": "observed", "frames": [int(start), int(crash)],
                                                 "time_s": [_t(start, times), _t(crash, times)]},
                }, "measures": {
                    # the background flowing right means the recording car turns left
                    "direction": "left" if sign > 0 else "right",
                    "duration_s": _r((crash - start) / config.FPS, 1),
                    "heading_change_deg": _r(abs(total), 1),
                    "max_heading_rate_deg_s": _r(float(np.max(np.abs(per_frame))) * config.FPS, 1),
                    "background_shift_px": _r(float(np.sum(flow["ego_dx"][lo:crash])), 0),
                    "b_lateral_start_m": m_s and m_s["lateral_m"],
                    "seconds_before_collision": _r((crash - start) / config.FPS, 1),
                }}
    if lc:
        events.append(lc)

    # 4) sudden stop / hard braking of Vehicle B ahead (the time-to-collision collapses)
    if not (lc and lc["vehicle"] == "B"):
        ahead = [k for k in sorted(mb) if k < crash and abs(mb[k]["centre_offset"]) <= 0.15]
        lows = [k for k in ahead if mb[k]["ttc_s"] is not None and mb[k]["ttc_s"] < config.TTC_SUDDEN_STOP_S]
        if lows:
            s0 = lows[0]
            pre = _closing([mb[k] for k in ahead if s0 - 10 <= k < s0])
            post = _closing([mb[k] for k in ahead if k >= s0])
            dur = (crash - s0) / config.FPS
            c_pre, c_post = _mean(pre), _mean(post)
            at0 = _src_at(s0, s0, times)
            w_pre = _src_win([k for k in ahead if s0 - 10 <= k < s0 and mb[k]["rel_speed_mps"] is not None], times)
            w_post = _src_win([k for k in ahead if k >= s0 and mb[k]["rel_speed_mps"] is not None], times)
            events.append({"type": "sudden_stop", "vehicle": "B", "track_id": b, "start": s0, "end": crash, "sources": {
                "ttc_at_start_s": at0, "b_distance_start_m": at0, "min_ttc_s": _src_win(lows, times),
                "closing_speed_before_mps": w_pre, "closing_speed_after_mps": w_post, "max_closing_speed_mps": w_post,
                "relative_deceleration_mps2": _src_win([k for k in ahead if s0 - 10 <= k], times),
                "duration_s": {"basis": "observed", "frames": [int(s0), int(crash)], "time_s": [_t(s0, times), _t(crash, times)]},
            }, "measures": {
                "ttc_at_start_s": mb[s0]["ttc_s"],
                "min_ttc_s": _r(min(mb[k]["ttc_s"] for k in lows)),
                "closing_speed_before_mps": _r(c_pre), "closing_speed_after_mps": _r(c_post),
                "max_closing_speed_mps": _r(max(post)) if post else None,
                # how quickly the gap starts closing faster = B slowing down relative to A (m/s^2)
                "relative_deceleration_mps2": _r((c_post - c_pre) / max(dur, 0.1)) if c_pre is not None and c_post is not None else None,
                "b_distance_start_m": mb[s0]["distance_m"],
                "duration_s": _r(dur, 1),
            }})

    # 5) following distance, SAFE_REF_S before the impact (or when Vehicle B finished its lane change),
    #    judged by the time-to-collision with Vehicle B (see config.SAFE_TTC_S)
    ref_frames = int(round(config.SAFE_REF_S * config.FPS))
    ref = lc["end"] if lc and lc["vehicle"] == "B" else crash - ref_frames
    m, f_m = _near_f(mb, ref)
    if m:
        cl = _closing([x for k, x in mb.items() if ref - 5 <= k <= ref])
        c = _mean(cl)
        at_m = _src_at(ref, f_m, times)
        w_c = _src_win([k for k in mb if ref - 5 <= k <= ref and mb[k]["rel_speed_mps"] is not None], times)
        lc_end = lc["sources"]["event_end"] if lc and lc["vehicle"] == "B" else None
        moment = (dict(lc_end, from_event="lane_change_end") if lc_end else
                  {"basis": "observed", "frame": int(ref), "time_s": _t(ref, times),
                   "from": f"{config.SAFE_REF_S:g} s before the collision"})
        safety_ttc = _safety_ttc(m, c)
        if config.SAFE_TTC_MODE == "min_before_ref":
            # minimum TTC of the approach up to the reference moment (van der Horst 1991: an interaction is critical
            # when its minimum TTC falls below the threshold)
            low = [mb[k]["ttc_s"] for k in mb if k <= ref and mb[k].get("ttc_s") is not None and mb[k]["ttc_s"] > 0]
            if low:
                safety_ttc = _r(min(low + ([safety_ttc] if safety_ttc is not None else [])))
        sd_src = at_m if m.get("ttc_s") is not None and m["ttc_s"] > 0 else w_c
        events.append({"type": "following_distance", "vehicle": "B", "track_id": b, "start": ref, "end": ref, "sources": {
            "safety_ttc_s": sd_src, "safe_distance": sd_src,
            "event_start": moment,
            "b_distance_m": at_m, "b_box_height_frac": at_m, "ttc_s": at_m,
            "closing_speed_mps": w_c,
            "gap_closing_time_s": None if w_c is None else
                                  _src_win(list(range(w_c["frames"][0], w_c["frames"][1] + 1)) + [f_m], times,
                                           inferred_from=f_m if f_m != ref else None),
        }, "measures": {
            "b_distance_m": m["distance_m"], "b_box_height_frac": m["height_frac"],
            "closing_speed_mps": _r(c), "ttc_s": m["ttc_s"],
            # seconds until the gap closes at the current closing speed (distance / closing speed)
            "gap_closing_time_s": _r(m["distance_m"] / c) if c and c > 0.2 else None,
            "safety_ttc_s": safety_ttc,
            "safe_distance_ttc_threshold_s": config.SAFE_TTC_S,
            "safe_distance": "Not maintained" if safety_ttc is not None and safety_ttc < config.SAFE_TTC_S else "Maintained",
        }})

    # 6) overtaking: a vehicle passes the recording car on the side (comes from beside it and pulls ahead)
    for tid, mt in meas.items():
        ks = [k for k in sorted(mt) if k <= crash]
        if len(ks) < config.OVERTAKE_MIN_FRAMES:
            continue
        a, z = mt[ks[0]], mt[ks[-1]]
        if (abs(a["centre_offset"]) >= 0.25 and a["height_frac"] >= 0.12 and z["distance_m"] > a["distance_m"] * 1.5
                and abs(z["centre_offset"]) < abs(a["centre_offset"])):
            rel = _mean([mt[k]["rel_speed_mps"] for k in ks])
            a0, z0 = _src_at(ks[0], ks[0], times), _src_at(ks[-1], ks[-1], times)
            wr = _src_win([k for k in ks if mt[k]["rel_speed_mps"] is not None], times)
            events.append({"type": "overtaking", "vehicle": "B" if tid == b else "other", "track_id": tid,
                           "start": ks[0], "end": ks[-1], "sources": {
                               "side": a0, "duration_s": _src_win(ks, times), "distance_start_m": a0, "distance_end_m": z0,
                               "mean_rel_speed_mps": wr, "mean_rel_speed_kmh": wr,
                           }, "measures": {
                               "side": "left" if a["centre_offset"] < 0 else "right",
                               "duration_s": _r((ks[-1] - ks[0]) / config.FPS, 1),
                               "distance_start_m": a["distance_m"], "distance_end_m": z["distance_m"],
                               "mean_rel_speed_mps": _r(rel), "mean_rel_speed_kmh": _r(rel * 3.6 if rel else None, 1),
                           }})
    for e in events:
        e["start_t"], e["end_t"] = _t(e["start"], times), _t(e["end"], times)
    events.sort(key=lambda e: (e["start"], e["type"] != "collision"))
    return events, crash


def reversing(mb, b, still, crash, times):
    """Front vehicle B reversing into the recording car: the background stands still (the recording car is not
    moving) while B comes closer just before the impact. Exploratory rule for R4 (see config.REVERSE_*)."""
    if b is None or crash is None or not mb or len(still) < config.REVERSE_WINDOW // 2:
        return None
    moving = float(np.median(list(still.values())))
    ks = [k for k in sorted(mb) if crash - config.REVERSE_WINDOW <= k <= crash]
    if moving > config.STILL_PX or len(ks) < 3:
        return None
    d0, d1 = mb[ks[0]]["distance_m"], mb[ks[-1]]["distance_m"]
    if d0 is None or d1 is None or d0 - d1 < config.REVERSE_CLOSE_M:
        return None
    win = {"basis": "estimated", "frames": [ks[0], ks[-1]], "time_s": [_t(ks[0], times), _t(ks[-1], times)]}
    e = {"type": "reversing", "vehicle": "B", "track_id": b, "start": ks[0], "end": crash,
         "sources": {k: win for k in ("background_motion_px", "b_distance_start_m", "b_distance_end_m", "closing_m")},
         "measures": {"background_motion_px": _r(moving, 2), "b_distance_start_m": _r(d0), "b_distance_end_m": _r(d1),
                      "closing_m": _r(d0 - d1)}}
    e["start_t"], e["end_t"] = _t(e["start"], times), _t(e["end"], times)
    return e


def behaviour(mt, cls):
    """Movement summary of one vehicle over the clip (driving behaviour, no judgement)."""
    ks = sorted(mt)
    a, z = mt[ks[0]], mt[ks[-1]]
    rel = _mean([mt[k]["rel_speed_mps"] for k in ks])
    lat = z["lateral_m"] - a["lateral_m"]
    return {"class": cls, "frames": len(ks), "first_frame": ks[0], "last_frame": ks[-1],
            "min_distance_m": _r(min(mt[k]["distance_m"] for k in ks)),
            "mean_distance_m": _r(_mean([mt[k]["distance_m"] for k in ks])),
            "mean_rel_speed_mps": _r(rel), "lateral_change_m": _r(lat),
            "longitudinal": None if rel is None else ("approaching" if rel < -0.5 else "moving away" if rel > 0.5 else "steady gap"),
            "lateral": "moving left" if lat < -0.8 else "moving right" if lat > 0.8 else "same position"}
