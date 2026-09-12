"""Bind first-run evidence to a committed source tree without rerunning models."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(run, question, commit):
    manifest = json.loads((run / "manifest.json").read_text())
    expected_status = "complete" if question == "Q3" else "complete_provisional"
    checks = {"complete": manifest["status"] == expected_status,
              "formal_dependency_disclosed": manifest["formal_use"] is False}
    mismatches = []
    for relative, digest in manifest["source_hashes"].items():
        blob = subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=ROOT)
        if hashlib.sha256(blob).hexdigest() != digest or sha(ROOT / relative) != digest:
            mismatches.append(relative)
    checks["source_matches_live_and_commit"] = not mismatches
    inputs = manifest["inputs"] if question == "Q3" else manifest["input_hashes"]
    checks["input_hashes_match"] = all(sha(ROOT / p) == h for p, h in inputs.items())
    version = run.parent.parent
    output_base = run if question == "Q3" else version
    bad_outputs = [p for p, h in manifest["outputs"].items() if sha(output_base / p) != h]
    checks["output_hashes_match"] = not bad_outputs
    figure_hashes = manifest.get("figures", {})
    checks["figure_hashes_match"] = all(sha(ROOT / p) == h for p, h in figure_hashes.items())
    if question == "Q3":
        checks["run_commit_matches"] = manifest["git_commit"] == commit
    else:
        checks["sources_unchanged_during_run"] = manifest["sources_unchanged"] and manifest["source_hashes_after"] == manifest["source_hashes"]
    return {"question": question, "run": str(run.relative_to(ROOT)), "manifest_sha256": sha(run / "manifest.json"),
        "passed": all(checks.values()), "checks": checks, "source_mismatches": mismatches,
        "output_mismatches": bad_outputs, "source_files": len(manifest["source_hashes"]),
        "outputs_checked": len(manifest["outputs"]), "figures_checked_separately": len(figure_hashes),
        "source_commit": commit, "elapsed_seconds": manifest["elapsed_seconds"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--q3-run", type=Path, required=True)
    parser.add_argument("--q4-run", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Joint verification output is immutable")
    results = [verify(args.q3_run.resolve(), "Q3", args.source_commit),
               verify(args.q4_run.resolve(), "Q4", args.source_commit)]
    output = {"schema_version": 1, "source_commit": args.source_commit,
        "passed": all(r["passed"] for r in results), "questions": results,
        "model_rerun": False, "formal_use": False,
        "scope": "Source/input/output provenance audit; independent modeling score is separate"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))
    if not output["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
