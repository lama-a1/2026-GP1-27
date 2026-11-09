# SIYAQ-BUG-001: the impact must not move to a later jolt (e.g. hitting the kerb) just because B's track goes on
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from siyaq_cv import events


def test_impact_is_not_moved_to_a_later_jolt_at_the_end_of_b_track():
    n = 50
    # B grows until the impact at frame 30, then stays at the same size (both cars stopped) until frame 45
    meas_b = {f: {"height_frac": min(0.1 + f * 0.01, 0.4)} for f in range(10, 46)}
    jolt = [1.0 + 0.1 * (f % 3) for f in range(n)]
    jolt[30] = 12.0          # the impact
    jolt[45] = 12.0          # a second jolt of the same strength later on (kerb), on B's last frame
    frame, _ = events.collision(meas_b, jolt, n)
    assert frame == 30
