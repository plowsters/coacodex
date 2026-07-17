import hashlib
import json

import pytest

from coa_client_extract.wow_constants import AUTHORED_INPUTS, load_authored_input


def test_all_authored_inputs_load_with_version_and_hash():
    for name in AUTHORED_INPUTS:
        ai = load_authored_input(name)
        assert ai.name == name and ai.version and len(ai.sha256) == 64
        assert isinstance(ai.payload, dict)


def test_hash_is_over_exact_on_disk_bytes(tmp_path):
    src = tmp_path / "wow_rules_v1.json"
    src.write_text(json.dumps({"version": "x", "rules": {}}))
    ai = load_authored_input("wow_rules", root=tmp_path)
    assert ai.sha256 == hashlib.sha256(src.read_bytes()).hexdigest()
    assert ai.version == "x"


def test_missing_version_key_raises(tmp_path):
    (tmp_path / "wow_rules_v1.json").write_text(json.dumps({"rules": {}}))
    with pytest.raises(ValueError):
        load_authored_input("wow_rules", root=tmp_path)
