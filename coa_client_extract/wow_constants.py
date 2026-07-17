from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

AUTHORED_INPUTS = ("wow_rules", "rating_enum", "power_type_enum",
                   "gt_axis_policy", "wotlk_reference_anchors")
_DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class AuthoredInput:
    name: str
    payload: dict
    version: str
    sha256: str


def load_authored_input(name: str, *, root: Path | None = None) -> AuthoredInput:
    path = (root or _DATA_DIR) / f"{name}_v1.json"
    raw = path.read_bytes()
    payload = json.loads(raw)
    version = payload.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{path.name}: missing string 'version'")
    return AuthoredInput(name=name, payload=payload, version=version,
                         sha256=hashlib.sha256(raw).hexdigest())
