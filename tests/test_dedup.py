from csv_pipeline.dedup import merge_records


def _row(entity_key, field_name, value, confidence, method="direct", file_id="f1", reason=None):
    return {
        "entity_key": entity_key, "field_name": field_name, "value": value,
        "confidence": confidence, "extraction_method": method, "file_id": file_id, "reason": reason,
    }


def test_deterministic_match_merges_same_key():
    rows = [
        _row("MRNAAA111", "age", "40", 1.0),
        _row("MRNAAA111", "zip_code", "10001", 1.0),
    ]
    records = merge_records(rows)
    assert len(records) == 1
    assert records[0].fields["age"][0] == "40"
    assert records[0].fields["zip_code"][0] == "10001"


def test_single_char_typo_merges_via_fuzzy_match():
    rows = [
        _row("MRNAAA111", "age", "40", 1.0),
        _row("MRNAAA112", "zip_code", "10001", 1.0),  # last char typo, edit distance 1
    ]
    records = merge_records(rows)
    assert len(records) == 1
    assert records[0].merged_keys == {"MRNAAA111", "MRNAAA112"}


def test_unrelated_keys_do_not_merge():
    rows = [
        _row("MRNAAA111", "age", "40", 1.0),
        _row("MRNZZZ999", "age", "55", 1.0),  # nothing in common, should stay separate
    ]
    records = merge_records(rows)
    assert len(records) == 2


def test_highest_confidence_wins_on_conflict():
    rows = [
        _row("MRNAAA111", "smoking_status", None, 0.0, method="human_review", reason="mnar_suspected"),
        _row("MRNAAA111", "smoking_status", "non_smoker", 0.8, method="backfilled"),
    ]
    records = merge_records(rows)
    value, confidence, method, _, reason = records[0].fields["smoking_status"]
    assert value == "non_smoker"
    assert confidence == 0.8
    assert method == "backfilled"
