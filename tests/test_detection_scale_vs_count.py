"""Scale versus count: the precision cost of widening the scale detector.

_is_scale_question currently misses every 0-based scale, which loses NPS and
the 0-10 batteries real instruments use. The obvious fix is to widen the range
check — but a 0-4 count of children and a 0-4 Likert item have identical value
distributions, so widening also drags count variables into the scale path,
where they would be averaged like Likert items and could end up inside a
construct score.

This module measures both directions so the trade-off is a number rather than
an assumption, and pins current behaviour so the pending fix has to declare
what it changed.

Measured while designing the fix (see docs/detection-benchmark.md):

    state                        scale recall   count misclassification
    current                          60%                 20%
    widen lower bound only           80%                 70%
    widen lower bound + unique cap  100%                100%
    ... + count-name heuristic      100%                  0%

The third row is the one that matters: fixing both gates without a name
heuristic destroys the distinction entirely.
"""
import json
import random
from pathlib import Path

import pandas as pd
import pytest

from src.question_type_detector import (
    QUESTION_TYPE_NUMERIC,
    QUESTION_TYPE_SCALE,
    detect_question_type,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "detection" / "scale_vs_count.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))


def column(spec):
    random.seed(spec["seed"])
    values = [random.randint(spec["low"], spec["high"]) for _ in range(DATA["rows"])]
    return pd.Series(values, name=spec["name"])


def verdict(spec):
    return detect_question_type(column(spec), column_name=spec["name"])


ALL_SPECS = [
    (group, spec)
    for group in ("scales", "counts", "ambiguous")
    for spec in DATA[group]
]


@pytest.mark.parametrize(
    "group,spec", ALL_SPECS, ids=["%s-%s" % (g, s["name"]) for g, s in ALL_SPECS]
)
def test_current_detection_is_pinned(group, spec):
    """Guard rail for the pending fix, not an endorsement of current behaviour.

    Rows carrying a `defect` note are wrong today and are expected to change.
    """
    assert verdict(spec) == spec["expected"], "%s (%s): %s" % (
        spec["name"], group, spec.get("defect", "unexpected change"))


def test_zero_based_scales_are_currently_missed():
    """The defect this fix exists for: NPS and every 0-10 battery reads as
    numeric, so respondents' ratings never reach the scale pipeline."""
    zero_based = [s for s in DATA["scales"] if s["low"] == 0]
    assert len(zero_based) == 4
    assert all(verdict(spec) == QUESTION_TYPE_NUMERIC for spec in zero_based)


def test_some_count_variables_are_already_misread_today():
    """Not a new problem introduced by the fix: any count whose range happens
    to sit inside 1-5 / 1-7 / 1-10 is read as a scale right now."""
    already_wrong = [s for s in DATA["counts"] if s["expected"] == QUESTION_TYPE_SCALE]
    assert [s["name"] for s in already_wrong] == ["家庭人口数", "房间数量"]


def test_current_recall_and_misclassification_rates():
    """The two numbers the fix has to move, asserted so a change is visible."""
    recall = sum(verdict(s) == QUESTION_TYPE_SCALE for s in DATA["scales"])
    misread = sum(verdict(s) == QUESTION_TYPE_SCALE for s in DATA["counts"])
    assert (recall, misread) == (6, 2), (
        "Scale recall / count misclassification changed from 6/10 and 2/10. "
        "If this is the planned fix, update the expectations here and the "
        "trade-off table in docs/detection-benchmark.md."
    )


def test_ambiguous_columns_are_documented_as_undecidable():
    """A 0-4 column named Q12 could be a 5-point item or a count of children.

    The values are identical. No detector setting resolves this, which is the
    empirical case for carrying a schema through the round trip rather than
    inferring types from recovered data alone.
    """
    for spec in DATA["ambiguous"]:
        assert spec["why"], spec["name"]
        assert verdict(spec) in (QUESTION_TYPE_SCALE, QUESTION_TYPE_NUMERIC)
