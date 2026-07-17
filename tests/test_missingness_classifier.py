import random

import pandas as pd

from csv_pipeline.missingness_classifier import MissingnessClassifier


def test_no_nulls_is_none():
    df = pd.DataFrame({"employee_count": [30, 40, 50, 60, 70], "region": ["1", "2", "3", "4", "5"]})
    cls, explain = MissingnessClassifier().classify(df, "employee_count", ["region"])
    assert cls == "NONE"
    assert explain is None


def test_mcar_detected_for_random_dropout():
    random.seed(2)
    n = 200
    employee_count = [random.randint(1, 500) for _ in range(n)]
    region_code = [None if random.random() < 0.2 else str(random.randint(10000, 99999)) for _ in range(n)]
    df = pd.DataFrame({"employee_count": employee_count, "region_code": region_code})

    cls, explain = MissingnessClassifier().classify(df, "region_code", ["employee_count"])
    assert cls == "MCAR"
    assert explain is None


def test_mar_detected_when_explained_by_another_column():
    # registration_number is null exactly when employee_count < 5 -- explainable by 'employee_count'
    employee_counts = [random.randint(20, 500) for _ in range(60)] + [random.randint(1, 4) for _ in range(20)]
    registration_numbers = ["REG-100001" if count >= 5 else None for count in employee_counts]
    df = pd.DataFrame({"employee_count": employee_counts, "registration_number": registration_numbers})

    cls, explain = MissingnessClassifier().classify(df, "registration_number", ["employee_count"])
    assert cls == "MAR"
    assert explain == "employee_count"


def test_domain_prior_overrides_statistical_independence():
    # Missingness here depends on an unobserved variable (whether there was a real
    # compliance issue to report), so it looks statistically independent of every
    # observed column -- exactly the case a domain prior needs to catch.
    random.seed(3)
    n = 100
    employee_count = [random.randint(20, 500) for _ in range(n)]
    compliance_flag = [None if random.random() < 0.4 else "flagged" for _ in range(n)]
    df = pd.DataFrame({"employee_count": employee_count, "compliance_flag": compliance_flag})

    without_prior, _ = MissingnessClassifier().classify(df, "compliance_flag", ["employee_count"])
    with_prior, _ = MissingnessClassifier(domain_priors={"compliance_flag": "MNAR"}).classify(
        df, "compliance_flag", ["employee_count"]
    )
    assert without_prior == "MCAR"
    assert with_prior == "MNAR"


def test_high_cardinality_identifier_column_does_not_spuriously_explain_missingness():
    # registration_number is near-unique per row (an id, not a category) -- every
    # "category" is a single row, so its null-rate trivially looks like 0% or 100%
    # by chance. A truly independent (MCAR) column must not get misclassified as
    # MAR just because it was tested against an id-like column first.
    random.seed(5)
    n = 100
    region_code = [None if random.random() < 0.2 else str(random.randint(10000, 99999)) for _ in range(n)]
    registration_number = [f"REG-{i:06d}" for i in range(n)]  # unique per row
    df = pd.DataFrame({"region_code": region_code, "registration_number": registration_number})

    cls, explain = MissingnessClassifier().classify(df, "region_code", ["registration_number"])
    assert cls == "MCAR"
    assert explain is None


def test_strategy_mapping():
    clf = MissingnessClassifier()
    assert clf.strategy_for("MCAR") == "auto_impute"
    assert clf.strategy_for("MAR") == "cross_file_backfill"
    assert clf.strategy_for("MNAR") == "flag_for_hitl"
    assert clf.strategy_for("NONE") == "skip"
