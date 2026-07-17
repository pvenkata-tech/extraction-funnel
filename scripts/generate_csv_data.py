"""
Generates synthetic CSV fixtures that exercise every missingness pattern the
funnel is built to handle:

- region_code: MCAR (pure random dropout, independent of every other column)
- registration_number: MAR (null exactly when employee_count < 5 -- sole
  proprietors/individual contractors in this fake procurement system just
  don't have a business registration number to capture)
- compliance_flag: MNAR (blank disproportionately for vendors with no issue --
  the textbook trap; statistically indistinguishable from MCAR without the
  domain prior the classifier applies)
- a second procurement_export batch with a renamed + a brand-new column, to
  exercise schema-drift detection
- a handful of typo'd entity_keys in finance_extract, to exercise fuzzy dedup

Run: python scripts/generate_csv_data.py
"""
import random
import string

import pandas as pd

random.seed(1)

N_ENTERPRISE = 51
N_SOLE_PROPRIETOR = 9
REGISTRATION_PREFIX = "REG"

_used_keys: set[str] = set()


def _new_entity_key() -> str:
    """
    Random alphanumeric vendor id rather than a sequential id. Sequential ids
    ("VEN0001", "VEN0002", ...) sit at edit-distance 1 from their neighbors, so
    any edit-distance-based fuzzy dedup would false-merge adjacent, unrelated
    entities. Randomizing the key makes an accidental collision astronomically
    unlikely while an injected 1-character typo is still reliably reversible.
    """
    while True:
        key = "VEN" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if key not in _used_keys:
            _used_keys.add(key)
            return key


def _region_code():
    return f"{random.randint(10000, 99999)}"


def _registration_number():
    return f"{REGISTRATION_PREFIX}-{random.randint(100000, 999999)}"


def build_batch1():
    rows = []
    entities = [_new_entity_key() for _ in range(N_ENTERPRISE + N_SOLE_PROPRIETOR)]
    employee_counts = (
        [random.randint(20, 500) for _ in range(N_ENTERPRISE)]
        + [random.randint(1, 4) for _ in range(N_SOLE_PROPRIETOR)]
    )
    pairs = list(zip(entities, employee_counts))
    random.shuffle(pairs)

    for entity_key, employee_count in pairs:
        is_sole_proprietor = employee_count < 5
        true_compliance_issue = random.random() < 0.3

        region_code = None if random.random() < 0.15 else _region_code()  # MCAR
        registration_number = None if is_sole_proprietor else _registration_number()  # MAR (explained by employee_count)

        if true_compliance_issue:
            compliance_flag = "flagged"
        else:
            compliance_flag = None if random.random() < 0.70 else "clear"  # MNAR

        rows.append({
            "entity_key": entity_key, "source_system": "procurement_export", "employee_count": employee_count,
            "region_code": region_code, "compliance_flag": compliance_flag, "registration_number": registration_number,
            "updated_at": "2026-01-15",
        })
    return pd.DataFrame(rows), pairs


def build_batch2_with_drift():
    """New vendors in a later batch; column renamed registration_number -> registration_no
    (fuzzy-matchable), plus a brand-new contract_tier column -- both should be
    caught as schema drift."""
    rows = []
    for _ in range(20):
        entity_key = _new_entity_key()
        employee_count = random.randint(20, 500)
        rows.append({
            "entity_key": entity_key, "source_system": "procurement_export", "employee_count": employee_count,
            "region_code": _region_code(), "compliance_flag": random.choice(["flagged", "clear"]),
            "registration_no": _registration_number(), "contract_tier": random.choice(["gold", "silver", "bronze"]),
            "updated_at": "2026-02-20",
        })
    return pd.DataFrame(rows)


def build_finance_extract(pairs):
    rows = []
    sole_proprietor_keys = [key for key, employee_count in pairs if employee_count < 5]
    typo_targets = random.sample(sole_proprietor_keys, k=min(3, len(sole_proprietor_keys)))

    for entity_key, employee_count in pairs:
        key_for_finance = entity_key
        if entity_key in typo_targets:
            # simulate a data-entry typo: replace the last character (edit distance 1)
            alphabet = string.ascii_uppercase + string.digits
            replacement = random.choice([c for c in alphabet if c != entity_key[-1]])
            key_for_finance = entity_key[:-1] + replacement

        registration_number = None
        if employee_count < 5 and random.random() < 0.7:  # finance captures it for most, not all -- some stay unresolved -> HITL
            registration_number = _registration_number()
        elif employee_count >= 5:
            registration_number = _registration_number()

        rows.append({
            "entity_key": key_for_finance, "source_system": "finance_extract",
            "region_code": _region_code(), "registration_number": registration_number,
            "updated_at": "2026-02-01",  # fresher than procurement_export -- valid backfill source
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out_dir = "sample_data/csv"
    batch1, pairs = build_batch1()
    batch2 = build_batch2_with_drift()
    finance = build_finance_extract(pairs)

    batch1.to_csv(f"{out_dir}/procurement_export_batch1.csv", index=False)
    batch2.to_csv(f"{out_dir}/procurement_export_batch2.csv", index=False)
    finance.to_csv(f"{out_dir}/finance_extract.csv", index=False)

    print(f"Wrote {len(batch1)} + {len(batch2)} procurement rows and {len(finance)} finance rows to {out_dir}/")
