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
    "LANE_LINE_RULE": ["off", "or", "and", "line"],
}

# The rules run in this order (Vehicle B's lane change, then the recording car's lane change only if B made none,
# then the sudden stop only if B made no lane change, then the following distance), so the search runs in the same
# stages, each with the earlier stages fixed. Each stage is scored on the event it changes.
STAGES = [
    (("LANE_SIDE_M", "LANE_SHIFT_M", "LANE_IN_M"), "lane_change"),
    (("LANE_ONSET_MPS",), "lane_change"),
    (("EGO_YAW_DEG",), "lane_change"),
    (("LANE_LINE_RULE",), "lane_change"),
    (("TTC_SUDDEN_STOP_S",), "sudden_stop"),
    (("SAFE_REF_S", "SAFE_TTC_S"), "safe_distance"),
]
