"""Analysis plan: sample sizes, reliability, and the method chosen for each pair.

Two things are asserted harder than the rest, because they are the two places a
wrong number would be believed:

- every ``min_n`` reaches the power it claims, checked against the exact
  distribution rather than against the formula that produced it
- the alpha interval is the standard Feldt form, not the multiplicative variant
  written with the degrees of freedom in the wrong order — which produces a
  plausible-looking but different interval and raises nothing
"""
import math

import pandas as pd
import pytest
from scipy import stats

from src.survey_gen.analysis_plan import (
    METHOD_ALPHA,
    METHOD_ANOVA,
    METHOD_CHI_SQUARE,
    METHOD_KRUSKAL,
    METHOD_MANN_WHITNEY,
    METHOD_ORDINAL_TREND,
    METHOD_T_TEST,
    anova_sample_size,
    build_analysis_plan,
    corrected_item_total_correlations,
    cronbach_alpha,
    feldt_confidence_interval,
    proportion_sample_size,
    rule_of_thumb_sample_size,
    two_group_sample_size,
)
from src.survey_gen.roundtrip import coerce_scale_column
from src.survey_gen.synthetic import generate_responses
from src.survey_gen.templates import build_template


@pytest.fixture(scope="module")
def survey():
    return build_template("service_satisfaction")


@pytest.fixture(scope="module")
def plan(survey):
    return build_analysis_plan(survey)


@pytest.fixture(scope="module")
def responses(survey):
    return generate_responses(survey, n_respondents=300, seed=11)[0]


def exact_power(n, d=0.5, alpha=0.05):
    df = 2 * n - 2
    nc = d * math.sqrt(n / 2)
    crit = stats.t.ppf(1 - alpha / 2, df)
    return stats.nct.sf(crit, df, nc) + stats.nct.cdf(-crit, df, nc)


# ---- sample size -------------------------------------------------------------


def test_two_group_size_is_the_exact_minimum_not_the_closed_form():
    result = two_group_sample_size()
    assert result["min_n_per_group"] == 64
    assert result["closed_form_n"] == 63
    # The reason the closed form is not used: it does not deliver its own claim.
    assert result["closed_form_actual_power"] < 0.80
    assert result["exact_power"] >= 0.80


@pytest.mark.parametrize("groups,expected", [(3, 86), (4, 99), (5, 109)])
def test_anova_sizes_come_from_bonferroni_corrected_pairwise_tests(groups, expected):
    result = anova_sample_size(groups)
    assert result["min_n_per_group"] == expected
    assert result["pairwise_comparisons"] == groups * (groups - 1) // 2
    assert result["closed_form_actual_power"] < 0.80


def test_every_reported_size_reaches_the_power_it_claims():
    """The property that matters, checked independently of how it was derived."""
    assert exact_power(two_group_sample_size()["min_n_per_group"]) >= 0.80
    for groups in (3, 4, 5):
        result = anova_sample_size(groups)
        assert exact_power(
            result["min_n_per_group"], alpha=result["adjusted_alpha"]
        ) >= 0.80


def test_one_fewer_respondent_would_miss_the_target():
    """min_n is minimal, not merely sufficient."""
    n = two_group_sample_size()["min_n_per_group"]
    assert exact_power(n - 1) < 0.80


def test_proportion_size_is_the_familiar_385():
    assert proportion_sample_size()["min_n"] == 385


def test_rule_of_thumb_counts_all_scale_items_and_carries_the_dispute():
    result = rule_of_thumb_sample_size(12)
    assert result["min_n"] == 120
    assert rule_of_thumb_sample_size(3)["min_n"] == 100, "floor applies"
    assert result["caveat_key"] == "ratio_disputed"


# ---- reliability -------------------------------------------------------------


def test_feldt_interval_is_the_divisive_form(responses, survey):
    """The multiplicative variant needs the df swapped.

    Written with the df in their original order it returns a different interval
    and raises nothing, so this pins the correct one by construction.
    """
    items = survey.questions_for_construct("c_service")
    frame = pd.DataFrame(
        {q.code: coerce_scale_column(responses[q.code], q) for q in items}
    )
    alpha_hat = cronbach_alpha(frame)
    n, k = len(frame), frame.shape[1]
    low, high = feldt_confidence_interval(alpha_hat, n, k)

    df1, df2 = n - 1, (n - 1) * (k - 1)
    assert low == pytest.approx(1 - (1 - alpha_hat) / stats.f.ppf(0.025, df1, df2))
    assert high == pytest.approx(1 - (1 - alpha_hat) / stats.f.ppf(0.975, df1, df2))
    # equivalent multiplicative form, df swapped
    assert low == pytest.approx(1 - (1 - alpha_hat) * stats.f.ppf(0.975, df2, df1))
    # the same form without swapping is a different number
    assert low != pytest.approx(1 - (1 - alpha_hat) * stats.f.ppf(0.975, df1, df2))
    assert low < alpha_hat < high


