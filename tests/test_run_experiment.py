# Experiment tool: evidence levels are never mixed, the Test split is refused, and the metric definitions
# match Siyaq_Part1/evaluation/siyaq_eval.py (collision +-5 frames, temporal IoU >= 0.3).
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import run_experiment as rx

ROW = {"split": "train", "accident_type": "Lane-change", "crash_start_frame": "30"}


def result(crash=31, lc=(12, 30), b=1):
    ev = [{"type": "collision", "start": crash, "end": crash, "measures": {}}]
    if lc:
        ev.append({"type": "lane_change", "vehicle": "B", "start": lc[0], "end": lc[1], "measures": {"direction": "left"}})
    return {"collision_frame": crash, "vehicle_b": b, "events": ev,
            "_tracks": {str(b): [[20, 0.6, 0.3, 0.9, 0.6]]}}


def test_tiou_and_hit_definitions():
    assert rx.tiou((10, 19), (15, 22)) == 5 / 13
    c = rx.compare("x", ROW, result(crash=35), {}, {})
    assert c["collision"]["vs_source_annotation"]["hit_within_0_5s"] is True      # 5 frames = 0.5 s
    c = rx.compare("x", ROW, result(crash=36), {}, {})
    assert c["collision"]["vs_source_annotation"]["hit_within_0_5s"] is False


def test_human_and_draft_are_reported_separately():
    human = {"x": {"vehicle_b": {"frame": 20, "box": [0.6, 0.3, 0.9, 0.6]},
                   "lane_change": {"vehicle": "B", "direction": "left", "start": 15, "end": 30}}}
    draft = {"x": {"lane_change_vehicle": "Vehicle B", "lane_change_direction": "Left", "lane_change_start": 5, "lane_change_end": 30}}
    c = rx.compare("x", ROW, result(), human, draft)
    assert c["vehicle_b"]["correct"] and c["vehicle_b"]["level"] == "human_reviewed"
    assert c["lane_change"]["vs_human_reviewed"]["level"] == "human_reviewed"
    assert c["lane_change"]["vs_draft_unreviewed"]["level"] == "draft_unreviewed"
    m = rx.aggregate([c], {})
    assert m["train"]["lane_change_human_reviewed"]["tp"] == 1
    assert m["train"]["lane_change_draft_unreviewed"]["n_clips_with_reference_row"] == 1
    assert m["train"]["sudden_stop_human_reviewed"] == rx.PENDING


def test_no_human_reference_means_pending_not_zero():
    c = rx.compare("y", ROW, result(), {}, {})
    m = rx.aggregate([c], {})
    assert m["train"]["lane_change_human_reviewed"] == rx.PENDING
    assert m["train"]["vehicle_b_identification"] == rx.PENDING


def test_draft_without_lane_change_counts_a_false_positive():
    c = rx.compare("z", ROW, result(), {}, {"z": {"lane_change_vehicle": None}})
    m = rx.aggregate([c], {})
    assert m["train"]["lane_change_draft_unreviewed"]["fp"] == 1


def test_test_split_is_refused_without_final():
    tool = Path(rx.__file__)
    r = subprocess.run([sys.executable, str(tool), "--exp-id", "X", "--title", "t", "--dataset", ".", "--splits", "test"],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "Refusing the Test split" in (r.stderr + r.stdout)
