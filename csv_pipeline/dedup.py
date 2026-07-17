"""
Golden-record dedup: the same entity can show up under slightly different keys
across sources (typo'd vendor id, reformatted account id). Deterministic match first,
fuzzy match as a fallback, highest-confidence-wins on conflicting field values.

Fuzzy matching uses edit distance rather than a similarity ratio: entity IDs
are short (5-10 chars), and ratio-based matching over short strings that share
a common prefix (e.g. "P0001" vs "P0002") produces false positives -- almost
every pair looks "close enough." Edit distance <=1 only catches genuine
single-character typos, which is what this failure mode actually looks like.
"""
from dataclasses import dataclass, field

MAX_EDIT_DISTANCE = 1


@dataclass
class GoldenRecord:
    canonical_key: str
    # field_name -> (value, confidence, method, file_id, reason)
    fields: dict[str, tuple[str, float, str, object, str]] = field(default_factory=dict)
    merged_keys: set[str] = field(default_factory=set)

    def absorb(self, entity_key: str, field_name: str, value, confidence: float, method: str, file_id, reason):
        self.merged_keys.add(entity_key)
        existing = self.fields.get(field_name)
        if existing is None or confidence > existing[1]:
            self.fields[field_name] = (value, confidence, method, file_id, reason)


def merge_records(rows: list[dict]) -> list[GoldenRecord]:
    """
    rows: [{"entity_key": ..., "field_name": ..., "value": ..., "confidence": ..., "extraction_method": ..., "file_id": ..., "reason": ...}, ...]
    Groups deterministic-equal keys first, then fuzzy-matches remaining singleton
    keys against the canonical keys already established.
    """
    records: dict[str, GoldenRecord] = {}

    for row in rows:
        key = row["entity_key"]
        canonical = key if key in records else _find_fuzzy_match(key, records.keys())
        if canonical is None:
            canonical = key
            records[canonical] = GoldenRecord(canonical_key=canonical)
        records[canonical].absorb(
            key, row["field_name"], row["value"], row["confidence"], row["extraction_method"],
            row["file_id"], row.get("reason"),
        )

    return list(records.values())


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    previous_row = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current_row = [i] + [0] * len(b)
        for j, char_b in enumerate(b, start=1):
            current_row[j] = min(
                previous_row[j] + 1,  # deletion
                current_row[j - 1] + 1,  # insertion
                previous_row[j - 1] + (char_a != char_b),  # substitution
            )
        previous_row = current_row
    return previous_row[-1]


def _find_fuzzy_match(key: str, known_keys) -> str | None:
    for candidate in known_keys:
        if abs(len(candidate) - len(key)) > MAX_EDIT_DISTANCE:
            continue
        if _levenshtein(key, candidate) <= MAX_EDIT_DISTANCE:
            return candidate
    return None
