import hashlib

import pytest

from coa_client_extract.artifacts import write_wow_constants, _atomic_write_bytes


class _AI:
    def __init__(self, name, version, sha256):
        self.name, self.version, self.sha256 = name, version, sha256


def _inputs():
    return [_AI("wow_rules", "wow-rules-v1", "a" * 64), _AI("rating_enum", "cr-3.3.5a-v1", "b" * 64),
            _AI("power_type_enum", "m1.14c-power-v1", "c" * 64),
            _AI("gt_axis_policy", "gt-layout-v1", "d" * 64),
            _AI("wotlk_reference_anchors", "wotlk-335a-anchors-v1", "e" * 64)]


def _write(out, **over):
    snap = {"schema_version": "coa-wow-constants-v1", "client_build": "3.3.5a+patch-M"}
    kw = dict(authored_inputs=_inputs(), source_dbc_sha256={"gtCombatRatings": "f" * 64},
              class_context_resolution="unproven", extractor_commit="deadbeef",
              client_build="3.3.5a+patch-M", table_summary={})
    kw.update(over)
    return write_wow_constants(snap, out, **kw)


def test_manifest_binds_artifact_and_every_authored_input(tmp_path):
    manifest = _write(tmp_path)
    art = tmp_path / "coa_wow_constants.json"
    assert manifest["artifact"]["sha256"] == hashlib.sha256(art.read_bytes()).hexdigest()
    assert manifest["artifact"]["byte_length"] == art.stat().st_size
    assert set(manifest["authored_inputs"]) == {"rules", "rating_enum", "power_type_enum",
                                                "axis_layout_policy", "reference_anchors"}
    assert manifest["authored_inputs"]["rules"] == {"version": "wow-rules-v1", "sha256": "a" * 64}
    assert manifest["class_context_resolution"] == "unproven"


def test_adjudication_bound_when_present(tmp_path):
    adj = {"name": "class_axis_adjudication", "version": "wow-class-axis-adjudication-v1",
           "sha256": "9" * 64}
    manifest = _write(tmp_path, class_axis_adjudication=adj)
    assert manifest["authored_inputs"]["class_axis_adjudication"] == {
        "version": "wow-class-axis-adjudication-v1", "sha256": "9" * 64}


def test_interrupted_write_leaves_no_valid_manifest(tmp_path, monkeypatch):
    orig = _atomic_write_bytes
    calls = {"n": 0}

    def flaky(data, path):
        calls["n"] += 1
        if calls["n"] == 2:                       # the manifest write
            raise OSError("disk full")
        return orig(data, path)
    monkeypatch.setattr("coa_client_extract.artifacts._atomic_write_bytes", flaky)
    with pytest.raises(OSError):
        _write(tmp_path)
    assert (tmp_path / "coa_wow_constants.json").exists()
    assert not (tmp_path / "coa_wow_constants.manifest.json").exists()
