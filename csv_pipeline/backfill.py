"""
Cross-file backfill for MAR-classified fields: join on entity_key across every
other ingested file and take the value — but only from a source newer than the
current row's own timestamp, otherwise you silently reintroduce stale data.
"""
import pandas as pd

TIMESTAMP_COLUMN = "updated_at"
ENTITY_KEY_COLUMN = "entity_key"


def backfill_column(df: pd.DataFrame, column: str, other_frames: list[pd.DataFrame]) -> pd.Series:
    """
    Returns a Series aligned to df.index: backfilled value where found+fresh, else
    unchanged (still null) so the caller can decide what happens to unresolved rows.
    """
    result = df[column].copy()
    if ENTITY_KEY_COLUMN not in df.columns:
        return result

    null_rows = df[result.isna()]
    if null_rows.empty:
        return result

    for other in other_frames:
        if column not in other.columns or ENTITY_KEY_COLUMN not in other.columns:
            continue
        candidates = other[other[column].notna()][[ENTITY_KEY_COLUMN, column, TIMESTAMP_COLUMN]].dropna(
            subset=[column]
        )
        if candidates.empty:
            continue

        for idx, row in null_rows.iterrows():
            if pd.notna(result.loc[idx]):
                continue  # already filled by an earlier, fresher source
            match = candidates[candidates[ENTITY_KEY_COLUMN] == row[ENTITY_KEY_COLUMN]]
            if match.empty:
                continue

            own_ts = row.get(TIMESTAMP_COLUMN)
            if TIMESTAMP_COLUMN in match.columns and pd.notna(own_ts):
                match = match[match[TIMESTAMP_COLUMN] > own_ts]
            if match.empty:
                continue

            newest = match.sort_values(TIMESTAMP_COLUMN, ascending=False).iloc[0]
            result.loc[idx] = newest[column]

    return result
