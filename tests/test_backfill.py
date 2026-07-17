import pandas as pd

from csv_pipeline.backfill import backfill_column


def test_backfills_from_fresher_source():
    df = pd.DataFrame({
        "entity_key": ["A", "B"],
        "diagnosis_code": [None, "I10"],
        "updated_at": ["2026-01-01", "2026-01-01"],
    })
    other = pd.DataFrame({
        "entity_key": ["A"],
        "diagnosis_code": ["E11.9"],
        "updated_at": ["2026-02-01"],  # fresher
    })

    result = backfill_column(df, "diagnosis_code", [other])
    assert result.loc[0] == "E11.9"
    assert result.loc[1] == "I10"  # untouched, was never null


def test_does_not_backfill_from_stale_source():
    df = pd.DataFrame({
        "entity_key": ["A"],
        "diagnosis_code": [None],
        "updated_at": ["2026-03-01"],
    })
    other = pd.DataFrame({
        "entity_key": ["A"],
        "diagnosis_code": ["E11.9"],
        "updated_at": ["2026-01-01"],  # older than df's own timestamp -- must be rejected
    })

    result = backfill_column(df, "diagnosis_code", [other])
    assert pd.isna(result.loc[0])


def test_leaves_null_when_no_matching_entity_key():
    df = pd.DataFrame({"entity_key": ["A"], "diagnosis_code": [None], "updated_at": ["2026-01-01"]})
    other = pd.DataFrame({"entity_key": ["B"], "diagnosis_code": ["E11.9"], "updated_at": ["2026-02-01"]})

    result = backfill_column(df, "diagnosis_code", [other])
    assert pd.isna(result.loc[0])
