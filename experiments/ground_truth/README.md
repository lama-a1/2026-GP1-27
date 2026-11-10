# Reference labels and their status

Siyaq uses four kinds of reference data. Only the last one is verified ground truth.

| Level | File / source | Who made it | Use in evaluation |
|---|---|---|---|
| 1. Original source annotations | `dataset_index.csv` (`crash_start_frame`, weather, time of day, ego involvement) from CCD and DADA-2000 | Dataset authors (crash frames re-computed after trimming DADA clips) | Collision timing, reported as "source annotation" |
| 2. Automatic pre-annotations | `Siyaq_Part1/cvat/preannotations.zip` and the CVAT exports `Task1-3.zip` | YOLOv8 + ByteTrack (Ultralytics), imported into CVAT | **Not used as reference.** The CVAT exports of 4 Nov 2026 contain only imported tracks (`source="file"`, every box `Other vehicle`, 0 tags) |
| 3. Unreviewed draft labels | `Siyaq_Part1/labeling/draft_labels.xlsx` | Generative-AI-assisted drafting from frame sheets | Reported separately as **draft-label agreement**, never as accuracy |
| 4. Human-reviewed ground truth | `human_reviewed.json` (this folder) | Siyaq team | The only **verified** reference. 3 train clips so far, 0 validation, 0 test |

When the team finishes reviewing in CVAT, export each task (CVAT for video 1.1), split it per clip with `Siyaq_Part1/cvat/split_export.py`, and add the approved clips here. Do not add a clip before a second member has approved it.
