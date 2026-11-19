"""Candidate values for the event thresholds, each range derived from a published value.

tools/cross_validate.py picks the value of each threshold from these lists inside every cross-validation fold,
on the training folds only. The ranges are wider than the published value because a single uncalibrated dashcam
measures metres and angles with an error.

Sources
  [FHWA]      FHWA, "Lane Width" - lanes are 3.0-3.6 m (10-12 ft). https://www.fhwa.dot.gov/planning/css/resources/lanewidth
  [highD]     R. Krajewski et al., "The highD Dataset", IEEE ITSC 2018 - a lane change = crossing the lane marking.
              https://arxiv.org/abs/1810.05642
  [Geurts]    M. Geurts et al., "Evaluating the Quality of Lane Change Event Detection", VEHITS 2022 - lateral distance
              and lateral speed thresholds are tuned on data (e.g. 0.2 -> 0.3 m, 0 -> 1 m).
              https://scitepress.org/PublishedPapers/2022/109984/pdf/index.html
  [Ramanujam] V. Ramanujam, "Lane changing models for arterial traffic", MIT 2007 - lane changes last 5-6 s on average.
              http://hdl.handle.net/1721.1/39286
  [vdHorst]   R. van der Horst (1991): critical time-to-collision 1.5 s; Vogel (2003): time headway thresholds 0.9-3.0 s;
              both as cited in "Comparative Analysis of Safety Performance Indicators...", Promet. https://hrcak.srce.hr/file/183359
  [NHTSA]     NHTSA NCAP forward collision warning test: the warning must come before TTC = 2.1 s.
  [Lu]        C. Lu et al., "Performance evaluation of surrogate measures of safety with naturalistic driving data",
              Accident Analysis & Prevention 162 (2021) - TTC threshold calibrated to 4.5 s; 1.5-3 s commonly used.
  [Krajewski] = [highD]: a lane change is the crossing of the lane marking.
  [ByteTrack] Y. Zhang et al., "ByteTrack", ECCV 2022 - a lost track is kept for 30 frames at 30 fps (1 s).
  [Archer]    J. Archer, "Indicators for traffic safety assessment and prediction and their application in
              micro-simulation modelling", PhD thesis, KTH Stockholm 2005 - deceleration rate to avoid the crash
              (DRAC = closing speed^2 / (2 x gap)), conflict when above 3.35 m/s^2.
  [SWOV]      SWOV fact sheet "Headway times and road safety" (2012) - a 2 s headway is the recommended minimum; the
              driver must be able to stop within the distance ahead.
              https://www.swov.nl/system/files/publication-downloads/fs_headway_archived.pdf
  [Duda]      R. O. Duda, P. E. Hart, D. G. Stork, Pattern Classification, 2nd ed., Wiley 2001 - the decision threshold
              depends on the prior probability of each class (here: the accident type of the user's report).
  [Dagan]     E. Dagan et al., "Forward collision warning with a single camera", IEEE IV 2004 - TTC from the change of
              the vehicle's image size (the method used in motion.py).
"""

