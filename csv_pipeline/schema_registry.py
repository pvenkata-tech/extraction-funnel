"""
Stage 2 (cheap filter) for CSV: tracks the expected column set per source_system
and detects drift instead of silently accepting whatever columns show up.

Backed by a JSON file so the demo needs no extra table — swap for a Glue Data
Catalog / Postgres table in production, the interface stays the same.
"""
import difflib
import json
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent / "schema_registry.json"
FUZZY_MATCH_CUTOFF = 0.75


class SchemaRegistry:
    def __init__(self, path: Path = REGISTRY_PATH):
        self.path = path
        self._data: dict[str, dict] = json.loads(path.read_text()) if path.exists() else {}

    def _save(self):
        self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True))

    def check(self, source_system: str, columns: list[str]) -> tuple[int, dict[str, str], list[str]]:
        """
        Returns (schema_version, renamed_column_map, newly_added_columns).
        Registers the source on first sighting rather than failing.
        """
        entry = self._data.get(source_system)
        if entry is None:
            self._data[source_system] = {"version": 1, "columns": columns}
            self._save()
            return 1, {}, []

        known = entry["columns"]
        missing_from_incoming = [c for c in known if c not in columns]
        renamed: dict[str, str] = {}
        for old_col in missing_from_incoming:
            match = difflib.get_close_matches(old_col, columns, n=1, cutoff=FUZZY_MATCH_CUTOFF)
            if match:
                renamed[match[0]] = old_col  # incoming name -> known name

        truly_new = [c for c in columns if c not in known and c not in renamed]

        if renamed or truly_new:
            merged_columns = list(known)
            for col in truly_new:
                if col not in merged_columns:
                    merged_columns.append(col)
            entry["version"] += 1
            entry["columns"] = merged_columns
            self._save()

        return entry["version"], renamed, truly_new
