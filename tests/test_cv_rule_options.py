# Rule options chosen by cross-validation (siyaq_cv/threshold_grid.py): impact after Vehicle B is lost, lane change
# inferred from the report type, end of B's lane change at the impact, following distance by DRAC, sudden stop.
import os, sys, tempfile
from contextlib import contextmanager
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH', str(Path(tempfile.gettempdir()) / ('siyaq_test_' + str(os.getpid()) + '.db')))
os.environ.setdefault('SECRET_KEY', 'test-only-secret')
from siyaq_cv import config, events

N, B, CRASH = 40, 3, 30


@contextmanager
def settings(**kw):
    saved = {k: getattr(config, k) for k in kw}
    saved_type = config.LANE_BY_TYPE
    try:
        config.LANE_BY_TYPE = {}
        for k, v in kw.items():
            setattr(config, k, v)
        yield
    finally:
        config.LANE_BY_TYPE = saved_type
        for k, v in saved.items():
            setattr(config, k, v)


def run(mb, accident_type=None):
    jolt = [1.0] * N
    jolt[CRASH] = 12.0
    flow = {"jolt": jolt, "yaw_rate": [0.0] * N, "ego_dx": [0.0] * N}
    evs, c = events.analyse({B: mb}, B, flow, [round(f / 10, 1) for f in range(N)], accident_type)
    return {e["type"]: e for e in evs}, c


def ahead(ttc=None, closing=1.0, last=CRASH):
    """B straight ahead in our lane, getting closer; tracked up to frame `last`."""
    mb = {}
    for f in range(0, last + 1):
        h = 0.10 + 0.004 * f
        mb[f] = {"lateral_m": 0.1, "centre_offset": 0.01, "distance_m": round(1.55 / h * 0.5, 2), "height_frac": h,
                 "ttc_s": ttc if f >= 5 else None, "rel_speed_mps": -closing if f >= 5 else None,
                 "lateral_speed_mps": 0.0, "flow_dx_px": 0.0, "at_edge": False}
    return mb


def test_impact_can_follow_a_lost_vehicle():
    mb = {f: {"height_frac": 0.2 + 0.02 * f} for f in range(15)}      # B grows, then is lost at frame 14
    jolt = [1.0] * 30
    jolt[18] = 40.0                                                     # the impact jolt 4 frames later
    with settings(COLLISION_LOST_WIN=0):
        assert events.collision(mb, jolt, 30)[0] <= 17
    with settings(COLLISION_LOST_WIN=5):
        assert events.collision(mb, jolt, 30)[0] == 18


def test_lane_change_inferred_from_the_report_is_marked_and_changes_nothing_else():
    with settings(LANE_FALLBACK_S=0.0, EGO_YAW_DEG=40.0):
        before, _ = run(ahead(ttc=8.0))
    with settings(LANE_FALLBACK_S=1.0, EGO_YAW_DEG=40.0):
        ev, crash = run(ahead(ttc=8.0))
    lc = ev["lane_change"]
    assert lc["vehicle"] == "B" and lc["start"] == crash - 10 and lc["end"] == crash
    assert lc["sources"]["event_start"]["basis"] == "inferred" and "report" in lc["measures"]["detected_by"]
    assert "lane_change" not in before
    assert ev["following_distance"]["start"] == before["following_distance"]["start"]
    assert ev["following_distance"]["measures"]["safe_distance"] == before["following_distance"]["measures"]["safe_distance"]


def test_following_distance_by_drac():
    mb = ahead(ttc=None, closing=6.0)                    # no box-scale TTC; the gap closes fast
    with settings(SAFE_RULE="drac", SAFE_DRAC_MPS2=2.0, SAFE_SUDDEN_STOP=False, SAFE_TTC_S=0.1):
        fd = run(mb)[0]["following_distance"]["measures"]
    assert fd["drac_mps2"] > 2.0 and fd["safe_distance"] == "Not maintained"
    with settings(SAFE_RULE="ttc", SAFE_TTC_S=0.1, SAFE_SUDDEN_STOP=False):
        assert run(mb)[0]["following_distance"]["measures"]["safe_distance"] == "Maintained"


def test_sudden_stop_then_impact_is_not_maintained():
    mb = ahead(ttc=1.0)
    with settings(SAFE_SUDDEN_STOP=True, SAFE_TTC_S=0.5, SAFE_RULE="ttc", TTC_SUDDEN_STOP_S=2.0):
        ev, _ = run(mb)
    assert "sudden_stop" in ev and ev["following_distance"]["measures"]["safe_distance"] == "Not maintained"


def test_report_type_settings_cover_every_setting_and_are_restored():
    with settings(SAFE_TTC_S=2.0):
        config.LANE_BY_TYPE = {"REAR_END": {"SAFE_TTC_S": 9.0}}
        fd = run(ahead(ttc=5.0), "Rear-end")[0]["following_distance"]["measures"]
        assert fd["safe_distance_ttc_threshold_s"] == 9.0
        assert config.SAFE_TTC_S == 2.0
