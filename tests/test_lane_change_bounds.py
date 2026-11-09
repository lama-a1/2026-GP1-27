# EXP-004: boundaries of Vehicle B's lane change (start = when B starts moving in, end = in the lane or impact)
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from siyaq_cv import config, events


def b_measures(frames, lateral, edge=()):
    """Measures of Vehicle B: lateral position (m) per frame, everything else plain."""
    return {f: {"lateral_m": x, "centre_offset": x / 10, "distance_m": 8.0 - 0.1 * i, "height_frac": 0.2 + 0.005 * i,
                "ttc_s": None, "rel_speed_mps": -1.0, "lateral_speed_mps": None, "flow_dx_px": None,
                "at_edge": f in edge}
            for i, (f, x) in enumerate(zip(frames, lateral))}


def bounds(mb, crash):
    fr = sorted(mb)
    xs = np.array([mb[k]["lateral_m"] for k in fr], float)
    xs = np.array([np.median(xs[max(0, i - 2): i + 3]) for i in range(len(xs))])
    ax = np.abs(xs)
    p = max([i for i, k in enumerate(fr) if k < crash - 2 and ax[i] >= config.LANE_SIDE_M], key=lambda i: ax[i])
    after = list(range(p + 1, len(fr)))
    inside = [i for i in after if ax[i] <= config.LANE_IN_M]
    e = inside[0] if inside else min(after, key=lambda i: ax[i])
    return events._lane_change_bounds(mb, fr, xs, p, e, crash)


def test_start_is_when_b_starts_moving_in_not_when_it_first_appears():
    # B is seen from frame 10 driving straight 2.7 m to the left; it starts moving in at frame 18
    frames = list(range(10, 30))
    lateral = [-2.7] * 8 + [-2.7 + 0.2 * i for i in range(1, 13)]
    start, end = bounds(b_measures(frames, lateral), crash=29)
    assert 16 <= start <= 19                          # the old rule gave frame 10 (where B was widest)


def test_lane_change_still_going_when_b_is_lost_ends_at_the_impact():
    # B moves in steadily and is lost at frame 24 (too close for the detector); the impact is at frame 27
    frames = list(range(10, 25))
    lateral = [-2.8 + 0.12 * i for i in range(len(frames))]
    start, end = bounds(b_measures(frames, lateral), crash=27)
    assert end == 27                                  # the old rule ended at the last tracked frame (24)


def test_track_lost_long_before_the_impact_is_not_extended():
    frames = list(range(0, 15))
    lateral = [-2.8 + 0.12 * i for i in range(len(frames))]
    gap = int(config.FPS / 30.0 * config.BT_TRACK_BUFFER)
    start, end = bounds(b_measures(frames, lateral), crash=14 + gap + 5)
    assert end == 14


def test_boxes_cut_by_the_image_side_are_not_used_for_the_speed():
    # frames 10-13: B half outside the picture, its box centre jumps; the real movement starts at frame 18
    frames = list(range(10, 30))
    lateral = [-3.6, -3.2, -2.9, -2.7] + [-2.7] * 4 + [-2.7 + 0.2 * i for i in range(1, 13)]
    start, _ = bounds(b_measures(frames, lateral, edge=range(10, 14)), crash=29)
    assert start >= 16
