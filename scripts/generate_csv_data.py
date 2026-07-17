"""
Generates synthetic CSV fixtures that exercise every missingness pattern the
funnel is built to handle:

- zip_code: MCAR (pure random dropout, independent of every other column)
- diagnosis_code: MAR (null exactly when age < 12 -- the pediatric template
  in this fake EHR just doesn't capture an adult diagnosis code field)
- smoking_status: MNAR (blank disproportionately for non-smokers -- the
  textbook clinical trap; statistically indistinguishable from MCAR without
  the domain prior the classifier applies)
- a second ehr_export batch with a renamed + a brand-new column, to exercise
  schema-drift detection
- a handful of typo'd entity_keys in billing_extract, to exercise fuzzy dedup

Run: python scripts/generate_csv_data.py
"""
import random
import string

import pandas as pd

random.seed(42)

N_ADULTS = 51
N_PEDIATRIC = 9
DIAGNOSIS_CODES = ["E11.9", "I10", "J45.909", "M54.5", "K21.9"]

_used_keys: set[str] = set()


def _new_entity_key() -> str:
    """
    Random alphanumeric MRN rather than a sequential id. Sequential ids
    ("P0001", "P0002", ...) sit at edit-distance 1 from their neighbors, so any
    edit-distance-based fuzzy dedup would false-merge adjacent, unrelated
    entities. Randomizing the key makes an accidental collision astronomically
    unlikely while an injected 1-character typo is still reliably reversible.
    """
    while True:
        key = "MRN" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if key not in _used_keys:
            _used_keys.add(key)
            return key


def _zip_code():
    return f"{random.randint(10000, 99999)}"


def build_batch1():
    rows = []
    entities = [_new_entity_key() for _ in range(N_ADULTS + N_PEDIATRIC)]
    ages = [random.randint(18, 85) for _ in range(N_ADULTS)] + [random.randint(4, 11) for _ in range(N_PEDIATRIC)]
    pairs = list(zip(entities, ages))
    random.shuffle(pairs)

    for entity_key, age in pairs:
        is_pediatric = age < 12
        true_smoker = random.random() < 0.3

        zip_code = None if random.random() < 0.15 else _zip_code()  # MCAR
        diagnosis_code = None if is_pediatric else random.choice(DIAGNOSIS_CODES)  # MAR (explained by age)

        if true_smoker:
            smoking_status = "smoker"
        else:
            smoking_status = None if random.random() < 0.70 else "non_smoker"  # MNAR

        rows.append({
            "entity_key": entity_key, "source_system": "ehr_export", "age": age,
            "zip_code": zip_code, "smoking_status": smoking_status, "diagnosis_code": diagnosis_code,
            "updated_at": "2026-01-15",
        })
    return pd.DataFrame(rows), pairs


def build_batch2_with_drift():
    """New patients in a later batch; column renamed diagnosis_code -> diagnosis_cd
    (fuzzy-matchable, ratio ~0.92), plus a brand-new insurance_type column --
    both should be caught as schema drift."""
    rows = []
    for _ in range(20):
        entity_key = _new_entity_key()
        age = random.randint(18, 85)
        rows.append({
            "entity_key": entity_key, "source_system": "ehr_export", "age": age,
            "zip_code": _zip_code(), "smoking_status": random.choice(["smoker", "non_smoker"]),
            "diagnosis_cd": random.choice(DIAGNOSIS_CODES), "insurance_type": random.choice(["PPO", "HMO", "Medicare"]),
            "updated_at": "2026-02-20",
        })
    return pd.DataFrame(rows)


def build_billing_extract(pairs):
    rows = []
    pediatric_keys = [key for key, age in pairs if age < 12]
    typo_targets = random.sample(pediatric_keys, k=min(3, len(pediatric_keys)))

    for entity_key, age in pairs:
        key_for_billing = entity_key
        if entity_key in typo_targets:
            # simulate a data-entry typo: replace the last character (edit distance 1)
            alphabet = string.ascii_uppercase + string.digits
            replacement = random.choice([c for c in alphabet if c != entity_key[-1]])
            key_for_billing = entity_key[:-1] + replacement

        diagnosis_code = None
        if age < 12 and random.random() < 0.7:  # billing captures it for most, not all -- some stay unresolved -> HITL
            diagnosis_code = random.choice(DIAGNOSIS_CODES)
        elif age >= 12:
            diagnosis_code = random.choice(DIAGNOSIS_CODES)

        rows.append({
            "entity_key": key_for_billing, "source_system": "billing_extract",
            "zip_code": _zip_code(), "diagnosis_code": diagnosis_code,
            "updated_at": "2026-02-01",  # fresher than ehr_export -- valid backfill source
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out_dir = "sample_data/csv"
    batch1, pairs = build_batch1()
    batch2 = build_batch2_with_drift()
    billing = build_billing_extract(pairs)

    batch1.to_csv(f"{out_dir}/ehr_export_batch1.csv", index=False)
    batch2.to_csv(f"{out_dir}/ehr_export_batch2.csv", index=False)
    billing.to_csv(f"{out_dir}/billing_extract.csv", index=False)

    print(f"Wrote {len(batch1)} + {len(batch2)} EHR rows and {len(billing)} billing rows to {out_dir}/")
