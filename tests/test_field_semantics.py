import pandas as pd

from src.field_semantics import (
    FIELD_ROLE_BOOLEAN,
    FIELD_ROLE_CATEGORICAL,
    FIELD_ROLE_DATETIME,
    FIELD_ROLE_EMPTY,
    FIELD_ROLE_FREE_TEXT,
    FIELD_ROLE_IDENTIFIER,
    FIELD_ROLE_MULTI_VALUE,
    FIELD_ROLE_NUMERIC,
    apply_role_overrides,
    detect_field_profile,
    detect_field_semantics,
)


def role_of(values, name="col"):
    return detect_field_profile(pd.Series(values), name).role


def test_identifier_detected_by_name_and_uniqueness():
    values = [f"ORD-{1000 + i}" for i in range(30)]
    assert role_of(values, "order_id") == FIELD_ROLE_IDENTIFIER


def test_sequential_integers_detected_as_identifier():
    assert role_of(list(range(1, 31)), "row") == FIELD_ROLE_IDENTIFIER


def test_repeated_numeric_values_are_metric_not_identifier():
    values = [10.5, 12.0, 10.5, 18.2, 12.0, 25.0, 18.2, 30.1] * 4
    assert role_of(values, "price") == FIELD_ROLE_NUMERIC


def test_datetime_strings_detected():
    values = [f"2024-0{month}-15" for month in range(1, 9)] * 3
    assert role_of(values, "order_date") == FIELD_ROLE_DATETIME
    assert role_of(values, "some_column") == FIELD_ROLE_DATETIME


def test_short_year_like_strings_are_not_datetime():
    values = ["1990", "1991", "1992", "1990", "1991"] * 4
    assert role_of(values, "cohort") == FIELD_ROLE_CATEGORICAL


def test_boolean_variants_detected():
    assert role_of(["yes", "no", "yes", "no", "yes"], "active") == FIELD_ROLE_BOOLEAN
    assert role_of(["是", "否", "是", "否"], "是否续费") == FIELD_ROLE_BOOLEAN
    assert role_of([0, 1, 1, 0, 1, 0], "flag") == FIELD_ROLE_BOOLEAN


def test_plain_categories_stay_categorical():
    values = ["East", "West", "North", "South"] * 8
    assert role_of(values, "region") == FIELD_ROLE_CATEGORICAL


def test_slash_categories_are_not_multi_value():
    values = ["1-2 times/week"] * 10 + ["3+ times/week"] * 8 + ["1-2 times/month"] * 7
    assert role_of(values, "frequency") == FIELD_ROLE_CATEGORICAL


def test_sentences_with_commas_are_free_text_not_multi_value():
    values = [
        f"I liked the product, but shipping took too long and support case {i} was never resolved properly."
        for i in range(20)
    ]
    assert role_of(values, "comment") == FIELD_ROLE_FREE_TEXT


def test_true_multi_select_detected():
    values = [
        "Swimming;Cycling",
        "Swimming",
        "Cycling;Running",
        "Swimming;Running;Yoga",
        "Yoga",
        "Running;Cycling",
        "Swimming;Cycling;Running",
        "Cycling",
        "Yoga;Swimming",
        "Running",
        "Swimming;Yoga",
        "Cycling;Yoga",
    ] * 2
    assert role_of(values, "activities") == FIELD_ROLE_MULTI_VALUE


def test_empty_and_constant_columns_flagged():
    assert role_of([None, None, None], "empty") == FIELD_ROLE_EMPTY
    assert role_of(["same", "same", "same"], "constant") == FIELD_ROLE_EMPTY


def test_detect_field_semantics_covers_all_columns():
    df = pd.DataFrame({"region": ["East", "West"] * 5, "amount": [10.0, 20.5] * 5})
    semantics = detect_field_semantics(df)
    assert set(semantics.keys()) == {"region", "amount"}
    assert semantics["region"].role == FIELD_ROLE_CATEGORICAL
    assert semantics["amount"].role == FIELD_ROLE_NUMERIC


def test_apply_role_overrides_replaces_role():
    df = pd.DataFrame({"region": ["East", "West"] * 5})
    semantics = detect_field_semantics(df)
    updated = apply_role_overrides(semantics, {"region": FIELD_ROLE_FREE_TEXT})
    assert updated["region"].role == FIELD_ROLE_FREE_TEXT
    assert semantics["region"].role == FIELD_ROLE_CATEGORICAL
