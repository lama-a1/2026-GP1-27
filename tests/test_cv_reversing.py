# Rule R4 in the cross-validation (tools/cross_validate.py): reversing is scored on every clip, and the reversing
# clips are left out of the safe-distance score only.
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import cross_validate as cv


def _ref(reversing=None, sd="Not maintained", valid_rev=True):
    return {"collision_frame": 30, "vehicle_b": None, "lane_change": None, "sudden_stop": None, "reversing": reversing,
            "safe_distance": [{"frame": 0, "value": sd}],
            "valid_for": {"collision": True, "vehicle_b": False, "lane_change": False, "sudden_stop": True,
                          "safe_distance": True, "accident_type": True, "reversing": valid_rev}}


def _pred(*types, sd="Not maintained"):
    evs = [{"type": t, "measures": {"safe_distance": sd} if t == "following_distance" else {}} for t in types]
    return {"collision_frame": 30, "events": evs, "vehicle_b_boxes": []}


def test_reversing_found_on_a_reversing_clip_is_correct():
    out = cv.score(_ref({"start": 18, "end": 30}), _pred("collision", "reversing", "following_distance"))
    assert out["reversing"] == 1 and out["_rv_ref"] and out["_rv_pred"]


def test_reversing_on_a_clip_without_it_is_wrong():
    assert cv.score(_ref(None), _pred("collision", "reversing"))["reversing"] == 0
    assert cv.score(_ref(None), _pred("collision"))["reversing"] == 1


def test_reversing_clip_is_left_out_of_safe_distance_only():
    rev = cv.score(_ref({"start": 18, "end": 30}), _pred("collision", "following_distance", sd="Maintained"))
    assert rev["safe_distance"] is None and rev["collision"] == 1
    plain = cv.score(_ref(None), _pred("collision", "following_distance", sd="Not maintained"))
    assert plain["safe_distance"] == 1


def test_unpaired_reversing_tags_are_not_scored():
    assert cv.score(_ref({"start": 18, "end": None}, valid_rev=False), _pred("collision"))["reversing"] is None


def test_baseline_scores_reversing_with_the_majority_and_skips_safe_distance_there():
    refs = {"a": _ref(None), "b": _ref(None), "c": _ref({"start": 18, "end": 30})}
    rows = {r["clip_id"]: r for r in cv.baseline_rows(["a", "b"], ["a", "c"], refs)}
    assert rows["a"]["reversing"] == 1 and rows["c"]["reversing"] == 0
    assert rows["c"]["safe_distance"] is None and rows["a"]["safe_distance"] is not None


def test_r4_settings_are_in_the_grid():
    from siyaq_cv.threshold_grid import GRID, STAGES
    keys = ("REVERSE_WINDOW", "REVERSE_STILL_PX", "REVERSE_CLOSE_RATIO")
    assert all(k in GRID and k in cv.DEFAULTS for k in keys)
    assert any(stage[0] == keys and stage[1] == "reversing" for stage in STAGES)
