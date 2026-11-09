# Sprint 2: ByteTrack tracker (Kalman filter + Hungarian matching + low-score second association)
import itertools, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from siyaq_cv import bytetrack


def test_hungarian_finds_the_cheapest_assignment():
    rng = np.random.default_rng(1)
    for _ in range(50):
        n = int(rng.integers(1, 6))
        cost = rng.random((n, n))
        best = min(sum(cost[i, p[i]] for i in range(n)) for p in itertools.permutations(range(n)))
        col = bytetrack._hungarian(cost)
        assert abs(cost[np.arange(n), col].sum() - best) < 1e-9


def test_linear_assignment_respects_the_threshold():
    cost = np.array([[0.1, 0.9], [0.95, 0.99]])
    matches, u_rows, u_cols = bytetrack.linear_assignment(cost, 0.8)
    assert matches.tolist() == [[0, 0]] and u_rows == (1,) and u_cols == (1,)


def car(x, score=0.9):
    return (x, 100.0, x + 80.0, 160.0, score, 'car')


def test_same_id_through_a_missed_frame_and_a_low_score_frame():
    # a car moving right; frame 3 has no detection, frame 5 only a low-score (blurred) one
    frames = [[car(100)], [car(110)], [car(120)], [], [car(140)], [car(150, 0.3)], [car(160)]]
    tracks, classes = bytetrack.track(frames)
    assert len(tracks) == 1
    (boxes,) = tracks.values()
    assert sorted(boxes) == [0, 1, 2, 4, 5, 6]          # the low-score frame is kept by the second association
    assert list(classes.values()) == ['car']


def test_two_cars_keep_their_own_ids_when_they_pass():
    a = [car(100 + 10 * f) for f in range(8)]
    b = [(400 - 10 * f, 300.0, 480 - 10 * f, 360.0, 0.9, 'truck') for f in range(8)]
    tracks, classes = bytetrack.track([[x, y] for x, y in zip(a, b)])
    assert len(tracks) == 2 and sorted(classes.values()) == ['car', 'truck']


def test_a_single_low_score_box_does_not_start_a_track():
    tracks, _ = bytetrack.track([[car(100, 0.3)], [car(105, 0.3)], [car(110, 0.3)]])
    assert tracks == {}
