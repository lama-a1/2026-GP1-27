# Videos of the rear camera (Vehicle B behind the recording car), the impact hidden by Vehicle B itself, and the end
# card of a repost (TikTok) cut off before the analysis.
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DATABASE_PATH', str(Path(tempfile.gettempdir()) / ('siyaq_test_' + str(os.getpid()) + '.db')))
os.environ.setdefault('SECRET_KEY', 'test-only-secret')
from siyaq_cv import analyse, config, events, video
from tests.test_cv_rule_options import N, B, CRASH, ahead, settings


def run(mb, camera, others=None):
    jolt = [1.0] * N
    jolt[CRASH] = 12.0
    flow = {"jolt": jolt, "yaw_rate": [0.0] * N, "ego_dx": [0.0] * N}
    meas = {B: mb, **(others or {})}
    evs, c = events.analyse(meas, B, flow, [round(f / 10, 1) for f in range(N)], None, camera=camera)
    return evs, c


def test_rear_camera_follower_is_vehicle_b_and_no_sudden_stop_of_b():
    mb = ahead(ttc=1.0)                          # B closes in fast: ahead = a sudden stop of B; behind = it is not
    with settings(TTC_SUDDEN_STOP_S=2.0, SAFE_SUDDEN_STOP=False, SAFE_TTC_S=2.0):
        front = {e["type"]: e for e in run(mb, "front")[0]}
        rear = {e["type"]: e for e in run(mb, "rear")[0]}
    assert "sudden_stop" in front and "sudden_stop" not in rear
    assert front["following_distance"]["measures"]["following_vehicle"] == "A"
    assert rear["following_distance"]["measures"]["following_vehicle"] == "B"
    # the same measures and the same verdict: only who had to keep the distance changes
    for k in ("b_distance_m", "ttc_s", "safe_distance"):
        assert front["following_distance"]["measures"][k] == rear["following_distance"]["measures"][k]
    assert front["collision"]["start"] == rear["collision"]["start"]


def test_rear_camera_overtaking_comes_from_behind():
    # vehicle 9: far and near the centre first, then close beside the car = it came from behind and passed (rear camera);
    # seen through the front camera the same movement is a vehicle falling behind, not an overtaking
    mt = {}
    for f in range(0, 20):
        k = f / 19
        mt[f] = {"centre_offset": 0.05 + 0.4 * k, "height_frac": 0.06 + 0.12 * k, "distance_m": 20 - 15 * k,
                 "rel_speed_mps": -1.0, "lateral_m": 0.2 + 3 * k}
    with settings():
        rear = [e for e in run(ahead(ttc=8.0), "rear", {9: mt})[0] if e["type"] == "overtaking"]
        front = [e for e in run(ahead(ttc=8.0), "front", {9: mt})[0] if e["type"] == "overtaking"]
    assert len(rear) == 1 and rear[0]["track_id"] == 9 and rear[0]["measures"]["side"] == "right"
    assert not front


def test_rear_picture_sides_are_turned_into_the_cars_sides():
    evs = [{"type": "lane_change", "vehicle": "B", "measures": {"direction": "left", "crossed_line_side": "right"}},
           {"type": "lane_change", "vehicle": "A", "measures": {"direction": "left"}},
           {"type": "overtaking", "vehicle": "other", "measures": {"side": "right"}}]
    analyse._rear_sides(evs)
    assert evs[0]["measures"] == {"direction": "right", "crossed_line_side": "left"}
    assert evs[1]["measures"]["direction"] == "left"           # the car's own turn reads the same from both cameras
    assert evs[2]["measures"]["side"] == "left"


def test_impact_hidden_by_vehicle_b_while_it_stays_near_afterwards():
    # B grows to 0.2 of the picture, is lost at frame 14 (it covers the camera at the impact, jolt at frame 17),
    # then is seen again, standing near and larger (0.3) - the largest box is after the impact
    mb = {f: {"height_frac": 0.1 + 0.007 * f} for f in range(15)}
    mb.update({f: {"height_frac": 0.3} for f in range(22, 40)})
    jolt = [1.0] * 40
    jolt[17] = 20.0
    with settings(COLLISION_GAP_MIN=0.0, COLLISION_LOST_WIN=5):
        assert events.collision(mb, jolt, 40)[0] >= 19      # where B is seen again, not the impact
    with settings(COLLISION_GAP_MIN=0.5, COLLISION_LOST_WIN=5):
        assert events.collision(mb, jolt, 40)[0] == 17
    with settings(COLLISION_GAP_MIN=0.8, COLLISION_LOST_WIN=5):    # B was too small when lost
        assert events.collision(mb, jolt, 40)[0] >= 19      # where B is seen again, not the impact


def test_end_card_of_a_repost_is_found():
    times = [k / 10 for k in range(100)]
    jolt = [1.0 + 0.2 * (k % 3) for k in range(100)]
    spread = [90.0] * 100
    assert video._end_card(times, jolt, spread) is None
    jolt[80] = 105.0                                  # hard cut to a flat end card
    assert video._end_card(times, jolt, spread) is None   # the picture after it is still a road picture
    for k in range(80, 100):
        spread[k] = 0.0 if k % 7 else 15.0
    assert video._end_card(times, jolt, spread) == 80
    jolt2 = list(jolt)
    jolt2[80], jolt2[20] = 1.0, 105.0                 # a cut in the first half is not an end card
    spread2 = [90.0] * 20 + [0.0] * 80
    assert video._end_card(times, jolt2, spread2) is None
