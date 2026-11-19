# Safe following distance is judged by the time-to-collision with Vehicle B (SAFE_TTC_S), SAFE_REF_S before the
# impact - not by the size of B's box. Time headway (the research measure) needs the recording car's speed.
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH', str(Path(tempfile.gettempdir()) / ('siyaq_test_' + str(os.getpid()) + '.db')))
os.environ.setdefault('SECRET_KEY', 'test-only-secret')
from siyaq_cv import config, events

N, B, CRASH = 40, 3, 30


def scene(ttc):
    """B ahead in our lane, getting closer with the given TTC from frame 5; the image jolts at CRASH."""
    mb = {}
    for f in range(0, CRASH + 1):
        h = 0.10 + 0.004 * f
        mb[f] = {"lateral_m": 0.1, "centre_offset": 0.01, "distance_m": round(1.55 / h * 0.5, 2), "height_frac": h,
                 "ttc_s": ttc if f >= 5 else None, "rel_speed_mps": -1.0 if f >= 5 else None,
                 "lateral_speed_mps": 0.0, "flow_dx_px": 0.0, "at_edge": False}
    jolt = [1.0] * N
    jolt[CRASH] = 12.0
    flow = {"jolt": jolt, "yaw_rate": [0.0] * N, "ego_dx": [0.0] * N}
    evs, c = events.analyse({B: mb}, B, flow, [round(f / 10, 1) for f in range(N)])
    return {e["type"]: e for e in evs}, c


def test_small_ttc_before_the_impact_is_not_maintained():
    ev, crash = scene(ttc=config.SAFE_TTC_S - 0.5)
    fd = ev["following_distance"]["measures"]
    assert fd["safe_distance"] == "Not maintained"
    assert fd["safety_ttc_s"] < fd["safe_distance_ttc_threshold_s"] == config.SAFE_TTC_S


def test_large_ttc_is_maintained_and_the_moment_follows_safe_ref_s():
    ev, crash = scene(ttc=config.SAFE_TTC_S + 3)
    fd = ev["following_distance"]
    assert fd["measures"]["safe_distance"] == "Maintained"
    if fd["sources"]["event_start"].get("from_event") is None:
        assert fd["start"] == crash - int(round(config.SAFE_REF_S * config.FPS))


def test_every_tuned_threshold_has_candidates_and_a_config_value():
    from siyaq_cv.threshold_grid import GRID, STAGES
    for k, vals in GRID.items():
        assert hasattr(config, k) and len(vals) >= 2
        if all(isinstance(v, (int, float)) for v in vals):          # numeric candidates in order; rule options keep
            assert vals == sorted(vals)                             # the original rule first
        else:
            assert vals[0] == 'off'
    assert {k for keys, _ in STAGES for k in keys} == set(GRID)
    assert not hasattr(config, "HEADWAY_FRAC")
