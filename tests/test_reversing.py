# Rule R4 evidence (exploratory): the front vehicle B reverses into a standing recording car.
from siyaq_cv import config, events


def _mb(d0, d1, crash=30):
    n = config.REVERSE_WINDOW
    return {crash - n + i: {"distance_m": d0 + (d1 - d0) * i / n} for i in range(n + 1)}


def _still(px, crash=30):
    return {f: px for f in range(crash - config.REVERSE_WINDOW, crash)}


def test_standing_car_and_b_closer_is_reversing():
    times = [i / 10 for i in range(50)]
    e = events.reversing(_mb(3.4, 2.7), 1, _still(0.02), 30, times)
    assert e and e["type"] == "reversing" and e["vehicle"] == "B" and e["measures"]["closing_m"] == 0.7


def test_moving_car_is_not_reversing():
    times = [i / 10 for i in range(50)]
    assert events.reversing(_mb(3.4, 2.7), 1, _still(1.5), 30, times) is None


def test_b_not_coming_closer_is_not_reversing():
    times = [i / 10 for i in range(50)]
    assert events.reversing(_mb(3.4, 3.2), 1, _still(0.02), 30, times) is None


def test_no_impact_or_no_b():
    times = [i / 10 for i in range(50)]
    assert events.reversing(_mb(3.4, 2.7), None, _still(0.02), 30, times) is None
    assert events.reversing(_mb(3.4, 2.7), 1, _still(0.02), None, times) is None
