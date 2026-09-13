"""Local sidecar tests; no annual runner or active result directory is invoked."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd
import pytest
import q4_parallel_runner as fast


def test_manifest_snapshot_checkpoints_and_restore(tmp_path, monkeypatch):
    frame = pd.DataFrame({"day_index": [78], "value": [3.0]})
    q42 = lambda *a, **kw: (frame, frame)
    q43 = lambda *a, **kw: (frame, frame, frame, frame, frame)
    monkeypatch.setattr(fast.run_q4, "q42", q42)
    monkeypatch.setattr(fast.run_q4, "q43", q43)
    original_policy = fast.run_q4.MidnightPolicy
    original_snapshot = fast.run_q4.source_snapshot
    original_write = fast.run_q4.write_json
    original_sources = original_snapshot()
    with pytest.raises(RuntimeError, match="later trajectory failure"):
        with fast.parallel_backend(2):
            snapshot = fast.run_q4.source_snapshot()
            wrapper = Path(fast.__file__).resolve()
            assert snapshot[str(wrapper.relative_to(fast.ROOT))] == hashlib.sha256(wrapper.read_bytes()).hexdigest()
            assert all(snapshot[p] == h for p, h in original_sources.items())
            value = {"status": "running", "source_hashes": snapshot, "input_hashes": {}}
            fast.run_q4.write_json(tmp_path / "manifest.json", value)
            manifest = json.loads((tmp_path / "manifest.json").read_text())
            backend = manifest["execution_backend"]
            assert backend["workers"] == 2 and backend["start_method"] == "spawn"
            assert (tmp_path / backend["wrapper_source_snapshot"]).read_bytes() == wrapper.read_bytes()
            fast.run_q4.q42()
            fast.run_q4.q43(settlement="A")
            for name in ("q4_2", "q4_3_A"):
                directory = tmp_path / "parallel_checkpoints" / name
                metadata = json.loads((directory / "checkpoint_manifest.json").read_text())
                assert metadata["formal_use"] is False
                assert "overall_run_not_yet_complete" in metadata["status"]
                for path, expected in metadata["outputs"].items():
                    assert hashlib.sha256((directory / path).read_bytes()).hexdigest() == expected
            with pytest.raises(FileExistsError):
                fast.run_q4.q42()
            raise RuntimeError("later trajectory failure")
    assert fast.run_q4.MidnightPolicy is original_policy
    assert fast.run_q4.q42 is q42 and fast.run_q4.q43 is q43
    assert fast.run_q4.source_snapshot is original_snapshot
    assert fast.run_q4.write_json is original_write
    assert (tmp_path / "parallel_checkpoints/q4_2/all_intervals.csv").exists()


def test_future_failure_is_propagated_without_serial_fallback():
    class BrokenPool:
        def map(self, *args, **kwargs):
            raise RuntimeError("worker failed")
    from types import SimpleNamespace
    policy = fast.ParallelMidnightPolicy(None, None, None, executor=BrokenPool())
    with pytest.raises(RuntimeError, match="worker failed"):
        policy.plan(0, 6000., SimpleNamespace(values=[.5]*144))
    assert policy.pending == []


def test_worker_count_and_benchmark_are_bounded():
    for count in (0, 16):
        with pytest.raises(ValueError):
            fast.PolicyFactory(count)
    with pytest.raises(ValueError):
        fast.benchmark(days=365)
