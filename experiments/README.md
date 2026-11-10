# Siyaq experiments

Every change to the analysis engine (`siyaq_cv/`) is made as a recorded experiment, so the GP report can trace each number back to a run.

## Folder contents

| Path | Content |
|---|---|
| `EXPERIMENT_LOG.csv` | One row per experiment: hypothesis, change, baseline, commit, splits, reference levels, key results, decision |
| `configs/<EXP>.json` | Full engine configuration used by the experiment, with the overridden values |
| `ground_truth/human_reviewed.json` | The only verified reference labels (team-reviewed). See `ground_truth/README.md` for the four evidence levels |
| `dataset/` | Final dataset (137 clips): `dataset_index.csv`, `splits/`, `excluded_clips.csv`, `clip_job_map_v2.csv` (CVAT jobs, with the 12 excluded jobs marked), duplicate and leakage checks |
| `history/` | Evidence for experiments run before this framework existed (HIST-02 tracker comparison, duplicate check) |
| `../results/<EXP>_<clip>/` | `prediction.json`, `comparison.json`, `diagnostics.csv`, `run_metadata.json` per clip |
| `../results/<EXP>_SUMMARY/metrics.json` | Aggregate metrics per split and evidence level |
| `../docs/EXPERIMENT_LOG.md` | Narrative write-up of each investigation (diagnosis, tables, decision) |

## Running an experiment

```bash
# baseline (no change)
python tools/run_experiment.py --exp-id EXP-007 --title "Frozen baseline" \
  --dataset ~/Downloads/Siyaq_Part1/dataset --splits train,val \
  --draft-labels ~/Downloads/Siyaq_Part1/labeling/draft_labels.xlsx

# one controlled change, tuned on train only
python tools/run_experiment.py --exp-id EXP-008 --title "..." --baseline EXP-007 \
  --dataset ~/Downloads/Siyaq_Part1/dataset --splits train \
  --set LANE_ONSET_MPS=0.5 --hypothesis "..." --draft-labels ...

# report tables and figures for Section 5.1
python tools/report_tables.py --exp EXP-008 --baseline EXP-007
```

## Rules

1. **One change at a time.** Change one thing per experiment, and compare it with a named baseline.
2. **Split roles.** Tune on `train`. Look at `val` once, after the choice is made. A change that improves train but degrades val is not adopted.
3. **Test split.** `test` is for the final frozen evaluation only. `run_experiment.py` refuses it without `--final`.
4. **Evidence levels.** Never mix evidence levels in one number. Human-reviewed ground truth is reported as accuracy. Draft labels are reported only as "agreement with unreviewed draft labels". Source crash frames are reported as "source annotation".
5. **No invented values.** A metric without approved ground truth is written `Pending approved Ground Truth`.
6. **Record every run.** Record the decision (accepted / reverted / open) in `EXPERIMENT_LOG.csv` and `docs/EXPERIMENT_LOG.md`, and add a regression test for the clip that motivated the change.
7. **Repeatability.** Results are only comparable when the code commit, model hashes and library versions in `run_metadata.json` match. Re-run the baseline after changing library versions.

## Experiment IDs

- `HIST-xx`: reconstructed from git history, before this framework existed.
- `SIYAQ-BUG-xxx`: bug investigations.
- `EXP-xxx`: numbered experiments. EXP-001 to EXP-003 were not recorded in the repository.
