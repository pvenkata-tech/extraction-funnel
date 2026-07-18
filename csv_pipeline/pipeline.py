"""
Orchestrates DIVE 1 end to end: ingest -> schema check -> validate -> classify
missingness -> impute/backfill/flag -> dedup -> write to the structured store.

Run: python -m csv_pipeline.pipeline sample_data/csv
"""
import asyncio
import hashlib
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

from common.db import get_session, init_db
from common.models import ColumnProfile, ExtractedField, FileRegistry, HitlReview
from csv_pipeline.backfill import backfill_column
from csv_pipeline.dedup import merge_records
from csv_pipeline.missingness_classifier import MissingnessClassifier
from csv_pipeline.schema_registry import SchemaRegistry
from csv_pipeline.validator import profile_columns
from integrations.notifier import HitlEvent, HitlNotifier

ENTITY_KEY_COLUMN = "entity_key"
SOURCE_SYSTEM_COLUMN = "source_system"

# Fields known from domain experience to be MNAR-prone even when the stats alone
# can't distinguish them from MCAR (see MissingnessClassifier docstring).
DOMAIN_MNAR_PRIORS = {"compliance_flag": "MNAR"}


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _impute(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(series.mean())
    mode = series.mode(dropna=True)
    return series.fillna(mode.iloc[0] if not mode.empty else "unknown")


def run(data_dir: str):
    init_db()
    csv_paths = sorted(Path(data_dir).glob("*.csv"))
    if not csv_paths:
        print(f"No CSVs found in {data_dir}")
        return

    registry = SchemaRegistry()
    classifier = MissingnessClassifier(domain_priors=DOMAIN_MNAR_PRIORS)
    frames = {path: pd.read_csv(path) for path in csv_paths}
    method_counts = Counter()
    all_rows = []
    file_names_by_id = {}
    hitl_events = []

    with get_session() as session:
        for path, df in frames.items():
            checksum = _checksum(path)
            if session.query(FileRegistry).filter_by(checksum=checksum).first():
                print(f"[skip] {path.name} already ingested (checksum match)")
                continue

            source_system = df[SOURCE_SYSTEM_COLUMN].iloc[0] if SOURCE_SYSTEM_COLUMN in df.columns else "unknown"
            version, renamed, added = registry.check(source_system, list(df.columns))
            if renamed:
                print(f"[schema] {path.name}: fuzzy-matched renamed columns {renamed}")
            if added:
                print(f"[schema] {path.name}: new columns {added} -> version {version}")

            file_row = FileRegistry(
                source_uri=str(path), file_type="csv", source_system=source_system,
                schema_version=version, checksum=checksum, row_count=len(df),
                ingest_status="processed",
            )
            session.add(file_row)
            session.flush()
            file_names_by_id[file_row.id] = path.name

            for profile in profile_columns(df):
                session.add(ColumnProfile(file_id=file_row.id, **profile))

            other_frames = [f for p, f in frames.items() if p != path]
            data_columns = [c for c in df.columns if c not in (ENTITY_KEY_COLUMN, SOURCE_SYSTEM_COLUMN, "updated_at")]

            for column in data_columns:
                other_columns = [c for c in data_columns if c != column]
                missingness_class, explaining_column = classifier.classify(df, column, other_columns)
                strategy = classifier.strategy_for(missingness_class)

                if missingness_class == "NONE":
                    resolved = df[column]
                    method_for_row = "direct"
                elif strategy == "auto_impute":
                    resolved = _impute(df[column])
                    method_for_row = "imputed"
                elif strategy == "cross_file_backfill":
                    resolved = backfill_column(df, column, other_frames)
                    method_for_row = "backfilled"
                    print(f"[classify] {path.name}.{column}: MAR (explained by '{explaining_column}') -> backfill")
                else:  # flag_for_hitl
                    resolved = df[column]
                    method_for_row = "human_review"
                    print(f"[classify] {path.name}.{column}: MNAR suspected -> flagging {df[column].isna().sum()} rows for HITL, never auto-filled")

                for idx, value in resolved.items():
                    was_null = pd.isna(df.at[idx, column])
                    reason = None
                    if not was_null:
                        method, confidence = "direct", 1.0
                    elif pd.notna(value):
                        method, confidence = method_for_row, (0.9 if method_for_row == "imputed" else 0.8)
                    else:
                        method, confidence = "human_review", 0.0
                        reason = "mnar_suspected" if missingness_class == "MNAR" else "unresolved_backfill"

                    method_counts[method] += 1
                    entity_key = str(df.at[idx, ENTITY_KEY_COLUMN]) if ENTITY_KEY_COLUMN in df.columns else str(idx)
                    all_rows.append({
                        "file_id": file_row.id, "entity_key": entity_key, "field_name": column,
                        "value": None if pd.isna(value) else str(value), "confidence": confidence,
                        "extraction_method": method, "reason": reason,
                    })

        if not all_rows:
            print("No new rows to process (all files already ingested).")
            return

        golden_records = merge_records(all_rows)
        print(f"\n[dedup] {len(all_rows)} raw field rows merged into {len(golden_records)} golden entities")

        for record in golden_records:
            for field_name, (value, confidence, method, file_id, reason) in record.fields.items():
                field = ExtractedField(
                    file_id=file_id, entity_key=record.canonical_key, field_name=field_name,
                    value=value, confidence=confidence, extraction_method=method,
                )
                session.add(field)
                if method == "human_review":
                    session.flush()
                    session.add(HitlReview(extracted_field_id=field.id, reason=reason))
                    hitl_events.append(HitlEvent(
                        file_name=file_names_by_id.get(file_id, "unknown"), entity_key=record.canonical_key,
                        field_name=field_name, value=value, reason=reason,
                    ))

    total = sum(method_counts.values()) or 1
    print("\n--- Data Quality Report ---")
    for method, count in method_counts.most_common():
        print(f"  {method:>14}: {count:>5}  ({count / total:.1%})")

    if hitl_events:
        asyncio.run(_send_hitl_notifications(hitl_events))


async def _send_hitl_notifications(events: list[HitlEvent]) -> None:
    async with HitlNotifier() as notifier:
        for event in events:
            await notifier.notify(event)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "sample_data/csv")
