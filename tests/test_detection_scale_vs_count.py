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
    before, widen lower bound only   80%                 70%
    before, + unique cap            100%                100%
    shipped: no widening, name demotion in the safe direction only
                                     60%                  0%

Widening was rejected: it takes count misclassification to 100%. What shipped
instead closes the dangerous direction (counts read as scales, 20% -> 0%) and
leaves the safe one open (zero-based scales stay numeric, surfaced as a hint).
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


def test_counts_inside_a_likert_window_are_demoted_by_name():
    """The dangerous direction, closed.

    Any count whose range happens to sit inside 1-5 / 1-7 / 1-10 used to be read
    as a scale, and a misread count reaches the report and AI layers where it is
    narrated as a rating. The demotion is monotone-safe: applied in this
    direction, a wrong call only turns a real scale into a numeric question,
    which loses information but cannot invent a false rating.
    """
    from src.question_type_detector import scale_demotion_reason

    demoted = {s["name"]: scale_demotion_reason(column(s), s["name"])
               for s in DATA["counts"] if s.get("fixed_by")}
    assert demoted == {"家庭人口数": "count_name:人口", "房间数量": "count_name:数量"}
    for spec in DATA["counts"]:
        assert verdict(spec) == QUESTION_TYPE_NUMERIC


def test_a_scoring_keyword_outranks_a_counting_one():
    """Guards the one way this demotion could hurt: "满意度分数" must survive."""
    import random

    import pandas as pd

    for name in ("满意度分数", "满意度频次", "agreement_frequency", "评分次数"):
        random.seed(1)
        values = pd.Series([random.randint(1, 5) for _ in range(300)], name=name)
        assert detect_question_type(values, column_name=name) == QUESTION_TYPE_SCALE, name


def test_the_known_cost_of_the_frequency_keyword():
    """Recorded rather than hidden.

    An English Likert frequency item whose name carries no scoring word is
    demoted. The Chinese 使用频率 is safe (the list holds 频次, not 频率), and any
    name with a scoring word is protected. The cost is information loss plus one
    manual override, which is the safe side of the asymmetry.
    """
    import random

    import pandas as pd

    random.seed(2)
    values = pd.Series([random.randint(1, 5) for _ in range(300)], name="frequency_of_use")
    assert detect_question_type(values, column_name="frequency_of_use") == QUESTION_TYPE_NUMERIC

    random.seed(2)
    chinese = pd.Series([random.randint(1, 5) for _ in range(300)], name="使用频率")
    assert detect_question_type(chinese, column_name="使用频率") == QUESTION_TYPE_SCALE


def test_current_recall_and_misclassification_rates():
    """The two numbers the fix has to move, asserted so a change is visible."""
    recall = sum(verdict(s) == QUESTION_TYPE_SCALE for s in DATA["scales"])
    misread = sum(verdict(s) == QUESTION_TYPE_SCALE for s in DATA["counts"])
    assert (recall, misread) == (6, 0), (
        "Scale recall / count misclassification changed from 6/10 and 0/10. "
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
