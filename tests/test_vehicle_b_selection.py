# EXP-005 - Wrong Vehicle B selection.
# Reviewed case: CCD 000023. The team's visual review says Vehicle B is the car on the left (engine track 4);
# the engine picks the large truck seen only in the first second (track 1).
# Tests marked xfail(strict=True) describe the wanted behaviour that the current pick_vehicle_b() does NOT have
# yet: they fail today on purpose, and pytest will report XPASS (an error, because strict) the day a change fixes
# them, so the mark must then be removed. They are not a claim that the problem is solved.
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from siyaq_cv import events, motion

DATA = Path(__file__).resolve().parent / "data"
W, H, N = 640, 360, 50


def fixture(name):
    d = json.loads((DATA / f"tracks_{name}.json").read_text())
    tracks = {int(t): {int(f): tuple(b) for f, b in tr.items()} for t, tr in d["tracks"].items()}
    return d, tracks


def box(cx, bottom, h, w):
    return (cx - w / 2, bottom - h, cx + w / 2, bottom)


def truck_and_cutting_in_car(car_height_px):
    """A large truck beside the recording car in the first second only, and a smaller car that moves from the
    neighbouring lane into the recording car's lane and is closest at the impact (last frames)."""
    truck = {f: box(500, 330, 320, 280) for f in range(0, 10)}                    # huge, right side, early (like 000023)
    car = {}
    for i, f in enumerate(range(20, N)):
        cx = 140 + (320 - 140) * min(1.0, i / 20)                                 # moves in from the left lane
        h = 40 + (car_height_px - 40) * i / (N - 21)                              # gets closer
        car[f] = box(cx, 200 + h * 0.6, h, h * 1.4)
    return {1: truck, 2: car}


def test_reviewed_dada_53_keeps_its_vehicle_b():
    # human-reviewed lane change (EXP-004): Vehicle B is engine track 4
    d, tracks = fixture("dada_training_type11_53")
    assert events.pick_vehicle_b(tracks, d["W"], d["H"], d["n"]) == 4


def test_truck_is_not_picked_when_the_maneuvering_car_ends_up_closer():
    # the cutting-in car ends large and right in front of the recording car: picked today
    assert events.pick_vehicle_b(truck_and_cutting_in_car(200), W, H, N) == 2


@pytest.mark.xfail(strict=True, reason="EXP-005 open: size outweighs timing - an early large truck beats a smaller "
                                       "vehicle that performs the maneuver and is present at the impact")
def test_early_large_truck_does_not_beat_the_smaller_maneuvering_car():
    assert events.pick_vehicle_b(truck_and_cutting_in_car(60), W, H, N) == 2


@pytest.mark.xfail(strict=True, reason="EXP-005 open: on reviewed clip 000023 the engine picks the early truck "
                                       "(track 1) instead of the reviewed left car (track 4)")
def test_reviewed_000023_picks_the_left_car():
    d, tracks = fixture("ccd_000023")
    assert events.pick_vehicle_b(tracks, d["W"], d["H"], d["n"]) == 4


def test_000023_truck_only_appears_long_before_the_impact():
    # the evidence the current rule ignores: track 1 ends ~3 s before the annotated impact
    d, tracks = fixture("ccd_000023")
    assert max(tracks[1]) + 20 < d["gt_crash_frame"]
    assert max(tracks[4]) > max(tracks[1])


@pytest.mark.xfail(strict=True, reason="EXP-005 open, separate cause: even with the reviewed Vehicle B (track 4) the "
                                       "impact is not found - the detector loses the edge-cut car at frame 29, 10 frames "
                                       "before the contact, and the impact search only looks within 3 frames of B's boxes")
def test_000023_with_the_reviewed_vehicle_b_the_impact_is_found():
    d, tracks = fixture("ccd_000023")
    mb = motion.vehicle_measures({f: (*b, 0.5) for f, b in tracks[4].items()}, "car", d["W"], d["H"], None)
    frame, _ = events.collision(mb, d["jolt"], d["n"])
    assert abs(frame - d["gt_crash_frame"]) <= 5          # today: frame 16 (1.6 s); annotated 38, contact jolt 39-40
