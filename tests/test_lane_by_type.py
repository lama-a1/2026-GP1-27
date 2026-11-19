from siyaq_cv import config, events


def test_report_type_names():
    assert events.report_type('REAR_END') == 'REAR_END'
    assert events.report_type('Lane-change') == 'LANE_CHANGE'
    assert events.report_type(None) is None


def test_lane_thresholds_follow_the_report_type(monkeypatch):
    seen = {}

    def fake(meas, b, flow, times, scene=None, camera='front'):
        seen['side'] = config.LANE_SIDE_M
        return [], None
    monkeypatch.setattr(events, '_analyse', fake)
    before = config.LANE_SIDE_M
    events.analyse({}, None, {}, [], 'LANE_CHANGE')
    assert seen['side'] == config.LANE_BY_TYPE['LANE_CHANGE']['LANE_SIDE_M']
    assert config.LANE_SIDE_M == before            # restored afterwards
    events.analyse({}, None, {}, [], None)
    assert seen['side'] == before
