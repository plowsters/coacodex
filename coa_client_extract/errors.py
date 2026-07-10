from __future__ import annotations


class ExtractError(Exception):
    """Base class for all client-extraction failures."""


class BackendUnavailable(ExtractError):
    """The archive backend (e.g. StormLib) could not be loaded/opened."""


class ArchiveError(ExtractError):
    """An archive or logical file could not be resolved through the plan."""


class DbcDriftError(ExtractError):
    """A DBC header disagreed with its declared layout beyond tolerance."""
