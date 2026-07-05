from __future__ import annotations

import re

SPEC_DISPLAY_NAMES: dict[tuple[str, str], str] = {
    ("runemaster", "arcane"): "Glyphic",
    ("runemaster", "runic"): "Engravement",
    ("venomancer", "venom"): "Rot",
    ("primalist", "life"): "Grovekeeper",
    ("primalist", "primal"): "Wildwalker",
    ("witch_hunter", "houndmaster"): "Darkness",
}


def display_spec_name(class_name: str, spec_name: str) -> str:
    return SPEC_DISPLAY_NAMES.get((slugify_key(class_name), slugify_key(spec_name)), spec_name)


def display_spec_title(class_name: str, spec_name: str) -> str:
    return f"{display_spec_name(class_name, spec_name)} {class_name}"


def slugify_key(value: str) -> str:
    lowered = value.lower().replace("'", "")
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