def test_alpha_is_in_a_realistic_range_and_the_interval_brackets_it(responses, survey):
    for construct_id in ("c_service", "c_value"):
        items = survey.questions_for_construct(construct_id)
        frame = pd.DataFrame(
            {q.code: coerce_scale_column(responses[q.code], q) for q in items}
        )
        alpha_hat = cronbach_alpha(frame)
        assert 0.4 < alpha_hat < 0.95, (construct_id, alpha_hat)
        low, high = feldt_confidence_interval(alpha_hat, len(frame), frame.shape[1])
        assert low < alpha_hat < high


def test_item_total_correlation_excludes_the_item_itself(responses, survey):
    """Corrected, so an item is not correlated with a total containing it."""
    items = survey.questions_for_construct("c_service")
    frame = pd.DataFrame(
        {q.code: coerce_scale_column(responses[q.code], q) for q in items}
    )
    corrected = corrected_item_total_correlations(frame)
    assert set(corrected) == {q.code for q in items}
    for code, value in corrected.items():
        uncorrected = frame[code].corr(frame.sum(axis=1))
        assert value < uncorrected, code
        assert 0.0 < value < 1.0, code


def test_alpha_is_undefined_rather_than_wrong_on_too_little_data():
    assert cronbach_alpha(pd.DataFrame({"a": [1, 2, 3]})) is None
    assert cronbach_alpha(pd.DataFrame({"a": [1, 1, 1], "b": [1, 1, 1]})) is None
    assert feldt_confidence_interval(0.8, n_respondents=2, item_count=4) is None


# ---- the plan ----------------------------------------------------------------


def test_composite_scores_get_parametric_tests_and_single_items_do_not(plan):
    """A single Likert item is ordinal; only the construct mean is treated as
    interval."""
    for analysis in plan["analyses"]:
        if analysis["method"] in (METHOD_T_TEST, METHOD_ANOVA):
            assert "composite score" in " ".join(analysis["assumptions"])
        if analysis["method"] in (METHOD_MANN_WHITNEY, METHOD_KRUSKAL):
            assert "single_item_ordinal" in analysis["caveats"]


def test_ordered_group_trend_is_never_presented_as_jonckheere(plan):
    """The name must not claim a test that is not being run.

    Somers' D measures ordinal association; Jonckheere-Terpstra is a k-sample
    trend test. They usually agree on ordered demographics against a Likert
    item, but they are not the same procedure. The caveat is allowed — required,
    in fact — to name J-T in order to draw the distinction; what may not happen
    is a method or a description presenting itself as J-T.
    """
    trend = [a for a in plan["analyses"] if a["method"] == METHOD_ORDINAL_TREND]
    assert trend

    for analysis in plan["analyses"]:
        assert "jonckheere" not in analysis["method"].lower()
        for text in analysis["description"].values():
            assert "jonckheere" not in text.lower()

    for analysis in trend:
        assert "ordinal_not_jonckheere" in analysis["caveats"]
        assert "somers" in " ".join(analysis["description"].values()).lower()

    # The caveat text does name it, which is the point of the caveat.
    assert "jonckheere" in plan["caveats"]["ordinal_not_jonckheere"]["en"].lower()


def test_residual_categories_are_excluded_from_counts_and_tables(survey, plan):
    """Gender carries a residual "prefer not to say", so it is a two-group
    comparison, not three."""
    gender = next(q for q in survey.all_questions() if q.code == "gender")
    assert len(gender.options) == 3
    assert sum(1 for option in gender.options if option.residual) == 1

    comparisons = [
        a for a in plan["analyses"]
        if a["target"].endswith("~ gender") and a["method"] in (METHOD_T_TEST, METHOD_ANOVA)
    ]
    assert comparisons
    for analysis in comparisons:
        assert analysis["method"] == METHOD_T_TEST
        assert analysis["min_n"] == 64
        assert "residual_excluded" in analysis["caveats"]


def test_chi_square_requires_five_per_cell(plan):
    chi = [a for a in plan["analyses"] if a["method"] == METHOD_CHI_SQUARE]
    assert chi
    for analysis in chi:
        assert analysis["min_n"] == analysis["sample_size_detail"]["cells"] * 5


def test_reliability_is_planned_per_construct_with_its_assumption(survey, plan):
    alphas = [a for a in plan["analyses"] if a["method"] == METHOD_ALPHA]
    assert {a["target"] for a in alphas} == {"c_service", "c_value"}
    for analysis in alphas:
        assert "tau_equivalence" in analysis["caveats"]
    service = next(a for a in alphas if a["target"] == "c_service")
    assert any("srv_wait" in note for note in service["assumptions"]), (
        "the reverse-keyed item must be named, since recoding it is a precondition"
    )


def test_every_caveat_referenced_exists_and_is_bilingual(plan):
    for analysis in plan["analyses"]:
        for key in analysis["caveats"]:
            assert key in plan["caveats"], key
    for key, text in plan["caveats"].items():
        assert text["zh-CN"] and text["en"], key


def test_the_plan_states_its_defaults(plan):
    assert plan["defaults"] == {"alpha": 0.05, "power": 0.80, "effect_size_d": 0.5}
    assert plan["recommended_total_n"] >= 100