GRID = {
    # Vehicle B starts in the neighbouring lane: sideways offset >= half a lane (1.5-1.8 m) [FHWA], +-0.6 m error.
    "LANE_SIDE_M": [1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4],
    # it moves at least this far towards our lane: 10-40 % of a 3.6 m lane; tuned on data as in [Geurts].
    "LANE_SHIFT_M": [0.3, 0.6, 0.9, 1.2, 1.5],
    # Vehicle B is inside our lane: half a lane minus half a car (~0.9 m) = 0.6-0.9 m, up to the marking 1.8 m [FHWA, highD].
    "LANE_IN_M": [0.6, 0.9, 1.2, 1.5, 1.8],
    # inward speed that marks the start of the move: a 3.6 m change in 5-6 s averages ~0.65 m/s [Ramanujam]; [Geurts].
    "LANE_ONSET_MPS": [0.2, 0.3, 0.4, 0.6, 0.8, 1.0],
    # heading change of the recording car for its own lane change: 3.6 m in 5-6 s at 10-25 m/s gives a peak heading of
    # about 2-8 deg [Ramanujam]; values above 8 measure how much the optical-flow heading overstates it.
    "EGO_YAW_DEG": [2.0, 4.0, 6.0, 8.0, 12.0, 16.0, 20.0, 30.0, 40.0],
    # sudden stop of the vehicle ahead: critical TTC 1.5 s [vdHorst]; FCW warning by 2.1 s [NHTSA].
    "TTC_SUDDEN_STOP_S": [1.0, 1.5, 2.0, 2.1, 2.5, 3.0],
    # safe following distance judged by TTC (time headway needs our own speed): 1.5 s critical [vdHorst],
    # 1.5-3 s common, 4.5 s calibrated [Lu].
    "SAFE_TTC_S": [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5],
    # when it is judged: not in the last second, where every rear-end approach has a small TTC.
    "SAFE_REF_S": [1.0, 1.5, 2.0, 2.5, 3.0],
    # B's lane change from the lane lines (B's road contact point crosses the marking) [highD]: not used, added to the
    # metric rule, used to confirm it, or both. "off" keeps the original rule, so the search can always keep it.
    "LANE_LINE_RULE": ["off", "or", "and", "line", "confirm", "add"],
    # impact after Vehicle B is lost at short range: up to the tracker's 1 s buffer (10 frames at 10 fps) [ByteTrack].
    "COLLISION_LOST_WIN": [0, 5, 10],
    "COLLISION_GAP_MIN": [0.0, 0.5, 0.7],
    # B must reach the recording car's lane for a lane change (a lane change = crossing the marking) [highD].
    "LANE_REQUIRE_IN": [False, True],
    # B's lane change that cuts in ends at the impact (the team's labels: median end = impact frame).
    "LANE_END_AT_IMPACT": [False, True],
    # no lane change found: B's lane change in this many s before the impact, marked as inferred from the report
    # (B makes most lane changes: prior probability [Duda]); 1-2 s around the median start of the labelled lane
    # changes (1.5 s before the impact). 0 = off.
    "LANE_FALLBACK_S": [0.0, 1.0, 1.5, 2.0],
    # following distance judged by TTC, by DRAC or by both [vdHorst, Lu, Archer].
    "SAFE_RULE": ["ttc", "drac", "ttc_or_drac", "ttc_and_drac"],
    # DRAC threshold 3.35 m/s^2 [Archer], +-50 % for the camera-model error in the gap (metres).
    "SAFE_DRAC_MPS2": [2.0, 3.35, 5.0],
    # decision when the gap to B is not closing (no TTC, no DRAC), chosen per report type [Duda].
    "SAFE_UNKNOWN": ["Maintained", "Not maintained"],
    # a safe distance lets the driver stop when the vehicle ahead brakes [SWOV]: sudden stop + impact = not maintained.
    "SAFE_SUDDEN_STOP": [False, True],
    # B not tracked at the judging moment: its nearest tracked frame within up to 1 s (the tracker's buffer) [ByteTrack].
    "SAFE_FALLBACK_S": [0.0, 0.5, 1.0],
}

# The rules run in this order (impact, Vehicle B's lane change, then the recording car's lane change only if B made
# none, then the sudden stop only if B made no lane change, then the following distance), so the search runs in the
# same stages, each with the earlier stages fixed. Each stage is scored on the event it changes. The third item says
# whether the stage is searched separately for each accident type of the report [Duda] (config.LANE_BY_TYPE).
STAGES = [
    (("COLLISION_LOST_WIN", "COLLISION_GAP_MIN"), "collision", False),
    (("LANE_SIDE_M", "LANE_SHIFT_M", "LANE_IN_M"), "lane_change", True),
    (("LANE_REQUIRE_IN",), "lane_change", True),
    (("LANE_ONSET_MPS",), "lane_change", True),
    (("EGO_YAW_DEG",), "lane_change", True),
    (("LANE_LINE_RULE",), "lane_change", True),
    (("LANE_END_AT_IMPACT",), "lane_change", True),
    (("LANE_FALLBACK_S", "EGO_YAW_DEG"), "lane_change", True),
    (("TTC_SUDDEN_STOP_S",), "sudden_stop", True),
    (("SAFE_REF_S", "SAFE_TTC_S"), "safe_distance", True),
    (("SAFE_RULE", "SAFE_DRAC_MPS2"), "safe_distance", True),
    (("SAFE_UNKNOWN",), "safe_distance", True),
    (("SAFE_SUDDEN_STOP",), "safe_distance", True),
    (("SAFE_FALLBACK_S",), "safe_distance", False),
]
