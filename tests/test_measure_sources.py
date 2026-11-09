# Where each event number comes from: observed in that frame, estimated over several frames, or inferred
# (carried over from Vehicle B's last tracked frame when B is no longer tracked at the moment shown).
# Case behind it: dada_training_type11_53 - B is tracked up to frame 19, the impact is at frame 21, and the
# distance 2.86 m shown "at 2.1 s" was B's distance at frame 19.
import copy, os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH', str(Path(tempfile.gettempdir()) / ('siyaq_test_' + str(os.getpid()) + '.db')))
os.environ.setdefault('SECRET_KEY', 'test-only-secret')
os.environ.setdefault('OTP_MODE', 'demo')
from siyaq_cv import events

N, B, LAST, CRASH = 30, 7, 19, 21


def scene(last=LAST, crash=CRASH):
    """B in the left lane (2.8 m) moves in from frame 10, getting closer, tracked up to `last`; the image jolts at `crash`."""
    mb = {}
    for f in range(0, last + 1):
        x = -2.8 if f < 10 else -2.8 + 0.12 * (f - 9)
        h = 0.15 + 0.007 * f
        mb[f] = {"lateral_m": x, "centre_offset": x / 10, "distance_m": round(1.55 / h * 0.5, 2), "height_frac": h,
                 "ttc_s": 2.0 if f >= 12 else None, "rel_speed_mps": -0.5 if f >= 12 else None,
                 "lateral_speed_mps": 1.0 if f >= 10 else None, "flow_dx_px": 0.5, "at_edge": False}
    jolt = [1.0 + 0.1 * (f % 3) for f in range(N)]
    jolt[crash] = 12.0
    flow = {"jolt": jolt, "yaw_rate": [0.0] * N, "ego_dx": [0.0] * N}
    times = [round(f / 10, 1) for f in range(N)]
    evs, c = events.analyse({B: mb}, B, flow, times)
    return {e["type"]: e for e in evs}, c, mb


def test_values_at_the_impact_are_marked_as_carried_from_the_last_tracked_frame():
    ev, crash, mb = scene()
    assert crash == CRASH
    col = ev["collision"]
    assert col["b_last_tracked_frame"] == LAST
    s = col["sources"]["b_distance_at_impact_m"]
    assert s["basis"] == "inferred" and s["frame"] == LAST and s["reported_for_frame"] == CRASH
    assert col["measures"]["b_distance_at_impact_m"] == mb[LAST]["distance_m"]       # value itself unchanged
    for k in ("b_box_height_frac", "b_lateral_at_impact_m"):
        assert col["sources"][k]["basis"] == "inferred" and col["sources"][k]["frame"] == LAST
    # the impact moment itself is read from the image jolt in frame 21
    assert col["sources"]["time_s"] == {"basis": "observed", "frame": CRASH, "time_s": 2.1}
    assert col["sources"]["b_distance_1s_before_m"]["basis"] == "observed"
    assert col["sources"]["b_distance_1s_before_m"]["frame"] == CRASH - 10


def test_window_values_are_estimates_over_observed_frames_only():
    ev, _, _ = scene()
    s = ev["collision"]["sources"]
    for k in ("closing_speed_last_1s_mps", "min_ttc_last_1s_s"):
        assert s[k]["basis"] == "estimated" and s[k]["frames"] == [12, LAST]      # never past B's last frame


def test_lane_change_end_extended_to_the_impact_is_inferred():
    ev, _, mb = scene()
    lc = ev["lane_change"]
    assert lc["end"] == CRASH                                                       # EXP-004 logic kept
    end = lc["sources"]["event_end"]
    assert end["basis"] == "inferred" and end["from"] == "collision" and end["last_tracked_frame"] == LAST
    for k in ("b_distance_end_m", "offset_end", "lateral_end_m"):
        assert lc["sources"][k]["basis"] == "inferred"
    assert lc["sources"]["b_distance_end_m"]["frame"] == LAST
    assert lc["measures"]["b_distance_end_m"] == mb[LAST]["distance_m"]
    assert lc["sources"]["b_distance_start_m"] == {"basis": "observed", "frame": lc["start"], "time_s": lc["start_t"]}


def test_following_distance_at_the_inferred_moment_uses_frame_19_and_says_so():
    ev, _, mb = scene()
    fd = ev["following_distance"]
    assert fd["start"] == CRASH
    assert fd["sources"]["event_start"]["basis"] == "inferred"
    for k in ("b_distance_m", "ttc_s", "safe_distance", "b_box_height_frac"):
        assert fd["sources"][k]["basis"] == "inferred" and fd["sources"][k]["frame"] == LAST
    assert fd["sources"]["closing_speed_mps"]["basis"] == "estimated"
    assert fd["sources"]["closing_speed_mps"]["frames"][1] == LAST
    assert fd["measures"]["b_distance_m"] == mb[LAST]["distance_m"]


def test_when_b_is_tracked_at_the_impact_its_values_are_observed():
    ev, crash, _ = scene(last=24, crash=CRASH)
    col = ev["collision"]
    assert crash == CRASH and col["b_last_tracked_frame"] == 24
    assert col["sources"]["b_distance_at_impact_m"] == {"basis": "observed", "frame": CRASH, "time_s": 2.1}


def test_the_page_labels_carried_values():
    from app import app
    import video_analysis as va
    from test_video_analysis import FAKE
    ev, _, _ = scene()
    r = copy.deepcopy(FAKE)
    r['events'] = [dict(ev['collision'], start_t=2.1, end_t=2.1), dict(ev['lane_change'])]
    with app.test_request_context():
        from flask import render_template
        html = render_template('_analysis_result.html', result=r, video_src='', event_ar=va.EVENT_AR,
                               vehicle_ar=va.VEHICLE_AR, measure_ar=va.MEASURE_AR, value_ar=va.VALUE_AR)
    assert 'src-inferred' in html and 'آخر قياس 1.9 ث' in html and 'آخر قياس 2.1' not in html
    assert 'src-observed' in html and 'src-estimated' in html
    assert 'لم تعد متتبَّعة لحظة الاصطدام' in html                     # collision note
    assert 'مستنتجة من لحظة الاصطدام' in html                          # lane-change end note
    # an old saved result without sources still renders
    with app.test_request_context():
        from flask import render_template
        old = render_template('_analysis_result.html', result=FAKE, video_src='', event_ar=va.EVENT_AR,
                              vehicle_ar=va.VEHICLE_AR, measure_ar=va.MEASURE_AR, value_ar=va.VALUE_AR)
    assert 'va-src src-' not in old.split('va-src-legend')[1].split('</p>', 1)[1]
