# Siyaq — Experiment Log

Earlier entries (EXP-001 to EXP-003) were not found in this repository. Add them here when available.

---

## EXP-004 — Lane Change Boundary Detection

**Date:** 2026-11-09 · **Component:** `siyaq_cv/events.py` (lane change of Vehicle B) · **Tracker:** ByteTrack (unchanged) · **Collision logic:** SIYAQ-BUG-001 version (unchanged)

### Trigger
`dada_training_type11_53` (train). Human-reviewed in CVAT: Vehicle B = dark car on the left, direction right, lane change frames 15–22. Siyaq: direction right, frames 10–19 (starts 5 frames early, ends 3 frames early).

### Diagnosis (measured on the clip)
| Hypothesis | Evidence | Verdict |
|---|---|---|
| Wrong Vehicle B | Track 4 is the dark car on the left (checked frame by frame, frames 10–19) | Not the cause |
| ByteTrack loses B | B tracked frames 10–19 with no gaps. Frames 20–21: **YOLO returns no box for B at all** (B fills the left side, partly outside the picture). Frame 22: one box at score 0.20, which ByteTrack by design does not use for a lost track | Detection gap, not a tracker bug. It sets where the track ends |
| Noisy lateral measurement | Frames 10–13: B's box touches the left image side (x1 = 0–6 px), so its centre — and the sideways position — is biased | Contributes to a wrong start |
| Start/end rule | Start = frame where B is **widest** from the lane = the **first tracked frame** (10) whenever B approaches steadily. End = frame **closest** to the lane = the **last tracked frame** (19) when the track ends early | **Root cause** |
| Definition mismatch | CVAT: start = B starts moving in; end = B in the lane or impact. 49 of 60 train/val draft lane changes end at the impact frame | The algorithm measured "widest → closest seen", not "starts moving in → in lane / impact" |

### Change
`_lane_change_bounds()` in `siyaq_cv/events.py`. Detection (whether there is a lane change, and its direction) is **unchanged**.
- **Start** — onset of sustained inward movement: inward speed from smoothed sideways positions ±2 frames apart; from the fastest inward frame, go back while speed ≥ `LANE_ONSET_MPS`. Frames whose box touches the image side (`at_edge`, new field in `motion.vehicle_measures`) are not used for the speed.
- **End** — as before (closest to / inside the lane), except: if that is B's last tracked frame, B is still outside the lane, and the impact follows within ByteTrack's own lost-track buffer (10 frames at 10 fps), the lane change ends at the impact.
- No fixed offsets, no clip-specific rule. New settings in `config.py`: `LANE_VEL_HALF = 2`, `LANE_ONSET_MPS = 0.4`, `EDGE_PX = 2`.

### Data and protocol
- Train (101 clips) and Validation (22 clips) only. **Test split not used.**
- Reference labels: **only one clip is human-reviewed** (`dada_training_type11_53`). All other lane-change labels are the **draft labels** (`draft_labels_with_rules.xlsx`, machine-assisted, low/medium confidence, **not human-reviewed**).
- `LANE_ONSET_MPS` chosen on train (0.2 / 0.3 / 0.4 / 0.5 / 0.6 → tIoU 0.483 / 0.492 / 0.512 / 0.513 / 0.492); validation looked at once, after the choice.
- Metrics on clips where both the engine and the label have a lane change. Errors in frames (10 fps). Precision/Recall: an event counts as correct with temporal IoU ≥ 0.3 (same rule as `siyaq_eval.py`).

### Results
| Split | Version | Start error (mean / MAE) | End error (mean / MAE) | tIoU | Direction acc. | Precision | Recall |
|---|---|---|---|---|---|---|---|
| Train (n=22) | Before | −16.18 / 16.73 | −4.27 / 5.09 | 0.380 | 0.909 | 0.394 | 0.271 |
| Train (n=22) | After | **−6.95 / 10.05** | **−3.27 / 4.36** | **0.512** | 0.909 | **0.545** | **0.375** |
| Val (n=4) | Before | −19.25 / 19.25 | −3.50 / 5.50 | 0.330 | 0.500 | 0.200 | 0.083 |
| Val (n=4) | After | **+4.25 / 4.25** | **−3.00 / 5.00** | **0.407** | 0.500 | **0.400** | **0.167** |

