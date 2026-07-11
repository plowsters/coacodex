import pytest

from coa_client_extract.errors import BackendUnavailable
from coa_client_extract.stormlib_ctypes import load_stormlib
from coa_client_extract.stormlib_backend import StormLibBackend


def test_load_stormlib_raises_backend_unavailable_for_bad_path(monkeypatch):
    monkeypatch.delenv("STORMLIB_PATH", raising=False)
    monkeypatch.setattr("ctypes.util.find_library", lambda name: None)
    with pytest.raises(BackendUnavailable):
        load_stormlib("/nonexistent/libstorm.so.999")


def test_backend_construction_fails_closed_without_library(monkeypatch):
    monkeypatch.delenv("STORMLIB_PATH", raising=False)
    monkeypatch.setattr("ctypes.util.find_library", lambda name: None)
    with pytest.raises(BackendUnavailable):
        StormLibBackend(stormlib_path="/nonexistent/libstorm.so.999")


def test_backend_identity_constants():
    assert StormLibBackend.name == "stormlib_ctypes"
    assert StormLibBackend.version == "coa-stormlib-v1"
