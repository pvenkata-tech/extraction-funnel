"""Stage 2 (cheap filter): type/null-rate/range/uniqueness profiling — no LLM involved."""
import pandas as pd


def profile_columns(df: pd.DataFrame) -> list[dict]:
    """One profile dict per column: null_rate, inferred_type, distinct_count."""
    profiles = []
    for column in df.columns:
        series = df[column]
        null_rate = float(series.isna().mean())
        if pd.api.types.is_numeric_dtype(series):
            inferred_type = "numeric"
        elif pd.api.types.is_bool_dtype(series):
            inferred_type = "boolean"
        else:
            inferred_type = "text"
        profiles.append({
            "column_name": column,
            "inferred_type": inferred_type,
            "null_rate": round(null_rate, 4),
            "distinct_count": int(series.nunique(dropna=True)),
        })
    return profiles