Human-reviewed clip `dada_training_type11_53` (GT 15–22): before 10–19, after **14–21**. The end is 21 because the engine's impact frame is 21; the lane-change rule ends exactly at the impact.

Ablation on train (tIoU): start rule only 0.463 · end rule only 0.405 · both 0.512 · both without the edge-cut filter 0.487.

Unchanged (checked on all 123 train/val clips): impact frames, which clips get a lane change, lane-change direction.

### Remaining failures
- 34 draft lane changes are not detected at all, and 12 detections have no draft lane change. Detection is outside this experiment.
- 11 matched clips still have tIoU < 0.3 or a start error > 8 frames. Examples: `000237`, `000436` (the engine's event is 2–3 s before the labelled one: probably another movement of B or a wrong B), `dada_validation_type11_90` and `dada_testing_type11_100` (A and B swapped).
- Direction accuracy did not change (rule unchanged). On val it is 2 of 4.

### Conclusion and limits
- Both rules help on train and on the small validation set. The gain is not only the example clip.
- **Not yet verified:** the train/val numbers use draft labels, and validation has only 4 matched clips. Re-run this experiment with the team's CVAT labels before quoting the numbers in the report.
- The end rule depends on the impact frame. Errors in collision detection carry over to the lane-change end.

## EXP-004a — provenance of event measurements (no change to any value or threshold)

Question: on `dada_training_type11_53` the page showed following distance 2.86 m "at 2.1 s" and collision distance 2.86 m. Are these measured at frame 21?

Finding: no. ByteTrack tracks Vehicle B in frames 10–19 only; the impact is frame 21 (image jolt). `_near(mb, f, tol=3)` filled frame 21 with frame 19's measurements.

| Displayed value | Source |
|---|---|
| collision time 2.1 s, jolt 7.1 | observed, frame 21 |
| distance at impact 2.86 m, box size 0.2807, lateral −2.04 m | frame 19 carried to 21 → inferred |
| distance 1 s before 3.43 m | observed, frame 11 |
| closing speed 0.21 m/s, min TTC 1.98 s | estimated over frames 12–19 |
| lane change end 2.1 s | inferred from the impact (last track frame 19) |
| lane change end distance 2.86 m, offset, lateral −2.14 m | frame 19 (lateral: median of 17–19) → inferred |
| following distance 2.86 m, TTC 1.98 s, size 0.2807, "Not maintained" | frame 19 → inferred |
| following closing speed 0.35 m/s | estimated over frames 16–19 |

Change: every event now carries `sources` (`observed` / `estimated` / `inferred`, source frame(s) and time; `reported_for_frame` when carried). The collision event carries `b_last_tracked_frame`. `detected_event.event_value` stores them under `_sources`. The page shows a badge per measure and a note when an event moment or its numbers are inferred. All measure values, ByteTrack, collision detection and lane-change logic and thresholds are unchanged. Tests: `tests/test_measure_sources.py`.

## EXP-005 — Wrong Vehicle B Selection (open, not solved)

**Issue.** CCD `000023` (train, lane change, annotated crash frame 38 = 3.8 s). The engine picks track 1 (truck) as Vehicle B, finds the collision at 0.3 s and no lane change. The team's visual review: Vehicle B is the car on the left.

**Ground truth used.** Approved: Vehicle B identity in `000023` (team visual review, this issue) and `dada_training_type11_53` (human-reviewed, EXP-004), plus the crash frames in `dataset_index.csv` (dataset annotations). Not ground truth: `draft_labels_with_rules.xlsx` and the CVAT review files (`build/review*`, `gtchk*`). Their `role = Vehicle B` is the engine's own pick (see `build_review_annotations.py`), so they mark the truck in `000023`. They were not used for scoring. The test split was not used.

### 1. Which track is the left car

The left car is **track 4**: one ByteTrack ID, frames 2–29. It is not fragmented into several IDs.
- **Class.** Labelled `truck` because the detector alternates car/truck on the partial, edge-cut view.
- **Frames 16–23.** The detector misses the car (no box, or confidence ≤ 0.19). ByteTrack keeps the ID and re-attaches it at frame 24.
- **After frame 29.** Lost for good. Frames 31–38 have only weak boxes (confidence 0.11–0.14) cut at the image side, about half as wide (IoU ≈ 0.37 with the last box), so neither stage of ByteTrack matches them. Frames 40–47 have no detection at all.
- **Contact.** Image jolt z = 4.9 / 7.0 at frames 39 / 40, with the recording car's heading changing +29 and +52 °/s (turning left) at the same frames. That is 10–11 frames after track 4's last box.

### 2. Why `pick_vehicle_b()` picks track 1

The score is the maximum over any frame of `box height × (1.2 − distance from image centre) × (0.5 + 0.5 × frame/n)`.

| Track | Box height | Frames | Score |
|---|---|---|---|
| 1 (truck) | 0.9 of the image | 0–9, about 3 s before the impact | 0.314 |
| 5 (grey car, right) | — | — | 0.174 |
| 4 (left car) | — | penalised for being at the image side | 0.147 |

The rule overweights **size**. It does not use **when** the vehicle is present relative to the impact. It penalises vehicles beside the recording car (a side impact) through the centre term. The time weight (≥ 0.5) is too weak to offset size.

### 3. Diagnostic with the reviewed Vehicle B forced (track 4); nothing else changed

| | B | Collision | Lane change |
|---|---|---|---|
| Current | 1 (truck) | 0.3 s (frame 3) | none |
| Forced reviewed B | 4 (left car) | 1.6 s (frame 16, a smaller jolt z 4.1) | none |
| Annotated | left car | 3.8 s (contact jolt 3.9–4.0 s) | — |

The correct B does not fix the result. The impact search only looks within 3 frames of B's boxes, and track 4 has none after frame 29. Track 4's sideways position stays at −3.8…−4.3 m while tracked, so no lane change of B can be measured. The sideways movement at the impact is the recording car's sharp left turn (frames 39–40). **A second cause, separate from selection, is proven:** losing an edge-cut vehicle close to the recording car (detector and tracker).

### 4. Candidate improvement, evaluated (not adopted)

**Idea (generalizable, no side or ID rule).** Anchor on the strongest image jolt, which does not depend on B. Score each track by:
- its box size over its last 10 frames up to the jolt;
- `exp(−gap/10)`, where gap = frames between the track's last box and the jolt;
- closing speed;
- continuity.

Collision, lane-change and ByteTrack code were unchanged.

**Results on train/val.** Crash frame vs annotation, within 5 frames:

| Variant | Train (101) | Val (22) | B changed |
|---|---|---|---|
| Current | 69 | 18 | — |
| Best candidate | 72 | **16 (regression)** | 22 train + 5 val clips, unreviewed |

Other variants (size + jolt + continuity at the track's own impact) were unstable. They picked tracks 6, 4 or 1 on `000023`, and train got worse (63–69).

**On the reviewed clips:**
- `dada_53`: B = 4 in every variant (correct).
- `000023`: the candidate picks **track 5** (the grey car on the right, closing at about 5 m/s, last box at frame 36). Its collision is 3.9 s, close to the annotated 3.8 s, but it is **not the reviewed B (track 4)**.

So the candidate is right on 1 of 2 reviewed clips, the same as the current rule, and regresses on validation. It is not adopted.

**Clips where the candidate changes B (for review, not ground truth).**
- Train: 000023, 000036, 000177, 000324, 000335, 000371, 000465, 000632, 000932, 001264, 001267, 001355, 001461, dada_testing_type11_107, dada_training_type11_11, dada_training_type11_12, dada_training_type11_17, dada_training_type11_45, dada_training_type11_5, dada_training_type11_52, dada_training_type11_66, dada_validation_type11_90.
- Val: 000358, 000854, 001062, dada_training_type11_37, dada_validation_type11_81.

### 5. Status and next steps

- **Status.** No engine change. ByteTrack, collision and lane-change thresholds are unchanged.
- **Tests.** `tests/test_vehicle_b_selection.py`, using track fixtures in `tests/data/`.
  - Passing guards: reviewed `dada_53` B = 4; a cutting-in car that ends close is picked over an early truck.
  - `xfail(strict)`, open on purpose: an early huge truck beats a smaller maneuvering car; `000023` should pick track 4; with track 4 the impact should be found.
- **Next.**
  1. Review B on more clips, starting with the list above. One reviewed clip with a known failure cannot validate a rule.
  2. A later experiment: keep an edge-cut vehicle that is lost while beside the recording car (weak side-cut boxes in frames 31–38), so the impact and B's last movement can be measured.
  3. Revisit the selection only when there are enough reviewed B labels.

## EXP-006 — Early Lane Change Onset in 000152 (diagnosed; no engine change)

**Issue.** CCD `000152` (train). Human-reviewed: Vehicle B = white hatchback on the right moving left; lane change frames 16–37; collision frame 37. Siyaq: B = track 1, lane change 2–34 (left), collision 34, lateral shift 6.53 m, distance 14.88 → 2.61 m. The predicted start is 14 frames early. (`dataset_index.csv` gives crash frame 32 for this clip, not 37.)

### 1. Vehicle B
Track 1 is the white hatchback: one ByteTrack ID, frames 0–49, checked on the overlay frame by frame. From frame 24 its box also takes in part of the parked car next to it (track 5), so it is a little too wide. B is correct.

### 2. Why `_lane_change_bounds()` started at frame 2
- `p` is the frame where B is widest from the lane: frame 0, smoothed lateral 8.1 m.
- Inward speed (smoothed lateral, ±2 frames) is 1.9–3.8 m/s from frame 2 onwards. The peak is at frame 5 (3.75 m/s). It never drops below `LANE_ONSET_MPS` = 0.4 before frame 16 (lowest 1.8 m/s).
- Going back from the peak while speed ≥ 0.4 stops at frame 2. Frames 0–1 have no speed yet (±2 window).

So the rule worked as written: B's sideways position shrinks steadily from the start of the clip.

### 3. Perspective and approach vs real sideways movement (track 1, frames 0–31)

| Check | Frames 0–15 | Frames 16–31 |
|---|---|---|
| Box left (inner) edge x1, px | 436 → 435 (flat) | 431 → 347 |
| Box right (outer) edge x2, px | 496 → 555 | 560 → 626 |
| Box height, px | 28 → 60 | 64 → 163 |
| Box centre, px | 466 → 495 (moves **outwards**) | 496 → 486 |
| Optical flow inside box (dx, px/frame) | +0.5…+2.8 (outwards) | +3.3 → −8 (inwards from frame 23) |
| Lateral (box-size metric), m | 8.03 → 4.54 | 4.23 → 1.59 |
| Edge flag | none | none (from frame 32: right side) |
| Ego motion (yaw, background dx) | ~0 | ~0 |
| Ego lane lines (TwinLiteNet), x at row 0.6 | stable (0.39 / 0.70); vanishing point x≈313, y≈130 | right line hidden by B after frame 14 |
| B's inner edge, lane widths outside ego's right line (box bottom row) | 0.89 → 0.15 | 0.07 (f16), 0.01 (f17), −0.05 (f18) … −0.32 |

- **The trend is not an approach/perspective artefact.** A car keeping the same sideways position would move outwards in the image in step with its box height. Its offset from the vanishing point would grow ×2.1 between frames 0 and 15, putting the box centre at about x=641, off the image. The real centre goes only from 466 to 495. Measured against the ego lane lines, with no camera height, FOV or car-height assumption, B's inner edge closes on the lane line from frame 3. The recording car is not drifting: its lane lines are stable and yaw is about 0. Either B drifts left slowly from the start, or its lane converges towards ours. Monocular geometry cannot tell these two apart.
- **The size is inflated by the distance estimate.** The box-size lateral overstates the shift at long range (8.1 m at about 14 m, against about 5.9 m from the lane lines). The reported 6.53 m shift and the early speeds (up to 3.75 m/s) are therefore too large. This affects magnitudes, not the onset frame.

### 4. Onset definition vs human annotation
- The written protocol (Part 1 README) only names the tags `lane_change_start` / `lane_change_end`. It does not define them. EXP-004 assumed start = "B starts moving in".
- On both human-reviewed clips, the human start is about one frame before B's near edge reaches the ego lane line:

| Clip | Engine (motion onset) | Near edge reaches ego line | Human start |
|---|---|---|---|
| `dada_training_type11_53` | 14 | between 15 and 16 | 15 |
| `000152` | 2 | between 17 and 18 | 16 |

  - On `dada_53` motion onset and lane entry coincide, so the current rule agrees.
  - On `000152` B creeps towards the lane for 1.5 s before entering it. The engine marks the creep; the human marks the entry.
- **Defect:** a definition mismatch, generalizable to any slow approach before a cut-in. It is not a perspective bug.

### 5. Candidate correction, tested (not adopted)
**Rule.** Start = the last frame B's near box edge is still outside the ego lane line on its side (TwinLiteNet lines, nearest analysed frame within 20 frames). Used only when it is later than the motion onset; otherwise the current rule. No offsets, no clip-specific rule. End, ByteTrack, collision and thresholds are unchanged.

**Human-approved, train only (n = 2).** Both clips were used to form the hypothesis, so this is in-sample, not validation.

| Version | Start MAE | tIoU |
|---|---|---|
| Current | 7.5 | 0.653 |
| Candidate | 0.5 (`dada_53` 15, `000152` 17) | 0.847 |

**Draft labels (not reviewed; reported separately).** The rule could only apply where lane lines exist on B's side: 7 of 36 B lane changes.

| Split | Version | n | Start MAE | tIoU |
|---|---|---|---|---|
| Train | Current | 22 | 10.09 | 0.510 |
| Train | Candidate | 22 (7 changed) | 9.36 | 0.499 (slightly lower) |
| Val | Current | 4 | 4.25 | 0.407 |
| Val | Candidate | 4 (0 changed) | 4.25 | 0.407 |

Changed train clips (start current → candidate, draft start):
- Closer to the draft: `000454` (0 → 11, draft 24), `000734` (13 → 15, 20).
- Further from the draft: `000195` (17 → 25, 20), `dada_validation_type10_51` (6 → 18, 8).
- Same error size: `dada_training_type11_63` (16 → 31, 24).

**Held-out reviewed validation:** none exists yet. No validation clip has a human-reviewed lane change, so the single held-out evaluation could not be run.

**Decision.** Not merged.
- The only supporting evidence is the 2 clips that produced the hypothesis.
- Draft results are mixed.
- The start definition is a protocol decision.
- `dada_training_type11_53` stays at 14–21.

### 6. Next
1. The team writes the start definition into the labelling protocol, for example "first frame B's wheels/near edge reach the line of the recording car's lane", and reviews lane changes on validation clips.
2. Then run the candidate once on those clips. Lane lines must exist over B's whole approach; today they are read only in the last 5 s before the impact, every 2nd frame.
3. Separately, the box-size lateral scale is inflated at long range. Reporting the shift in lane widths (from the lane lines) would be more reliable than metres.

## EXP-007 — Frozen baseline (no change)

**Purpose.** Freeze the current engine (commit `d3ea9c2`) as the reference for all later tuning, using the new experiment framework (`tools/run_experiment.py`). Training (101) and Validation (22) clips. The Test split was not run.

**Results** (full tables in Section 5.1 of the GP report (Word, kept outside the repository); per-clip outputs in `results/EXP-007_*`):

| Measure | Reference | Train | Val |
|---|---|---|---|
| Collision within ±0.5 s | Source annotation | 68.3 % (n = 101; 2 without prediction) | 81.8 % (n = 22) |
| Vehicle B correct | Human-reviewed | 2/3 | Pending |
| Lane change F1 / mean tIoU | Human-reviewed | 1.00 / 0.653 (n = 2) | Pending |
| Lane change F1 / mean tIoU | Draft (unreviewed) | 0.44 / 0.510 | 0.23 / 0.407 |
| Processing time per clip | — | 16.0 s mean (2-core CPU) | 15.9 s |

The draft-label lane-change numbers match the values recorded after EXP-004, so the framework reproduces the earlier result.

**Decision.** Frozen as the baseline. The next experiments start from the open failures listed in Section 5.1 of the report draft.
