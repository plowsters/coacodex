from __future__ import annotations

from .domain import BuildValidationResult, ValidationIssue


def issue_to_dict(issue: ValidationIssue) -> dict:
    return {
        "code": issue.code,
        "message": issue.message,
        "node_id": issue.node_id,
        "details": issue.details,
    }


def validation_to_dict(result: BuildValidationResult) -> dict:
    return {
        "valid": result.valid,
        "state": result.state.to_dict() if result.state else None,
        "issues": [issue_to_dict(issue) for issue in result.issues],
        "warnings": [issue_to_dict(issue) for issue in result.warnings],
    }


def scored_build_to_dict(scored) -> dict:
    return scored.to_dict()
