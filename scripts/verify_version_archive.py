from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOL = ROOT / "solutions"
Q2 = SOL / "Q2_V2_OFFICIAL_ONLINE_RISK"
Q3 = SOL / "Q3_V2_WRONG_UPSTREAM_ARCHIVE"
Q4 = SOL / "Q4_WRONG_UPSTREAM_ARCHIVE"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


status = json.loads((ROOT / "VERSION_STATUS.json").read_text(encoding="utf-8"))
questions = status["questions"]
require(questions["Q2"]["formal_use"] is True, "Q2 must be formal")
require(questions["Q3"]["formal_use"] is False, "Q3 wrong archive must not be formal")
require(questions["Q4"]["formal_use"] is False, "Q4 wrong archive must not be formal")

identity = json.loads((Q2 / "V2_IDENTITY.json").read_text(encoding="utf-8"))
require(identity["model_id"] == "ONLINE-RISK-SP-A-S10-BATA", "Q2 V2 model mismatch")
require(abs(identity["total_cost_yuan"] - 13808033.330642482) <= 1e-6, "Q2 cost mismatch")
for name, expected in identity["core_hashes"].items():
    require(sha256(Q2 / "program" / name) == expected, f"Q2 core hash mismatch: {name}")
for name, expected in identity["result_hashes"].items():
    require(sha256(Q2 / "result" / "正式结果" / name) == expected, f"Q2 result hash mismatch: {name}")

q3_code = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in (Q3 / "program").glob("*.py"))
require("q2_pipeline_v1" in q3_code, "Q3 archive no longer demonstrates its recorded wrong upstream")
require(not (Q3 / "program" / "run_q2_online_selector.py").exists(), "Q3 archive unexpectedly contains official selector")
require((Q3 / "DO_NOT_USE_AS_FORMAL.md").exists(), "Q3 warning missing")

q4_code = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in (Q4 / "program").glob("*.py"))
require("q2_pipeline_v1" in q4_code and "q2_v2_compatible" in q4_code, "Q4 wrong-upstream evidence missing")
require((Q4 / "DO_NOT_USE_AS_FORMAL.md").exists(), "Q4 warning missing")

large = [(path, path.stat().st_size) for path in ROOT.rglob("*") if path.is_file() and ".git" not in path.parts and path.stat().st_size >= 95 * 1024 * 1024]
require(not large, f"files too large for normal GitHub push: {large}")

print("PASS: repository version identities and archive warnings verified")
print("Q2=OFFICIAL ONLINE-RISK-SP-A-S10-BATA")
print("Q3=WRONG_UPSTREAM_ARCHIVE_ONLY")
print("Q4=WRONG_UPSTREAM_ARCHIVE_ONLY")
