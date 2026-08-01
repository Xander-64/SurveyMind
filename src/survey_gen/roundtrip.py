"""Closing the loop on data we exported ourselves.

Scope, stated up front: this resolves columns by **exact code match** only. Our
own CSV template writes ``Question.code`` as the header, so a file that came
back untouched matches perfectly. Recovered data whose column names a platform
renamed, reordered or split needs the fuzzy alignment layer, which is a later
batch and deliberately not faked here.

What this buys today is the thing the whole product positioning rests on. A
0-10 recommendation column is indistinguishable from a count of purchases by
its values alone, so the detector reads it as numeric — correctly, since
guessing would be worse (docs/detection-benchmark.md). With the schema present
the same column resolves to a scale, and its construct score becomes
computable. Same bytes, more meaning, because the meaning travelled with them.
"""
from __future__ import annotations

import pandas as pd

from src.question_type_detector import QUESTION_TYPE_SCALE, detect_question_types
from src.survey_gen.schema import Question, Survey

RESOLUTION_DECLARED = "declared"
RESOLUTION_DETECTED = "detected"


def questions_by_code(survey: Survey) -> dict[str, Question]:
    return {question.code: question for _, question in survey.iter_questions()}


def resolve_types(df: pd.DataFrame, survey: Survey | None = None) -> dict[str, dict[str, str]]:
    """Per-column type plus where it came from.

    Without a survey this is exactly ``detect_question_types``. With one, any
    column whose header matches a declared code takes the declared type and is
    marked ``declared``; everything else still goes through the detector, so a
    stray platform column is handled rather than dropped.
    """
    detected = detect_question_types(df)
    resolved: dict[str, dict[str, str]] = {
        column: {"type": q_type, "resolution": RESOLUTION_DETECTED}
        for column, q_type in detected.items()
    }
    if survey is None:
        return resolved

    declared = questions_by_code(survey)
    for column in df.columns:
        question = declared.get(column)
        if question is None:
            continue
        resolved[column] = {
            "type": question.question_type,
            "resolution": RESOLUTION_DECLARED,
        }
    return resolved


def coerce_scale_column(series: pd.Series, question: Question) -> pd.Series:
    """Numeric scale values, using the declaration to interpret them.

    Handles the "5分" text form some platforms export, and reverse-codes when
    the schema says the item is reverse-keyed — which is knowledge the recovered
    data does not carry on its own.
    """
    values = pd.to_numeric(series, errors="coerce")
    if values.isna().all():
        extracted = series.astype("string").str.extract(r"(\d+)", expand=False)
        values = pd.to_numeric(extracted, errors="coerce")
    spec = question.scale_spec
    if spec is not None and question.reverse_coded:
        values = spec.min_value + spec.max_value - values
    return values


def construct_scores(df: pd.DataFrame, survey: Survey) -> dict[str, pd.Series]:
    """Composite score per construct: the mean of its items, reverse-keyed ones
    flipped first.

    Only defined because the schema says which columns belong together and
    which are reverse-keyed. Neither fact is recoverable from the CSV.
    """
    scores: dict[str, pd.Series] = {}
    for construct in survey.constructs:
        items = [
            question
            for question in survey.questions_for_construct(construct.construct_id)
            if question.question_type == QUESTION_TYPE_SCALE and question.code in df.columns
        ]
        if len(items) < 2:
            continue
        frame = pd.DataFrame(
            {question.code: coerce_scale_column(df[question.code], question) for question in items}
        )
        scores[construct.construct_id] = frame.mean(axis=1)
    return scores
