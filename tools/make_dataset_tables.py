"""Dataset tables and figure for GP report Section 4.4.3, generated from dataset_index.csv.

    python tools/make_dataset_tables.py --dataset /path/to/Siyaq_Part1/dataset [--weather-flags clip_job_map.csv]
"""
import argparse, collections, csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_T = ROOT / "docs" / "gp_report" / "tables"
OUT_F = ROOT / "docs" / "gp_report" / "figures"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--weather-flags", default="")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(Path(a.dataset) / "dataset_index.csv")))
    flags = set()
    if a.weather_flags and Path(a.weather_flags).exists():
        flags = {r["clip_id"] for r in csv.DictReader(open(a.weather_flags)) if (r.get("weather_check") or "").strip()}
    OUT_T.mkdir(parents=True, exist_ok=True); OUT_F.mkdir(parents=True, exist_ok=True)
    splits, types, sources = ["train", "val", "test"], ["Rear-end", "Lane-change"], ["CCD", "DADA-2000"]
    c = collections.Counter((r["accident_type"], r["source"], r["split"]) for r in rows)
    L = ["| Accident type | Source | Train | Validation | Test | Total |", "|---|---|---:|---:|---:|---:|"]
    for t in types:
        for s in sources:
            v = [c[(t, s, sp)] for sp in splits]
            L.append(f"| {t} | {s} | {v[0]} | {v[1]} | {v[2]} | {sum(v)} |")
        v = [sum(c[(t, s, sp)] for s in sources) for sp in splits]
        L.append(f"| **{t} total** | | **{v[0]}** | **{v[1]}** | **{v[2]}** | **{sum(v)}** |")
    v = [sum(1 for r in rows if r["split"] == sp) for sp in splits]
    L.append(f"| **All clips** | | **{v[0]}** | **{v[1]}** | **{v[2]}** | **{sum(v)}** |")
    night = collections.Counter(r["split"] for r in rows if r["time_of_day"] == "Night")
    L.append(f"| Night clips (subset) | | {night['train']} | {night['val']} | {night['test']} | {sum(night.values())} |")
    if flags:
        fl = collections.Counter(r["split"] for r in rows if r["clip_id"] in flags)
        L.append(f"| Snow/rain seen in review, decision pending (subset) | | {fl['train']} | {fl['val']} | {fl['test']} | {sum(fl.values())} |")
    (OUT_T / "table_dataset_distribution.md").write_text(
        "Table X. Siyaq dataset distribution by accident type, source and split (generated from dataset_index.csv).\n\n" + "\n".join(L) + "\n")
    nf = collections.Counter(r["num_frames"] for r in rows)
    (OUT_T / "table_dataset_format.md").write_text(
        "Table X. Video format after preprocessing (from dataset_index.csv and the video files).\n\n"
        "| Property | CCD clips | DADA-2000 clips |\n|---|---|---|\n"
        "| Count | %d | %d |\n" % (sum(r["source"] == "CCD" for r in rows), sum(r["source"] == "DADA-2000" for r in rows)) +
        "| Resolution | 1280 x 720 | 792 x 330 (DADA-2000 'small' release) |\n"
        "| Frame rate | 10 fps (as released) | 10 fps (resampled from 30 fps) |\n"
        "| Length | 50 frames (5 s) | 5 s window around the accident; %s |\n" %
        ", ".join(f"{k} frames: {v}" for k, v in sorted(nf.items(), key=lambda x: -int(x[0]))) +
        "| Container / codec | MP4 (MPEG-4 Part 2) | MP4 (H.264), converted from AVI |\n| Audio | none | none |\n")
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=200)
    colors = {("Rear-end", "CCD"): "#2f6b45", ("Rear-end", "DADA-2000"): "#7fb08f",
              ("Lane-change", "CCD"): "#41618f", ("Lane-change", "DADA-2000"): "#93a9c9"}
    names = ["Train", "Validation", "Test"]
    bottom = [0, 0, 0]
    for t in types:
        for s in sources:
            v = [c[(t, s, sp)] for sp in splits]
            ax.bar(names, v, bottom=bottom, color=colors[(t, s)], label=f"{t} - {s}", width=0.55, edgecolor="white", linewidth=0.8)
            for i, x in enumerate(v):
                if x >= 4:
                    ax.text(i, bottom[i] + x / 2, str(x), ha="center", va="center", fontsize=8, color="white")
            bottom = [b + x for b, x in zip(bottom, v)]
    for i, b in enumerate(bottom):
        ax.text(i, b + 1.5, str(b), ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylabel("Number of clips"); ax.set_ylim(0, max(bottom) * 1.15)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    fig.tight_layout(); fig.savefig(OUT_F / "fig_dataset_distribution.png"); print("ok", len(rows))


if __name__ == "__main__":
    main()
