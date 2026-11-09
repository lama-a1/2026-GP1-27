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


def _near(meas, f, tol=3):
    ks = [k for k in meas if abs(k - f) <= tol]
    return meas[min(ks, key=lambda k: abs(k - f))] if ks else None


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


def analyse(meas, b, flow, times):
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
    m_c = mb.get(crash) or _near(mb, crash)
    m_1s = _near(mb, crash - 10)
    events.append({"type": "collision", "vehicle": "B", "track_id": b, "start": crash, "end": crash, "measures": {
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
            if ax[p] - ax[e] >= config.LANE_SHIFT_M and crash - fr[p] >= 3:
                start, end = _lane_change_bounds(mb, fr, xs, p, e, crash)
                seg = [mb[k] for k in fr if start <= k <= end]
                lat = [abs(m["lateral_speed_mps"]) for m in seg if m["lateral_speed_mps"] is not None]
                flow_dx = [m["flow_dx_px"] for m in seg if m["flow_dx_px"] is not None]
                ms, me = mb[start], mb[end] if end in mb else mb[fr[-1]]
                lc = {"type": "lane_change", "vehicle": "B", "track_id": b, "start": start, "end": end, "measures": {
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
                m_s = _near(mb, start)
                lc = {"type": "lane_change", "vehicle": "A", "track_id": None, "start": start, "end": crash, "measures": {
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
            events.append({"type": "sudden_stop", "vehicle": "B", "track_id": b, "start": s0, "end": crash, "measures": {
                "ttc_at_start_s": mb[s0]["ttc_s"],
                "min_ttc_s": _r(min(mb[k]["ttc_s"] for k in lows)),
                "closing_speed_before_mps": _r(c_pre), "closing_speed_after_mps": _r(c_post),
                "max_closing_speed_mps": _r(max(post)) if post else None,
                # how quickly the gap starts closing faster = B slowing down relative to A (m/s^2)
                "relative_deceleration_mps2": _r((c_post - c_pre) / max(dur, 0.1)) if c_pre is not None and c_post is not None else None,
                "b_distance_start_m": mb[s0]["distance_m"],
                "duration_s": _r(dur, 1),
            }})

    # 5) following distance, 1 s before the impact (or when Vehicle B finished its lane change)
    ref = lc["end"] if lc and lc["vehicle"] == "B" else crash - 10
    m = _near(mb, ref)
    if m:
        cl = _closing([x for k, x in mb.items() if ref - 5 <= k <= ref])
        c = _mean(cl)
        events.append({"type": "following_distance", "vehicle": "B", "track_id": b, "start": ref, "end": ref, "measures": {
            "b_distance_m": m["distance_m"], "b_box_height_frac": m["height_frac"],
            "closing_speed_mps": _r(c), "ttc_s": m["ttc_s"],
            # seconds until the gap closes at the current closing speed (distance / closing speed)
            "gap_closing_time_s": _r(m["distance_m"] / c) if c and c > 0.2 else None,
            "safe_distance": "Not maintained" if m["height_frac"] > config.HEADWAY_FRAC else "Maintained",
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
            events.append({"type": "overtaking", "vehicle": "B" if tid == b else "other", "track_id": tid,
                           "start": ks[0], "end": ks[-1], "measures": {
                               "side": "left" if a["centre_offset"] < 0 else "right",
                               "duration_s": _r((ks[-1] - ks[0]) / config.FPS, 1),
                               "distance_start_m": a["distance_m"], "distance_end_m": z["distance_m"],
                               "mean_rel_speed_mps": _r(rel), "mean_rel_speed_kmh": _r(rel * 3.6 if rel else None, 1),
                           }})
    for e in events:
        e["start_t"], e["end_t"] = _t(e["start"], times), _t(e["end"], times)
    events.sort(key=lambda e: (e["start"], e["type"] != "collision"))
    return events, crash


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
