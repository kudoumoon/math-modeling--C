"""Visualize prespecified Q3 release schedules from an existing summary."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--figure-dir", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.figure_dir.exists() or args.result_dir.exists():
        raise FileExistsError("Do not overwrite figure evidence")
    summary = json.loads(args.summary.read_text())
    keys = ["baseline", "A_6", "A_6_12", "A"]
    labels = ["Fixed Q2 contract", "06:00", "06:00 + 12:00", "06:00 + 12:00 + 18:00"]
    frame = pd.DataFrame([{"variant": k, "schedule": label,
        "cash_cost_yuan": summary[k]["total_cost_yuan"],
        "emergency_kwh": summary[k]["emergency_kwh"],
        "end_soc_kwh": summary[k]["end_soc_kwh"],
        "accepted_releases": summary[k]["accepted_releases"]} for k, label in zip(keys, labels)])
    frame["saving_vs_fixed_contract_yuan"] = frame.cash_cost_yuan.iloc[0]-frame.cash_cost_yuan
    args.result_dir.mkdir(parents=True)
    args.figure_dir.mkdir(parents=True)
    frame.to_csv(args.result_dir / "q3_release_value.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), layout="constrained")
    colors = ["#697275", "#337EAA", "#B64B65", "#22856F"]
    positions = np.arange(len(frame))
    for ax, column, ylabel in [(axes[0], "saving_vs_fixed_contract_yuan", "Cash saving (10,000 yuan)"),
                               (axes[1], "emergency_kwh", "Emergency purchase (10,000 kWh)")]:
        values = frame[column].to_numpy()/10000
        ax.barh(positions, values, color=colors)
        ax.set_yticks(positions, labels)
        ax.invert_yaxis()
        ax.set_xlabel(ylabel)
        ax.set_xlim(0, max(values)*1.22)
        ax.grid(axis="x", alpha=.2)
        ax.set_axisbelow(True)
        for y, value in zip(positions, values):
            ax.text(value+max(values)*.025, y, f"{value:.2f}", va="center", fontsize=9)
    fig.suptitle("Q3: value of prespecified intraday release schedules (settlement A)", fontsize=11)
    fig.savefig(args.figure_dir / "q3_release_value.png", dpi=180)
    fig.savefig(args.figure_dir / "q3_release_value.pdf")
    plt.close(fig)
    metadata = {"summary": str(args.summary), "summary_sha256": hashlib.sha256(args.summary.read_bytes()).hexdigest(),
        "selection_allowed": False, "model_rerun": False,
        "figures": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in args.figure_dir.iterdir()}}
    (args.result_dir / "figure_provenance.json").write_text(json.dumps(metadata, indent=2)+"\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
