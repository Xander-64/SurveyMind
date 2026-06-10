"""Sanity tests for question-type detection.

Run with:  python -m pytest tests/ -q
(use the interpreter that has pandas/streamlit installed)
"""
from __future__ import annotations

import pandas as pd

from src.question_type_detector import (
    QUESTION_TYPE_MULTIPLE,
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_OPEN,
    QUESTION_TYPE_SCALE,
    QUESTION_TYPE_SINGLE,
    detect_question_type,
)


def test_single_choice_low_cardinality():
    series = pd.Series(["Male", "Female", "Male", "Female", "Male"])
    assert detect_question_type(series) == QUESTION_TYPE_SINGLE


def test_multiple_choice_with_delimiters():
    series = pd.Series(["A,B", "B,C", "A", "A,B,C", "C"])
    assert detect_question_type(series) == QUESTION_TYPE_MULTIPLE


def test_integer_likert_scale():
    series = pd.Series([1, 2, 3, 4, 5, 3, 4, 2, 5, 1])
    assert detect_question_type(series) == QUESTION_TYPE_SCALE


def test_large_numeric_is_numeric():
    series = pd.Series([1727, 1904, 2300, 980, 1500, 3200, 2750])
    assert detect_question_type(series) == QUESTION_TYPE_NUMERIC


def test_ordinal_range_label_is_not_multiple_choice():
    # "1-2 times/week" contains a "/" but is a single ordinal label, not a
    # multi-select answer. Splitting it would invent fragments like "week".
    series = pd.Series(
        ["1-2 times/week", "3-4 times/week", "5+ times/week", "Never", "1-2 times/month"] * 4,
        name="fitness_frequency",
    )
    assert detect_question_type(series) == QUESTION_TYPE_SINGLE


def test_genuine_multiple_choice_still_detected():
    # Few atomic options combine into many full values -> still multiple-choice.
    series = pd.Series(
        ["A,B", "B,C", "A", "A,B,C", "C", "A,C", "B", "A,B"],
        name="preferred_activities",
    )
    assert detect_question_type(series) == QUESTION_TYPE_MULTIPLE


def test_decimal_satisfaction_score_is_scale():
    # A 1-5 satisfaction score stored with decimals (1.1, 2.7, ...) used to be
    # misclassified as a plain numeric question.
    series = pd.Series(
        [1.1, 2.7, 3.4, 4.8, 2.2, 5.0, 3.1, 4.4, 1.9, 3.8],
        name="satisfaction_score",
    )
    assert detect_question_type(series) == QUESTION_TYPE_SCALE


def test_large_scores_outside_range_stay_numeric():
    # A column named "score" but ranging 0-100 is a measurement, not a Likert scale.
    series = pd.Series([12, 45, 88, 73, 51, 99, 30, 64], name="exam_score")
    assert detect_question_type(series) == QUESTION_TYPE_NUMERIC


def test_open_ended_long_text():
    series = pd.Series(
        [
            "Convenient workout spaces near the dorm would increase my exercise frequency.",
            "My choices are strongly affected by academic pressure and budget.",
            "I would spend more if the quality felt more consistent over time.",
            "The cafeteria options are limited and I often cook by myself instead.",
        ]
    )
    assert detect_question_type(series) == QUESTION_TYPE_OPEN
