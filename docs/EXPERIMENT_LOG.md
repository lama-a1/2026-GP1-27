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
