from coa_client_extract.errors import (
    ArchiveError,
    BackendUnavailable,
    DbcDriftError,
    ExtractError,
)


def test_error_hierarchy():
    for cls in (BackendUnavailable, ArchiveError, DbcDriftError):
        assert issubclass(cls, ExtractError)


def test_errors_carry_message():
    err = DbcDriftError("Spell.dbc: field_count 300 != expected 234")
    assert "expected 234" in str(err)


def test_pytest_markers_are_registered(pytestconfig):
    # Real assertion that pyproject.toml registered both extraction tiers.
    markers = "\n".join(pytestconfig.getini("markers"))
    assert "stormlib:" in markers
    assert "client:" in markers
