from __future__ import annotations

import json
from pathlib import Path

from .mechanics import MechanicRecord, MechanicsLoadError, mechanic_from_raw


class MechanicsRepository:
    def __init__(self, records: list[MechanicRecord]):
        self.records = list(records)
        self._by_spell_id = {record.spell_id: record for record in records}
        self._by_name = {record.name.casefold(): record for record in records}
        self._by_kind: dict[str, list[MechanicRecord]] = {}
        self._by_node: dict[int, list[MechanicRecord]] = {}
        for record in records:
            self._by_kind.setdefault(record.kind, []).append(record)
            for node_id in record.source_node_ids:
                self._by_node.setdefault(node_id, []).append(record)

    @classmethod
    def from_jsonl(cls, path: Path | str) -> "MechanicsRepository":
        records: list[MechanicRecord] = []
        source_path = Path(path)
        with source_path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise MechanicsLoadError(f"{source_path}:{line_no} invalid JSON: {exc}") from exc
                records.append(mechanic_from_raw(raw, f"{source_path}:{line_no}"))
        return cls(records)

    def by_spell_id(self, spell_id: int) -> MechanicRecord:
        return self._by_spell_id[spell_id]

    def get_spell_id(self, spell_id: int) -> MechanicRecord | None:
        return self._by_spell_id.get(spell_id)

    def by_name(self, name: str) -> MechanicRecord:
        return self._by_name[name.casefold()]

    def records_by_kind(self, kind: str) -> list[MechanicRecord]:
        return list(self._by_kind.get(kind, []))

    def records_for_node(self, node_id: int) -> list[MechanicRecord]:
        return list(self._by_node.get(node_id, []))
