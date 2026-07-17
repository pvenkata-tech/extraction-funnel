import random

import pandas as pd

from csv_pipeline.missingness_classifier import MissingnessClassifier


def _seeded(fn):
    random.seed(7)
    return fn()


def test_no_nulls_is_none():
    df = pd.DataFrame({"age": [30, 40, 50, 60, 70], "zip": ["1", "2", "3", "4", "5"]})
    cls, explain = MissingnessClassifier().classify(df, "age", ["zip"])
    assert cls == "NONE"
    assert explain is None


def test_mcar_detected_for_random_dropout():
    random.seed(2)
    n = 200
    age = [random.randint(18, 90) for _ in range(n)]
    zip_code = [None if random.random() < 0.2 else str(random.randint(10000, 99999)) for _ in range(n)]
    df = pd.DataFrame({"age": age, "zip_code": zip_code})

    cls, explain = MissingnessClassifier().classify(df, "zip_code", ["age"])
    assert cls == "MCAR"
    assert explain is None


def test_mar_detected_when_explained_by_another_column():
    # diagnosis_code is null exactly when age < 12 -- explainable by 'age'
    ages = [random.randint(18, 85) for _ in range(60)] + [random.randint(4, 11) for _ in range(20)]
    diagnosis = ["E11.9" if age >= 12 else None for age in ages]
    df = pd.DataFrame({"age": ages, "diagnosis_code": diagnosis})

    cls, explain = MissingnessClassifier().classify(df, "diagnosis_code", ["age"])
    assert cls == "MAR"
    assert explain == "age"


def test_domain_prior_overrides_statistical_independence():
    # Missingness here depends on an unobserved variable (true smoking status),
    # so it looks statistically independent of every observed column -- exactly
    # the case a domain prior needs to catch.
    random.seed(3)
    n = 100
    age = [random.randint(18, 85) for _ in range(n)]
    smoking_status = [None if random.random() < 0.4 else "smoker" for _ in range(n)]
    df = pd.DataFrame({"age": age, "smoking_status": smoking_status})

    without_prior, _ = MissingnessClassifier().classify(df, "smoking_status", ["age"])
    with_prior, _ = MissingnessClassifier(domain_priors={"smoking_status": "MNAR"}).classify(
        df, "smoking_status", ["age"]
    )
    assert without_prior == "MCAR"
    assert with_prior == "MNAR"


def test_strategy_mapping():
    clf = MissingnessClassifier()
    assert clf.strategy_for("MCAR") == "auto_impute"
    assert clf.strategy_for("MAR") == "cross_file_backfill"
    assert clf.strategy_for("MNAR") == "flag_for_hitl"
    assert clf.strategy_for("NONE") == "skip"
