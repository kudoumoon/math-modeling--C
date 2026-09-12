"""Publish byte-identical prerequisites for the user-authorized joint workflow."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
VERSION = Path(__file__).resolve().parents[1]
RUN_ID = "q2v3-r2-full-b0-a-20260913-01"
COMMIT = "17f25a508deaf7f9248ef18c3b498be12f5c083a"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    source = ROOT / "runs" / RUN_ID
    target = VERSION / "results/q2_provisional"
    provenance = VERSION / "others/q2_provisional_provenance.json"
    if target.exists() or provenance.exists():
        raise FileExistsError("Do not overwrite an upstream package")
    manifest = json.loads((source / "manifest.json").read_text())
    if (manifest["status"], manifest["run_id"], manifest["git_commit"]) != (
        "complete", RUN_ID, COMMIT
    ):
        raise ValueError("Unexpected upstream identity")
    for group in ("source_hashes", "input_hashes"):
        for relative, expected in manifest[group].items():
            if digest(ROOT / relative) != expected:
                raise ValueError(f"Live {group} mismatch: {relative}")
            if group == "source_hashes":
                blob = subprocess.check_output(["git", "show", f"{COMMIT}:{relative}"], cwd=ROOT)
                if hashlib.sha256(blob).hexdigest() != expected:
                    raise ValueError(f"Git source mismatch: {relative}")
    for relative, expected in manifest["outputs"].items():
        if digest(source / relative) != expected:
            raise ValueError(f"Output hash mismatch: {relative}")
    files = {**manifest["outputs"], "manifest.json": digest(source / "manifest.json")}
    target.mkdir(parents=True)
    for relative, expected in files.items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
        if digest(destination) != expected:
            raise ValueError(f"Copy hash mismatch: {relative}")
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(json.dumps({
        "schema_version": 1,
        "status": "PROVISIONAL_USER_AUTHORIZED_Q2_P2_DEFERRED",
        "formal_use": False,
        "source_run": str(source.relative_to(ROOT)),
        "source_commit": COMMIT,
        "portable_directory": str(target.relative_to(ROOT)),
        "files": files,
        "model_rerun": False,
        "authorization": "reports/q3_q4_joint_iteration_contract.md",
        "deferred_issue": "Q2 RESET1 finalizer boundary audit; main run is RESET0",
    }, indent=2) + "\n")
    print(json.dumps({"files": len(files), "target": str(target.relative_to(ROOT)), "hashes_passed": True}))


if __name__ == "__main__":
    main()
