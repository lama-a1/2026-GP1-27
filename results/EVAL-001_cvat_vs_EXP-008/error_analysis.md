# Error analysis — EVAL-001_cvat_vs_EXP-008

| Field | OK | System error | Annotation missing | Annotation conflict | Pending definition |
|---|---|---|---|---|---|
| collision | 23 | 6 | 0 | 0 | 0 |
| vehicle_b | 20 | 9 | 0 | 0 | 0 |
| lane_change | 13 | 14 | 0 | 2 | 0 |
| sudden_stop | 20 | 9 | 0 | 0 | 0 |
| safe_distance | 4 | 5 | 11 | 0 | 9 |
| accident_type | 0 | 0 | 0 | 1 | 0 |

| Clip | Type | Field | Reference | Prediction | Difference | Category | Likely cause |
|---|---|---|---|---|---|---|---|
| 000004 | Rear-end | vehicle_b | labelled B | track 1 | identity OK (IoU 0.965); not at impact | System error | correct vehicle; no predicted B box within 3 frames of the impact (boxes at frames 0-37, measured 38 frames) |
| 000004 | Rear-end | sudden_stop | 32-41 | none | missed | System error | lowest TTC of B in the labelled window 2.08 s (rule: < 1.6 s) |
| 000117 | Rear-end | vehicle_b | labelled B | track 2 | identity OK (IoU 0.909); not at impact | System error | correct vehicle; no predicted B box within 3 frames of the impact (boxes at frames 0-28, measured 29 frames) |
| 000117 | Rear-end | sudden_stop | none | 17-31 | spurious | System error | TTC below the threshold without a labelled stop |
| 000117 | Rear-end | safe_distance | Not maintained | Maintained | disagree | Pending definition | label is the judgement at the impact; the system verdict uses image size of B at one earlier frame |
| 000152 | Lane-change | lane_change | 5-37 left | 2-34 left | tIoU 0.833 | Annotation conflict | approved review gives 16-37 |
| 000152 | Lane-change | safe_distance | Unclear | Not maintained |  | Annotation missing | label is Unclear |
| 000308 | Lane-change | collision | 30 | 17 | -13 | System error | Vehicle B not tracked within 3 frames of the impact (tracked 0-19); strongest image jolt at frame 28 |
| 000308 | Lane-change | vehicle_b | labelled B | track 1 | identity OK (IoU 0.884); not at impact | System error | correct vehicle; no predicted B box within 3 frames of the impact (boxes at frames 0-19, measured 16 frames) |
| 000308 | Lane-change | lane_change | 24-30 left | none | missed | System error | no lane-change event; Vehicle B tracked in 16 frames |
| 000308 | Lane-change | safe_distance | Unclear | Maintained |  | Annotation missing | label is Unclear |
| 000324 | Rear-end | collision | 31 | 46 | 15 | System error | Vehicle B not tracked within 3 frames of the impact (tracked 42-49); strongest image jolt at frame 8 |
| 000324 | Rear-end | vehicle_b | labelled B | track 5 | identity OK (IoU 0.786); not at impact | System error | correct vehicle; no predicted B box within 3 frames of the impact (boxes at frames 42-49, measured 8 frames) |
| 000324 | Rear-end | sudden_stop | 18-31 | none | missed | System error | no TTC for B in the labelled window (B not tracked) |
| 000324 | Rear-end | safe_distance | Not maintained | none |  | System error | no following-distance verdict |
| 000454 | Lane-change | lane_change | 24-35 right | 0-35 right | tIoU 0.333, start -24, end +0 | System error | onset earlier than the label (EXP-006 definition) |
| 000454 | Lane-change | safe_distance |  |  |  | Annotation missing | no safe_distance tag |
| 000465 | Rear-end | collision | 30 | 41 | 11 | System error | Vehicle B not tracked within 3 frames of the impact (tracked 41-49); strongest image jolt at frame 31 |
| 000465 | Rear-end | vehicle_b | labelled B | track 11 | identity OK (IoU 0.609); not at impact | System error | correct vehicle; no predicted B box within 3 frames of the impact (boxes at frames 41-49, measured 9 frames) |
| 000465 | Rear-end | sudden_stop | 20-30 | none | missed | System error | no TTC for B in the labelled window (B not tracked) |
| 000465 | Rear-end | safe_distance | Not maintained | none |  | System error | no following-distance verdict |
| 000727 | Rear-end | lane_change |  |  |  | Annotation conflict | lane change tagged in a rear-end clip |
| 001264 | Lane-change | collision | 40 | 24 | -16 | System error | Vehicle B not tracked within 3 frames of the impact (tracked 0-27); strongest image jolt at frame 48 |
| 001264 | Lane-change | vehicle_b | labelled B | track 1 | identity OK (IoU 0.953); not at impact | System error | correct vehicle; no predicted B box within 3 frames of the impact (boxes at frames 0-27, measured 27 frames) |
| 001264 | Lane-change | lane_change | 25-40 left | none | missed | System error | no lane-change event; Vehicle B tracked in 27 frames |
| 001269 | Rear-end | safe_distance | Not maintained | Maintained | disagree | Pending definition | label is the judgement at the impact; the system verdict uses image size of B at one earlier frame |
| dada_testing_type11_107 | Rear-end | sudden_stop | 25-35 | none | missed | System error | no TTC for B in the labelled window (B not tracked) |
| dada_testing_type11_107 | Rear-end | safe_distance | Maintained | none |  | System error | no following-distance verdict |
| dada_testing_type11_107 | Rear-end | accident_type | Rear-end | Lane-change (dataset index, draft) | differs | Annotation conflict | CVAT label differs from the draft accident type in dataset_index.csv |
| dada_training_type10_48 | Lane-change | lane_change | 24-35 left | none | missed | System error | no lane-change event; Vehicle B tracked in 25 frames |
| dada_training_type10_48 | Lane-change | safe_distance |  |  |  | Annotation missing | no safe_distance tag |
| dada_training_type11_16 | Rear-end | lane_change | none (rear-end) | 21-37 right | spurious | System error | lane change reported in a rear-end clip |
| dada_training_type11_16 | Rear-end | sudden_stop | 24-36 | none | missed | System error | not checked: the rule skips sudden stop when a lane change by B is reported (here a spurious one) |
| dada_training_type11_16 | Rear-end | safe_distance | Not maintained | Maintained | disagree | Pending definition | label is the judgement at the impact; the system verdict uses image size of B at one earlier frame |
| dada_training_type11_29 | Rear-end | sudden_stop | 23-35 | none | missed | System error | lowest TTC of B in the labelled window 29.00 s (rule: < 1.6 s) |
| dada_training_type11_29 | Rear-end | safe_distance | Not maintained | none |  | System error | no following-distance verdict |
| dada_training_type11_53 | Lane-change | safe_distance | Maintained | Not maintained | disagree | Pending definition | label is the judgement at the impact; the system verdict uses image size of B at one earlier frame |
| dada_training_type12_1 | Lane-change | lane_change | 28-40 left | 31-40 right | tIoU 0.769, start +3, end +0 | System error | wrong direction |
| dada_training_type12_1 | Lane-change | safe_distance |  |  |  | Annotation missing | no safe_distance tag |
| dada_training_type12_7 | Lane-change | collision | 34 | 41 | 7 | System error | Vehicle B not tracked within 3 frames of the impact (tracked 44-49); strongest image jolt at frame 36 |
| dada_training_type12_7 | Lane-change | vehicle_b | labelled B | track 1 | identity OK (IoU 0.828); not at impact | System error | correct vehicle; no predicted B box within 3 frames of the impact (boxes at frames 44-49, measured 6 frames) |
| dada_training_type12_7 | Lane-change | lane_change | 27-34 left | none | missed | System error | no lane-change event; Vehicle B tracked in 6 frames (short track) |
| dada_training_type12_7 | Lane-change | safe_distance | Maintained | none |  | System error | no following-distance verdict |
| dada_validation_type11_73 | Lane-change | lane_change | 28-35 left | 11-36 left | tIoU 0.308, start -17, end +1 | System error | onset earlier than the label (EXP-006 definition) |
| dada_validation_type11_73 | Lane-change | safe_distance | Maintained | Not maintained | disagree | Pending definition | label is the judgement at the impact; the system verdict uses image size of B at one earlier frame |
| dada_validation_type11_90 | Lane-change | lane_change | 16-35 left | 8-35 left | tIoU 0.714, start -8, end +0 | System error | onset earlier than the label (EXP-006 definition) |
| dada_validation_type11_90 | Lane-change | safe_distance |  |  |  | Annotation missing | no safe_distance tag |
| dada_testing_type11_104 | Rear-end | safe_distance | Not maintained | Maintained | disagree | Pending definition | label is the judgement at the impact; the system verdict uses image size of B at one earlier frame |
| dada_testing_type11_112 | Rear-end | safe_distance | Not maintained | Maintained | disagree | Pending definition | label is the judgement at the impact; the system verdict uses image size of B at one earlier frame |
| dada_testing_type11_114 | Lane-change | collision | 35 | 46 | 11 | System error | B tracked at the impact; strongest jolt at frame 48, chosen frame 46: check visually |
| dada_testing_type11_114 | Lane-change | lane_change | 16-35 left | none | missed | System error | no lane-change event; Vehicle B tracked in 30 frames |
| dada_testing_type11_114 | Lane-change | safe_distance | Unclear | Not maintained |  | Annotation missing | label is Unclear |
| dada_training_type11_11 | Lane-change | lane_change | 20-35 unclear | none | missed | System error | no lane-change event; Vehicle B tracked in 50 frames |
| dada_training_type11_11 | Lane-change | safe_distance |  |  |  | Annotation missing | no safe_distance tag |
| dada_training_type11_18 | Rear-end | vehicle_b | labelled B | track 1 | identity OK (IoU 0.925); not at impact | System error | correct vehicle; B box present at the impact but IoU 0.27 (box off) |
| dada_training_type11_18 | Rear-end | safe_distance | Not maintained | Maintained | disagree | Pending definition | label is the judgement at the impact; the system verdict uses image size of B at one earlier frame |
| dada_training_type11_31 | Rear-end | lane_change | none (rear-end) | 7-37 left | spurious | System error | lane change reported in a rear-end clip |
| dada_training_type11_31 | Rear-end | sudden_stop | 28-35 | none | missed | System error | not checked: the rule skips sudden stop when a lane change by B is reported (here a spurious one) |
| dada_training_type11_31 | Rear-end | safe_distance |  |  |  | Annotation missing | no safe_distance tag |
| dada_training_type11_41 | Rear-end | lane_change | none (rear-end) | 12-34 right | spurious | System error | lane change reported in a rear-end clip |
| dada_training_type11_41 | Rear-end | sudden_stop | 28-41 | none | missed | System error | not checked: the rule skips sudden stop when a lane change by B is reported (here a spurious one) |
| dada_training_type11_41 | Rear-end | safe_distance | Not maintained | Maintained | disagree | Pending definition | label is the judgement at the impact; the system verdict uses image size of B at one earlier frame |
| dada_training_type11_45 | Lane-change | lane_change | 20-29 left | none | missed | System error | no lane-change event; Vehicle B tracked in 14 frames (short track) |
| dada_training_type11_45 | Lane-change | safe_distance |  |  |  | Annotation missing | no safe_distance tag |
| dada_training_type11_59 | Lane-change | vehicle_b | labelled B | track 2 | mean IoU 0.14 | System error | predicted B overlaps the labelled B only near the end (IoU at collision 0.547): another vehicle or a looser box; check visually |
| dada_training_type11_59 | Lane-change | safe_distance | Unclear | Maintained |  | Annotation missing | label is Unclear |
