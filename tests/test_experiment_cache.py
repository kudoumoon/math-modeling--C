import json

import pytest

from forecasting.experiment import _reuse_forecasts


def test_forecast_cache_rejects_changed_training_dependency_before_copy(tmp_path):
    parent = tmp_path / "old"
    parent.mkdir()
    module = tmp_path / "src/forecasting/data.py"
    module.parent.mkdir(parents=True)
    module.write_text("changed implementation")
    manifest = {"config_sha256": "same", "input_hashes": {},
                "source_hashes": {"src/forecasting/data.py": "old_hash"}}
    (parent / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="training dependency changed"):
        _reuse_forecasts(tmp_path, parent, tmp_path / "new", "same", {})
    assert not (tmp_path / "new").exists()


def test_forecast_cache_rejects_different_configuration(tmp_path):
    parent = tmp_path / "old"
    parent.mkdir()
    (parent / "manifest.json").write_text(json.dumps({"config_sha256": "before", "input_hashes": {}}))
    with pytest.raises(ValueError, match="different configuration"):
        _reuse_forecasts(tmp_path, parent, tmp_path / "new", "after", {})
