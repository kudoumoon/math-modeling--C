"""Archive existing runs and package the four frozen solutions without solving."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "deliveries/final-20260913-r1"
QUESTIONS = ("Q1_BASELINE", "Q2_V3_CAUSAL_FORECAST", "Q3_V3_ALIGNED", "Q4_V1_ALIGNED")
GENERATED = {"FILE_MANIFEST.json", "PACKAGE_RECEIPT.json", "SHA256SUMS"}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files(path: Path):
    if path.is_file():
        yield path
        return
    for child in sorted(path.rglob("*")):
        if child.is_file() and not any(part in {"__pycache__", ".pytest_cache", ".git"} for part in child.parts):
            if child.suffix not in {".pyc", ".pyo", ".zip"}:
                yield child


def copy_verified(source: Path, target: Path) -> dict:
    if target.exists():
        if sha(source) != sha(target):
            raise ValueError(f"Refusing to replace different existing artifact: {target}")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if sha(source) != sha(target):
        raise ValueError(f"Copy mismatch: {target}")
    return {"source": source.relative_to(ROOT).as_posix(),
            "destination": target.relative_to(ROOT).as_posix(), "sha256": sha(target)}


def archive() -> None:
    copied = []
    q2 = ROOT / "solutions/Q2_V3_CAUSAL_FORECAST"
    annual = sorted((ROOT / "runs").glob("q2v3-r2-full-*-20260913-01"))
    development = sorted((ROOT / "runs").glob("q2v3-r2-dev-*-20260913-01"))
    if len(annual) != 5 or len(development) != 4:
        raise ValueError("Expected five annual and four development source runs")
    for group, runs in (("annual_runs", annual), ("development_runs", development)):
        for run in runs:
            manifest = json.loads((run / "manifest.json").read_text())
            if manifest.get("status") != "complete":
                raise ValueError(f"Incomplete run: {run}")
            for name, expected in manifest["outputs"].items():
                if sha(run / name) != expected:
                    raise ValueError(f"Source manifest mismatch: {run / name}")
            for source in files(run):
                copied.append(copy_verified(source, q2 / "results" / group / run.name / source.relative_to(run)))
    joint = ROOT / "solutions/Q3_Q4_JOINT"
    for question in ("Q3_V3_ALIGNED", "Q4_V1_ALIGNED"):
        for source in files(joint / "others"):
            copied.append(copy_verified(source, ROOT / "solutions" / question / "others/joint_review" / source.relative_to(joint / "others")))
    for source in files(joint / "figures/round01_q3_release_value"):
        copied.append(copy_verified(source, ROOT / "solutions/Q3_V3_ALIGNED/figures/release_value" / source.name))
    for source in files(joint / "results/round01_price_diagnostics"):
        copied.append(copy_verified(source, ROOT / "solutions/Q4_V1_ALIGNED/results/price_diagnostics" / source.name))
    snapshots = {
        "Q2_V3_CAUSAL_FORECAST": q2 / "results/annual_runs/q2v3-r2-full-b0-a-20260913-01/manifest.json",
        "Q3_V3_ALIGNED": ROOT / "solutions/Q3_V3_ALIGNED/results/q3v3-r1/manifest.json",
        "Q4_V1_ALIGNED": ROOT / "solutions/Q4_V1_ALIGNED/results/q4-v1-annual-20260913-01/manifest.json",
    }
    for question, manifest_path in snapshots.items():
        manifest = json.loads(manifest_path.read_text())
        commit = manifest.get("git_commit", manifest.get("source_commit"))
        for relative, expected in manifest["source_hashes"].items():
            content = subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=ROOT)
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError(f"Executed source mismatch: {commit}:{relative}")
            target = ROOT / "solutions" / question / "others/executed_source" / relative
            if target.exists() and sha(target) != expected:
                raise ValueError(f"Existing source snapshot differs: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            copied.append({"source": f"git:{commit}:{relative}",
                           "destination": target.relative_to(ROOT).as_posix(), "sha256": expected})
    output = RELEASE / "others/ARCHIVE_MAPPING.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"model_rerun": False, "copies": copied}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"archived_files": len(copied), "all_copy_hashes_match": True}))


def selected_files() -> list[Path]:
    roots = [ROOT / "solutions" / q for q in QUESTIONS]
    roots += [ROOT / p for p in (
        "solutions/Q3_Q4_JOINT", "data", "problem", "plan", "docs", "reports",
        "scripts", "deliveries/final-20260913-r1", "README.md", "VERSION_STATUS.json",
        "data_manifest.json", "pyproject.toml", "NOTICE.md", "使用指南.md",
        "题目分析报告.md", "术语表格.md",
        "solutions/EXPERT_REVIEW_R2/others/CONFIRMED_CONVENTIONS_v1.md",
    )]
    result = sorted({p for root in roots for p in files(root)
                     if not (p.is_relative_to(RELEASE) and p.name in GENERATED)})
    if any(p.is_symlink() for p in result):
        raise ValueError("Delivery must use regular files, not symbolic links")
    return result


def category(path: Path) -> str:
    rel = path.relative_to(ROOT)
    if path.suffix in {".py", ".m", ".sh"}:
        return "program"
    if "figures" in rel.parts or "figure" in rel.parts:
        return "figures" if path.suffix in {".png", ".svg", ".pdf"} else "others"
    if rel.parts[0] != "data" and path.suffix in {".xlsx", ".csv", ".npz"}:
        return "results"
    return "others"


def package(output: Path) -> None:
    sources = selected_files()
    entries = [{"path": p.relative_to(ROOT).as_posix(), "category": category(p),
                "bytes": p.stat().st_size, "sha256": sha(p)} for p in sources]
    manifest = {"schema_version": 1, "release_id": "final-20260913-r1",
                "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "questions": list(QUESTIONS), "model_rerun": False,
                "new_conventions_implemented": False, "files": entries}
    manifest_path = RELEASE / "others/FILE_MANIFEST.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for entry, source in zip(entries, sources):
            archive.write(source, arcname=entry["path"])
        archive.write(manifest_path, arcname=manifest_path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC check failed")
        for entry in entries:
            with archive.open(entry["path"]) as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if digest != entry["sha256"] or sha(ROOT / entry["path"]) != digest:
                raise ValueError(f"Archive/source mismatch: {entry['path']}")
        expected = {e["path"] for e in entries} | {manifest_path.relative_to(ROOT).as_posix()}
        if set(archive.namelist()) != expected or len(archive.namelist()) != len(expected):
            raise ValueError("ZIP file coverage mismatch")
    receipt = {"archive": output.name, "bytes": output.stat().st_size,
               "sha256": sha(output), "files": len(entries),
               "counts_by_category": dict(Counter(e["category"] for e in entries)),
               "crc_and_all_file_hashes_verified": True,
               "manifest_sha256": sha(manifest_path), "model_rerun": False}
    (RELEASE / "others/PACKAGE_RECEIPT.json").write_text(json.dumps(receipt, indent=2) + "\n")
    (RELEASE / "others/SHA256SUMS").write_text(f"{receipt['sha256']}  {output.name}\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("archive", "workbooks", "package"))
    parser.add_argument("--output", type=Path, default=RELEASE / "Q1-Q4-final-20260913-r1.zip")
    args = parser.parse_args()
    if args.action == "archive":
        archive()
    elif args.action == "workbooks":
        sources = {
            "result1.xlsx": "Q1_BASELINE/results/baseline/result1_v2.xlsx",
            "result2.xlsx": "Q2_V3_CAUSAL_FORECAST/results/final_v1/result2.xlsx",
            "result3.xlsx": "Q3_V3_ALIGNED/results/q3v3-r1/A/result3.xlsx",
            "result4-2.xlsx": "Q4_V1_ALIGNED/results/q4-v1-annual-20260913-01/result4-2.xlsx",
            "result4-3.xlsx": "Q4_V1_ALIGNED/results/q4-v1-annual-20260913-01/result4-3.xlsx",
        }
        mapping = [copy_verified(ROOT / "solutions" / source, RELEASE / "results" / name)
                   for name, source in sources.items()]
        (RELEASE / "others/WORKBOOK_MAPPING.json").write_text(
            json.dumps({"model_rerun": False, "copies": mapping}, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"workbooks": len(mapping), "all_hashes_match": True}))
    else:
        package(args.output)
