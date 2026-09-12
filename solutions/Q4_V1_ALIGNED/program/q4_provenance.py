"""Content hashes for provisional Q4, including portable Q2 dependencies."""
import hashlib
import json
from pathlib import Path
import subprocess
from q4_core import ROOT, VERSION

PINNED_RUN = "q2v3-r2-full-b0-a-20260913-01"
PINNED_COMMIT = "17f25a508deaf7f9248ef18c3b498be12f5c083a"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+"\n", encoding="utf-8")


def upstream_path():
    portable = ROOT / "solutions/Q3_Q4_JOINT/results/q2_provisional"
    return portable if (portable / "manifest.json").exists() else ROOT / "runs" / PINNED_RUN


def verify_q2():
    run = upstream_path()
    m = json.loads((run / "manifest.json").read_text())
    if sha256(run / "manifest.json") != "d3b7453440b36ed32785ef5108a3b908634fa460472826ecfdf84d78f7463728":
        raise ValueError("Q2 manifest hash mismatch")
    if m["status"] != "complete" or m["git_commit"] != PINNED_COMMIT:
        raise ValueError("Q2 provisional identity mismatch")
    for key, expected in {"forecast_arm": "B0", "scoring_mode": "A", "scenario_count": 10,
        "time_mapping": "A", "battery_interpretation": "A", "observation_delay_slots": 0,
        "compatibility_reset_on_report_start": False}.items():
        if m["configuration"][key] != expected:
            raise ValueError(f"Q2 config mismatch: {key}")
    for key, expected in m["source_hashes"].items():
        if sha256(ROOT / key) != expected:
            raise ValueError(f"Q2 live source mismatch: {key}")
        blob = subprocess.check_output(["git", "show", f"{PINNED_COMMIT}:{key}"], cwd=ROOT)
        if hashlib.sha256(blob).hexdigest() != expected:
            raise ValueError(f"Q2 commit source mismatch: {key}")
    for field, base in (("input_hashes", ROOT), ("outputs", run)):
        for key, expected in m[field].items():
            path = (base / key).resolve()
            if not path.is_relative_to(base.resolve()) or sha256(path) != expected:
                raise ValueError(f"Q2 {field} mismatch: {key}")
    return {"upstream_version": "Q2_V3_CAUSAL_FORECAST", "run_id": PINNED_RUN,
            "source_commit": PINNED_COMMIT, "source_hashes": m["source_hashes"],
            "manifest_sha256": sha256(run / "manifest.json"), "path": str(run.relative_to(ROOT)),
            "formal_use": False, "p2_status": "USER_DEFERRED_RESET_PACKAGING",
            "authorization": "reports/q3_q4_joint_iteration_contract.md"}


def source_snapshot():
    paths = list((VERSION / "program").rglob("*.py"))
    for name in ("Q2_V3_CAUSAL_FORECAST", "Q3_V3_ALIGNED"):
        paths += list((ROOT / "solutions" / name / "program").glob("*.py"))
    paths += [ROOT / "题目分析报告.md", ROOT / "术语表格.md", ROOT / "reports/q3_q4_joint_iteration_contract.md"]
    return {str(p.relative_to(ROOT)): sha256(p) for p in sorted(paths)}


def input_snapshot():
    paths = [ROOT / "data" / f"附件{n}.xlsx" for n in range(1, 5)]
    paths += [ROOT / "data/附件5" / f"result4-{n}.xlsx" for n in (2, 3)]
    hashes = {str(p.relative_to(ROOT)): sha256(p) for p in paths}
    frozen = {entry["path"]: entry["sha256"] for entry in json.loads((ROOT / "data_manifest.json").read_text())["files"]}
    for name, value in hashes.items():
        if frozen.get(name) != value:
            raise ValueError(f"frozen attachment hash mismatch: {name}")
    return hashes
